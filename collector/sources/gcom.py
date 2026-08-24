"""gcom control-plane source. No stack service account needed for any of this (SPEC §3, source 1)."""

from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Sequence

from collector.config import GCOM, Config
from collector.coverage import Coverage
from collector.httpclient import ReadOnlyClient

# The inventory carries 114 fields per stack. This is the deliberate subset the pillars use; adding a
# field here is cheap, so prefer that over passing the raw record around.
STACK_FIELDS = (
    "id", "slug", "name", "orgId", "orgSlug", "url", "status", "plan", "planName", "trial",
    "createdAt", "createdBy", "updatedAt", "updatedBy", "deleteProtection", "description",
    "regionSlug", "regionPublicName", "clusterSlug", "provider", "providerRegion", "runningVersion",
    "customAuth", "customDomain", "ssl", "support",
    "dashboardCnt", "dashboardQuota", "alertCnt", "alertQuota", "userQuota", "datasourceCnts",
    "currentActiveUsers", "currentActiveAdminUsers", "currentActiveEditorUsers",
    "currentActiveViewerUsers", "dailyUserCnt", "dailyAdminCnt", "dailyEditorCnt", "dailyViewerCnt",
    "billingActiveUsers", "billingGrafanaActiveUsers", "billingOnCallActiveUsers",
    "billingStartDate", "billingEndDate",
    "hmInstancePromId", "hmInstancePromUrl", "hmInstancePromCurrentActiveSeries",
    "hmInstancePromCurrentUsage", "hmInstancePromBillingUsage",
    "hmInstanceGraphiteId", "hmInstanceGraphiteCurrentUsage", "hmInstanceGraphiteBillingUsage",
    "hlInstanceId", "hlInstanceUrl", "hlInstanceCurrentUsage", "hlInstanceBillingUsage",
    "htInstanceId", "htInstanceUrl", "htInstanceCurrentUsage", "htInstanceBillingUsage",
    "hpInstanceId", "hpInstanceUrl", "hpInstanceCurrentUsage", "hpInstanceBillingUsage",
    "amInstanceId", "amInstanceUrl", "amInstanceStatus",
    "agentManagementInstanceId", "agentManagementInstanceUrl", "agentManagementInstanceStatus",
    "incident", "machineLearning", "k6OrgId",
    "regionSyntheticMonitoringApiUrl", "regionAssistantUrl",
)


def fetch_inventory(client: ReadOnlyClient, cfg: Config) -> list[dict[str, Any]]:
    """T1  -  one call for the whole estate."""
    resp = client.get(f"{GCOM}/instances", params={"orgId": cfg.org_id}, bearer=cfg.cap)
    if not resp.ok:
        raise RuntimeError(f"inventory failed: HTTP {resp.status}")
    items = resp.json().get("items", [])
    return [{k: s.get(k) for k in STACK_FIELDS} for s in items]


def fetch_org_members(client: ReadOnlyClient, cfg: Config) -> dict[str, Any]:
    """T1  -  org membership and conditional Grafana staff-access windows."""
    resp = client.get(f"{GCOM}/orgs/{cfg.org_id}/members", bearer=cfg.cap)
    if not resp.ok:
        raise RuntimeError(f"org members failed: HTTP {resp.status}")
    body = resp.json()
    if not isinstance(body, Mapping) or not isinstance(body.get("items"), list):
        raise RuntimeError("org members response is missing items")
    members = []
    for member in body["items"]:
        if not isinstance(member, Mapping):
            raise RuntimeError("org member is not an object")
        if member.get("id") is None:
            raise RuntimeError("org member is missing id")
        if not member.get("role"):
            raise RuntimeError(f"org member {member['id']} is missing role")
        staff_present = "grafanaStaffAccess" in member
        staff = member.get("grafanaStaffAccess")
        if staff_present and not isinstance(staff, Mapping):
            staff = {}
        members.append({
            "id": member.get("id"),
            "user_id": member.get("userId"),
            "name": member.get("userName"),
            "email": member.get("userEmail"),
            "login": member.get("userUsername"),
            "role": member.get("role"),
            "created_at": member.get("createdAt"),
            "mfa_enabled": member.get("mfaEnabled"),
            "staff_access": ({
                "expires_at": staff.get("accessExpiresAt"),
                "reason": staff.get("publicReason"),
                "ticket_id": staff.get("ticketId"),
            } if staff_present else None),
        })
    return {"state": "ok", "members": members}


def user_record(user: dict[str, Any]) -> dict[str, Any]:
    """Flatten a gcom user into the record the pillars consume.

    **Identities are kept in clear by design:** this is internal, and Grafana
    already holds these users. It is also what makes Pillar D's ownership directory work  -  "who do I
    ask about a named stack" cannot be answered by a hash.

    `email_domain` is derived because it is independently useful: `example.com` vs
    `contractors.example.com` vs `external.example.com` separates staff from contractors.

    On the organisation stacks **`login` IS the email address**, so treat both as identifying. The one hard rule
    that still applies is a CARDINALITY rule, not a privacy one: none of these fields may ever become
    a metric label (SPEC §5.3). They belong in Loki and S3.
    """
    login = (user.get("login") or "").strip()
    email = (user.get("email") or login).strip()
    return {
        "login": login or None,
        "name": user.get("name"),
        "email": email or None,
        "email_domain": email.lower().rpartition("@")[2] if "@" in email else None,
        "role": user.get("role"),
        "lastSeenAt": user.get("lastSeenAt"),
        "createdAt": user.get("createdAt"),
        "isServiceAccount": user.get("isServiceAccount"),
    }


def fetch_stack_detail(
    client: ReadOnlyClient, cfg: Config, slug: str
) -> dict[str, Any]:
    """T2  -  per-stack users, plugins and service accounts. Daily, not hourly (SPEC §5.2)."""
    out: dict[str, Any] = {"slug": slug}

    users = client.get(f"{GCOM}/instances/{slug}/users", bearer=cfg.cap)
    if users.status == 409:
        # gcom's answer for a stack whose Grafana is not running.
        raise StackUnavailable(f"users HTTP 409 for {slug}")
    if not users.ok:
        raise RuntimeError(f"users HTTP {users.status}")
    out["users"] = [user_record(u) for u in users.json().get("items", [])]

    plugins = client.get(f"{GCOM}/instances/{slug}/plugins", bearer=cfg.cap)
    out["plugins"] = (
        [
            {
                "pluginSlug": p.get("pluginSlug"),
                "pluginName": p.get("pluginName"),
                "version": p.get("version"),
                "latestVersion": p.get("latestVersion"),
                "createdAt": p.get("createdAt"),
            }
            for p in plugins.json().get("items", [])
        ]
        if plugins.ok
        else []
    )

    # **The service-account inventory is NOT fetched here.** The gcom proxy route
    # `/instances/<slug>/api/serviceaccounts/search` answers 403 to the deployment credential: there is
    # no `stack-service-accounts:read` scope, only `:write`, which would also permit creating and
    # deleting service accounts on every stack in the realm. `sources/serviceaccounts.py` reads it from
    # each stack's OWN API with that stack's own reader token, using the stack-local
    # `serviceaccounts:read` action that has been in the provisioned role all along (PLAN 18.13).
    #
    # The keys are seeded here rather than left absent so a consumer that never gets the second pass -
    # a hydrated `stack_detail` from before this change, say - reads "not gathered" instead of "none".
    out["service_accounts"] = []
    out["service_accounts_state"] = "not_gathered"

    return out


class StackUnavailable(RuntimeError):
    """The stack cannot be scanned by design  -  paused, so its Grafana is not running."""


def fetch_all_stack_detail(
    client: ReadOnlyClient,
    cfg: Config,
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Fan out across stacks. A failing stack is recorded and skipped, never fatal (SPEC §5.2).

    Paused stacks are skipped up front rather than attempted: gcom answers 409 for them, and the
    estate's 4 paused stacks would otherwise cap coverage at 98.5% permanently.
    """
    results: dict[str, Any] = {}

    def one(stack: dict[str, Any]) -> None:
        slug = str(stack["slug"])
        if stack.get("status") == "paused":
            coverage.record_skipped(slug, "paused")
            return
        try:
            results[slug] = fetch_stack_detail(client, cfg, slug)
        except StackUnavailable:
            coverage.record_skipped(slug, "unavailable")
        except Exception as exc:  # noqa: BLE001 - reason string is what coverage needs
            reason = type(exc).__name__
            coverage.record_failure(slug, reason)
            if on_error:
                on_error(slug, f"{reason}: {exc}")
        else:
            coverage.record_ok(slug)

    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        list(pool.map(one, stacks))
    return results


# Access policies are stored PER REGION and `/v1/accesspolicies` returns only the region asked for.
# Measured 2026-08-17: `us` holds 15 of the org's 753  -  reading only `us` showed 2% of them. The legacy
# short names (`us`, `eu`, `au`) and the modern regionSlugs are distinct namespaces, so both are swept.
# The control-plane realms that can hold ORG-realm policies regardless of where any stack sits. `us` is
# where this project's own `gcinsight-reader` lives, and it is not any stack's `regionSlug`, so it
# can never be derived from the inventory  -  hence a floor rather than a full list.
POLICY_REALMS = ("us", "eu", "au")


def policy_regions(stacks: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Every region that could hold a policy: the fixed realms plus every region the estate occupies.

    **Derived, not configured.** A literal region list stops covering the estate the moment the organisation
    create a stack in a region nobody added here, and it fails by returning fewer policies rather than
    by erroring  -  so `risk_access_policies` would quietly under-report and look healthy doing it.
    `regionSlug` comes from the same inventory call every tier already makes, so this costs nothing.
    """
    seen = list(POLICY_REALMS)
    for r in sorted({str(s.get("regionSlug")) for s in stacks if s.get("regionSlug")}):
        if r not in seen:
            seen.append(r)
    return tuple(seen)


def fetch_access_policies(
    client: ReadOnlyClient, cfg: Config, stacks: Sequence[Mapping[str, Any]] = ()
) -> list[dict[str, Any]]:
    """Every access policy across every region, each tagged with the region it lives in.

    Pass the current inventory so a region new to the estate is covered on its first scan.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    gcom_parts = urllib.parse.urlsplit(GCOM)
    expected_path = f"{gcom_parts.path}/v1/accesspolicies"
    for region in policy_regions(stacks):
        url = f"{GCOM}/v1/accesspolicies"
        params: dict[str, Any] | None = {"region": region}
        seen_next_pages: set[str] = set()
        while True:
            resp = client.get(url, params=params, bearer=cfg.cap)
            if not resp.ok:
                raise RuntimeError(f"access policies in {region} failed: HTTP {resp.status}")
            body = resp.json()
            for p in body.get("items", []):
                policy_id = str(p.get("id") or "")
                if not policy_id:
                    raise RuntimeError(f"access policy in {region} is missing id")
                identity = (region, policy_id)
                if identity in seen:
                    continue
                seen.add(identity)
                out.append({
                    "name": p.get("name"),
                    # Needed to find one again: the delete/update call is also region-scoped.
                    "region": region,
                    "realms": [
                        {"type": r.get("type"), "identifier": r.get("identifier")}
                        for r in p.get("realms", [])
                    ],
                    "scopes": p.get("scopes"),
                    "createdAt": p.get("createdAt"),
                    "status": p.get("status"),
                })
            next_page = (((body.get("metadata") or {}).get("pagination") or {}).get("nextPage"))
            if not next_page:
                break
            if next_page in seen_next_pages:
                raise RuntimeError(f"access policies in {region}: repeated nextPage {next_page!r}")
            seen_next_pages.add(next_page)
            # Resolve only beneath the existing `/api/` base. `urljoin(GCOM, '/v1/...')` would silently
            # drop `/api`, while string concatenation would accept an absolute attacker-controlled URL.
            resolved = urllib.parse.urljoin(f"{GCOM}/", str(next_page).lstrip("/"))
            parsed = urllib.parse.urlsplit(resolved)
            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            next_regions = [value for key, value in query if key == "region"]
            if (
                parsed.scheme != gcom_parts.scheme
                or parsed.netloc != gcom_parts.netloc
                or parsed.path != expected_path
                or bool(parsed.fragment)
                or any(value != region for value in next_regions)
            ):
                raise RuntimeError(f"access policies in {region}: unsafe nextPage {next_page!r}")
            # Region is load-bearing and remains explicit on every call. Strip any identical copy from
            # nextPage so the request cannot carry two conflicting region parameters.
            safe_query = urllib.parse.urlencode(
                [(key, value) for key, value in query if key != "region"], doseq=True
            )
            url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, safe_query, "")
            )
            params = {"region": region}
    return out
