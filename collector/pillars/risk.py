"""Pillar E - governance and attack surface (PLAN 4.5).

This pillar keeps the governance work queues visible: admin-heavy stacks, inactive Fleet registrations,
unconfigured collectors, service-account and token sprawl, alert-routing inheritance, delete protection,
plugin drift, org membership and configured public dashboards.

Public-dashboard inventory and usage answer different questions. The stack-local enumeration says what
exists; Pillar J's usage-insights events say what was opened. A missing or unauthorised enumeration is
unknown, never a compliant zero.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
from typing import Any, Mapping

from collector.coverage import Coverage
from collector.sources import public_dashboards as pubdash
from collector.sources import serviceaccounts as sa

# Above this share of admins a stack is flagged. Estate median is 50%, so this is not a strict bar.
ADMIN_HEAVY_SHARE = 50.0
# A service account holding more than this many live tokens is worth a look on its own.
TOKEN_HOARD = 5

# States in which the per-stack inventory really was read, so an empty list means "none" (PLAN 18.13).
# Everything else - no credential yet, a refused token, a role missing `serviceaccounts:read`, an HTTP
# failure, a truncated sweep - means NOT MEASURED, and must never render as 0. `truncated` is excluded
# deliberately: a short list is worse than no list, because it reads as good hygiene.
SA_READABLE = frozenset({"ok"})

# What each unreadable state means to somebody who has to fix it. Split because the repairs differ: a
# missing credential self-heals on the next provisioner run, a 403 needs the role re-patched, and a
# 401 needs the token re-minted.
SA_STATE_LABEL = {
    "not_gathered": "not gathered (the tier that reads it has not run)",
    "no_credential": "awaiting its per-stack credential",
    "token_401": "credential refused - needs re-minting",
    "forbidden_403": "role is missing `serviceaccounts:read`",
    "http_error": "HTTP error",
    "transport_error": "unreachable",
    "truncated": "listing truncated - reported as unmeasured rather than short",
}

# Deliberately carries NO figure. The count moves, and a number frozen into a view row that this
# pillar does not compute is the "measured figure in always-on prose" defect: it goes stale silently
# and gets quoted. Point at the panel that measures it instead.
#: Used only when the enumeration has NOT run. Never replaced by a bare `0`: this pillar cannot tell an
#: unreadable stack from one with no configured public dashboards without the per-stack credential.
#: Enumeration supersedes the old "not measurable in Phase 1" position.
PUBLIC_DASHBOARD_NOTE = (
    "See the Public dashboards tab for the configured count, enabled subset, measured-stack denominator "
    "and observed usage. Compare the inventory with the deployment's public-sharing policy."
)


def _ratio(part: Any, whole: Any) -> float | None:
    """None, never 0.0, when either side is absent. A zero would read as a measured 0%."""
    if part is None or not whole:
        return None
    return round(100 * float(part) / float(whole), 1)


def _admin_share(stack: dict[str, Any]) -> float | None:
    users = stack.get("currentActiveUsers") or 0
    if not users:
        return None
    return round(100 * (stack.get("currentActiveAdminUsers") or 0) / users, 1)


ORG_MEMBER_STAFF_ACCESS_STATES = ("active", "expired", "none", "unknown")


def _staff_access_state(staff: Any, now: dt.datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    if staff is None:
        return "none"
    if not isinstance(staff, Mapping):
        return "unknown"
    try:
        expires = dt.datetime.fromisoformat(str(staff.get("expires_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "unknown"
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    return "active" if expires > now else "expired"


# Unprotected stacks below this are deletion CANDIDATES, not deletion risks - reporting them inverts
# the advice. Measured across the 269 unprotected stacks on 2026-08-18: active series p50=6, p75=5,881,
# p90=74,271, p95=146,411, max=3,043,915, and 39 of them carry literally zero series. 50,000 sits
# between p75 and p90 and yields 36 stacks that genuinely hold production load. Unfiltered this kind
# would report 269 findings, which is the inventory again rather than a findings list.
DELETE_PROTECTION_SERIES_FLOOR = 50_000

# Finding views are deliberately narrow projections. Reusing the wide per-stack row made every
# specialised view depend on every optional source represented in that row: an unavailable
# service-account sweep could withhold the admin, delete-protection and Fleet findings even though
# none of those findings reads a service-account field.
ADMIN_SPRAWL_FIELDS = (
    " Stack", "Region", "Users (active)", "Admins", "Admin share %", "Delete protection",
    "Alert rules", "Active series",
)
DELETE_PROTECTION_FIELDS = (
    " Stack", "Region", "Users (active)", "Admins", "Admin share %", "Delete protection",
    "Alert rules", "Active series",
)
FLEET_DEAD_FIELDS = (
    " Stack", "Region", "Collectors", "Collectors (active)", "Collectors (inactive)",
    "Inactive %", "Pipelines", "Pipelines (enabled)", "FM dead", "Alert rules", "Active series",
)

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "risk_service_accounts": (
        (" Stack", "string"), ("Service account", "string"), ("Kind", "string"),
        ("Role", "string"), ("Assigned roles", "string"), ("Role read", "string"),
        ("Tokens", "number"), ("Expired tokens", "number"),
        ("Non-expiring tokens", "number"), ("Never-used tokens", "number"),
        ("Stale live tokens (90d)", "number"), ("Nearest token expiry", "string"),
        ("Token read", "string"), ("Token hygiene", "string"),
        ("Disabled", "boolean"), ("Flag", "string"),
    ),
    "risk_org_members": (
        ("Name", "string"), ("Email", "string"), ("Login", "string"), ("Role", "string"),
        ("MFA enabled", "boolean"), ("Member since", "string"), ("Staff access", "string"),
        ("Staff access expires", "string"), ("Staff access reason", "string"),
        ("Staff access ticket", "string"),
    ),
    "risk_fleet_attributes": (
        (" Stack", "string"), ("Attribute", "string"), ("Value", "string"),
        ("Active collectors", "number"), ("Distinct values", "number"),
        ("Truncated", "boolean"),
    ),
    "risk_fleet_pipelines": (
        (" Stack", "string"), ("Pipeline", "string"), ("Enabled", "boolean"),
        ("Source", "string"), ("Config type", "string"),
        ("Collectors targeted", "number"), ("Enabled collectors targeted", "number"),
        ("Matchers", "string"), ("Updated at", "string"),
    ),
    "risk_public_dashboards": (
        (" Stack", "string"), ("Dashboard", "string"),
        ("Dashboard uid", "string"), ("Enabled", "boolean"),
    ),
    "risk_alert_routing": (
        (" Stack", "string"), ("Rules", "number"), ("Active", "number"),
        ("Direct receiver", "number"), ("Active inherited", "number"),
        ("Active missing receiver", "number"), ("Unverified built-in receiver", "number"),
        ("Contact point integrations", "number"), ("Completeness", "string"),
        ("Findings retained", "number"), ("Findings total", "number"),
        ("Findings truncated", "boolean"),
    ),
    "risk_alert_routing_findings": (
        (" Stack", "string"), ("Rule", "string"), ("Rule uid", "string"),
        ("Folder uid", "string"), ("Rule group", "string"), ("Paused", "boolean"),
        ("Routing", "string"), ("Receiver", "string"), ("Receiver state", "string"),
    ),
}


def _project(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row[field] for field in fields}


def _service_account_flag(account: dict[str, Any], kind: str) -> str | None:
    """Actionable credential risks for customer-created accounts only.

    Grafana-managed ``extsvc-*`` accounts deliberately skip token enrichment; treating that unknown
    metadata as clean or risky would both be wrong. Custom accounts keep the existing token-hoard
    finding and additionally surface permanent and stale live credentials when (and only when) the
    token metadata was completely classified. Never-used is retained as context, but a freshly minted
    token is not a finding until it crosses the stale threshold.
    """
    if kind != "custom":
        return None
    findings: list[str] = []
    if account.get("role") == "Admin" and (account.get("tokens") or 0) > TOKEN_HOARD:
        findings.append("admin with many tokens")
    if account.get("token_hygiene_state") == sa.OK:
        non_expiring = account.get("tokens_non_expiring") or 0
        stale = account.get("tokens_stale") or 0
        if non_expiring:
            findings.append(f"{non_expiring} non-expiring token{'s' if non_expiring != 1 else ''}")
        if stale:
            findings.append(f"{stale} stale live token{'s' if stale != 1 else ''}")
    return "; ".join(findings) or None


def build(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    dataplane: dict[str, Any] | None = None,
    stack_detail: dict[str, Any] | None = None,
    access_policies: list[dict[str, Any]] | None = None,
    fleet: dict[str, Any] | None = None,
    public_dashboards: dict[str, Any] | None = None,
    service_accounts: dict[str, Any] | None = None,
    alert_routing: dict[str, Any] | None = None,
    org_members: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    dataplane = dataplane or {}
    public_dashboards = public_dashboards or {}
    # Fleet Management moved to its own HOURLY input. The 6-hourly `dataplane` payload still carries a
    # `fleet` sub-object on any scan taken before the move, so it is the fallback rather than an error -
    # but it only has the old count-only shape, so the active/inactive split is absent there and reads
    # as unmeasured rather than as zero.
    fleet = fleet or {}
    stack_detail = stack_detail or {}
    service_accounts = service_accounts or {}
    alert_routing = alert_routing or {}
    access_policies = access_policies or []
    now = now or dt.datetime.now(dt.timezone.utc)
    metrics: list[tuple[str, dict[str, str], float]] = []
    live_slugs = [str(stack["slug"]) for stack in stacks]

    def fleet_record(slug: str) -> dict[str, Any]:
        return fleet.get(slug) or (dataplane.get(slug) or {}).get("fleet") or {}

    rows: list[dict[str, Any]] = []
    for s in stacks:
        slug = str(s["slug"])
        fm = fleet_record(slug)
        detail = stack_detail.get(slug) or {}
        sa_record = service_accounts.get(slug) or {}
        sas = sa_record.get("accounts") or []
        # A read that did not happen is not an empty inventory. See `SA_READABLE` below.
        sa_readable = sa_record.get("state") in SA_READABLE
        custom_sas = [a for a in sas if a.get("kind") == "custom"]
        rows.append({
            " Stack": slug,
            "Region": s.get("regionSlug"),
            "Users (active)": s.get("currentActiveUsers") or 0,
            "Admins": s.get("currentActiveAdminUsers") or 0,
            # None, not 0 - a stack with no users has no meaningful admin share.
            "Admin share %": _admin_share(s),
            "Delete protection": bool(s.get("deleteProtection")),
            "Alert rules": s.get("alertCnt") or 0,
            "Active series": s.get("hmInstancePromCurrentActiveSeries") or 0,
            # `Collectors` is every REGISTRATION Fleet Management returns, unchanged, so the published
            # series stays continuous. Registrations can include inactive collectors, so read the active
            # and inactive columns beside it before treating this as the current fleet size.
            "Collectors": fm.get("collectors") if fm.get("available") else None,
            "Collectors (active)": fm.get("collectors_active") if fm.get("available") else None,
            "Collectors (inactive)": fm.get("collectors_inactive") if fm.get("available") else None,
            "Inactive %": _ratio(fm.get("collectors_inactive"), fm.get("collectors")),
            "Pipelines": fm.get("pipelines") if fm.get("available") else None,
            "Pipelines (enabled)": fm.get("pipelines_enabled") if fm.get("available") else None,
            "FM dead": fm.get("provisioned_but_empty") if fm.get("available") else None,
            # None, not 0, when the read was denied - a 0 here reads as "no sprawl".
            "Service accounts": len(sas) if sa_readable else None,
            "Service accounts (custom)": len(custom_sas) if sa_readable else None,
            "SA tokens": sum(a.get("tokens") or 0 for a in sas) if sa_readable else None,
        })

    admin_heavy = [r for r in rows if (r["Admin share %"] or 0) > ADMIN_HEAVY_SHARE]
    metrics.append(("gcinsight_risk_admin_heavy_stacks", {}, float(len(admin_heavy))))

    # Delete protection. The METRIC counts every unprotected stack and the VIEW carries only the ones
    # holding real load, deliberately: "2 of 271 stacks are protected" is the governance headline, while
    # "these 36 need it turned on" is the work. Measured 2026-08-18: 269 unprotected, and the only two
    # protected are paused `teststack*` leftovers - protection is on the two stacks that need it least.
    # Absent rather than 0 when everything is protected, so it cannot be confused with a failed read.
    unprotected = [r for r in rows if not r["Delete protection"]]
    if unprotected:
        metrics.append(("gcinsight_risk_stacks_without_delete_protection", {},
                        float(len(unprotected))))

    fm_entries = [(slug, fleet_record(slug)) for slug in live_slugs]
    fm_available = [(slug, fm) for slug, fm in fm_entries if fm.get("available")]
    if fm_available:
        metrics.append(("gcinsight_risk_collectors_total", {},
                        float(sum(fm.get("collectors") or 0 for _, fm in fm_available))))
        metrics.append(("gcinsight_risk_stacks_pipelines_no_collectors", {},
                        float(len([1 for _, fm in fm_available if fm.get("provisioned_but_empty")]))))
        # **ABSENT, not zero, on a payload that predates the split.** The old count-only shape has no
        # `collectors_active`, and emitting 0 there would say the estate has no live collectors at all -
        # which is both false and exactly the kind of confident zero this platform keeps having to fix.
        split = [fm for _s, fm in fm_available if fm.get("collectors_active") is not None]
        if split:
            metrics.append(("gcinsight_risk_collectors_active", {},
                            float(sum(fm.get("collectors_active") or 0 for fm in split))))
            metrics.append(("gcinsight_risk_collectors_inactive", {},
                            float(sum(fm.get("collectors_inactive") or 0 for fm in split))))
            for slug, fm in fm_available:
                if fm.get("collectors_active") is not None:
                    metrics.append(("gcinsight_stack_collectors_active", {"stack": slug},
                                    float(fm["collectors_active"])))
        pipes = [fm for _s, fm in fm_available if fm.get("pipelines_enabled") is not None]
        if pipes:
            metrics.append(("gcinsight_risk_pipelines_total", {},
                            float(sum(fm.get("pipelines") or 0 for fm in pipes))))
            metrics.append(("gcinsight_risk_pipelines_enabled", {},
                            float(sum(fm.get("pipelines_enabled") or 0 for fm in pipes))))
            metrics.append(("gcinsight_risk_pipelines_generated", {},
                            float(sum(fm.get("pipelines_generated") or 0 for fm in pipes))))
        # The evaluator's own health. A non-zero value means a matcher shape this platform does not
        # parse, so at least one "collectors targeted" figure is UNKNOWN rather than small.
        unparsed = sum(fm.get("matchers_unparsed") or 0 for _s, fm in fm_available)
        if any(fm.get("matchers_unparsed") is not None for _s, fm in fm_available):
            metrics.append(("gcinsight_risk_fleet_matchers_unparsed", {}, float(unparsed)))
        # Collectors no ENABLED pipeline targets: registered, alive, and receiving no configuration.
        unmatched = [fm.get("collectors_unmatched") for _s, fm in fm_available
                     if fm.get("collectors_unmatched") is not None]
        if unmatched:
            metrics.append(("gcinsight_risk_collectors_unconfigured", {},
                            float(sum(unmatched))))

    # --- T2 halves: service accounts and plugin drift. ---
    sa_rows: list[dict[str, Any]] = []
    drift_rows: list[dict[str, Any]] = []
    sa_by_kind = {"extsvc": 0, "custom": 0}
    sa_states = {
        slug: str((service_accounts.get(slug) or {}).get("state") or "not_gathered")
        for slug in live_slugs
    }
    sa_readable_stacks = [slug for slug, st in sa_states.items() if st in SA_READABLE]
    sa_unreadable = collections.Counter(st for st in sa_states.values() if st not in SA_READABLE)
    for slug in live_slugs:
        detail = service_accounts.get(slug) or {}
        for account in (detail or {}).get("accounts", []) or []:
            kind = account.get("kind") or "custom"
            sa_by_kind[kind] = sa_by_kind.get(kind, 0) + 1
            hygiene_readable = account.get("token_hygiene_state") == sa.OK
            sa_rows.append({
                " Stack": slug,
                # Names are unbounded, so they live here and never in a label.
                "Service account": account.get("name"),
                "Kind": kind,
                "Role": account.get("role"),
                "Assigned roles": ", ".join(
                    str(r.get("name") or r.get("uid"))
                    for r in (account.get("assigned_roles") or [])
                    if r.get("name") or r.get("uid")
                ) or None,
                "Role read": account.get("roles_state"),
                "Tokens": account.get("tokens") or 0,
                "Expired tokens": len([
                    t for t in (account.get("token_metadata") or []) if t.get("hasExpired")
                ]) if hygiene_readable else None,
                "Non-expiring tokens": (
                    account.get("tokens_non_expiring") if hygiene_readable else None
                ),
                "Never-used tokens": (
                    account.get("tokens_never_used") if hygiene_readable else None
                ),
                f"Stale live tokens ({sa.TOKEN_STALE_AFTER_DAYS}d)": (
                    account.get("tokens_stale") if hygiene_readable else None
                ),
                "Nearest token expiry": (
                    account.get("token_nearest_future_expiry") if hygiene_readable else None
                ),
                "Token read": account.get("tokens_state"),
                "Token hygiene": account.get("token_hygiene_state"),
                "Disabled": bool(account.get("isDisabled")),
                "Flag": _service_account_flag(account, kind),
            })
    for slug, detail in stack_detail.items():
        for plugin in (detail or {}).get("plugins", []) or []:
            version, latest = plugin.get("version"), plugin.get("latestVersion")
            if version and latest and version != latest:
                drift_rows.append({
                    " Stack": slug,
                    "Plugin": plugin.get("pluginSlug"),
                    "Installed": version,
                    "Latest": latest,
                })
    # Emit the SA totals only where at least one stack could actually be read. With the minimum-scope
    # reader every stack is denied, and a 0 would publish "no service-account sprawl org-wide".
    if sa_readable_stacks:
        for kind, count in sorted(sa_by_kind.items()):
            metrics.append(("gcinsight_risk_service_accounts_total", {"kind": kind}, float(count)))
    if stack_detail:
        metrics.append(("gcinsight_risk_plugin_drift_stacks", {},
                        float(len({r[" Stack"] for r in drift_rows}))))

    # --- Public dashboards, ENUMERATED -------------------------------------------------------------
    # Two rules keep a policy comparison honest:
    #
    #   1. Only stacks whose state is `ok` are added up. The endpoint answers 200 with a
    #      PERMISSION-FILTERED list rather than 403, so an unreadable stack contributes nothing to the
    #      numerator AND nothing to the denominator - counting it as zero would report a breach as
    #      compliance in a zero-tolerance deployment.
    #   2. Nothing is emitted at all unless at least one stack was read. A gap is an absent series.
    _pd_ok = [v for v in (public_dashboards.get(str(s["slug"])) for s in stacks)
              if isinstance(v, dict) and v.get("state") in pubdash.READABLE]
    _pd_measured = len(_pd_ok)
    _pd_total = sum(v.get("total") or 0 for v in _pd_ok)
    _pd_enabled = sum(v.get("enabled") or 0 for v in _pd_ok)
    _pd_hits = [v for v in _pd_ok if (v.get("total") or 0) > 0]
    _pd_stacks = len(_pd_hits)
    if _pd_measured:
        metrics.append(("gcinsight_risk_public_dashboards_measured", {}, float(_pd_measured)))
        metrics.append(("gcinsight_risk_public_dashboards_enumerated", {}, float(_pd_total)))
        metrics.append(("gcinsight_risk_public_dashboards_enabled", {}, float(_pd_enabled)))
        metrics.append(("gcinsight_risk_public_dashboards_stacks", {}, float(_pd_stacks)))

    # --- Alert routing: rule-to-receiver coverage from each stack's provisioning API. -----------
    # Only complete-enough successful reads contribute. The endpoints expose bare arrays with no
    # server total, so the source records that limitation explicitly rather than claiming completeness.
    routing_ok = [
        record for slug in live_slugs
        for record in [alert_routing.get(slug)]
        if isinstance(record, dict) and record.get("available") and record.get("state") == "ok"
    ]
    if routing_ok:
        metrics.extend([
            ("gcinsight_risk_alert_routing_stacks_measured", {}, float(len(routing_ok))),
            ("gcinsight_risk_alert_rules_total", {},
             float(sum(r.get("rules_total") or 0 for r in routing_ok))),
            ("gcinsight_risk_alert_rules_active_inherited", {},
             float(sum(r.get("rules_active_inherited") or 0 for r in routing_ok))),
            ("gcinsight_risk_alert_rules_active_missing_receiver", {},
             float(sum(r.get("rules_active_missing_receiver") or 0 for r in routing_ok))),
            ("gcinsight_risk_alert_rules_unverified_builtin", {},
             float(sum(r.get("rules_unverified_builtin") or 0 for r in routing_ok))),
        ])

    # --- Grafana.com org membership ---------------------------------------------------------------
    # This is one complete org-level response, not a per-stack sample. A missing or malformed input is
    # unknown and emits nothing; a successful empty list is a measured zero and clears the prior view.
    member_rows: list[dict[str, Any]] | None = None
    if isinstance(org_members, Mapping) and org_members.get("state") == "ok" \
            and isinstance(org_members.get("members"), list) \
            and all(isinstance(member, Mapping) for member in org_members["members"]):
        members = org_members["members"]
        metrics.append(("gcinsight_risk_org_members_admins", {},
                        float(sum(1 for member in members if member.get("role") == "Admin"))))
        metrics.append(("gcinsight_risk_org_members_viewers", {},
                        float(sum(1 for member in members if member.get("role") == "Viewer"))))
        states = collections.Counter(
            _staff_access_state(member.get("staff_access"), now) for member in members
        )
        for state in ORG_MEMBER_STAFF_ACCESS_STATES:
            metrics.append(("gcinsight_risk_org_members_staff_access", {"status": state},
                            float(states[state])))
        member_rows = []
        for member in members:
            staff = member.get("staff_access")
            member_rows.append({
                "Name": member.get("name"),
                "Email": member.get("email"),
                "Login": member.get("login"),
                "Role": member.get("role"),
                "MFA enabled": member.get("mfa_enabled"),
                "Member since": member.get("created_at"),
                "Staff access": _staff_access_state(staff, now),
                "Staff access expires": staff.get("expires_at") if isinstance(staff, Mapping) else None,
                "Staff access reason": staff.get("reason") if isinstance(staff, Mapping) else None,
                "Staff access ticket": staff.get("ticket_id") if isinstance(staff, Mapping) else None,
            })

    views: dict[str, list[dict[str, Any]]] = {
        "risk": sorted(rows, key=lambda r: -(r["Admin share %"] or 0)),
        "risk_admin_sprawl": sorted(
            [_project(r, ADMIN_SPRAWL_FIELDS) for r in admin_heavy],
            key=lambda r: (-(r["Active series"] or 0), -(r["Admin share %"] or 0)),
        ),
        # Sorted by what is at stake, so the largest exposure is the first row a reader sees. Composes
        # with `risk_admin_sprawl`: a stack that is admin-heavy AND unprotected means every one of those
        # admins can delete it, which neither finding says on its own.
        "risk_delete_protection": sorted(
            [_project(r, DELETE_PROTECTION_FIELDS) for r in unprotected
             if (r["Active series"] or 0) >= DELETE_PROTECTION_SERIES_FLOOR],
            key=lambda r: -(r["Active series"] or 0),
        ),
    }
    if member_rows is not None:
        views["risk_org_members"] = member_rows
    # **Emit a view ONLY where the input existed.** Every tier writes every view it returns, so a tier
    # without the data would overwrite a richer tier's table with an empty one - and an empty security
    # table reads as "there are none". Measured: T3 blanked `risk_access_policies` (754 rows -> 0).
    if _pd_measured:
        # One row per PUBLIC DASHBOARD, not per stack - the remediation is per dashboard, and a stack
        # row would hide that one stack alone carries 12 of the estate's 34. `accessToken` is never
        # here: it is the live public URL and this view is served to a wide Infinity reader. A
        # successful measured zero deliberately publishes `[]` so S3 clears a stale prior finding;
        # with no readable stacks the view remains withheld.
        views["risk_public_dashboards"] = sorted(
            [
                {
                    " Stack": v["slug"],
                    "Dashboard": d.get("title"),
                    "Dashboard uid": d.get("dashboard_uid"),
                    "Enabled": d.get("enabled"),
                }
                for v in _pd_hits for d in (v.get("dashboards") or [])
            ],
            key=lambda r: (not r["Enabled"], r[" Stack"], r["Dashboard"] or ""),
        )
    if routing_ok:
        views["risk_alert_routing"] = sorted([
            {
                " Stack": r.get("slug"),
                "Rules": r.get("rules_total"),
                "Active": r.get("rules_active"),
                "Direct receiver": r.get("rules_direct_receiver"),
                "Active inherited": r.get("rules_active_inherited"),
                "Active missing receiver": r.get("rules_active_missing_receiver"),
                "Unverified built-in receiver": r.get("rules_unverified_builtin"),
                "Contact point integrations": r.get("contact_point_integrations"),
                "Completeness": r.get("completeness"),
                "Findings retained": r.get("findings_retained"),
                "Findings total": r.get("findings_total"),
                "Findings truncated": bool(r.get("findings_truncated")),
            }
            for r in routing_ok
        ], key=lambda row: (
            -(row["Active missing receiver"] or 0), -(row["Active inherited"] or 0),
            row[" Stack"] or "",
        ))
        # A successful zero deliberately publishes an empty list, clearing a remediated stale finding.
        views["risk_alert_routing_findings"] = sorted([
            {
                " Stack": r.get("slug"),
                "Rule": finding.get("title"),
                "Rule uid": finding.get("rule_uid"),
                "Folder uid": finding.get("folder_uid"),
                "Rule group": finding.get("rule_group"),
                "Paused": finding.get("paused"),
                "Routing": finding.get("routing"),
                "Receiver": finding.get("receiver"),
                "Receiver state": finding.get("receiver_state"),
            }
            for r in routing_ok for finding in (r.get("findings") or [])
        ], key=lambda row: (
            row["Receiver state"] != "missing", row["Paused"], row[" Stack"] or "",
            row["Rule"] or "",
        ))
    if fm_available:
        # Configured and never connected. The actionable Fleet Management set.
        views["risk_fleet_dead"] = sorted(
            [_project(r, FLEET_DEAD_FIELDS) for r in rows if r["FM dead"]],
            key=lambda r: -(r["Pipelines"] or 0),
        )
        # Every bounded Fleet attribute the source retains, over ACTIVE collectors only. The source
        # caps values per attribute and carries the uncapped distinct count, so truncation remains
        # explicit rather than making version or platform drift look tidier than it is.
        views["risk_fleet_attributes"] = sorted([
            {
                " Stack": slug,
                "Attribute": attribute,
                "Value": value,
                "Active collectors": count,
                "Distinct values": detail.get("distinct"),
                "Truncated": int(detail.get("distinct") or 0)
                             > len(detail.get("values") or {}),
            }
            for slug, fm in fm_available
            for attribute, detail in (fm.get("attributes") or {}).items()
            if isinstance(detail, dict)
            for value, count in (detail.get("values") or {}).items()
        ], key=lambda row: (
            row["Attribute"] != "collector.version",
            -(row["Active collectors"] or 0), row[" Stack"], row["Value"],
        ))
        # Pipeline matcher reach is evaluated by the source against the active fleet. Publish the named
        # rows where an owner can decide whether a disabled, unmatched or user-owned pipeline is obsolete.
        # Full pipeline contents are never retained.
        views["risk_fleet_pipelines"] = sorted([
            {
                " Stack": slug,
                "Pipeline": pipeline.get("name"),
                "Enabled": bool(pipeline.get("enabled")),
                "Source": pipeline.get("source_type"),
                "Config type": pipeline.get("config_type"),
                "Collectors targeted": pipeline.get("targeted"),
                "Enabled collectors targeted": pipeline.get("targeted_enabled"),
                "Matchers": "; ".join(
                    matcher if isinstance(matcher, str)
                    else json.dumps(matcher, sort_keys=True, separators=(",", ":"))
                    for matcher in (pipeline.get("matchers") or [])
                ),
                "Updated at": pipeline.get("updated_at"),
            }
            for slug, fm in fm_available
            for pipeline in (fm.get("pipeline_detail") or [])
            if isinstance(pipeline, dict)
        ], key=lambda row: (
            row["Enabled"], -(row["Enabled collectors targeted"] or 0),
            row[" Stack"], row["Pipeline"] or "",
        ))
    if access_policies:
        views["risk_access_policies"] = sorted(
            [
                {
                    " Policy": p.get("name"),
                    # Policies are region-scoped and so is the call to change one. Without this column
                    # a reader cannot find the policy again.
                    "Region": p.get("region"),
                    "Realm types": ", ".join(sorted({
                        str(r.get("type")) for r in (p.get("realms") or [])
                    })) or None,
                    "Stack-scoped": all(
                        r.get("type") == "stack" for r in (p.get("realms") or [])
                    ) if p.get("realms") else None,
                    "Scopes": ", ".join(p.get("scopes") or []),
                    "Scope count": len(p.get("scopes") or []),
                    # The ones worth reviewing first: broad write power over the whole org.
                    "Org-wide write": any(
                        r.get("type") == "org" for r in (p.get("realms") or [])
                    ) and any(
                        not s.endswith(":read") for s in (p.get("scopes") or [])
                    ),
                    "Created": p.get("createdAt"),
                }
                for p in access_policies
            ],
            key=lambda r: (not r["Org-wide write"], -(r["Scope count"] or 0)),
        )
    views["risk_summary"] = [{
            # `len(rows)` is every stack in the inventory, INCLUDING the paused ones this pillar can still
            # describe from inventory alone. `coverage.scannable` excludes them. So the two are not the
            # same population, and the old "{rows} of {scannable} scannable" phrasing rendered the literal
            # nonsense "273 of 269 scannable" - a denominator smaller than its own numerator, on the first
            # row of a summary table whose whole job is to establish the denominator.
            #
            # Stated as what it is: rows in this table, out of the whole estate.
            " Metric": "Stacks in this table",
            "Value": f"{len(rows)} of {coverage.total} in the estate "
                     f"({coverage.scannable} reachable by a live scan, "
                     f"{coverage.total - coverage.scannable} paused)",
        }, {
            " Metric": f"Stacks with over {ADMIN_HEAVY_SHARE:.0f}% admins",
            "Value": len(admin_heavy),
        }, {
            " Metric": "Median admin share %",
            "Value": (lambda v: v[len(v) // 2] if v else None)(
                sorted(r["Admin share %"] for r in rows if r["Admin share %"] is not None)
            ),
        }, {
            " Metric": "Fleet Management: pipelines configured, zero collectors",
            "Value": len([r for r in rows if r["FM dead"]]) if fm_available else "needs a T1 scan",
        }, {
            " Metric": "Collectors registered org-wide",
            "Value": sum(r["Collectors"] or 0 for r in rows) if fm_available else "needs a T1 scan",
        }, {
            " Metric": "Stacks without delete protection",
            "Value": len([r for r in rows if not r["Delete protection"]]),
        }, {
            # A number ONLY where the enumeration actually read the stack; words otherwise. See
            # PUBLIC_DASHBOARD_NOTE - a bare 0 from an unreadable estate reads as compliant.
            " Metric": "Configured public dashboards",
            "Value": PUBLIC_DASHBOARD_NOTE,
        }, {
            " Metric": "Access policies on the org",
            "Value": len(access_policies) if access_policies else "needs a T1 scan",
        }]
    if sa_readable_stacks:
        views["risk_service_accounts"] = sorted(
            sa_rows, key=lambda r: (r["Flag"] is None, -(r["Tokens"] or 0))
        )
    if stack_detail:
        views["risk_plugin_drift"] = sorted(drift_rows, key=lambda r: (r[" Stack"], r["Plugin"]))
    if service_accounts:
        # The unreadable stacks are named BY REASON rather than collapsed into one count, because the
        # three reasons have three different repairs and the row is where somebody decides what to do.
        why = ", ".join(f"{n} {SA_STATE_LABEL.get(st, st)}"
                        for st, n in sorted(sa_unreadable.items(), key=lambda kv: -kv[1]))
        views["risk_summary"].insert(1, {
            " Metric": "Stacks with service-account detail",
            "Value": (
                f"{len(sa_readable_stacks)} of {len(live_slugs)} scanned"
                + (f". NOT MEASURED on the rest: {why}." if why else "")
            ),
        })
    return metrics, views
