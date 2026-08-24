"""Per-stack reader provisioning (PLAN 17D). Decision logic only  -  I/O lives in `bin/provision.py`.

## What this exists to create

One persistent, read-only identity per stack, so the collector can read Assistant data and the one T2
figure the org CAP cannot reach (per-stack service accounts  -  `stack-service-accounts:read` does not
exist as a gcom scope, only `:write`).

Per stack, created once and then reconciled:

- custom role `custom:gcinsight.reader`  -  27 read permission pairs (26 unique action names),
  listed in `DESIRED_PERMISSIONS`
- service account `gcinsight-data`, basic role **None**, holding that role
- one **non-expiring** token, stored in SSM at `/gcinsight/stack-token/<slug>`

## Why the per-run mint-and-destroy model was rejected

gcom is one shared control plane paced at 6 req/s. An unthrottled 271-stack read sweep of 813 calls
already drew 77 HTTP 429s and covered 71.6% of the estate; ~1,600 writes per run would be throttled or
flagged. Steady state here is ~270 gcom READS and zero writes.

## The failure modes this module is shaped around

Each was probed live on 2026-08-20 (PLAN 17D-review), and each one drives a specific branch:

- **A duplicate service-account name is refused** (400 `serviceaccounts.ErrAlreadyExists`), so creation
  cannot sprawl  -  but "the SA exists" is NOT proof we hold a working credential. A crash between creating
  the SA and storing its token leaves a stack broken for ever while a name check reads healthy. Coverage
  is therefore a THREE-part check; see `Presence` and `plan_action`.
- **401 and 403 mean different repairs.** A revoked or invalid token returns 401; a valid token with the
  wrong permissions returns 403. Conflating them means either re-minting on every permission problem or
  never noticing a lost role assignment.
- **Service-account token names are unique per ORG, not per service account.** A fixed token name works
  on the first stack and fails on the other 272  -  hence `token_name`.
- **Role creation is not idempotent** (400 on a duplicate name), so reconciliation is
  GET → compare → PUT. The comparison is an UNORDERED SET (`role_drift`): comparing ordered lists would
  see drift every run and rewrite 273 roles daily, which is the audit-log noise the persistent model
  exists to avoid.
- **Paused stacks 403 on the service-account endpoint itself**  -  you cannot even list, let alone create.
  Counting them as missing would fire the coverage alert forever on four automated-test leftovers.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from collections.abc import Mapping as _MappingABC
from typing import Any, Iterable, Mapping, Sequence

from collector import identity

# --- The frozen seam -------------------------------------------------------------------------------
# Changing any name here means reconciling every provisioned stack. Treat as an interface, not a constant.

ROLE_NAME = identity.env("GCINSIGHT_ROLE_NAME", "custom:gcinsight.reader")
ROLE_DISPLAY = identity.env("GCINSIGHT_ROLE_DISPLAY", "Grafana Cloud Org Insights reader")
ROLE_GROUP = identity.env("GCINSIGHT_ROLE_GROUP", "Grafana Cloud Org Insights")
READER_SA_NAME = identity.env("GCINSIGHT_READER_SA_NAME", "gcinsight-data")
# The transient Admin identity that creates and assigns the role. Deleted LAST, every run.
ADMIN_SA_NAME = identity.env("GCINSIGHT_ADMIN_SA_NAME", "gcinsight-insights-provisioner")
SSM_PREFIX = identity.env("GCINSIGHT_STACK_TOKEN_PREFIX", "/gcinsight/stack-token")
TOKEN_NAME_PREFIX = identity.env("GCINSIGHT_TOKEN_NAME_PREFIX", "gcinsight-data")

# Short on purpose. A run killed between creating this identity and deleting it leaves an Admin service
# account on a customer stack; a 15-minute token means the leftover is inert almost immediately, and the
# next run's sweep removes the account itself.
ADMIN_TOKEN_TTL = 900

ASSISTANT_ACTIONS = (
    "usage:read",
    "investigations:read",
    "investigations.all:read",
    "investigations.system:read",
    "mcps.tenant:read",
    "skills.tenant:read",
    "automations.tenant:read",
    "rules.tenant:read",
    "watcher-agents:read",
)

# The role as WE declare it. Grafana attaches actions of its own accord, so `role_drift` compares only
# the actions we asked for: an extra action Grafana added is not drift and must not trigger a rewrite.
#
# **`datasources:read` and `datasources:query` ARE SEPARATE ACTIONS, and conflating them cost this
# platform real capability.** The original decision refused `datasources:*` on the grounds that it would
# be "query rights over the customer's production datasources on every stack". That is true of
# `datasources:query` and FALSE of `datasources:read`, which only LISTS. So the list is estate-wide and
# the query right stays pinned to one Grafana-provisioned telemetry datasource.
USAGE_INSIGHTS_DS_UID = "grafanacloud-usage-insights"

# The Adaptive Logs plugin. Its recommendations carry `projected_savings` outright, which the metrics
# equivalent does not - there we compute the saving ourselves from series counts.
#
# **The route is the app-plugin proxy, NOT the plugin's resource handler.**
# `/api/plugin-proxy/grafana-adaptivelogs-app/recommendations` returns 200; every
# `/api/plugins/grafana-adaptivelogs-app/resources/*` path returns 500 `plugin.requestFailureError`,
# and the datasource proxy returns 400 "Authentication to data source failed". Two of those three look
# like a permission problem and are not. The gcom scope `adaptive-logs:admin` is NOT needed and must not
# be granted: it is the only adaptive-logs scope that exists, so it would carry write capability over
# the customer's log drop rules.
ADAPTIVE_LOGS_PLUGIN = "grafana-adaptivelogs-app"

# Adaptive Traces is not collected yet. Keep its mutation actions explicitly refused, but grant no read
# access until a consumer exists: capability without a caller is unnecessary standing authority.
ADAPTIVE_TRACES_PLUGIN = "grafana-adaptivetraces-app"

DESIRED_PERMISSIONS: tuple[dict[str, str], ...] = (
    {"action": "plugins.app:access", "scope": "plugins:id:grafana-assistant-app"},
    *({"action": f"grafana-assistant-app.{a}"} for a in ASSISTANT_ACTIONS),
    {"action": "plugins.app:access", "scope": f"plugins:id:{ADAPTIVE_LOGS_PLUGIN}"},
    {"action": f"{ADAPTIVE_LOGS_PLUGIN}.patterns:read"},
    # --- Inventory the org access policy cannot reach ------------------------------------------------
    # Each of these was verified by reading the required action off the endpoint's own 403 rather than
    # from the documentation, and each one closes a case where the API returns **200 with a
    # permission-filtered list** rather than 403. That is the dangerous shape: measured on one stack
    # against an Admin identity, the reader saw 0 dashboards against 5, one pseudo-folder against 30,
    # and 1 datasource against 42. A count taken from any of them without these actions is a confident
    # zero, not a gap.
    {"action": "serviceaccounts:read", "scope": "serviceaccounts:*"},
    {"action": "serviceaccounts.permissions:read", "scope": "serviceaccounts:*"},
    {"action": "datasources:read", "scope": "datasources:*"},
    {"action": "datasources.caching:read", "scope": "datasources:*"},
    {"action": "folders:read", "scope": "folders:*"},
    # `dashboards:*` rather than `folders:*`: a dashboard in the General location sits in no folder, so
    # a folder-scoped grant would silently miss it - and a missed dashboard on a compliance check reads
    # as compliant. This is also the action that makes a zero-public-dashboards policy VERIFIABLE:
    # `/api/dashboards/public-dashboards` answers 200 with `totalCount: 0` without it, on stacks that
    # demonstrably serve public dashboards.
    {"action": "dashboards:read", "scope": "dashboards:*"},
    {"action": "snapshots:read"},
    {"action": "teams:read", "scope": "teams:*"},
    {"action": "teams.permissions:read", "scope": "teams:*"},
    {"action": "teams.roles:read", "scope": "teams:*"},
    {"action": "users.roles:read", "scope": "users:*"},
    {"action": "roles:read", "scope": "roles:*"},
    # Alerting inventory. `alert.rules:read` only accepts folder scopes.
    {"action": "alert.rules:read", "scope": "folders:*"},
    {"action": "alert.notifications.receivers:read", "scope": "receivers:*"},
    # Usage insights. Both actions are needed: `read` to resolve the datasource, `query` to use its
    # proxy. The read is covered by the estate-wide grant above; the QUERY stays uid-pinned.
    {"action": "datasources:query", "scope": f"datasources:uid:{USAGE_INSIGHTS_DS_UID}"},
)

# Never granted, and each for a stated reason. A future "we just need one more read" lands here first.
REFUSED_ACTIONS: dict[str, str] = {
    "alert.provisioning.secrets:read": "exports contact points with DECRYPTED secrets",
    "alert.notifications.receivers.secrets:read": "exports contact points with DECRYPTED secrets",
    "secret.securevalues:read": "reads the stack's secure values",
    "users.authtoken:read": "lists a user's live session tokens",
    "settings:read": "reads Grafana configuration including auth settings",
    "support.bundles:read": "support bundles carry configuration and logs",
    "provisioning:write": "this credential is read-only by construction",
    f"{ADAPTIVE_TRACES_PLUGIN}.recommendations:apply": "applies a sampling recommendation",
    f"{ADAPTIVE_TRACES_PLUGIN}.policies:write": "creates or changes sampling policy",
    f"{ADAPTIVE_TRACES_PLUGIN}.policies:delete": "deletes sampling policy",
    f"{ADAPTIVE_TRACES_PLUGIN}.config:write": "changes Adaptive Traces configuration",
}
DESIRED_ACTIONS = frozenset(p["action"] for p in DESIRED_PERMISSIONS)

# **Drift is compared on (action, SCOPE) pairs, not on action names.** Two things make names insufficient,
# and both are live: `plugins.app:access` is declared twice at different plugin scopes, so a role holding
# only the Assistant one would report no drift while Adaptive Logs stayed silently unreachable; and
# Grafana attaches `folders:read` itself at `folders:uid:sharedwithme`, which is a real permission on a
# pseudo-folder and satisfies nothing we declared. A scopeless action is reported by the API as `['']`.
DESIRED_PAIRS = frozenset((p["action"], p.get("scope", "")) for p in DESIRED_PERMISSIONS)
# Permissions this project previously granted and now deliberately removes. All other extra pairs are
# preserved: pruning arbitrary customer-added access is not reconciliation. Adaptive Traces has no
# collector consumer yet, so these two grants are unnecessary standing authority.
RETIRED_PAIRS = frozenset({
    ("plugins.app:access", f"plugins:id:{ADAPTIVE_TRACES_PLUGIN}"),
    (f"{ADAPTIVE_TRACES_PLUGIN}.recommendations:read", ""),
})


def held_pairs(permissions: Mapping[str, Iterable[str]] | Iterable[str]) -> frozenset[tuple[str, str]]:
    """Normalise `/api/access-control/user/permissions` into (action, scope) pairs.

    Accepts a bare iterable of action names too, so a caller that only has names degrades to a
    scope-blind comparison rather than crashing - but it is recorded as such by `pairs_are_scoped`.
    """
    if isinstance(permissions, _MappingABC):
        return frozenset(
            (action, scope or "")
            for action, scopes in permissions.items()
            for scope in (list(scopes) or [""])
        )
    return frozenset((action, "") for action in permissions)


def pairs_are_scoped(permissions: Mapping[str, Iterable[str]] | Iterable[str]) -> bool:
    """Whether the comparison about to happen can actually see scopes."""
    return isinstance(permissions, _MappingABC)

# Everything a per-stack token COULD reach and deliberately does not: dashboards, alert rules, folders,
# teams, org users, plugins, annotations, library elements, snapshots, SLOs, and every datasource other
# than the single usage-insights one named above. All verified reachable with an Admin token. Adding any
# of them is a separate security decision about 273 customer stacks (PLAN 17D)  -  not a convenience edit
# here.


def token_name(slug: str) -> str:
    """Token names collide across the whole ORG, so the slug has to be in the name."""
    return f"{TOKEN_NAME_PREFIX}-{slug}"


def ssm_path(slug: str) -> str:
    return f"{SSM_PREFIX}/{slug}"


# --- Classification -------------------------------------------------------------------------------

PROVISIONABLE = "provisionable"
PAUSED = "not provisionable (paused)"
OPTED_OUT = "opted out"
NO_ASSISTANT = "not provisionable (plugin absent)"


def classify(stack: Mapping[str, Any], opted_out: Iterable[str] = ()) -> str:
    """Why a stack is or is not a provisioning target.

    Opt-out beats paused: a stack the organisation asked us to leave alone should read as our decision to skip it,
    not as an incidental property of the stack.
    """
    slug = str(stack.get("slug"))
    if slug in set(opted_out):
        return OPTED_OUT
    if stack.get("status") != "active":
        # Verified: a paused stack returns 403 on /api/serviceaccounts/search itself.
        return PAUSED
    return PROVISIONABLE


# --- Coverage and repair ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Presence:
    """The three independent facts that together mean "this stack is provisioned".

    `sa_exists` alone is the trap: it stays true forever after a crash that never stored a token.
    """
    sa_exists: bool
    secret_exists: bool
    # None = not probed (because there was no secret to probe with).
    token_status: int | None = None
    basic_role: str | None = None
    role_exists: bool = False
    # `{action: (scope, ...)}` from `/api/access-control/user/permissions`. A bare set of action names
    # is still accepted by `role_drift`, which then compares scope-blind and says so.
    role_actions: Any = field(default_factory=dict)
    assigned: bool = False


CREATE_SA = "create_sa"
MINT_TOKEN = "mint_token"
ENSURE_ROLE = "ensure_role"
ASSIGN_ROLE = "assign_role"
RESET_BASIC_ROLE = "reset_basic_role"
PATCH_ROLE = "patch_role"
OK = "ok"
# A credential that authenticates, against a role that looks correct, and the API still refuses. There is
# no repair to attempt, so it must NOT report as `ok`  -  a stack 403ing on every read while counted as
# provisioned is exactly the confidently-healthy failure this platform refuses everywhere else.
UNEXPLAINED_403 = "unexplained_403"


def role_drift(current, desired: Iterable[tuple[str, str]] = DESIRED_PAIRS) -> bool:
    """True when the role is missing an (action, scope) pair we declared.

    **Subset, not equality, and unordered.** Grafana attaches permissions of its own accord, so
    demanding equality would report drift on every stack for ever and rewrite the whole estate daily.
    Ordered comparison would do the same. Drift is a MISSING declared pair or one of the narrow,
    explicitly named `RETIRED_PAIRS`; arbitrary extras remain untouched.

    **Scope is part of the comparison.** See `DESIRED_PAIRS` - comparing action names alone would call a
    role complete while a declared grant sat at the wrong scope, which is how a wildcard silently becomes
    a pseudo-folder.

    A caller holding only action names gets a scope-blind comparison. That is weaker on purpose rather
    than fatal: `missing_pairs` reports what could not be checked so the weakness is visible.
    """
    held = held_pairs(current)
    return bool(
        missing_pairs(current, desired)
        or (held & RETIRED_PAIRS)
        or dangerous_extra_pairs(current, desired)
    )


def dangerous_extra_pairs(
    current, desired: Iterable[tuple[str, str]] = DESIRED_PAIRS,
) -> frozenset[tuple[str, str]]:
    """Unexpected grants that invalidate the standing reader's read-only blast-radius claim.

    Grafana may attach harmless read permissions, so arbitrary extras are not equality drift. Write-like
    actions, explicitly refused reads, Assistant chat access, and a broadened datasource query are
    different: preserving any of them would make a role with customer write/query reach report healthy.
    """
    held = held_pairs(current)
    wanted = frozenset(desired)
    if not pairs_are_scoped(current):
        # A scope-blind response cannot prove a query action is still uid-pinned. Missing scopes are
        # already visible through `missing_pairs`; avoid inventing scope facts here.
        return frozenset()

    def dangerous(action: str, scope: str) -> bool:
        if (action, scope) in wanted or (action, scope) in RETIRED_PAIRS:
            return False
        if action in REFUSED_ACTIONS or action == "chats:access":
            return True
        if action == "datasources:query":
            return True
        tail = action.rsplit(":", 1)[-1].lower()
        return tail in {"write", "create", "delete", "admin"}

    return frozenset((action, scope) for action, scope in held if dangerous(action, scope))


def missing_pairs(current, desired: Iterable[tuple[str, str]] = DESIRED_PAIRS
                  ) -> frozenset[tuple[str, str]]:
    """Exactly which declared pairs the role does not hold. Empty means complete."""
    held = held_pairs(current)
    if not pairs_are_scoped(current):
        # Names only. Compare names, and say so by returning name-shaped pairs.
        names = {a for a, _s in held}
        return frozenset((a, s) for a, s in desired if a not in names)
    return frozenset(p for p in desired if p not in held)


def needs_repair(p: Presence) -> bool:
    """Phase-1 verdict, from READ-ONLY facts only.

    The run is two-phase on purpose. Phase 1 asks "is this stack fine?" using nothing but a service
    account listing, an SSM read and one call with the stored token  -  **zero gcom writes**, which is the
    whole point of the persistent model. Only a stack that fails here gets a transient Admin identity in
    phase 2, where the role and its assignment can actually be inspected.

    Role facts are deliberately NOT consulted here: without an Admin identity they are unknowable, and
    guessing "the role is missing" would make phase 2 POST a role that already exists  -  which returns 400,
    because role creation is not idempotent.
    """
    if not p.sa_exists or not p.secret_exists:
        return True
    if p.basic_role is not None and p.basic_role != "None":
        return True
    # 200 means the credential works AND carries every declared action. Anything else needs a look.
    return p.token_status != 200 or role_drift(p.role_actions)


def plan_action(p: Presence) -> str:
    """The single next repair for one stack. Ordered by what unblocks the rest.

    Returns one action, not a list: each repair changes what the next probe would see, so the caller
    re-probes rather than executing a stale plan.
    """
    if not p.sa_exists:
        return CREATE_SA
    if not p.role_exists:
        return ENSURE_ROLE
    if role_drift(p.role_actions):
        return PATCH_ROLE
    # A Viewer/Admin basic role would silently break the "provably read-only" property we told the organisation
    # about, so it is corrected before anything that depends on the credential working.
    if p.basic_role is not None and p.basic_role != "None":
        return RESET_BASIC_ROLE
    if not p.assigned:
        return ASSIGN_ROLE
    if not p.secret_exists:
        return MINT_TOKEN
    # 401 = the credential is dead (revoked, or never stored). 403 = the credential is fine and the
    # permissions are not  -  which the role/assignment branches above already handle, so reaching here
    # with a 403 means the role looked right and the API still refused: do NOT re-mint, it would loop.
    if p.token_status == 401:
        return MINT_TOKEN
    if p.token_status == 403:
        return UNEXPLAINED_403
    return OK


def needs_token_mint(p: Presence) -> bool:
    """Whether this repair has to mint a reader token, as opposed to only fixing the role.

    The repair path is monolithic - one Admin identity, then every fix the stack needs - and minting
    used to be unconditional. Token names are unique per ORG, so a mint against a live token falls back
    to a timestamped name and leaves the original live and untracked. Expanding the role across the
    estate would have done that once per stack.

    A credential that answers 200 is working; a role patch does not invalidate it. Only a missing secret
    or a dead one (401) needs a new token. A 403 must never mint: the credential is fine and the
    permissions are not, so minting would loop for ever.
    """
    if not p.secret_exists:
        return True
    return p.token_status == 401


def prune_targets(stored: Iterable[str], inventory: Iterable[str]) -> list[str]:
    """Slugs holding a stored credential that are no longer in the estate.

    An EMPTY inventory returns nothing. A failed inventory call must never be read as "the estate is
    gone" and delete all 273 credentials  -  the same rule `carry.carry_forward` applies to `live_stacks`.
    """
    live = set(inventory)
    if not live:
        return []
    return sorted(set(stored) - live)


# --- Reporting -------------------------------------------------------------------------------------

@dataclass
class Outcome:
    slug: str
    state: str
    action: str = OK
    detail: str = ""
    first_seen_missing: str | None = None


def coverage_metrics(
    outcomes: Sequence[Outcome], now: dt.datetime | None = None
) -> list[tuple[str, dict[str, str], float]]:
    """Bounded gauges only. The per-stack detail belongs in a view, not in labels.

    **The count is not the alert.** A count above zero is normal the moment the organisation creates a stack and
    clears at the next run; what is abnormal is a gap that PERSISTS. So the age of the oldest gap is
    emitted too, and that is what gets the alert rule  -  the same shape as the dead-man's switch and
    carry-forward.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    missing = [o for o in outcomes if o.state == PROVISIONABLE and o.action != OK]
    ages = []
    for o in missing:
        if not o.first_seen_missing:
            continue
        try:
            seen = dt.datetime.fromisoformat(o.first_seen_missing.replace("Z", "+00:00"))
        except ValueError:
            continue
        ages.append((now - seen).total_seconds())
    out = [
        ("gcinsight_stacks_missing_credential", {}, float(len(missing))),
        ("gcinsight_stacks_provisioned", {},
         float(len([o for o in outcomes if o.state == PROVISIONABLE and o.action == OK]))),
    ]
    # Emitted only when something is actually missing. A zero would read as "nothing has been waiting",
    # which is true, but so would a broken run that found nothing at all.
    if ages:
        out.append(("gcinsight_missing_credential_age_seconds", {}, float(max(ages))))
    return out


def coverage_view(outcomes: Sequence[Outcome]) -> list[dict[str, Any]]:
    """The actionable table: which stacks lack a credential, since when, and why."""
    return [
        {
            "Stack": o.slug,
            "State": o.state,
            "Next action": o.action,
            "Detail": o.detail,
            "First seen without credential": o.first_seen_missing or "",
        }
        for o in sorted(outcomes, key=lambda x: (x.state != PROVISIONABLE, x.action == OK, x.slug))
    ]
