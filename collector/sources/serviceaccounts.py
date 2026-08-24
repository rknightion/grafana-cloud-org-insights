"""Per-stack service-account inventory, read with that stack's OWN credential.

**This replaces a route that never worked for the deployment credential.** The inventory used to be
fetched through the gcom proxy at `/instances/<slug>/api/serviceaccounts/search` with the org access
policy, and that returns **403** to the deployment reader: there is no `stack-service-accounts:read`
scope in Grafana Cloud, only `:write`, which would also permit CREATING and DELETING service accounts
on every stack in the realm. So the column read "NOT MEASURABLE" on every scheduled run.

The stack-local RBAC action `serviceaccounts:read` has no such problem, it is already in
`provision.DESIRED_PERMISSIONS`, and it has been live on the estate's per-stack readers since they were
provisioned. Verified live 2026-08-20 on four stacks: HTTP 200, totalCount 37 / 23 / 22 / 18.

**Deliberately the ONLY route.** The gcom-proxy call is gone rather than kept as a fallback, because a
fallback is what produced a defect worth naming: a hand-run scan with a `set:cloud-admin` credential
published a 5,269-row inventory that the scheduled platform could not sustain, and the next scheduled
run overwrote it empty. One route means the output is the same whoever runs the scan.

Three states, never collapsed into "no data". A stack with no credential yet is a provisioning state
that fixes itself on the next provisioner run; a 403 is a role that needs repairing; an HTTP error is
neither. `risk.py` reports each differently and none of them as `0`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from collector.httpclient import ReadOnlyClient

SEARCH_PATH = "/api/serviceaccounts/search"
ROLES_PATH = "/api/access-control/users/{account_id}/roles"
TOKENS_PATH = "/api/serviceaccounts/{account_id}/tokens"

# The API's own default is 1000 per page and the estate's busiest stack carries 37, so one call covers
# every stack today. Paging anyway: `totalCount` is returned alongside the page, so a silent truncation
# is detectable, and undercounting an inventory is exactly the defect the Fleet Management collector
# count turned out to have.
PER_PAGE = 1000
MAX_PAGES = 20
MAX_ASSIGNED_ROLES_PER_ACCOUNT = 50
MAX_TOKENS_PER_ACCOUNT = 100
CONCURRENCY = 12
# A live token whose last use is older than this is actionable credential debt. For a token which has
# never been used, age is measured from creation instead. Keep this name and the view column explicit:
# changing the threshold changes the finding, so it must never be an unlabeled magic number.
TOKEN_STALE_AFTER_DAYS = 90

NO_CREDENTIAL = "no_credential"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
TRUNCATED = "truncated"
OK = "ok"
SKIPPED_EXTSVC = "skipped_extsvc"
MISSING_ID = "missing_id"
PARTIAL_METADATA = "partial_metadata"
INVALID_URL = "invalid_url"


def _base_url(stack: Mapping[str, Any]) -> str | None:
    """The inventory URL, validated as an HTTPS authority and never reconstructed from the slug."""
    if not isinstance(stack, Mapping):
        return None
    value = stack.get("url")
    if not isinstance(value, str) or not value.strip():
        return None
    url = value.rstrip("/")
    try:
        parsed = urlsplit(url)
        # The inventory contract is an HTTPS origin. Silently trimming whitespace or preserving a path
        # would turn schema drift into requests against a different route, while embedded credentials,
        # a query, or a fragment change the authority or request semantics outright.
        if (
            value != value.strip()
            or any(ch.isspace() for ch in value)
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            return None
        _ = parsed.port  # force validation of malformed/out-of-range ports
    except ValueError:
        return None
    return url


def _unknown_hygiene(state: str) -> dict[str, Any]:
    """The shape consumed by Pillar E when no complete token classification is possible."""
    return {
        "token_hygiene_state": state,
        "tokens_non_expiring": None,
        "tokens_never_used": None,
        "tokens_stale": None,
        "token_nearest_future_expiry": None,
    }


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def summarise_token_hygiene(
    tokens: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fold complete token metadata into bounded, decision-ready account fields.

    One malformed token makes the summary unknown. Publishing the known subset as counts would turn
    parser or API drift into reassuring zeroes, particularly for non-expiring and stale credentials.
    Raw metadata remains bounded separately for investigation, but dashboards consume this fold.

    ``tokens_stale`` counts LIVE tokens only. An expired credential is not still an access path. A
    never-used token becomes stale once its creation time crosses the same fixed threshold.
    """
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = observed_at - timedelta(days=TOKEN_STALE_AFTER_DAYS)
    non_expiring = 0
    never_used = 0
    stale = 0
    future_expiries: list[datetime] = []

    for token in tokens:
        # Null is meaningful for expiration and last use; an absent key is schema drift, not "never".
        if not all(key in token for key in ("expiration", "lastUsedAt", "hasExpired")):
            return _unknown_hygiene(PARTIAL_METADATA)
        has_expired = token.get("hasExpired")
        if not isinstance(has_expired, bool):
            return _unknown_hygiene(PARTIAL_METADATA)

        expiration_raw = token.get("expiration")
        if expiration_raw is None:
            if has_expired:
                return _unknown_hygiene(PARTIAL_METADATA)
            non_expiring += 1
            expiration = None
        else:
            expiration = _timestamp(expiration_raw)
            if expiration is None:
                return _unknown_hygiene(PARTIAL_METADATA)
            if not has_expired and expiration > observed_at:
                future_expiries.append(expiration)

        last_used_raw = token.get("lastUsedAt")
        if last_used_raw is None:
            never_used += 1
            if "created" not in token:
                return _unknown_hygiene(PARTIAL_METADATA)
            activity = _timestamp(token.get("created"))
        else:
            activity = _timestamp(last_used_raw)
        if activity is None:
            return _unknown_hygiene(PARTIAL_METADATA)

        # Trust both the API's hasExpired field and our observation time. The latter closes the small
        # race where a token expires between the API response and this fold.
        live = not has_expired and (expiration is None or expiration > observed_at)
        if live and activity <= cutoff:
            stale += 1

    return {
        "token_hygiene_state": OK,
        "tokens_non_expiring": non_expiring,
        "tokens_never_used": never_used,
        "tokens_stale": stale,
        "token_nearest_future_expiry": (
            _rfc3339(min(future_expiries)) if future_expiries else None
        ),
    }


def record(account: Mapping[str, Any]) -> dict[str, Any]:
    """One service account, in the shape `risk.py` already consumes.

    `kind` classifies rather than making every consumer re-derive it: Grafana auto-provisions an
    `extsvc-*` account per app plugin, and on this estate they outnumber the ones somebody created
    roughly nine to one. A combined count buries the accounts that matter.
    """
    name = str(account.get("name") or "")
    output = {
        "name": name or None,
        "kind": "extsvc" if name.startswith("extsvc-") else "custom",
        "role": account.get("role"),
        # `role` is kept for existing consumers; the explicit name prevents a custom-role assignment
        # from being mistaken for the account's basic Grafana role.
        "basic_role": account.get("role"),
        "isDisabled": account.get("isDisabled"),
        "tokens": account.get("tokens"),
        "assigned_roles": [],
        "assigned_roles_total": None,
        "roles_state": SKIPPED_EXTSVC if name.startswith("extsvc-") else MISSING_ID,
        "token_metadata": [],
        "tokens_state": SKIPPED_EXTSVC if name.startswith("extsvc-") else MISSING_ID,
    }
    output.update(_unknown_hygiene(output["tokens_state"]))
    return output


def role_record(role: Mapping[str, Any]) -> dict[str, Any]:
    """The bounded identity of one directly assigned role, whatever its namespace."""
    return {key: role.get(key) for key in ("uid", "name", "displayName", "global")}


def token_record(token: Mapping[str, Any]) -> dict[str, Any]:
    """Documented token metadata only  -  never the token key or another secret-bearing field."""
    return {key: token.get(key) for key in (
        "id", "name", "role", "created", "expiration", "secondsUntilExpiration", "hasExpired",
        "lastUsedAt",
    ) if key in token}


def _state(resp: Any, required_action: str) -> tuple[str, str | None]:
    if resp.status == 401:
        return UNAUTHORISED, "token refused"
    if resp.status == 403:
        return FORBIDDEN, f"{required_action} missing from the role"
    if not resp.ok:
        return HTTP_ERROR, f"HTTP {resp.status}"
    return OK, None


def enrich(client: ReadOnlyClient, base_url: str, token: str, raw: Mapping[str, Any],
           account: dict[str, Any]) -> None:
    """Add role identity and token hygiene for a customer-created account.

    Grafana's `extsvc-*` accounts are app-managed and dominate the inventory, so enriching them would
    spend two calls each while burying the identities a platform owner can act on.
    """
    if account["kind"] == "extsvc":
        return
    account_id = raw.get("id")
    if account_id is None:
        return

    try:
        resp = client.get(base_url + ROLES_PATH.format(account_id=account_id),
                          params={"includeHidden": "true"}, bearer=token)
        state, detail = _state(resp, "users.roles:read")
        account["roles_state"] = state
        if detail:
            account["roles_detail"] = detail
        else:
            body = resp.json()
        if not detail and isinstance(body, list):
            assigned_roles = [
                role_record(r) for r in body
                if isinstance(r, Mapping)
            ]
            account["assigned_roles_total"] = len(assigned_roles)
            account["assigned_roles"] = assigned_roles[:MAX_ASSIGNED_ROLES_PER_ACCOUNT]
            if len(assigned_roles) > MAX_ASSIGNED_ROLES_PER_ACCOUNT:
                account["roles_state"] = TRUNCATED
                account["roles_detail"] = (
                    f"retained {MAX_ASSIGNED_ROLES_PER_ACCOUNT} of {len(assigned_roles)} assigned roles"
                )
        elif not detail:
            account["roles_state"] = HTTP_ERROR
            account["roles_detail"] = "HTTP 200 response was not a list"
    except Exception as exc:  # noqa: BLE001 - one account must never fail the stack sweep
        account["roles_state"] = TRANSPORT_ERROR
        account["roles_detail"] = type(exc).__name__

    try:
        resp = client.get(base_url + TOKENS_PATH.format(account_id=account_id), bearer=token)
        state, detail = _state(resp, "serviceaccounts:read")
        account["tokens_state"] = state
        account.update(_unknown_hygiene(state))
        if detail:
            account["tokens_detail"] = detail
        else:
            body = resp.json()
        if not detail and isinstance(body, list):
            all_tokens = [token_record(t) for t in body if isinstance(t, Mapping)]
            account["token_metadata"] = all_tokens[:MAX_TOKENS_PER_ACCOUNT]
            reported = account.get("tokens")
            mismatch = isinstance(reported, int) and len(all_tokens) != reported
            if len(all_tokens) > MAX_TOKENS_PER_ACCOUNT or mismatch:
                account["tokens_state"] = TRUNCATED
                account.update(_unknown_hygiene(TRUNCATED))
                expected = reported if isinstance(reported, int) else "unknown"
                account["tokens_detail"] = (
                    f"listed {len(all_tokens)} of {expected}; retained at most "
                    f"{MAX_TOKENS_PER_ACCOUNT} metadata records"
                )
            else:
                account.update(summarise_token_hygiene(all_tokens))
        elif not detail:
            account["tokens_state"] = HTTP_ERROR
            account.update(_unknown_hygiene(HTTP_ERROR))
            account["tokens_detail"] = "HTTP 200 response was not a list"
    except Exception as exc:  # noqa: BLE001 - one account must never fail the stack sweep
        account["tokens_state"] = TRANSPORT_ERROR
        account.update(_unknown_hygiene(TRANSPORT_ERROR))
        account["tokens_detail"] = type(exc).__name__


def probe_stack(client: ReadOnlyClient, stack: Mapping[str, Any], token: str) -> dict[str, Any]:
    """Every service account on one stack, or the reason there are none to report."""
    base_url = _base_url(stack)
    if base_url is None:
        return {"state": INVALID_URL, "accounts": [],
                "detail": "inventory url missing or invalid"}
    if not token:
        return {"state": NO_CREDENTIAL, "accounts": []}

    raw_accounts: list[Mapping[str, Any]] = []
    total: int | None = None
    for page in range(1, MAX_PAGES + 1):
        try:
            resp = client.get(base_url + SEARCH_PATH, params={"perpage": PER_PAGE, "page": page},
                              bearer=token)
        except Exception as exc:  # noqa: BLE001 - the reason string is the whole point
            return {"state": TRANSPORT_ERROR, "accounts": [], "detail": type(exc).__name__}
        if resp.status == 401:
            return {"state": UNAUTHORISED, "accounts": [], "detail": "token refused"}
        if resp.status == 403:
            return {"state": FORBIDDEN, "accounts": [],
                    "detail": "serviceaccounts:read missing from the role"}
        if not resp.ok:
            return {"state": HTTP_ERROR, "accounts": [], "detail": f"HTTP {resp.status}"}

        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001 - malformed JSON is an unreadable inventory
            return {"state": HTTP_ERROR, "accounts": [],
                    "detail": f"invalid JSON: {type(exc).__name__}"}
        if not isinstance(body, Mapping):
            return {"state": HTTP_ERROR, "accounts": [],
                    "detail": "HTTP 200 response was not an object"}
        batch = body.get("serviceAccounts")
        page_total = body.get("totalCount")
        if not isinstance(batch, list) or not isinstance(page_total, int) or isinstance(page_total, bool):
            return {"state": HTTP_ERROR, "accounts": [],
                    "detail": "HTTP 200 response lacked list serviceAccounts or integer totalCount"}
        if any(not isinstance(a, Mapping) for a in batch):
            return {"state": HTTP_ERROR, "accounts": [],
                    "detail": "serviceAccounts contained a non-object record"}
        if total is None:
            total = page_total
        elif page_total != total:
            return {"state": TRUNCATED, "accounts": [], "total": page_total,
                    "detail": f"totalCount changed from {total} to {page_total} during pagination"}
        if len(raw_accounts) + len(batch) > total:
            return {"state": HTTP_ERROR, "accounts": [], "total": total,
                    "detail": f"listed more than totalCount {total}"}
        raw_accounts.extend(batch)
        if len(raw_accounts) >= (total or 0):
            break
        if not batch:
            return {"state": TRUNCATED, "accounts": [], "total": total,
                    "detail": f"empty page {page} with {len(raw_accounts)} of {total}"}
    else:
        # Ran out of pages with rows still outstanding. Say so rather than publishing a short list:
        # an undercount reads as good hygiene.
        return {"state": TRUNCATED, "accounts": [], "total": total,
                "detail": f"stopped at {MAX_PAGES} pages with {len(raw_accounts)} of {total}"}

    accounts = []
    for raw in raw_accounts:
        account = record(raw)
        enrich(client, base_url, token, raw, account)
        accounts.append(account)
    return {"state": OK, "accounts": accounts, "total": total}


def probe_all(
    client: ReadOnlyClient,
    stacks: list[dict[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Sweep the LIVE inventory, left-joining the credential store (CLAUDE.md golden rule).

    Iterating the credential store instead would give a decommissioned stack a row for as long as its
    parameter survived, and would give a stack added since the last provisioner run no row at all.
    """
    out: dict[str, dict[str, Any]] = {}

    def one(stack: Mapping[str, Any]) -> None:
        slug = str(stack.get("slug") or "")
        if not slug:
            return
        if stack.get("status") == "paused":
            # Verified: a paused stack answers 403 on this path, which would read as a broken role.
            return
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = probe_stack(client, stack, token)
        if result["state"] not in (OK, NO_CREDENTIAL) and on_error:
            on_error(slug, f"service accounts: {result['state']} {result.get('detail', '')}".strip())
        out[slug] = result

    # Parallelise by stack only. Each stack is a different host; the account enrich calls inside one
    # stack remain sequential so we do not burst one tenant or scramble its bounded pagination.
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        list(pool.map(one, stacks))
    return out
