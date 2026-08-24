"""Per-stack data plane. Everything here works with the org CAP alone  -  no service account.

Auth is HTTP basic `<per-signal instance id>:<CAP>`, and the user differs per signal (SPEC §6). Getting
it wrong fails as a 401, not a crash, so `auth_for()` is tested rather than trusted.

Endpoints, all verified 2026-08-17:

- Mimir cardinality  `<prom>/api/prom/api/v1/cardinality/label_names`   -  Pillar B's cost lever
- Adaptive Metrics   `<prom>/aggregations/{rules,recommendations}`      -  Pillar B's savings lever
- Fleet Management   `<fm>/collector.v1.CollectorService/ListCollectors` (POST-shaped, but read-only)
- Tempo              `<tempo>/tempo/api/v2/search/tags`   -  **the `/tempo` prefix is required**
- Pyroscope          Connect-RPC, 400s without a time range

Fleet Management and Pyroscope are Connect-RPC and want POST. The collector's client is GET-only by
construction, so those two are read via a narrowly-scoped helper that does exactly one POST shape and
nothing else  -  see `_connect_rpc`.
"""

from __future__ import annotations

import base64
import decimal
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping

from collector.coverage import Coverage
from collector.httpclient import ReadOnlyClient

# Which inventory field supplies the basic-auth user, per signal. Fleet Management uses the STACK id,
# not a signal instance id  -  an easy and silent mistake.
AUTH_FIELD = {
    "metrics": "hmInstancePromId",
    "logs": "hlInstanceId",
    "traces": "htInstanceId",
    "profiles": "hpInstanceId",
    "fleet": "id",
}


def auth_for(stack: dict[str, Any], signal: str, cap: str) -> tuple[str, str]:
    field = AUTH_FIELD[signal]
    value = stack.get(field)
    if not value:
        raise KeyError(f"{stack.get('slug')} has no {field} for signal {signal}")
    return (str(value), cap)


def _connect_rpc(
    url: str,
    user: str,
    cap: str,
    timeout: float = 30.0,
    *,
    payload: Mapping[str, Any] | None = None,
) -> Any:
    """One narrowly-scoped POST for Connect-RPC list calls (Fleet Management, Pyroscope).

    Deliberately NOT part of `ReadOnlyClient`: that class refuses non-GET on purpose and must stay that
    way. This helper reaches only `*Service/List*` and `QuerierService` paths. The latter accepts a
    bounded read-query payload for Pyroscope label values; the path guard remains the mutation barrier.
    """
    if "Service/List" not in url and "QuerierService" not in url:
        raise ValueError(f"refusing non-list Connect-RPC call: {url}")
    token = base64.b64encode(f"{user}:{cap}".encode()).decode()
    data = json.dumps(dict(payload or {}), separators=(",", ":")).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return json.loads(fh.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return {"_http": exc.code}


def cardinality(client: ReadOnlyClient, stack: dict[str, Any], cap: str, limit: int = 20) -> dict[str, Any]:
    """Mimir cardinality  -  the most actionable cost lever, and it needs no service account."""
    base = stack.get("hmInstancePromUrl")
    if not base:
        return {"available": False}
    resp = client.get(
        f"{base}/api/prom/api/v1/cardinality/label_names",
        params={"limit": limit},
        basic=auth_for(stack, "metrics", cap),
    )
    if not resp.ok:
        return {"available": False, "http": resp.status}
    body = resp.json()
    top = body.get("cardinality", [])
    return {
        "available": True,
        "label_names_count": body.get("label_names_count"),
        "label_values_count_total": body.get("label_values_count_total"),
        # Offender NAMES are unbounded, so they go to Loki/S3 and never become a metric label (§5.3).
        "top_labels": [
            {"label": c.get("label_name"), "values": c.get("label_values_count")} for c in top[:limit]
        ],
    }


# How many recommendations survive into the scan envelope as a sample. The rest are summed and
# discarded: one real stack returned 25,779 records at 11 MB, and 267 of those would be a scan
# envelope nobody can read and S3 storage nobody needs.
RECOMMENDATION_SAMPLE = 10
SAVINGS_ACTIONS = frozenset({"add", "update"})
KNOWN_RECOMMENDATION_ACTIONS = frozenset({"add", "update", "keep", "remove"})


def _series_count(value: Any) -> int | None:
    """Parse one API count without truncating fractions or accepting negative/non-finite values."""
    if isinstance(value, bool):
        return None
    try:
        parsed = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def summarise_recommendations(rec_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the verbose recommendation payload into the few numbers a dashboard needs.

    `remediable_series` is the sum of positive marginal reductions for `add` and `update` actions.
    `keep` changes no rule and `remove` can only preserve or increase the output series set, so neither
    is an unrealised saving. The sum is exposed only when every savings-bearing row has a nonempty,
    unique metric identity and non-negative integral counts. One live payload had 25,779
    recommendations and 25,779 distinct metrics, but that observation is not treated as an API
    guarantee.

    The live API legitimately omits count fields on `keep` and `remove`. For savings-bearing actions it
    has shipped two equivalent field pairs: `current_series_count` / `recommended_series_count` and the
    documented `total_series_before_aggregation` / `total_series_after_aggregation`. `raw_series_count`
    is deliberately NOT a fallback: on an update it is the unaggregated input, so using it would count
    savings already realised by the current rule.

    Only a real reduction counts. A record whose recommended count exceeds its current count is not a
    saving, whatever `recommended_action` says, and treating it as one would net out against genuine
    savings elsewhere.

    `remediable_series_unused` is the subset where the metric appears in no rule, query or dashboard.
    That is the part which can be applied without a review conversation, and conflating it with the
    total overstates what anyone can action this week.
    """
    under = after = remediable = remediable_unused = 0
    pending = records_with_counts = savings_bearing = unknown_actions = invalid_metric_identities = 0
    duplicate_metric_identities = invalid_series_counts = invalid_usage_counts = 0
    actions: dict[str, int] = {}
    sample: list[dict[str, Any]] = []
    metric_identities: set[str] = set()

    for r in rec_list:
        action = r.get("recommended_action")
        if action:
            actions[action] = actions.get(action, 0) + 1
        if action != "keep":
            pending += 1
        if action not in KNOWN_RECOMMENDATION_ACTIONS:
            unknown_actions += 1
            continue
        if action not in SAVINGS_ACTIONS:
            continue
        savings_bearing += 1
        metric = r.get("metric")
        metric_identity_valid = isinstance(metric, str) and bool(metric.strip())
        if not metric_identity_valid:
            invalid_metric_identities += 1
        elif metric in metric_identities:
            duplicate_metric_identities += 1
        else:
            metric_identities.add(metric)
        cur = r.get("current_series_count")
        if cur is None:
            cur = r.get("total_series_before_aggregation")
        rec_c = r.get("recommended_series_count")
        if rec_c is None:
            rec_c = r.get("total_series_after_aggregation")
        if cur is None or rec_c is None:
            continue
        records_with_counts += 1
        cur, rec_c = _series_count(cur), _series_count(rec_c)
        if cur is None or rec_c is None:
            invalid_series_counts += 1
            continue
        if not metric_identity_valid:
            continue
        under += cur
        after += rec_c
        delta = max(0, cur - rec_c)
        remediable += delta
        usage_counts = tuple(_series_count(r.get(field) or 0) for field in (
            "usages_in_rules", "usages_in_queries", "usages_in_dashboards",
        ))
        if any(value is None for value in usage_counts):
            invalid_usage_counts += 1
            continue
        used = sum(value for value in usage_counts if value is not None)
        if not used:
            remediable_unused += delta
        sample.append({
            "metric": metric,
            "current_series": cur,
            "recommended_series": rec_c,
            "remediable_series": delta,
            "used_in": used,
        })

    sample.sort(key=lambda x: -x["remediable_series"])
    missing_savings_counts = savings_bearing - records_with_counts
    ambiguous_metric_identities = bool(invalid_metric_identities or duplicate_metric_identities)
    invalid_savings_payload = (
        ambiguous_metric_identities or bool(invalid_series_counts) or bool(invalid_usage_counts)
    )
    if invalid_savings_payload:
        # A recommendation is identified by metric and its counts drive customer-facing money. If
        # either contract is malformed, no aggregate or sample is safe to expose: summing can
        # double-count or manufacture savings, while selecting one row invents precedence.
        under = after = remediable = remediable_unused = 0
        sample = []
    return {
        "recommendations_pending": pending,
        "recommendation_records_total": len(rec_list),
        "recommendation_records_savings_bearing": savings_bearing,
        "recommendation_records_with_series_counts": records_with_counts,
        "recommendation_records_missing_series_counts": missing_savings_counts,
        "recommendation_records_missing_metric_identity": invalid_metric_identities,
        "recommendation_records_duplicate_metric_identity": duplicate_metric_identities,
        "recommendation_records_invalid_series_counts": invalid_series_counts,
        "recommendation_records_invalid_usage_counts": invalid_usage_counts,
        "recommendation_records_unknown_action": unknown_actions,
        "series_counts_complete": not unknown_actions and not missing_savings_counts
        and not invalid_savings_payload,
        # Compatibility field for older scan readers. It is deliberately false for an unknown action
        # or any savings-bearing record without marginal counts; count-less keep/remove rows are a
        # documented verbose shape and do not make the payload incomplete.
        "verbose": bool(rec_list) and not unknown_actions and not missing_savings_counts
        and not invalid_savings_payload,
        "actions": actions,
        "series_under_recommendation": under,
        "series_after_recommendation": after,
        "remediable_series": remediable,
        "remediable_series_unused": remediable_unused,
        "sample_recommendations": sample[:RECOMMENDATION_SAMPLE],
    }


def adaptive_metrics(client: ReadOnlyClient, stack: dict[str, Any], cap: str) -> dict[str, Any]:
    """Applied aggregation rules vs waiting recommendations = the unrealised saving."""
    base = stack.get("hmInstancePromUrl")
    if not base:
        return {"available": False}
    auth = auth_for(stack, "metrics", cap)
    rules = client.get(f"{base}/aggregations/rules", basic=auth)
    # `?verbose=true` is LOAD-BEARING. Without it the response carries only `metric`, `drop_labels`
    # and `aggregations`: no series counts, so no saving can be derived from it at all. The default
    # payload looks complete, which is why this is pinned by a test.
    #
    # It costs ~3x the bytes (measured: one stack returned 25,779 records, 3.7 MB plain against
    # 11.3 MB verbose) for the same latency. That is affordable because the records are summarised
    # here and never stored.
    recs = client.get(f"{base}/aggregations/recommendations?verbose=true", basic=auth)
    if not rules.ok and not recs.ok:
        return {"available": False, "http": rules.status}

    try:
        rule_list = rules.json() if rules.ok else []
        raw_recommendations = recs.json() if recs.ok else None
    except (TypeError, ValueError):
        return {"available": False, "recommendations_available": False,
                "series_counts_complete": False, "reason": "invalid_json"}
    recommendations_available = recs.ok and isinstance(raw_recommendations, list)
    rec_list = raw_recommendations if recommendations_available else []
    rule_list = rule_list if isinstance(rule_list, list) else []
    summary = summarise_recommendations(rec_list)
    if not recommendations_available:
        # An empty successful payload proves there are zero recommendations. A failed request proves
        # nothing, even when the rules endpoint succeeded and keeps the broader Adaptive probe alive.
        summary["series_counts_complete"] = False
    return {
        "available": True,
        "rules_applied": len(rule_list),
        # A stack with recommendations and zero applied rules has taken none of the saving on offer.
        "adopted": len(rule_list) > 0,
        "recommendations_available": recommendations_available,
        **summary,
    }


def fleet(stack: dict[str, Any], cap: str) -> dict[str, Any]:
    """Fleet Management collector inventory. Basic-auth user is the STACK id, not a signal id."""
    base = stack.get("agentManagementInstanceUrl")
    if not base:
        return {"available": False}
    user, _ = auth_for(stack, "fleet", cap)
    collectors = _connect_rpc(f"{base}/collector.v1.CollectorService/ListCollectors", user, cap)
    pipelines = _connect_rpc(f"{base}/pipeline.v1.PipelineService/ListPipelines", user, cap)
    if "_http" in (collectors or {}):
        return {"available": False, "http": collectors["_http"]}
    clist = (collectors or {}).get("collectors", []) or []
    plist = (pipelines or {}).get("pipelines", []) or []
    return {
        "available": True,
        "collectors": len(clist),
        "pipelines": len(plist),
        # Pillar E: FM provisioned and enabled but nothing registered is a silent dead end.
        "provisioned_but_empty": bool(plist) and not clist,
        "collector_versions": sorted({c.get("attributes", {}).get("collector.version", "?") for c in clist}),
    }


def probe_stack(client: ReadOnlyClient, stack: dict[str, Any], cap: str) -> dict[str, Any]:
    return {
        "slug": stack["slug"],
        "cardinality": cardinality(client, stack, cap),
        "adaptive_metrics": adaptive_metrics(client, stack, cap),
        "fleet": fleet(stack, cap),
    }


def probe_all(
    client: ReadOnlyClient,
    cap: str,
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    concurrency: int = 12,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}

    def one(stack: dict[str, Any]) -> None:
        slug = str(stack["slug"])
        if stack.get("status") == "paused":
            coverage.record_skipped(slug, "paused")
            return
        try:
            results[slug] = probe_stack(client, stack, cap)
        except Exception as exc:  # noqa: BLE001
            coverage.record_failure(slug, type(exc).__name__)
            if on_error:
                on_error(slug, f"{type(exc).__name__}: {exc}")
        else:
            coverage.record_ok(slug)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, stacks))
    return results
