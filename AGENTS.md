# grafana-cloud-org-insights

Estate-wide insight for a large Grafana Cloud organisation.

## The golden rule: the estate is DISCOVERED every run, never configured

As stacks are added or removed the data must follow with no code or config change. This outranks
convenience everywhere in this project.

The pattern every collector copies: call `gcom.fetch_inventory` fresh, iterate the live stacks, and
treat any per-stack payload as a left-join lookup. Never iterate the payload, and never key a rollup
off anything but the live inventory.

- Never a literal list of stacks or regions. Regions come from the live inventory unioned with the
  three control-plane realms in `gcom.POLICY_REALMS` (`us` holds this project's own reader and is not
  any stack's `regionSlug`, so it can never be derived). Dashboard stack sets are PromQL; a `$stack`
  variable comes from Mimir label values.
- Anything that republishes state re-checks the estate. Carry-forward takes the live stack set and
  drops carried series whose `stack` label has left the org. An empty stack set means unknown, never
  an estate of zero, so a failed inventory call must not blank every per-stack series.
- Inventory and provisioning state do not belong in a config store; per-stack service-account state is
  itself live-queryable. A config store is only for genuine policy: an opt-out list of stacks the org
  asks you to skip, and tunables.
- `collector/emit/budget.py`'s `STACK` constant is the one accepted literal. Cardinality planning
  only, and it never reaches published output.

## Hard rules

- Emit natively: Loki push and Mimir remote_write, never via the OTLP gateway. Routing our own
  telemetry through the org's gateway inflates their gateway request counts and corrupts the
  protocol-adoption numbers this platform then publishes.
- `collector/httpclient.py` refuses any method other than GET. Read-only by construction, and that
  property is load-bearing in what you can tell an org about what this runs.
- Metric labels carry bounded dimensions only: `stack`, `region`, fixed enums. Metric names, dashboard
  uids, user identities and rule names never become labels. Identity-bearing detail may enter Loki or
  S3 only when the deployment explicitly accepts it and enforces minimization, access control,
  encryption and retention for those stores. Cardinality safety is not that privacy decision.
- Every metric a pillar emits is declared in `budget.py`'s `CATALOGUE`, or `tests/test_budget.py`
  fails. A per-stack metric costs one series per live stack multiplied by every bounded enum
  dimension, so it has to justify itself by needing a time series: a trend, an alert, or a Grafana
  time-range interaction. Anything point-in-time is a view, which costs nothing.
- The series denominator is the write stack, never the org. Everything lands on one stack, so the org
  figure understates the footprint by roughly the number of stacks in the org.
- A gap is an absent series, never a zero. A pillar must not emit a metric it cannot compute: an
  hourly tier writing a structural zero overwrites the real value a slower tier published, and
  carry-forward correctly refuses to rescue a series the live tier claims to own.
- A view whose inputs are unsatisfied is withheld, never written. The last good copy stays on the
  bucket with its own older timestamp. Visibly stale beats silently wrong.
- A limited run cannot publish. `--limit` and `--stack` compose estate rollups over a subset, so
  `scan.py` refuses every S3, Mimir and Loki write unless `--dry-run` is also set. Without that guard
  a two-stack debug run publishes a two-row table that reads as a finding about the whole estate.
- Minting a service account on a stack is a write on a live customer system. Explicit, idempotent,
  logged, and recorded for teardown, never implicit in a collector.
- Teardown and reconciliation key on recorded object IDs, never on a name pattern. A name-matching
  teardown deleted the provisioning account and orphaned the custom role it was the only identity able
  to remove.
- Never touch an access policy this project did not create. Surfacing the org's own teams' policies is
  the deliverable; changing them is not.
- Alert rules deploy paused and unrouted, and activation requires an explicit receiver. The write
  stack's contact points can include production ticketing, and a rule with `notification_settings`
  unset inherits its notification policy, so an unpaused rule can raise a real ticket because a
  scanner was late. `bin/alerts.py --publish` preserves an existing rule's pause state and routing and
  a new rule still lands paused and unrouted; confirm live state after any publish.
- The per-stack reader stays basic-role-None and query-scoped. Compare role drift as action/scope
  pairs. `datasources:read` may use `datasources:*`; `datasources:query` stays pinned to
  `datasources:uid:grafanacloud-usage-insights`.
- A repair must not re-mint a working credential. Token names are organisation-wide unique, so an
  unnecessary mint can leave an untracked credential while SSM points at the replacement.
- Adaptive savings require verbose recommendation counts. Sum positive marginal reductions for `add`
  and `update`; never use the whole active-series count as the saving.
- Currency is absent when it cannot be priced. A missing or partially priced rate card must not
  manufacture a zero or label a subtotal as the estate total. Metrics use `base_rate_only`, which
  explicitly excludes DPM, or `dpm_aware`, which applies the contracted included-DPM divisor per
  stack.

## Hydration: every tier composes from the FULL input set

`collector/emit/hydrate.py`. A tier hydrates the inputs it lacks from `scans/<tier>/latest.json`, so
every run publishes a complete view set rather than flattening views only a slower tier can compute.

- `INPUT_OWNER` says which tier gathers each input. Inventory is never hydrated: a tier with no
  inventory has nothing to compose.
- A tier never hydrates its own input from its own last scan. That would make a broken gatherer look
  healthy indefinitely.
- `VIEW_INPUTS` is derived, not hand-written: composing every subset of the optional inputs against
  the synthetic compose fixture and recording the minimal subset that reproduces the full output byte
  for byte. A test re-derives it and fails on drift. Hand-editing the table reintroduces the exact
  defect it exists to prevent, where a pillar gains a dependency, the table does not, and a tier that
  cannot compute the view publishes it as zeros.
- `MAX_INPUT_AGE` is deliberately the same constant as `carry.MAX_CARRY_AGE`. One staleness story.
  Two constants that can drift apart would mean a view withheld while its metric is still carried, or
  the reverse.
- Per-input provenance rides in every view's `meta.inputs` and in the input-age metrics. The
  dashboards read the age of the INPUT, not of the run: they differ by hours, and the input age is
  what governs how current a figure is.

## Dashboards

`collector/dashboards/build.py` is the panel library and holds the `DASHBOARDS` registry;
`bin/dashboards.py` holds the per-dashboard definitions plus `BUILDERS` and `PILLAR_OF`. A new
dashboard must be added to all three or it loses its cross-links or fails to build.

`operations` and `commercial` read `grafanacloud-usage` only: panels, no collector code, no
credential, zero series. `ai` mixes both sources and its banner says so, because neither standard
banner is true there. `dashboards` (Pillar J) reads each stack's own `grafanacloud-usage-insights`
datasource with that stack's reader token and the mandatory `instance_id` guard in
`collector/sources/usage_insights.py`; a selector without that filter silently attributes another
stack's logs.

## Task interface

`just check` is the gate and is exactly what CI enforces. The suite runs with no AWS credentials, no
network and no live estate, so run and rerun it freely.

`just publish-image` is `[confirm]`-gated and pushes a real image to the configured ECR repository.
Never pass `--yes` or `JUST_YES=1` to get past that gate.

`testdata/` is a synthetic estate and `tests/fixtures/` a synthetic scan. Read `testdata/README.md`
before treating any number in either as a measurement.

Four kinds of test here earn their keep beyond the usual proportionality bar, because each catches a
class of bug that looks like working code:

- Contract tests that read a real artifact back. A test written from the implementation cannot catch
  the implementation being wrong about an external contract.
- Tests that re-derive a declared table from live data rather than asserting the table's contents.
  `VIEW_INPUTS` and the empty-view schemas are both in this category.
- Coverage gates over assembled dashboards: every published view is rendered and every declared metric
  is rendered or alerted. Exemptions need an explicit reason.
- Fixture hygiene as a security boundary. Live compose exports go to a separate path and are
  anonymised before use; the exporter refuses to overwrite the committed fixture.

## Deeper references

- `docs/traps.md` - read before writing a panel, a PromQL expression, an Infinity query or a collector
  source. Live-verified behaviour, mostly cases where a wrong call returns HTTP 200 and a wrong answer.
- `SPEC.md` - capability model, architecture, correlation traps, security posture.
- `CAPABILITIES.md` - what an org-realm token reaches and what it does not, endpoint by endpoint.
- `RUNBOOK.md` - read before running, rotating, rolling back or tearing down a deployment.
- `BUDGET.md` - the declared metric catalogue, generated from `collector/emit/budget.py`; never
  hand-edited.
- `terraform/README.md` - read before changing the module or ordering a first deployment.
