"""Pillar I - Grafana Assistant adoption, per stack and estate-wide (PLAN 17E).

Reads the `assistant` input gathered by T2 (`collector/sources/assistant.py`) and left-joins it onto the
live inventory, so a stack that appeared this morning gets a row saying `no_credential` and a stack that
left the estate has no row at all. Iterating the payload instead of the inventory would invert both -
that is the golden rule, and it is the shape every pillar here uses.

## What earns a Mimir series, and what does not

The platform's standing rule is that per-stack detail belongs in a **view**; a per-stack *metric* has to
justify itself by needing a trend, an alert or a Grafana time-range interaction. Three do:

- `gcinsight_ai_messages{stack}` - the adoption volume. Exists nowhere else: `grafanacloud-usage`
  carries Assistant *users* and *tokens* per `stack_id`, but no message count.
- `gcinsight_ai_tokens_per_active_user{stack}` - the outlier detector, and the ratio rather than its
  two components because the ratio is the thing worth watching. **Absent where there are no active
  users**, because the ratio is undefined, not zero.
- `gcinsight_ai_machine_share{stack}` - the share of categorised messages arriving from a non-`web`
  surface. This is the human-vs-machine signal and it exists in no other datasource at all.

Per-stack Assistant *users* is deliberately NOT emitted: `grafanacloud-usage` already carries it against
`stack_id`, and the estate rule is that a datasource already on the target stack beats a pipeline.

`category` x `surface` is emitted **estate-wide only, with no `stack` label** - 21 real combinations
today, 64 declared. The per-stack cross product would be 273 x 21 and it is a table, which is exactly
what `ai_category_surface` is.

## Three measured facts a consumer must not paper over

1. **Categorisation covers a minority of traffic.** Estate-wide 2,624 of 8,787 messages (29.9%);
   per-stack median 25%, p10 7%. Every category figure ships with `uncategorised` beside it and nothing
   normalises to total messages.
2. **`hero-stats` and the category frame can disagree in the other direction.** Measured 2026-08-20:
   `stack131` reported 0 messages and 8 categorised, `stack025` 0 and 1. The remainder is
   clamped at zero and the disagreement is surfaced as a column rather than hidden by the clamp.
3. **Every inventory count is TENANT-scoped**, so the columns say "Tenant skills", never "Skills". A
   user-scoped object is invisible to a full Admin and does not even appear in `pagination.total`.

Estate-wide measurements 2026-08-20, for orientation and not as constants: 269 stacks measured, **81 with
any Assistant activity**, **7 with any tenant configuration**, 10 tenant skills, 4 rules, 3 MCP
integrations and **zero automations** across the whole estate. `automation` is the single largest surface
(1,321 categorised messages) ahead of `web` (1,200), almost all of it one stack.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

from collector.coverage import Coverage
from collector import provision as prov
from collector.emit import gapstate
from collector.sources.assistant import (
    INVESTIGATION_INVENTORY_NOT_MEASURABLE, NO_CREDENTIAL,
    USER_SCOPED_NOT_MEASURABLE, WATCHERS_NOT_MEASURABLE, WINDOW_DAYS, split_category,
)

# --- Finding thresholds. Each sits at a measured point in the estate's own distribution ------------

# Messages in the window above which "no tenant configuration at all" is worth telling somebody about.
# The active-stack distribution measured 2026-08-20: p50 13, p75 86, p90 243, p95 369, max 3,096. 100
# sits just above p75 and yields 13 stacks - an actionable list rather than a wall.
ENABLEMENT_MESSAGE_FLOOR = 100

# Tokens per active user above which a stack is an outlier worth explaining. Distribution: p50 1.74M,
# p75 9.27M, p90 24.97M, p95 37.08M, max 96.36M. 25M is p90 and yields 7-10 stacks. Re-derive it if the
# estate's usage grows; a fixed threshold on an absolute token count will drift.
TOKENS_PER_USER_OUTLIER = 25_000_000

# A share of categorised messages above this makes a stack machine-driven rather than human-driven. Only
# 4 stacks clear it today (estate p50 is 0.0), which is what makes it a useful label rather than a
# gradient.
MACHINE_DRIVEN_SHARE = 0.5

# Label enums, declared in emit/budget.py at these ceilings. Observed 2026-08-20: 6 categories
# (Dashboard, Investigate, Learn, Observe, Other, Errors) and 6 surfaces (web, automation, a2a, cli,
# slack, lodestone) in 21 combinations. Both are Assistant's own taxonomy, not anything a tenant authors,
# so they are bounded - but `gcinsight_ai_estate_category_combos` is emitted so drift is visible
# rather than silently expanding the series count.
TENANT_KINDS = ("skills", "rules", "automations", "integrations")
INVESTIGATION_ORIGINS = ("assistant", "user")


# Every tenant object gets the SAME keys, filled with None where the API does not supply them. Infinity
# derives a table's column spec from the FIRST row, so a heterogeneous row set silently drops any column
# the first row happens to lack - and the first row here is a skill, which carries no `enabled` and no
# `authenticationFailed`. Those two are the whole point of the table.
OBJECT_ROW_KEYS = ("kind", "name", "enabled", "scope", "type", "authenticationFailed",
                   "createdBy", "created", "modified")


def _object_row(slug: str, obj: Mapping[str, Any]) -> dict[str, Any]:
    return {" Stack": slug, **{key: obj.get(key) for key in OBJECT_ROW_KEYS}}


# --- Column specs for the views that can legitimately be EMPTY --------------------------------------
#
# Infinity's backend parser 500s on an empty `columns` array, and `build.columns_for` derives that array
# from the view's own first row. So a condition-matched view where finding NOTHING is the good outcome -
# no failed MCP authentication, no disabled objects, every stack provisioned - would fail the dashboard
# BUILD on a healthy estate, and the failure takes down the whole dashboard rather than one panel.
# `build.table_panel(schema=...)` uses these instead when the live view has no rows.
#
# `tests/test_dashboards.py` re-derives the SELECTORS from the live views and fails on drift. It does not
# compare types, because a type is a property of the data rather than of the view: a `ai_tenant_config`
# holding only skills types `enabled` as `string`, since every value is None, and the same column is
# `boolean` once one rule appears. On an empty view no row is parsed, so the declared type is inert.
_STACK_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"), ("Region", "string"), ("Users (active)", "number"),
    ("Measured", "boolean"), ("Why not", "string"), ("Detail", "string"),
    ("Assistant users", "number"), (f"Days active of {WINDOW_DAYS}", "number"),
    ("Messages", "number"), ("Messages categorised", "number"),
    ("Messages uncategorised", "number"), ("Categorised exceeds total", "boolean"),
    ("Machine share of categorised", "number"), ("Tokens", "number"),
    ("Chat tokens", "number"), ("Investigation tokens", "number"),
    ("Tokens per Assistant user", "number"), ("Investigations created", "number"),
    ("Investigations by Assistant", "number"), ("Investigations by user", "number"),
    ("Tenant skills", "number"), ("Tenant rules", "number"),
    ("Tenant automations", "number"), ("Tenant MCP integrations", "number"),
    ("Tenant objects", "number"),
)
_OBJECT_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"), ("kind", "string"), ("name", "string"), ("enabled", "boolean"),
    ("scope", "string"), ("type", "string"), ("authenticationFailed", "boolean"),
    ("createdBy", "string"), ("created", "string"), ("modified", "string"),
)
VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "ai_category_surface": ((" Stack", "string"), ("Category", "string"), ("Surface", "string"),
                            ("Messages", "number"), ("Human driven", "boolean")),
    "ai_tenant_config": _OBJECT_ROW_SCHEMA,
    "ai_mcp_auth_failed": _OBJECT_ROW_SCHEMA,
    "ai_config_disabled": _OBJECT_ROW_SCHEMA,
    "ai_enablement_gap": _STACK_ROW_SCHEMA,
    "ai_token_outliers": _STACK_ROW_SCHEMA,
    "ai_credential_coverage": ((" Stack", "string"), ("State", "string"), ("Actionable", "boolean"),
                               ("Detail", "string"), ("First seen without credential", "string")),
}


def missing_slugs(
    stacks: Sequence[Mapping[str, Any]],
    assistant: Mapping[str, Any] | None,
    opted_out: Sequence[str] = (),
) -> list[str]:
    """Provisionable stacks with no usable Assistant credential. The input to the coverage alert.

    Split out of `build` because the caller has to know the missing set BEFORE composing: the first-seen
    stamps come from `emit/gapstate.py`, which needs the set to merge against, and the pillar then needs
    the merged stamps to emit an age. Pure, so both the state update and the pillar see one definition.

    Paused and opted-out stacks are excluded - they are not gaps. Counting the estate's automated-test
    leftovers as missing would hold the alert on for ever (PLAN 17D).
    """
    if not assistant:
        return []
    out: list[str] = []
    for stack in stacks:
        slug = str(stack.get("slug"))
        record = assistant.get(slug)
        if record and record.get("available"):
            continue
        if prov.classify(stack, opted_out) == prov.PROVISIONABLE:
            out.append(slug)
    return sorted(out)


def _rows_for(stack: Mapping[str, Any], record: Mapping[str, Any] | None) -> dict[str, Any]:
    """One row of the wide per-stack table, whether or not the stack produced data."""
    slug = str(stack.get("slug"))
    base = {
        " Stack": slug,
        "Region": stack.get("regionSlug"),
        "Users (active)": stack.get("currentActiveUsers") or 0,
    }
    if not record or not record.get("available"):
        return {
            **base,
            "Measured": False,
            "Why not": (record or {}).get("reason") or NO_CREDENTIAL,
            "Detail": (record or {}).get("detail") or "",
        }
    return {
        **base,
        "Measured": True,
        "Why not": None,
        "Detail": "",
        "Assistant users": record["active_users"],
        f"Days active of {WINDOW_DAYS}": record["days_active"],
        "Messages": record["messages"],
        "Messages categorised": record["messages_categorised"],
        "Messages uncategorised": record["messages_uncategorised"],
        # A plain bool, not `... or None`. The column type has to be STABLE across every view that
        # carries it: with None for false, a filtered view where nothing disagrees types the column
        # `string` while `ai_assistant` types it `boolean`, and the schema declaration can then only
        # match one of them.
        "Categorised exceeds total": record["categorised_exceeds_total"],
        "Machine share of categorised": record["machine_share_of_categorised"],
        "Tokens": record["tokens"],
        "Chat tokens": record["chat_tokens"],
        "Investigation tokens": record["investigation_tokens"],
        "Tokens per Assistant user": record["tokens_per_active_user"],
        "Investigations created": record["investigations_created"],
        "Investigations by Assistant": record["investigations_by_origin"].get("assistant"),
        "Investigations by user": record["investigations_by_origin"].get("user"),
        "Tenant skills": record["tenant"].get("skills"),
        "Tenant rules": record["tenant"].get("rules"),
        "Tenant automations": record["tenant"].get("automations"),
        "Tenant MCP integrations": record["tenant"].get("integrations"),
        "Tenant objects": record["tenant_objects"],
    }


def build(
    stacks: Sequence[Mapping[str, Any]],
    coverage: Coverage,
    assistant: Mapping[str, Any] | None = None,
    *,
    opted_out: Sequence[str] = (),
    gap_first_seen: Mapping[str, str] | None = None,
    now: dt.datetime | None = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    """`assistant` is the optional T2 payload. Without it this pillar emits and publishes nothing."""
    now = now or dt.datetime.now(dt.timezone.utc)
    metrics: list[tuple[str, dict[str, str], float]] = []
    views: dict[str, list[dict[str, Any]]] = {}
    if not assistant:
        # Nothing at all, not zeros. A tier without this input must not flatten the views a tier that
        # has it published - the whole reason emit/hydrate.py exists.
        return metrics, views

    rows: list[dict[str, Any]] = []
    combos: dict[tuple[str, str], int] = {}
    per_stack_combo: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    missing: list[str] = []

    measured = with_usage = with_config = 0
    est_messages = est_categorised = est_users = est_tokens = 0
    est_investigations = {origin: 0 for origin in INVESTIGATION_ORIGINS}
    est_tenant = {kind: 0 for kind in TENANT_KINDS}

    for stack in stacks:
        slug = str(stack.get("slug"))
        record = assistant.get(slug)
        rows.append(_rows_for(stack, record))
        state = prov.classify(stack, opted_out)

        if not record or not record.get("available"):
            reason = (record or {}).get("reason") or NO_CREDENTIAL
            # A paused or opted-out stack is not a gap. Counting the estate's automated-test leftovers
            # as missing would hold the coverage alert on for ever (PLAN 17D).
            actionable = state == prov.PROVISIONABLE
            if actionable:
                missing.append(slug)
            coverage_rows.append({
                " Stack": slug,
                "State": state if not actionable else f"missing ({reason})",
                "Actionable": actionable,
                "Detail": (record or {}).get("detail") or "",
                "First seen without credential": (gap_first_seen or {}).get(slug, ""),
            })
            continue

        measured += 1
        est_messages += record["messages"]
        est_categorised += record["messages_categorised"]
        est_users += record["active_users"]
        est_tokens += record["tokens"]
        if record["messages"] > 0:
            with_usage += 1
        if record["tenant_objects"] > 0:
            with_config += 1
        for kind in TENANT_KINDS:
            est_tenant[kind] += int(record["tenant"].get(kind) or 0)
        for origin, count in record["investigations_by_origin"].items():
            if origin in est_investigations:
                est_investigations[origin] += int(count)

        metrics.append(("gcinsight_ai_messages", {"stack": slug}, float(record["messages"])))
        # Absent, not zero: with no active user the ratio is undefined, and a 0 would rank a dormant
        # stack as the most efficient in the estate.
        if record["tokens_per_active_user"] is not None:
            metrics.append((
                "gcinsight_ai_tokens_per_active_user", {"stack": slug},
                float(record["tokens_per_active_user"]),
            ))
        # Likewise: nothing categorised means no share exists, not a share of zero.
        if record["machine_share_of_categorised"] is not None:
            metrics.append((
                "gcinsight_ai_machine_share", {"stack": slug},
                float(record["machine_share_of_categorised"]),
            ))

        for name, count in record["categories"].items():
            category, surface = split_category(name)
            combos[(category, surface)] = combos.get((category, surface), 0) + int(count)
            per_stack_combo.append({
                " Stack": slug, "Category": category, "Surface": surface,
                "Messages": int(count),
                "Human driven": surface == "web",
            })
        for obj in record["tenant_objects_detail"]:
            objects.append(_object_row(slug, obj))

    # --- Estate rollups. No `stack` label, so these are cheap and they are what leadership reads. ---
    metrics += [
        ("gcinsight_ai_estate_messages_total", {}, float(est_messages)),
        ("gcinsight_ai_estate_messages_uncategorised", {},
         float(max(0, est_messages - est_categorised))),
        ("gcinsight_ai_estate_users", {}, float(est_users)),
        ("gcinsight_ai_estate_tokens", {}, float(est_tokens)),
        # Series count drift detector: 21 combinations today. A jump means Assistant added a category or
        # a surface, which is worth noticing before it shows up as an unexplained series increase.
        ("gcinsight_ai_estate_category_combos", {}, float(len(combos))),
        ("gcinsight_ai_estate_stacks", {"kind": "measured"}, float(measured)),
        ("gcinsight_ai_estate_stacks", {"kind": "with_usage"}, float(with_usage)),
        ("gcinsight_ai_estate_stacks", {"kind": "with_tenant_config"}, float(with_config)),
    ]
    for (category, surface), count in sorted(combos.items()):
        metrics.append((
            "gcinsight_ai_estate_messages",
            {"category": category, "surface": surface}, float(count),
        ))
    for kind in TENANT_KINDS:
        metrics.append(("gcinsight_ai_estate_tenant_objects", {"kind": kind},
                        float(est_tenant[kind])))
    for origin in INVESTIGATION_ORIGINS:
        metrics.append(("gcinsight_ai_estate_investigations", {"kind": origin},
                        float(est_investigations[origin])))

    # --- Credential coverage. The COUNT is not the alert; the AGE of the oldest gap is (PLAN 17D). ---
    metrics += [
        ("gcinsight_stacks_provisioned", {}, float(measured)),
        ("gcinsight_stacks_missing_credential", {}, float(len(missing))),
    ]
    age = gapstate.oldest_age_seconds(
        {slug: stamp for slug, stamp in (gap_first_seen or {}).items() if slug in set(missing)}, now
    )
    # ABSENT when there is no gap. A zero would be indistinguishable from a gap that started this
    # instant, which is exactly the moment the alert must NOT fire.
    if age is not None:
        metrics.append(("gcinsight_missing_credential_age_seconds", {}, float(age)))

    # --- Views. The finding sources are pre-filtered here, which findings.py prefers to a threshold
    # living in its own table (see its `require`/`at_least` comment). ---
    active = [r for r in rows if r["Measured"]]
    views["ai_assistant"] = sorted(active, key=lambda r: -(r.get("Messages") or 0)) + [
        r for r in rows if not r["Measured"]
    ]
    views["ai_category_surface"] = sorted(
        per_stack_combo, key=lambda r: (-r["Messages"], r[" Stack"])
    )
    views["ai_tenant_config"] = sorted(objects, key=lambda r: (r[" Stack"], r["kind"]))
    views["ai_enablement_gap"] = sorted(
        [r for r in active
         if (r.get("Messages") or 0) >= ENABLEMENT_MESSAGE_FLOOR and not r.get("Tenant objects")],
        key=lambda r: -(r.get("Messages") or 0),
    )
    views["ai_token_outliers"] = sorted(
        [r for r in active
         if (r.get("Tokens per Assistant user") or 0) >= TOKENS_PER_USER_OUTLIER],
        key=lambda r: -(r.get("Tokens per Assistant user") or 0),
    )
    views["ai_mcp_auth_failed"] = [o for o in objects if o.get("authenticationFailed")]
    # Declared so a dashboard can render an empty result rather than failing to build. Derived from the
    # row builders above, and `tests/test_dashboards.py` re-derives it against the live views.
    # `enabled` is absent on skills - the API does not return it - so a missing value is unknown, not
    # disabled. Only an explicit False counts.
    views["ai_config_disabled"] = [o for o in objects if o.get("enabled") is False]
    views["ai_credential_coverage"] = sorted(
        coverage_rows, key=lambda r: (not r["Actionable"], r[" Stack"])
    )
    views["ai_summary"] = _summary(
        measured=measured, with_usage=with_usage, with_config=with_config,
        est_messages=est_messages, est_categorised=est_categorised, est_users=est_users,
        est_tokens=est_tokens, est_tenant=est_tenant, est_investigations=est_investigations,
        combos=len(combos), missing=len(missing), coverage=coverage,
    )
    return metrics, views


def _summary(**f: Any) -> list[dict[str, Any]]:
    """Headline facts, and the three boundaries stated as boundaries rather than as zeros."""
    measured = f["measured"]
    est_messages = f["est_messages"]
    est_categorised = f["est_categorised"]
    return [
        {" Metric": "Stacks with Assistant data measured",
         "Value": f"{measured} of {f['coverage'].scannable} scannable"},
        {" Metric": "Stacks with any Assistant activity",
         "Value": f"{f['with_usage']} ({100 * f['with_usage'] / measured:.0f}%)" if measured else None},
        {" Metric": "Stacks with any tenant Assistant configuration",
         "Value": f"{f['with_config']} ({100 * f['with_config'] / measured:.0f}%)" if measured else None},
        {" Metric": f"Assistant messages ({WINDOW_DAYS}d)", "Value": est_messages},
        {" Metric": "Of which categorised",
         "Value": (f"{est_categorised} ({100 * est_categorised / est_messages:.0f}%) - the rest carry no "
                   f"category, so no category chart may be normalised to total messages")
                  if est_messages else None},
        {" Metric": f"Assistant tokens ({WINDOW_DAYS}d)", "Value": f["est_tokens"]},
        {" Metric": "Assistant active users (sum of per-stack figures)", "Value": f["est_users"]},
        {" Metric": "Tenant skills / rules / automations / MCP integrations",
         "Value": " / ".join(str(f["est_tenant"][k]) for k in TENANT_KINDS)},
        {" Metric": "Investigations created (Assistant / user)",
         "Value": " / ".join(str(f["est_investigations"][o]) for o in INVESTIGATION_ORIGINS)},
        {" Metric": "Category x surface combinations in use", "Value": f["combos"]},
        {" Metric": "Stacks awaiting a credential",
         "Value": f"{f['missing']} - provisioned nightly at 03:35 UTC; see the coverage table"},
        {" Metric": "Watcher agents", "Value": f"NOT MEASURABLE. {WATCHERS_NOT_MEASURABLE}"},
        {" Metric": "Investigation inventory",
         "Value": f"NOT MEASURABLE. {INVESTIGATION_INVENTORY_NOT_MEASURABLE}"},
        {" Metric": "User-scoped skills and rules",
         "Value": f"NOT MEASURABLE. {USER_SCOPED_NOT_MEASURABLE}"},
        {" Metric": "Prompts, transcripts, skill bodies, MCP URLs and headers",
         "Value": "NOT COLLECTED, by design. Aggregates and metadata only (PLAN 17D)."},
    ]
