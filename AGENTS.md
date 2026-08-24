# grafana-cloud-org-insights

Estate-wide insight for a large Grafana Cloud organisation. `README.md` is the front door and explains
what the thing is; this file is the working agreement for changing it.

## Read before doing anything here

- **`docs/traps.md`** - live-verified API and dashboard behaviour. Read the relevant section before
 writing a panel, a PromQL expression, an Infinity query or a collector source. Most of it is
 behaviour where a wrong call returns HTTP 200 and a wrong answer.
- **`SPEC.md`** - the design: capability model, architecture, correlation traps, security posture.
- **`CAPABILITIES.md`** - what an org-realm token reaches and what it does not, endpoint by endpoint.
- **`RUNBOOK.md`** - operating a deployment. Read before running, rotating, rolling back or tearing
 anything down.
- **`BUDGET.md`** - the declared metric catalogue. Generated from `collector/emit/budget.py`; never
 hand-edited.
- **`terraform/README.md`** - the module and its first-deployment order.

## The golden rule: the estate is DISCOVERED every run, never configured

As stacks are added or removed the data must follow with no code or config change. This outranks
convenience everywhere in this project.

The pattern every collector copies: call `gcom.fetch_inventory` fresh, iterate the live stacks, and
treat any per-stack payload as a **left-join lookup**. A new stack then gets a row on its first scan
with its missing inputs handled honestly, and a removed stack has no row whatever a stale payload still
holds. **Never iterate the payload, and never key a rollup off anything but the live inventory.**

Corollaries, each of which has been a real defect somewhere:

- **Never a literal list of stacks or regions.** Regions come from the live inventory unioned with the
 three control-plane realms. Dashboard stack sets are PromQL. A `$stack` variable comes from Mimir
 label values.
- **Anything that republishes state must re-check the estate.** Carry-forward takes the live stack set
 and drops carried series whose `stack` label has left the org. An **empty** stack set means *unknown*,
 never an estate of zero, so a failed inventory call must not blank every per-stack series.
- **Inventory and provisioning state do not belong in a config store.** That replaces discovery with
 configuration and reintroduces the drift. Per-stack service-account state is itself live-queryable. A
 config store is only for genuine policy: an opt-out list of stacks the org asks you to skip, and
 tunables.
- `emit/budget.py`'s stack count is the one accepted literal. Cardinality *planning* only, and it never
 reaches published output.

## Hard rules

- **Emit natively: Loki push and Mimir remote_write. Never via the OTLP gateway.** Routing your own
 telemetry through the org's gateway inflates their gateway request counts and corrupts the
 protocol-adoption numbers this platform then publishes.
- **The collector's HTTP client refuses any method other than GET.** Read-only by construction, and that
 property is load-bearing in what you can tell an org about what this runs.
- **Metric labels carry bounded dimensions only** - `stack`, `region`, fixed enums. Metric names,
 dashboard uids, user identities and rule names never become labels. Identity-bearing detail may enter
 Loki or S3 only when the deployment explicitly accepts it and enforces minimization, access control,
 encryption and retention for those stores. Cardinality safety never substitutes for that privacy
 decision.
- **Every metric a pillar emits must be declared in `budget.py`'s `CATALOGUE`** or `tests/test_budget.py`
 fails. A per-stack metric costs one series per live stack, multiplied by every bounded enum dimension;
 `collector/emit/budget.py` performs the current calculation. It has to justify itself by needing a time
 series - a trend, an alert, or a Grafana time-range interaction. Anything point-in-time is a view,
 which costs nothing.
- **The series denominator is the write stack, never the org.** Everything lands on one stack, so the
 org figure understates the footprint by roughly the number of stacks in the org.
- **A gap is an absent series, never a zero.** A pillar must not emit a metric it cannot compute: an
 hourly tier writing a structural zero overwrites the real value a slower tier published, and
 carry-forward correctly refuses to rescue a series the live tier claims to own.
- **A view whose inputs are unsatisfied is withheld, never written.** The last good copy stays on the
 bucket with its own older timestamp. Visibly stale beats silently wrong.
- **A limited run cannot publish.** `--limit` and `--stack` compose over a subset, so `run()` refuses to
 write views unless `--dry-run` is also set. Without that guard a two-stack debug run publishes a
 two-row table that reads as a finding about the whole estate.
- **Minting a service account on a stack is a write on a live customer system.** Explicit, idempotent,
 logged, and recorded for teardown - never implicit in a collector.
- **Teardown and reconciliation key on recorded object IDs, never on a name pattern.** A name-matching
 teardown once deleted the provisioning account and orphaned the custom role it was the only identity
 able to remove.
- **Never touch an access policy this project did not create.** An estate contains policies belonging to
 the org's own teams. Surfacing them is the deliverable; changing them is not.
- **Alert rules deploy paused and unrouted, and activation requires an explicit receiver.** The write
 stack is real: its contact points can include production ticketing, and its notification policy may
 route hundreds of rules that are not yours. A rule with `notification_settings` unset inherits that
 policy, so an unpaused rule can raise a real ticket because a scanner was late.
- **`bin/alerts.py --publish` preserves an existing rule's pause state and routing.** A new rule still
 lands paused and unrouted. After any publish, confirm the live state rather than assuming.
- **The per-stack reader stays basic-role-None and query-scoped.** Compare role drift as action/scope
 pairs. `datasources:read` may use `datasources:*`; `datasources:query` must remain pinned to
 `datasources:uid:grafanacloud-usage-insights`.
- **A repair must not re-mint a working credential.** Token names are organisation-wide unique and an
 unnecessary mint can leave an untracked credential while SSM points at the replacement.
- **Adaptive savings require verbose recommendation counts.** Sum positive marginal reductions for
 `add` and `update`; never use the whole active-series count as the saving.
- **Currency is absent when it cannot be priced.** A missing or partially priced rate card must not
 manufacture a zero or label a subtotal as the estate total. Metrics can use `base_rate_only`, which
 explicitly excludes DPM, or `dpm_aware`, which applies the contracted included-DPM divisor per stack.

## Hydration: every tier composes from the FULL input set

`collector/emit/hydrate.py`. A tier hydrates the inputs it lacks from `scans/<tier>/latest.json`, so
every run publishes a complete view set rather than flattening views only a slower tier can compute.

- `INPUT_OWNER` says which tier gathers each input. Inventory is never hydrated: a tier with no
 inventory has nothing to compose.
- **A tier never hydrates its OWN input from its own last scan.** That would make a broken gatherer look
 healthy indefinitely.
- **`VIEW_INPUTS` is DERIVED, not hand-written.** It is produced by composing every subset of the
 optional inputs against the synthetic compose fixture and recording the minimal subset that reproduces
 the full output
 byte for byte. A test re-derives it and fails on drift. Hand-editing that table reintroduces the exact
 defect it exists to prevent: a pillar gains a dependency, the table does not, and the view is
 published as zeros by a tier that cannot compute it.
- `MAX_INPUT_AGE` is deliberately the same constant as the carry-forward maximum age. One staleness
 story. Two constants that can drift apart would mean a view withheld while its metric is still
 carried, or the reverse.
- Per-input provenance rides in every view's `meta.inputs` and in the input-age metrics. The dashboards
 read the age of the INPUT, not of the run: they differ by hours, and the input age is what governs how
 current a figure is.

## Dashboards

`collector/dashboards/build.py` is the panel library, `bin/dashboards.py` the ten dashboard
definitions. `build.DASHBOARDS` is the registry; a new dashboard must be added there AND to `BUILDERS`
AND to `PILLAR_OF` or it loses its cross-links or fails to build.

`operations` and `commercial` read `grafanacloud-usage` only - panels, no collector code, no credential,
zero series. `ai` mixes both sources and its banner says so, because neither standard banner is true
there. `dashboards` is Pillar J and reads each stack's own usage-insights datasource with that stack's
reader token and mandatory `instance_id` guard.

Everything else about authoring a panel is in `docs/traps.md`, and the traps there are the difference
between a working page and one that renders "plugin not found".

## Testing

The suite runs with no AWS credentials, no network and no live estate:

```bash
python3 -m pytest tests -q
```

`testdata/` is a synthetic estate and `tests/fixtures/` a synthetic scan. Read `testdata/README.md`
before treating any number in either as a measurement.

Proportionate testing, per the usual bar: logic that can be wrong gets a test first, and declarative
config gets validated rather than unit-tested. Two kinds of test here earn their keep more than usual,
because both catch a class of bug that looks like working code:

- **Contract tests that read a real artifact back.** A test written from the implementation cannot catch
 the implementation being wrong about an external contract.
- **Tests that re-derive a declared table from live data** rather than asserting the table's contents.
 `VIEW_INPUTS` and the empty-view schemas are both in this category.
- **Coverage gates over assembled dashboards.** Every published view is rendered and every declared
 metric is rendered or alerted. Exemptions need an explicit reason.
- **Fixture hygiene is a security boundary.** Live compose exports go to a separate path and are
 anonymised before use; the exporter refuses to overwrite the committed fixture.

## Conventions

- `AGENTS.md` is the canonical working agreement. `CLAUDE.md` is only the `@AGENTS.md` import stub;
 never maintain a second copy that can drift.
- Always-loaded files contain current operating facts only. Put dates, changelogs and superseded
 behavior in Backlog documents. Where a wrong belief is genuinely seductive, one clause is enough.
- No measured figures in prose that is always on screen. Name the command that fetches it live.
