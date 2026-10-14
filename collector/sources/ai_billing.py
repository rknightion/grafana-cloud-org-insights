"""Aggregate-only observed AI monthly gauges from the existing write-stack reader.

Identity joins execute upstream. An identity-bearing response is rejected, never projected or logged.
These observations describe billing previews, not final invoices or licensed seat counts.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

DS_UID = "grafanacloud-usage"
MAX_ROWS = 20_000
MAX_NUMBER = 2**53 - 1
MAX_REQUESTS = 14
STACK_ID = re.compile(r"^[0-9]{1,20}$")


def _selector(metric: str, user_type: str | None = None, *, monetary: bool = False) -> str:
    labels = ['__ignore_usage__=""']
    if user_type:
        labels.append(f'user_type="{user_type}"')
    if monetary:
        labels.append('monetary="true"')
    return metric + "{" + ",".join(labels) + "}"


def _distance(left: str, right: str, *, stack: bool = False) -> str:
    if not stack:
        return f"abs(({left}) - ({right}))"
    # Native membership gauges explicitly emit zero for some stack/categories where the
    # per-identity series is absent. Only an unmatched positive native/identity aggregate
    # contradicts that population. A zero fallback comes from an observed aggregate,
    # never vector(0), so absence on both sides still remains unavailable.
    return (f"(sum(abs(({left}) - ({right})) "
            f"or (((({left}) unless ({right})) > 0) * 0 + 1) "
            f"or (((({right}) unless ({left})) > 0) * 0 + 1)) "
            f"or (sum({left}) * 0) or (sum({right}) * 0))")


def queries(personal_allowance: int = 40_000_000) -> dict[str, str]:
    """Every result has either no labels or stack_id; emails never cross the GET boundary."""
    if type(personal_allowance) is not int or not 0 <= personal_allowance <= MAX_NUMBER:
        raise ValueError("invalid personal allowance")
    user = _selector("grafanacloud_ai_tokens_user_total_tokens", "user")
    service = _selector("grafanacloud_ai_tokens_user_total_tokens", "service")
    identities = f"sum by(email)({user})"
    service_identities = f"sum by(email)({service})"
    stack_users = f"sum by(stack_id,email)({user})"
    stack_services = f"sum by(stack_id,email)({service})"
    human_count = f"sum(({identities}) > bool 0)"
    service_count = f"sum(({service_identities}) > bool 0)"
    human_stack_count = f"sum by(stack_id)(({stack_users}) > bool 0)"
    service_stack_count = f"sum by(stack_id)(({stack_services}) > bool 0)"
    human_tokens = f"sum({user})"
    service_tokens = f"sum({service})"
    human_stack_tokens = f"sum by(stack_id)({user})"
    service_stack_tokens = f"sum by(stack_id)({service})"
    excess = f"clamp_min(({identities}) - {personal_allowance}, 0)"
    # Filtering the denominator avoids NaN/0 for existing zero-valued identities.
    allocation = (f"sum by(stack_id)(({stack_users}) * on(email) group_left() "
                  f"(({excess}) / (({identities}) > 0)))")
    distances = []
    for category, count, stack_count, tokens, stack_tokens in (
        ("user", human_count, human_stack_count, human_tokens, human_stack_tokens),
        ("service", service_count, service_stack_count, service_tokens, service_stack_tokens),
    ):
        native_count = _selector("grafanacloud_org_ai_tokens_active_users", category)
        native_stack_count = _selector("grafanacloud_ai_tokens_active_users", category)
        native_tokens = _selector("grafanacloud_ai_tokens_total_tokens", category)
        distances.extend((
            _distance(count, f"sum({native_count})"),
            _distance(tokens, f"sum({native_tokens})"),
            _distance(stack_count, f"sum by(stack_id)({native_stack_count})", stack=True),
            _distance(stack_tokens, f"sum by(stack_id)({native_tokens})", stack=True),
        ))
    return {
        "users": human_count, "service_users": service_count,
        "user_tokens": human_tokens, "service_tokens": service_tokens,
        "user_excess": f"sum({excess})",
        "users_over_allowance": f"sum(({identities}) > bool {personal_allowance})",
        "stack_users": human_stack_count, "stack_service_users": service_stack_count,
        "stack_user_tokens": human_stack_tokens, "stack_service_tokens": service_stack_tokens,
        "stack_user_excess": allocation,
        "reconciliation": " + ".join(f"({expression})" for expression in distances),
        "billed_overage": f"sum({_selector('grafanacloud_org_ai_tokens_overage', monetary=True)})",
        "stack_billed_overage": f"sum by(stack_id)({_selector('grafanacloud_ai_tokens_overage', monetary=True)})",
    }


class InvalidAggregate(ValueError):
    """Closed parser failure without upstream detail."""


def _number(value: Any, *, integer: bool) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InvalidAggregate
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise InvalidAggregate from None
    if not math.isfinite(result) or not 0 <= result <= MAX_NUMBER or (integer and not result.is_integer()):
        raise InvalidAggregate
    return int(result) if result.is_integer() else result


def _values(body: Any, *, stack: bool, integer: bool, query_time: int) -> dict[str, int | float]:
    if (not isinstance(body, Mapping) or body.get("status") != "success"
            or body.get("warnings") or body.get("infos")):
        raise InvalidAggregate
    data = body.get("data")
    if not isinstance(data, Mapping) or data.get("resultType") != "vector":
        raise InvalidAggregate
    rows = data.get("result")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise InvalidAggregate
    result = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"metric", "value"}:
            raise InvalidAggregate
        labels = row.get("metric")
        if not isinstance(labels, Mapping) or set(labels) != ({"stack_id"} if stack else set()):
            raise InvalidAggregate
        key = labels["stack_id"] if stack else "org"
        if stack and (not isinstance(key, str) or not STACK_ID.fullmatch(key)):
            raise InvalidAggregate
        sample = row.get("value")
        if not isinstance(sample, list) or len(sample) != 2:
            raise InvalidAggregate
        timestamp = _number(sample[0], integer=False)
        if timestamp != query_time or key in result:
            raise InvalidAggregate
        result[key] = _number(sample[1], integer=integer)
    return result


def probe(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *, write_stack: str, now: dt.datetime | None = None,
    personal_allowance: int = 40_000_000, system_allowance: int = 500_000_000,
) -> dict[str, Any]:
    """Bound fourteen guarded GETs to fresh inventory and one exact observation instant."""
    def unavailable(reason: str) -> dict[str, Any]:
        return {"available": False, "reason": reason}

    if type(system_allowance) is not int or not 0 <= system_allowance <= MAX_NUMBER:
        return unavailable("invalid_allowance")
    try:
        expressions = queries(personal_allowance)
    except ValueError:
        return unavailable("invalid_allowance")
    stack = next((item for item in stacks if item.get("slug") == write_stack
                  and item.get("status") != "paused"), None)
    if stack is None:
        return unavailable("write_stack_missing")
    base, error = validated_base_url(stack)
    if error:
        return unavailable("invalid_url")
    token = (credentials.get(write_stack) or {}).get("token")
    if not isinstance(token, str) or not token:
        return unavailable("no_credential")
    now = now or dt.datetime.now(dt.timezone.utc)
    now = now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)
    instant = int(now.timestamp())
    now = dt.datetime.fromtimestamp(instant, dt.timezone.utc)
    endpoint = f"{base}/api/datasources/proxy/uid/{DS_UID}/api/v1/query"
    live_ids = {str(item["id"]) for item in stacks if item.get("id") is not None}
    if not live_ids:
        return unavailable("inventory_unavailable")
    values = {}
    for name, expression in expressions.items():
        comparison = name in {"billed_overage", "stack_billed_overage"}
        try:
            response = client.get(endpoint, params={"query": expression, "time": str(instant)},
                                  bearer=token, guarded=True)
            if response.status in (401, 403):
                return unavailable("auth_error")
            if response.status != 200:
                if comparison:
                    values[name] = {}
                    continue
                return unavailable("http_error")
            parsed = _values(response.json(), stack=name.startswith("stack_"),
                             integer=not (name.endswith("billed_overage") or name == "stack_user_excess"),
                             query_time=instant)
        except RuntimeError:
            if comparison:
                values[name] = {}
                continue
            return unavailable("transport_error")
        except (ValueError, TypeError, OverflowError):
            # Malformed billing comparisons cannot introduce identity data either.
            if comparison:
                values[name] = {}
                continue
            return unavailable("invalid_response")
        values[name] = parsed
    org_fields = ("users", "service_users", "user_tokens", "service_tokens", "user_excess", "users_over_allowance")
    if any("org" not in values[key] for key in org_fields):
        return unavailable("missing_observation")
    if values["reconciliation"].get("org") != 0:
        return unavailable("reconciliation_failed")
    if any(key not in live_ids and value > 0 for name, rows in values.items()
           if name.startswith("stack_") and name != "stack_billed_overage"
           for key, value in rows.items()):
        return unavailable("inventory_mismatch")
    org = {key: values[key]["org"] for key in org_fields}
    if org["users_over_allowance"] > org["users"] or org["user_excess"] > org["user_tokens"]:
        return unavailable("reconciliation_failed")
    # Allocation is org-wide, so do not silently discard reporting departed stack totals.
    if not math.isclose(sum(values["stack_user_excess"].values()), org["user_excess"], rel_tol=1e-9, abs_tol=1e-6):
        return unavailable("reconciliation_failed")
    org["system_excess"] = max(org["service_tokens"] - system_allowance, 0)
    org["billed_overage"] = values["billed_overage"].get("org")
    stack_fields = ("users", "service_users", "user_tokens", "service_tokens", "user_excess", "billed_overage")
    return {
        "available": True, "source": "billing_observation", "query_time": now.isoformat(),
        "captured_month": now.strftime("%Y-%m"),
        "period_status": "rollover_unverified" if now.day == 1 else "observed_mtd",
        "personal_allowance": personal_allowance, "system_allowance": system_allowance,
        "org": org,
        "stacks": {key: {field: values[f"stack_{field}"].get(key) for field in stack_fields}
                   for key in sorted(live_ids)},
    }
