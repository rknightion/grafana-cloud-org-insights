"""Aggregate-only AI model views. Token-active identities are model seats, not licenses."""
from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

MAX_HISTORY_ROWS = 26
MAX_STACKS = 20_000
MAX_NUMBER = 2**53 - 1
ORG_FIELDS = ("users", "service_users", "user_tokens", "service_tokens", "user_excess",
              "users_over_allowance", "system_excess", "billed_overage")
STACK_FIELDS = ("users", "service_users", "user_tokens", "service_tokens", "user_excess", "billed_overage")
ORG_COLUMNS = {
    "users": "Token-active users", "service_users": "Service users",
    "user_tokens": "User tokens", "service_tokens": "Service tokens",
    "user_excess": "User excess tokens", "users_over_allowance": "Users over allowance",
    "system_excess": "System excess tokens", "billed_overage": "Billing overage USD",
}
ORG_SCHEMA = (
    ("Source", "string"), ("Month", "string"), ("Period status", "string"),
    ("Observed at", "string"), ("Personal allowance", "number"), ("System allowance", "number"),
    *((column, "number") for column in ORG_COLUMNS.values()),
    ("Model seat USD20", "number"), ("Model token USD2", "number"), ("Model total USD", "number"),
)
STACK_SCHEMA = (
    (" Stack", "string"), ("Region", "string"), ("Month", "string"),
    ("Period status", "string"), ("Observed at", "string"), ("Personal allowance", "number"),
    ("Token-active user memberships", "number"), ("Service user memberships", "number"),
    ("User tokens", "number"), ("Service tokens", "number"), ("Allocated user excess tokens", "number"),
)
VIEW_SCHEMAS = {"ai_cost_current": ORG_SCHEMA, "ai_cost_monthly": ORG_SCHEMA,
                "ai_cost_stacks": STACK_SCHEMA}


def _number(value: Any, *, nullable: bool = False) -> bool:
    if nullable and value is None:
        return True
    return (type(value) in (int, float) and 0 <= value <= MAX_NUMBER and math.isfinite(value))


def _observation(snapshot: Any) -> dict[str, Any] | None:
    """Copy only the closed aggregate projection, including when hydrated input is supplied."""
    if not isinstance(snapshot, Mapping) or snapshot.get("available") is not True:
        return None
    source = snapshot.get("source")
    month = snapshot.get("captured_month")
    period = snapshot.get("period_status")
    query_time = snapshot.get("query_time")
    if (source not in {"billing_observation", "bi_one_time"}
            or not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month)
            or period not in {"observed_mtd", "rollover_unverified"}
            or not isinstance(query_time, str)):
        return None
    try:
        parsed_time = dt.datetime.fromisoformat(query_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed_time.tzinfo is None or parsed_time.utcoffset() != dt.timedelta(0):
        return None
    if parsed_time.strftime("%Y-%m") != month:
        return None
    allowances = (snapshot.get("personal_allowance"), snapshot.get("system_allowance"))
    if any(type(value) is not int or not _number(value) for value in allowances):
        return None
    org = snapshot.get("org")
    if not isinstance(org, Mapping) or not all(_number(org.get(key), nullable=key == "billed_overage") for key in ORG_FIELDS):
        return None
    if any(not float(org[key]).is_integer() for key in ("users", "service_users", "users_over_allowance")):
        return None
    if (org["users_over_allowance"] > org["users"]
            or org["user_excess"] > org["user_tokens"]
            or org["system_excess"] != max(org["service_tokens"] - allowances[1], 0)):
        return None
    row = {
        "Source": source, "Month": month, "Period status": period, "Observed at": query_time,
        "Personal allowance": allowances[0], "System allowance": allowances[1],
        **{column: org[key] for key, column in ORG_COLUMNS.items()},
        "Model seat USD20": org["users"] * 20,
        "Model token USD2": (org["user_excess"] + org["system_excess"]) * 2 / 1_000_000,
    }
    row["Model total USD"] = row["Model seat USD20"] + row["Model token USD2"]
    return row


def build(stacks: Sequence[Mapping[str, Any]], ai_billing: Mapping[str, Any] | None):
    """Current and dated source-keyed monthly observations, never inferred final months."""
    if not stacks or not ai_billing:
        return [], {}
    current = _observation(ai_billing)
    if current is None:
        return [], {}
    records = ai_billing.get("stacks")
    if not isinstance(records, Mapping) or len(records) > MAX_STACKS:
        return [], {}
    rows = []
    for stack in stacks:
        if stack.get("status") == "paused" or stack.get("id") is None or not stack.get("slug"):
            continue
        record = records.get(str(stack["id"]))
        if not isinstance(record, Mapping) or not all(_number(record.get(key), nullable=True) for key in STACK_FIELDS):
            continue
        rows.append({
            " Stack": str(stack["slug"]), "Region": stack.get("regionSlug"),
            "Month": current["Month"], "Period status": current["Period status"],
            "Observed at": current["Observed at"], "Personal allowance": current["Personal allowance"],
            "Token-active user memberships": record.get("users"),
            "Service user memberships": record.get("service_users"),
            "User tokens": record.get("user_tokens"), "Service tokens": record.get("service_tokens"),
            "Allocated user excess tokens": record.get("user_excess"),
        })
    history = ai_billing.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY_ROWS:
        return [], {}
    monthly = {}
    for entry in [*history, ai_billing]:
        row = _observation(entry)
        if row is None or row["Period status"] != "observed_mtd":
            continue
        key = (row["Source"], row["Month"])
        previous = monthly.get(key)
        if previous is None or dt.datetime.fromisoformat(row["Observed at"].replace("Z", "+00:00")) > dt.datetime.fromisoformat(previous["Observed at"].replace("Z", "+00:00")):
            monthly[key] = row
    return [], {"ai_cost_current": [current], "ai_cost_stacks": rows,
                "ai_cost_monthly": [monthly[key] for key in sorted(monthly)]}
