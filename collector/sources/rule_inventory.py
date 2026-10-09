"""Default-off, unwired count-only inventory of witnessed alerting GET routes.

The caller supplies fresh inventory and the org CAP. No rules, expressions,
labels, annotations, receivers or matchers survive parsing. Counts describe
configured objects/current states, not execution history or notification delivery.
Independent failed reads leave their counts unknown, never manufactured zeros.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from collector.httpclient import DeadlineExceeded, ReadOnlyClient

_ROUTES = {
    "mimir": ("hmInstancePromUrl", "hmInstancePromId", "/api/prom/api/v1/rules", "/api/prom/api/v1/alerts"),
    "loki": ("hlInstanceUrl", "hlInstanceId", "/prometheus/api/v1/rules"),
    "alertmanager": ("amInstanceUrl", "amInstanceId", "/alertmanager/api/v2/alerts", "/alertmanager/api/v2/silences"),
}
_RULE_FIELDS = ("rule_groups", "alerting_rules", "recording_rules", "firing", "pending")
_AM_FIELDS = ("active", "suppressed", "unprocessed", "silences_active", "silences_pending", "silences_expired")


class _Unavailable(Exception):
    """Only closed reason enums cross the request/parse boundary."""


def _rows(value: Any) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise _Unavailable("invalid_response")
    return value


def _prometheus(doc: Any, field: str) -> list[dict]:
    if (not isinstance(doc, dict) or doc.get("status") != "success"
            or not isinstance(doc.get("data"), dict) or doc.get("warnings")
            or doc.get("error") or doc.get("errorType")):
        raise _Unavailable("invalid_response")
    return _rows(doc["data"].get(field))


def _states(rows: list[dict], allowed: tuple[str, ...], *, nested=False) -> dict[str, int]:
    counts = dict.fromkeys(allowed, 0)
    for row in rows:
        status = row.get("status") if nested else row
        state = status.get("state") if isinstance(status, dict) else None
        if not isinstance(state, str) or state not in counts:
            raise _Unavailable("invalid_response")
        counts[state] += 1
    return counts


def _rules(doc: Any) -> dict[str, int]:
    groups = _prometheus(doc, "groups")
    counts = {"rule_groups": len(groups), "alerting_rules": 0, "recording_rules": 0}
    for group in groups:
        for rule in _rows(group.get("rules")):
            kind = rule.get("type")
            if kind not in ("alerting", "recording"):
                raise _Unavailable("invalid_response")
            counts[kind + "_rules"] += 1
    return counts


def _parse(doc: Any, family: str, index: int) -> dict[str, int]:
    if family in ("mimir", "loki"):
        if index == 0:
            return _rules(doc)
        return _states(_prometheus(doc, "alerts"), ("firing", "pending"))
    states = ("active", "suppressed", "unprocessed") if index == 0 else ("active", "pending", "expired")
    counts = _states(_rows(doc), states, nested=True)
    return counts if index == 0 else {"silences_" + key: value for key, value in counts.items()}


def _read(client: ReadOnlyClient, stack: dict[str, Any], cap: str,
          family: str, index: int) -> dict[str, int]:
    host, tenant, *routes = _ROUTES[family]
    base = stack.get(host)
    try:
        parts = urlsplit(base if isinstance(base, str) else "")
        valid = (parts.scheme == "https" and parts.hostname and not parts.username
                 and not parts.password and parts.path in ("", "/")
                 and not parts.query and not parts.fragment)
    except ValueError:
        valid = False
    if not valid or not stack.get(tenant):
        raise _Unavailable("missing_endpoint")
    if not isinstance(cap, str) or not cap:
        raise _Unavailable("missing_credentials")
    try:
        response = client.get(base.rstrip("/") + routes[index],
                              basic=(str(stack[tenant]), cap),
                              headers={"Accept": "application/json"}, guarded=True)
    except (DeadlineExceeded, TimeoutError):
        raise _Unavailable("deadline") from None
    except Exception:
        raise _Unavailable("request_failed") from None
    if response.status != 200:
        raise _Unavailable("http_error")
    try:
        doc = response.json()
    except (ValueError, UnicodeError):
        raise _Unavailable("invalid_response") from None
    return _parse(doc, family, index)


def _family(client: ReadOnlyClient, stack: dict[str, Any], cap: str, family: str) -> dict:
    fields = _AM_FIELDS if family == "alertmanager" else _RULE_FIELDS
    result = dict.fromkeys(fields)
    failures = []
    successes = 0
    for index in range(len(_ROUTES[family]) - 2):
        try:
            result.update(_read(client, stack, cap, family, index))
            successes += 1
        except _Unavailable as exc:
            failures.append(exc.args[0])
    return {"state": "partial" if failures and successes else "unavailable" if failures else "complete",
            "reason": failures[0] if failures else "none", **result}


def probe_all(client: ReadOnlyClient, stacks: list[dict[str, Any]], cap: str, *,
              enabled: bool = False) -> dict:
    """Left-join reads to fresh inventory; disabled makes zero requests."""
    if not enabled:
        return {}
    return {"stacks": {str(stack["slug"]): {
        family: _family(client, stack, cap, family) for family in _ROUTES
    } for stack in stacks if str(stack.get("status", "")).lower() != "paused"}}


def composition_inputs(inputs: dict) -> dict:
    """Mirror label_inventory's shallow composition-input copy; no wiring here."""
    return dict(inputs)
