"""Read-only per-stack alert-rule routing inventory.

The provisioning endpoints return JSON arrays and expose no pagination or total-count envelope. A
healthy stack therefore costs exactly two GETs: alert rules and contact points. The result says
``api_has_no_total`` explicitly rather than presenting response completeness as proven.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient

BUILTIN_DEFAULT_RECEIVER = "grafana-default-email"
OK = "ok"
API_HAS_NO_TOTAL = "api_has_no_total"
NO_CREDENTIAL = "no_credential"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
NOT_PROVISIONED = "endpoint_absent_404"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
INVALID_RESPONSE = "invalid_response"
PROVISIONED = "provisioned"
MISSING = "missing"
UNVERIFIED_BUILTIN = "unverified_builtin"
NOT_APPLICABLE = "not_applicable"

# Detail is for the named drill-down, not another unbounded inventory. The aggregate counts remain
# over the complete API response when more findings exist.
MAX_FINDINGS = 100

RULES_PATH = "api/v1/provisioning/alert-rules"
CONTACTS_PATH = "api/v1/provisioning/contact-points"


def unavailable(slug: str, state: str, detail: str = "") -> dict[str, Any]:
    return {"available": False, "slug": slug, "state": state, "detail": detail[:240]}


def _http_state(status: int) -> str:
    return {
        401: UNAUTHORISED,
        403: FORBIDDEN,
        404: NOT_PROVISIONED,
    }.get(status, HTTP_ERROR)


def _get_list(client: ReadOnlyClient, url: str, token: str, what: str) -> tuple[list[Any] | None, str, str]:
    try:
        response = client.get(url, bearer=token)
    except Exception as exc:  # noqa: BLE001 - one stack must not fail the estate sweep
        return None, TRANSPORT_ERROR, f"{what}: {type(exc).__name__}"
    if not response.ok:
        return None, _http_state(response.status), f"{what}: HTTP {response.status}"
    try:
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - malformed JSON is an explicit source state
        return None, INVALID_RESPONSE, f"{what}: invalid JSON ({type(exc).__name__})"
    if not isinstance(body, list):
        return None, INVALID_RESPONSE, f"{what}: expected a JSON array, got {type(body).__name__}"
    if not all(isinstance(item, Mapping) for item in body):
        return None, INVALID_RESPONSE, f"{what}: array contains a non-object item"
    return body, OK, ""


def _validate_rules(rules: list[Any]) -> str | None:
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        # The API schema requires these fields. Defaulting one would turn an incompatible response into
        # a plausible routing classification, which is worse than refusing the measurement.
        for field in ("uid", "title", "folderUID", "ruleGroup"):
            if not isinstance(rule.get(field), str) or not rule.get(field):
                return f"alert rule {index} has invalid {field}"
        uid = rule["uid"]
        if uid in seen:
            return f"alert rules contain duplicate uid at item {index}"
        seen.add(uid)
        if not isinstance(rule.get("isPaused"), bool):
            return f"alert rule {index} has invalid isPaused"
        settings = rule.get("notification_settings")
        if settings is not None:
            if not isinstance(settings, Mapping):
                return f"alert rule {index} has invalid notification_settings"
            receiver = settings.get("receiver")
            if not isinstance(receiver, str) or not receiver:
                return f"alert rule {index} has invalid notification_settings.receiver"
    return None


def _validate_contacts(contacts: list[Any]) -> str | None:
    for index, contact in enumerate(contacts):
        if not isinstance(contact.get("name"), str) or not contact.get("name"):
            return f"contact point {index} has invalid name"
    return None


def _receiver(rule: Mapping[str, Any]) -> str | None:
    settings = rule.get("notification_settings")
    if not isinstance(settings, Mapping):
        return None
    value = settings.get("receiver")
    return value if isinstance(value, str) and value else None


def _rule_row(rule: Mapping[str, Any], contact_names: set[str]) -> dict[str, Any]:
    receiver = _receiver(rule)
    if receiver is None:
        receiver_state = NOT_APPLICABLE
        routing = "inherited"
    elif receiver in contact_names:
        receiver_state = PROVISIONED
        routing = "direct"
    elif receiver == BUILTIN_DEFAULT_RECEIVER:
        # Grafana's built-in receiver is not guaranteed to appear in the provisioning response. Its
        # absence is therefore unresolved, never proof that routing is broken.
        receiver_state = UNVERIFIED_BUILTIN
        routing = "direct"
    else:
        receiver_state = MISSING
        routing = "direct"
    return {
        "rule_uid": rule.get("uid"),
        "title": rule.get("title"),
        "folder_uid": rule.get("folderUID"),
        "rule_group": rule.get("ruleGroup"),
        "paused": bool(rule.get("isPaused")),
        "routing": routing,
        "receiver": receiver,
        "receiver_state": receiver_state,
    }


def _finding_priority(row: Mapping[str, Any]) -> int:
    if row.get("receiver_state") == MISSING:
        return 0
    if row.get("receiver_state") == UNVERIFIED_BUILTIN:
        return 1
    if row.get("routing") == "inherited" and not row.get("paused"):
        return 2
    return 3


def probe_stack(client: ReadOnlyClient, stack: Mapping[str, Any], token: str) -> dict[str, Any]:
    slug = str(stack.get("slug") or "")
    raw_url = stack.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return unavailable(slug, INVALID_RESPONSE, "inventory carries no valid url")
    try:
        parsed_url = urllib.parse.urlsplit(raw_url)
        _ = parsed_url.port
    except ValueError:
        return unavailable(slug, INVALID_RESPONSE, "inventory carries no valid url")
    if (
        raw_url != raw_url.strip()
        or any(char.isspace() for char in raw_url)
        or parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.path not in ("", "/")
        or bool(parsed_url.query)
        or bool(parsed_url.fragment)
    ):
        return unavailable(slug, INVALID_RESPONSE, "inventory carries no valid url")
    if not token:
        return unavailable(slug, NO_CREDENTIAL, "no stored per-stack reader token")
    base = raw_url.rstrip("/")
    rules, state, detail = _get_list(client, f"{base}/{RULES_PATH}", token, "alert rules")
    if rules is None:
        return unavailable(slug, state, detail)
    if validation := _validate_rules(rules):
        return unavailable(slug, INVALID_RESPONSE, validation)
    contacts, state, detail = _get_list(client, f"{base}/{CONTACTS_PATH}", token, "contact points")
    if contacts is None:
        return unavailable(slug, state, detail)
    if validation := _validate_contacts(contacts):
        return unavailable(slug, INVALID_RESPONSE, validation)
    contact_names = {
        item.get("name") for item in contacts
        if isinstance(item, Mapping) and isinstance(item.get("name"), str) and item.get("name")
    }
    direct = [_receiver(rule) for rule in rules]
    missing = [
        receiver for receiver in direct
        if receiver and receiver not in contact_names and receiver != BUILTIN_DEFAULT_RECEIVER
    ]
    builtin = [
        receiver for receiver in direct
        if receiver == BUILTIN_DEFAULT_RECEIVER and receiver not in contact_names
    ]
    classified = [_rule_row(rule, contact_names) for rule in rules]
    findings = sorted(
        (row for row in classified
         if row["routing"] == "inherited" or row["receiver_state"] != PROVISIONED),
        key=_finding_priority,
    )
    return {
        "available": True,
        "slug": slug,
        "state": OK,
        "completeness": API_HAS_NO_TOTAL,
        "rules_total": len(rules),
        "rules_active": sum(1 for row in classified if not row["paused"]),
        "rules_paused": sum(1 for rule in rules if bool(rule.get("isPaused"))),
        "rules_direct_receiver": sum(1 for receiver in direct if receiver),
        "rules_inherited": sum(1 for receiver in direct if not receiver),
        "rules_active_direct_receiver": sum(
            1 for row in classified if not row["paused"] and row["routing"] == "direct"
        ),
        "rules_paused_direct_receiver": sum(
            1 for row in classified if row["paused"] and row["routing"] == "direct"
        ),
        "rules_active_inherited": sum(
            1 for row in classified if not row["paused"] and row["routing"] == "inherited"
        ),
        "rules_paused_inherited": sum(
            1 for row in classified if row["paused"] and row["routing"] == "inherited"
        ),
        "rules_missing_receiver": len(missing),
        "rules_active_missing_receiver": sum(
            1 for row in classified
            if not row["paused"] and row["receiver_state"] == MISSING
        ),
        "rules_paused_missing_receiver": sum(
            1 for row in classified
            if row["paused"] and row["receiver_state"] == MISSING
        ),
        "rules_unverified_builtin": len(builtin),
        "contact_point_integrations": len(contacts),
        "contact_point_names": len(contact_names),
        "findings_total": len(findings),
        "findings_retained": min(len(findings), MAX_FINDINGS),
        "findings_truncated": len(findings) > MAX_FINDINGS,
        "findings": findings[:MAX_FINDINGS],
    }


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Sweep live inventory; the credential store is only a left-join lookup."""
    out: dict[str, dict[str, Any]] = {}
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = probe_stack(client, stack, token)
        out[slug] = result
        if result["state"] not in (OK, NO_CREDENTIAL) and on_error is not None:
            on_error(slug, f"alert routing: {result['state']} {result.get('detail', '')}".strip())
    return out
