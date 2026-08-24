"""Per-stack usage insights: who opened which dashboard, what it queried, and what it cost.

**This is the seam the per-stack reader credential unlocked.** Every Grafana Cloud stack is provisioned
with its own `grafanacloud-usage-insights` Loki datasource, reachable through the stack's datasource
proxy. The org access policy cannot reach it (401 on the data plane, and the gcom proxy does not route
it), so before the per-stack service accounts existed this needed one credential per region and covered
a fraction of the estate. With a reader on every stack it covers all of them.

The custom role keeps `datasources:query` scoped to this ONE datasource uid. `datasources:read` is a
separate metadata-list action and is deliberately scoped to `datasources:*` so the bounded query-cost
view can resolve an opaque uid to a human-readable datasource name. The wide read does not confer query
rights; `datasources:query` on `datasources:*` would be the unacceptable production-data grant.

**Aggregate in Loki, never here.** A single stack produced 800 raw lines in a 24-hour window and a busy
one produces far more. Every query below is a LogQL metric expression, so the response is a handful of
numbers whatever the stack's volume. Pulling lines and counting them in Python would work on a small
stack and fall over on a real one.

Two event types exist, verified live:

- `dashboard-view`  -  a dashboard was opened. Carries `dashboardUid`, `dashboardName`, `folderName`,
  `userId`, `username`, `publicDashboardUid`.
- `data-request`  -  a panel ran a query. Adds `panelId`, `panelName`, `datasourceType`, `datasourceUid`,
  `duration`, `error`, `source`, plus `totalQueries` and `cachedQueries`.

**`publicDashboardUid` is the public-exposure activity signal.** A non-empty value on a dashboard-open
event means an already-public dashboard was used, and `userId="-1"` / `username="anonymous"` is an
unauthenticated reader. It cannot enumerate dormant configured shares or say when sharing was enabled;
the stack-local public-dashboard source owns that compliance inventory.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

if TYPE_CHECKING:
    from collector.httpclient import ReadOnlyClient

# The stack's own usage-insights datasource. Stable uid on every stack, and the only one the reader role
# is scoped to. Must match `provision.USAGE_INSIGHTS_DS_UID`.
DS_UID = "grafanacloud-usage-insights"

# The window every figure is measured over. 24h matches the daily tier that gathers it, so a figure is
# never a partial day, and it is short enough that Loki answers a metric query quickly.
WINDOW = "24h"

# Per-stack concurrency. One host per tenant, so gcom's 6 req/s ceiling does not apply here  -  the
# Assistant sweep measured 2,153 requests across the estate in 54 seconds at this width.
CONCURRENCY = 12

TOP_DASHBOARDS = 10

# Stage 19's full dashboard-opening inventory uses a deliberately separate window from the existing
# daily operational figures.  A dashboard is "unopened" only when this complete 31-day observation
# set was measured; absence from an unavailable set is UNKNOWN.
ACTIVITY_WINDOW = "31d"
TOP_DATASOURCES = 10

# Grafana emits `duration` as `request.endTime - request.startTime`; both are JavaScript epoch
# timestamps in milliseconds (`public/app/features/query/state/queryAnalytics.ts`). Live obs-hub
# values (for example 223, 2,431 and 2,523) match that contract. Do not relabel this as seconds.
DURATION_UNIT = "ms"

NO_CREDENTIAL = "no_credential"
FORBIDDEN = "forbidden_403"
UNAUTHORISED = "token_401"
NOT_PROVISIONED = "datasource_absent"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
MALFORMED_RESPONSE = "malformed_response"

# A 403 immediately after a role patch is RBAC cache, not a permission problem: measured, the first call
# 403'd and the next succeeded on the same token. 401 and 404 are not retried, because neither changes
# in a few seconds.
RETRY_STATUSES = frozenset({403, 408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
RETRY_DELAY = 4.0

NO_INSTANCE_ID = "no_instance_id"

# **The `instance_id` filter is load-bearing and its absence is silent.**
#
# A stack's usage-insights datasource returns its WHOLE REGION. Measured: obs-hub's exposed 490
# instance_ids belonging to 140 distinct stacks. A selector without the id filter therefore attributes
# every neighbour's activity to whichever stack was asked - and it looks plausible, because the numbers
# are real. The first sweep built that way reported 340 public dashboards across 170 stacks, which was
# 2 public dashboards counted 170 times, each with an identical event count.
#
# For `instance_type="grafana"` the label carries the stack's own `id` (verified: obs-hub's 654321
# against a region total many times larger). Not `hmInstancePromId`, which is the metrics tenant.
_SEL = '{{instance_type="grafana", instance_id="{instance_id}"}} | logfmt'


def selector(*, instance_id: str) -> str:
    """The stream selector for one stack. Never call Loki without going through this."""
    return _SEL.format(instance_id=instance_id)


_BASE = "%(sel)s"
_VIEW = '%(sel)s | eventName="dashboard-view"'
_REQ = '%(sel)s | eventName="data-request"'

# Every figure, as a LogQL metric expression TEMPLATE. `%(sel)s` is substituted with the per-stack
# selector at query time, so there is exactly one place a stack's identity enters a query.
SCALARS: Mapping[str, str] = {
    "views": "sum(count_over_time(" + _VIEW + " [" + WINDOW + "]))",
    # Human reach excludes Grafana's anonymous sentinel and an absent identity. Anonymous opens are a
    # separate scalar below; counting `-1` once per stack inflated the viewer total by up to one for
    # every anonymously-read tenant while presenting the result as people.
    "viewers": (
        "count(sum by (userId) (count_over_time("
        + _VIEW + ' | userId!="-1" | userId!="" [' + WINDOW + "])))"
    ),
    "dashboards_viewed": "count(sum by (dashboardUid) (count_over_time(" + _VIEW + " [" + WINDOW + "])))",
    "public_events": 'sum(count_over_time(' + _VIEW + ' | publicDashboardUid!="" [' + WINDOW + ']))',
    # This scalar is the complete per-stack count of public dashboards OBSERVED IN USE. The separately
    # bounded `public_dashboards` breakdown is only the named top-ten activity detail. Neither is the
    # configured compliance inventory; `sources.public_dashboards` owns that question.
    "public_dashboards_distinct": (
        "count(sum by (publicDashboardUid) (count_over_time("
        + _VIEW + ' | publicDashboardUid!="" [' + WINDOW + "])))"
    ),
    "anonymous_views": 'sum(count_over_time(' + _VIEW + ' | userId="-1" [' + WINDOW + ']))',
    "requests": "sum(count_over_time(" + _REQ + " [" + WINDOW + "]))",
    "request_errors": 'sum(count_over_time(' + _REQ + ' | error!="" [' + WINDOW + ']))',
    "queries_total": "sum(sum_over_time(" + _REQ + " | unwrap totalQueries [" + WINDOW + "]))",
    "queries_cached": "sum(sum_over_time(" + _REQ + " | unwrap cachedQueries [" + WINDOW + "]))",
    "panel_identity_requests": (
        "sum(count_over_time(" + _REQ
        + ' | dashboardUid!="" | panelId!="" [' + WINDOW + "]))"
    ),
    "panels_queried": (
        "count(sum by (dashboardUid, panelId) (count_over_time("
        + _REQ + ' | dashboardUid!="" | panelId!="" [' + WINDOW + "])))"
    ),
    "datasources_queried": "count(sum by (datasourceType) (count_over_time(" + _REQ + " [" + WINDOW + "])))",
}

# Breakdowns, each returning a labelled series. Bounded by `topk` or a small closed label set, so a
# stack with thousands of dashboards cannot produce a huge response.
BREAKDOWNS: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "top_dashboards": (
        "topk(" + str(TOP_DASHBOARDS) + ", sum by (dashboardUid, dashboardName, folderName) "
        "(count_over_time(" + _VIEW + " [" + WINDOW + "])))",
        ("dashboardUid", "dashboardName", "folderName"),
    ),
    "public_dashboards": (
        "topk(" + str(TOP_DASHBOARDS) + ", sum by (publicDashboardUid, dashboardUid, dashboardName) "
        '(count_over_time(' + _VIEW + ' | publicDashboardUid!="" [' + WINDOW + '])))',
        ("publicDashboardUid", "dashboardUid", "dashboardName"),
    ),
    "datasource_types": (
        "sum by (datasourceType) (count_over_time(" + _REQ + " [" + WINDOW + "]))",
        ("datasourceType",),
    ),
    "datasource_duration_ms": (
        "sum by (datasourceType) (sum_over_time("
        + _REQ + ' | duration!="" | unwrap duration | __error__="" [' + WINDOW + "]))",
        ("datasourceType",),
    ),
    "datasource_errors": (
        "sum by (datasourceType) (count_over_time("
        + _REQ + ' | error!="" [' + WINDOW + "]))",
        ("datasourceType",),
    ),
}

# Full distinct dashboard set, not top-N. The current dashboard catalogue is joined in Python; Loki
# returns one bounded-by-inventory identity and count per dashboard that was actually opened.
DASHBOARD_ACTIVITY_QUERY = (
    "sum by (dashboardUid) (count_over_time("
    + _VIEW + ' | dashboardUid!="" [' + ACTIVITY_WINDOW + "]))"
)

_DS_COST = (
    "topk(" + str(TOP_DATASOURCES)
    + ", sum by (datasourceUid, datasourceType) (sum_over_time("
    + _REQ
    + ' | datasourceUid!="" | duration!="" | unwrap duration | __error__="" ['
    + WINDOW + "])))"
)
_DS_TOTAL = (
    "sum by (datasourceUid, datasourceType) (sum_over_time("
    + _REQ
    + ' | datasourceUid!="" | totalQueries!="" | unwrap totalQueries | __error__="" ['
    + WINDOW + "]))"
)
_DS_CACHED = (
    "sum by (datasourceUid, datasourceType) (sum_over_time("
    + _REQ
    + ' | datasourceUid!="" | cachedQueries!="" | unwrap cachedQueries | __error__="" ['
    + WINDOW + "]))"
)
_DS_CACHE_RATIO = (
    "((" + _DS_CACHED + ") / (" + _DS_TOTAL + "))"
    + " and on(datasourceUid, datasourceType) (" + _DS_TOTAL + " > 0)"
    + " and on(datasourceUid, datasourceType) (" + _DS_COST + ")"
)

# One Loki request returns both measures. `measure` makes the two otherwise-identical label sets
# distinct under `or`; the parser removes it and joins the values by datasource UID. Every embedded
# stream selector remains subject to `_assert_scoped` at runtime.
DATASOURCE_COST_QUERY = (
    'label_replace((' + _DS_COST
    + '), "measure", "cost_ms", "datasourceUid", ".*")'
    + " or "
    + 'label_replace((' + _DS_CACHE_RATIO
    + '), "measure", "cache_hit_ratio", "datasourceUid", ".*")'
)


class InsightsError(RuntimeError):
    pass


class RegionalQueryRefused(RuntimeError):
    """A query without a stack filter would return the whole region. Refused, not warned about."""


_STREAM_SELECTOR = re.compile(r"\{[^{}]*\}")


def _exact_matchers(selector_text: str, label: str) -> list[tuple[str, str]]:
    """Return the operators and values used for one label in a LogQL stream selector."""
    return re.findall(
        rf"(?<![A-Za-z0-9_]){re.escape(label)}\s*(=~|!~|!=|=)\s*\"([^\"]*)\"",
        selector_text,
    )


def _assert_scoped(expr: str, expected_instance_id: str) -> None:
    """Require every stream selector to select exactly this stack's Grafana instance.

    Looking for one `instance_id` substring is insufficient: a binary LogQL expression may contain a
    correctly scoped left-hand selector and an unscoped regional selector on the right. Both are sent
    to Loki, so every selector must carry the exact equality matchers.
    """
    selectors = _STREAM_SELECTOR.findall(expr)
    valid = bool(expected_instance_id) and bool(selectors)
    for stream in selectors:
        valid = valid and _exact_matchers(stream, "instance_id") == [("=", expected_instance_id)]
        valid = valid and _exact_matchers(stream, "instance_type") == [("=", "grafana")]
    if not valid:
        raise RegionalQueryRefused(
            "refusing a usage-insights query whose every stream selector is not scoped to this "
            f"stack's exact instance_id ({expected_instance_id!r}) and instance_type=\"grafana\". "
            f"Build every selector with `selector()`. Query: {expr[:160]}"
        )


def _query(base: str, token: str, expr: str, *, expected_instance_id: str,
           timeout: float = 90.0, client: ReadOnlyClient | None = None) -> Any:
    """One instant LogQL metric query through the stack's datasource proxy.

    **Refuses any expression without an `instance_id` filter.** This is belt and braces on top of the
    template check in `tests/test_usage_insights.py`, and it is here because the failure is silent and
    plausible: an unfiltered query returns the whole region, so a stack's figures become its
    neighbours' and every number still looks like a real number. The first version of this module got
    it wrong and reported 340 public dashboards where there were 2.
    """
    _assert_scoped(expr, expected_instance_id)
    url = (f"{base}/api/datasources/proxy/uid/{DS_UID}/loki/api/v1/query?"
           + urllib.parse.urlencode({"query": expr, "time": int(time.time())}))
    if client is not None:
        response = client.get(url, bearer=token)
        if not response.ok:
            raise urllib.error.HTTPError(url, response.status, f"HTTP {response.status}", None, None)
        return response.json()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _execute_query(
    base: str, token: str, expr: str, *, expected_instance_id: str,
    client: ReadOnlyClient | None,
) -> Any:
    """Keep the legacy test/probe seam while production uses the shared deadline client."""
    if client is None:
        return _query(base, token, expr, expected_instance_id=expected_instance_id)
    return _query(
        base, token, expr, expected_instance_id=expected_instance_id, client=client,
    )


def _vector_result(body: Any) -> list[Any]:
    """Validate the Loki success envelope before any empty result can be interpreted as zero."""
    if not isinstance(body, Mapping) or body.get("status") != "success":
        raise InsightsError("Loki response is not a success envelope")
    data = body.get("data")
    if not isinstance(data, Mapping) or data.get("resultType") != "vector":
        raise InsightsError("Loki response is not an instant vector")
    result = data.get("result")
    if not isinstance(result, list):
        raise InsightsError("Loki vector result is not a list")
    return result


def _sample_value(row: Any) -> float:
    if not isinstance(row, Mapping):
        raise InsightsError("Loki vector row is not an object")
    sample = row.get("value")
    if not isinstance(sample, (list, tuple)) or len(sample) != 2:
        raise InsightsError("Loki vector row has no timestamp/value pair")
    try:
        value = float(sample[1])
    except (TypeError, ValueError) as exc:
        raise InsightsError("Loki vector value is not numeric") from exc
    if not math.isfinite(value):
        raise InsightsError("Loki vector value is not finite")
    return value


def _scalar(body: Any) -> float:
    """A metric query returns a vector; empty means zero events, not a missing measurement."""
    result = _vector_result(body)
    if not result:
        return 0.0
    if len(result) != 1:
        raise InsightsError(f"scalar query returned {len(result)} vector rows")
    return _sample_value(result[0])


def _series(body: Any, labels: Sequence[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _vector_result(body):
        if not isinstance(row, Mapping):
            raise InsightsError("Loki breakdown row is not an object")
        metric = row.get("metric") or {}
        if not isinstance(metric, Mapping):
            raise InsightsError("Loki breakdown labels are not an object")
        value = _sample_value(row)
        out.append({**{k: metric.get(k) or "" for k in labels}, "count": value})
    return sorted(out, key=lambda r: -r["count"])


def unavailable(slug: str, reason: str, detail: str = "") -> dict[str, Any]:
    return {"slug": slug, "available": False, "reason": reason, "detail": detail[:200]}


def probe_stack(slug: str, url: str, token: str, *, instance_id: str = "",
                sleep: Callable[[float], None] = time.sleep,
                client: ReadOnlyClient | None = None) -> dict[str, Any]:
    """Every figure for one stack. Never raises: a stack that cannot be read says so.

    `instance_id` is the stack's own `id`. Without it the only honest answer is "not measured": the
    datasource would return the whole region and the figures would be its neighbours' activity wearing
    this stack's name.
    """
    if not token:
        return unavailable(slug, NO_CREDENTIAL)
    if not instance_id:
        return unavailable(slug, NO_INSTANCE_ID, "inventory carries no id to filter on")
    sel = selector(instance_id=instance_id)
    base = url.rstrip("/")
    out: dict[str, Any] = {"slug": slug, "available": True, "window": WINDOW,
                           "instance_id": instance_id}
    first = True
    for field, template in SCALARS.items():
        expr = template % {"sel": sel}
        try:
            body = _execute_query(
                base, token, expr, expected_instance_id=instance_id, client=client,
            )
        except urllib.error.HTTPError as exc:
            if first and exc.code in RETRY_STATUSES:
                sleep(RETRY_DELAY)
                first = False
                try:
                    body = _execute_query(
                        base, token, expr, expected_instance_id=instance_id, client=client,
                    )
                except urllib.error.HTTPError as retry:
                    return unavailable(slug, _reason(retry.code), f"{field}: HTTP {retry.code}")
                except Exception as retry:                              # noqa: BLE001
                    return unavailable(slug, TRANSPORT_ERROR, f"{field}: {retry}")
            else:
                return unavailable(slug, _reason(exc.code), f"{field}: HTTP {exc.code}")
        except Exception as exc:                                        # noqa: BLE001
            return unavailable(slug, TRANSPORT_ERROR, f"{field}: {exc}")
        first = False
        try:
            out[field] = _scalar(body)
        except InsightsError as exc:
            return unavailable(slug, MALFORMED_RESPONSE, f"{field}: {exc}")

    if out["panels_queried"] > out["panel_identity_requests"]:
        return unavailable(
            slug,
            MALFORMED_RESPONSE,
            "distinct dashboard-panel pairs exceed identified panel requests",
        )

    for field, (template, labels) in BREAKDOWNS.items():
        try:
            body = _execute_query(
                base, token, template % {"sel": sel},
                expected_instance_id=instance_id, client=client,
            )
            out[field] = _series(body, labels)
        except urllib.error.HTTPError as exc:
            return unavailable(slug, _reason(exc.code), f"{field}: HTTP {exc.code}")
        except InsightsError as exc:
            return unavailable(slug, MALFORMED_RESPONSE, f"{field}: {exc}")
        except Exception as exc:                                       # noqa: BLE001
            return unavailable(slug, TRANSPORT_ERROR, f"{field}: {exc}")
    return out


def _stage19_series_probe(
    slug: str,
    url: str,
    token: str,
    *,
    instance_id: str,
    expression: str,
    labels: Sequence[str],
    field: str,
    sleep: Callable[[float], None] = time.sleep,
    client: ReadOnlyClient | None = None,
) -> dict[str, Any]:
    if not token:
        return unavailable(slug, NO_CREDENTIAL)
    if not instance_id:
        return unavailable(slug, NO_INSTANCE_ID, "inventory carries no id to filter on")
    expr = expression % {"sel": selector(instance_id=instance_id)}
    try:
        body = _execute_query(
            url.rstrip("/"), token, expr, expected_instance_id=instance_id, client=client,
        )
    except urllib.error.HTTPError as exc:
        if exc.code in RETRY_STATUSES:
            sleep(RETRY_DELAY)
            try:
                body = _execute_query(
                    url.rstrip("/"), token, expr, expected_instance_id=instance_id, client=client,
                )
            except urllib.error.HTTPError as retry:
                return unavailable(slug, _reason(retry.code), f"{field}: HTTP {retry.code}")
            except Exception as retry:  # noqa: BLE001
                return unavailable(slug, TRANSPORT_ERROR, f"{field}: {retry}")
        else:
            return unavailable(slug, _reason(exc.code), f"{field}: HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        return unavailable(slug, TRANSPORT_ERROR, f"{field}: {exc}")
    try:
        rows = _series(body, labels)
    except InsightsError as exc:
        return unavailable(slug, MALFORMED_RESPONSE, f"{field}: {exc}")
    return {
        "slug": slug,
        "available": True,
        "instance_id": instance_id,
        "window": ACTIVITY_WINDOW if field == "dashboard_activity" else WINDOW,
        field: rows,
    }


def probe_dashboard_activity_stack(
    slug: str, url: str, token: str, *, instance_id: str = "",
    sleep: Callable[[float], None] = time.sleep, client: ReadOnlyClient | None = None,
) -> dict[str, Any]:
    record = _stage19_series_probe(
        slug, url, token, instance_id=instance_id,
        expression=DASHBOARD_ACTIVITY_QUERY, labels=("dashboardUid",),
        field="dashboard_activity", sleep=sleep, client=client,
    )
    if record.get("available"):
        rows = record.pop("dashboard_activity")
        seen: set[str] = set()
        for row in rows:
            uid = str(row.get("dashboardUid") or "")
            count = float(row.get("count") or 0)
            if not uid:
                return unavailable(
                    slug, MALFORMED_RESPONSE,
                    "dashboard_activity: row has no dashboardUid grouping label",
                )
            if uid in seen:
                return unavailable(
                    slug, MALFORMED_RESPONSE,
                    f"dashboard_activity: dashboardUid {uid!r} is repeated",
                )
            if count < 0 or not count.is_integer():
                return unavailable(
                    slug, MALFORMED_RESPONSE,
                    f"dashboard_activity: dashboardUid {uid!r} has an invalid count",
                )
            seen.add(uid)
        record["opened"] = rows
    return record


def _cost_rows(body: Any) -> list[dict[str, Any]]:
    measures = _series(body, ("datasourceUid", "datasourceType", "measure"))
    by_uid: dict[tuple[str, str], dict[str, Any]] = {}
    seen: set[tuple[str, str, str]] = set()
    for item in measures:
        uid = str(item.get("datasourceUid") or "")
        kind = str(item.get("datasourceType") or "")
        measure = str(item.get("measure") or "")
        if not uid or measure not in ("cost_ms", "cache_hit_ratio"):
            raise InsightsError("datasource cost row has invalid uid or measure")
        identity = (uid, kind, measure)
        if identity in seen:
            raise InsightsError(f"datasource cost repeats {measure} for uid {uid!r}")
        seen.add(identity)
        row = by_uid.setdefault(
            (uid, kind),
            {"datasourceUid": uid, "datasourceType": kind,
             "cost_ms": None, "cache_hit_ratio": None},
        )
        value = float(item["count"])
        if measure == "cost_ms":
            if value < 0:
                raise InsightsError("datasource cost is negative")
            row["cost_ms"] = value
        else:
            if value < 0 or value > 1:
                raise InsightsError("datasource cache-hit ratio is outside 0..1")
            row["cache_hit_ratio"] = value
    rows = [row for row in by_uid.values() if row["cost_ms"] is not None]
    return sorted(rows, key=lambda row: -float(row["cost_ms"]))[:TOP_DATASOURCES]


def probe_datasource_cost_stack(
    slug: str, url: str, token: str, *, instance_id: str = "",
    sleep: Callable[[float], None] = time.sleep, client: ReadOnlyClient | None = None,
) -> dict[str, Any]:
    if not token:
        return unavailable(slug, NO_CREDENTIAL)
    if not instance_id:
        return unavailable(slug, NO_INSTANCE_ID, "inventory carries no id to filter on")
    expr = DATASOURCE_COST_QUERY % {"sel": selector(instance_id=instance_id)}
    try:
        body = _execute_query(
            url.rstrip("/"), token, expr, expected_instance_id=instance_id, client=client,
        )
    except urllib.error.HTTPError as exc:
        if exc.code in RETRY_STATUSES:
            sleep(RETRY_DELAY)
            try:
                body = _execute_query(
                    url.rstrip("/"), token, expr, expected_instance_id=instance_id, client=client,
                )
            except urllib.error.HTTPError as retry:
                return unavailable(slug, _reason(retry.code),
                                   f"datasource_query_cost: HTTP {retry.code}")
            except Exception as retry:  # noqa: BLE001
                return unavailable(slug, TRANSPORT_ERROR, f"datasource_query_cost: {retry}")
        else:
            return unavailable(slug, _reason(exc.code),
                               f"datasource_query_cost: HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        return unavailable(slug, TRANSPORT_ERROR, f"datasource_query_cost: {exc}")
    try:
        rows = _cost_rows(body)
    except InsightsError as exc:
        return unavailable(slug, MALFORMED_RESPONSE, f"datasource_query_cost: {exc}")
    return {
        "slug": slug, "available": True, "instance_id": instance_id,
        "window": WINDOW, "costs": rows,
    }


def _reason(status: int) -> str:
    if status == 401:
        return UNAUTHORISED
    if status == 403:
        return FORBIDDEN
    if status == 404:
        return NOT_PROVISIONED
    return HTTP_ERROR


def _stage19_probe_all(
    probe: Callable[..., dict[str, Any]],
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    concurrency: int = CONCURRENCY,
    on_error: Callable[[str, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    client: ReadOnlyClient | None = None,
) -> dict[str, dict[str, Any]]:
    # Imported lazily to keep the stack-API catalogue independent of the Loki source.
    from collector.sources.stack_catalog import validated_base_url

    selected = [stack for stack in stacks
                if stack.get("slug") and stack.get("status") != "paused"]

    def one(stack: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        slug = str(stack.get("slug") or "")
        base, url_error = validated_base_url(stack)
        if url_error:
            record = unavailable(slug, NOT_PROVISIONED, url_error.get("detail") or "invalid url")
        else:
            token = str((credentials.get(slug) or {}).get("token") or "")
            record = probe(
                slug, str(base), token, instance_id=str(stack.get("id") or ""), sleep=sleep,
                client=client,
            )
        if not record.get("available") and on_error is not None:
            on_error(slug, f"{record.get('reason')}: {record.get('detail', '')}".strip())
        return slug, record

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(one, selected))


def probe_dashboard_activity_all(
    stacks: Sequence[Mapping[str, Any]], credentials: Mapping[str, Mapping[str, Any]], **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    return _stage19_probe_all(probe_dashboard_activity_stack, stacks, credentials, **kwargs)


def probe_datasource_cost_all(
    stacks: Sequence[Mapping[str, Any]], credentials: Mapping[str, Mapping[str, Any]], **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    return _stage19_probe_all(probe_datasource_cost_stack, stacks, credentials, **kwargs)


def probe_all(stacks: Sequence[Mapping[str, Any]], credentials: Mapping[str, Mapping[str, Any]],
              *, concurrency: int = CONCURRENCY,
              on_error: Callable[[str, str], None] | None = None,
              sleep: Callable[[float], None] = time.sleep,
              client: ReadOnlyClient | None = None) -> dict[str, dict[str, Any]]:
    """Sweep the LIVE inventory, looking each stack's credential up.

    Iterates `stacks`, never the credential store: a stack added since the last provisioner run gets a
    row saying it has no credential yet, and a stack that has left the org gets no row at all whatever
    SSM still holds. Takes no Coverage  -  the caller owns coverage accounting for its own tier.
    """
    from collector.sources.stack_catalog import validated_base_url

    selected = [stack for stack in stacks
                if stack.get("slug") and stack.get("status") != "paused"]

    def one(stack: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        slug = str(stack.get("slug") or "")
        url, url_error = validated_base_url(stack)
        if url_error:
            return slug, url_error
        token = str((credentials.get(slug) or {}).get("token") or "")
        # The stack's own `id`. For `instance_type="grafana"` that is what the usage-insights
        # `instance_id` label carries - NOT `hmInstancePromId`, which is the metrics tenant.
        instance_id = str(stack.get("id") or "")
        record = probe_stack(
            slug, str(url), token, instance_id=instance_id, sleep=sleep, client=client,
        )
        if not record.get("available") and on_error is not None:
            on_error(slug, str(record.get("reason")))
        return slug, record

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(one, selected))
