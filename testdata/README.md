# testdata

**Every file in here is SYNTHETIC.** It was derived from real scans of a production Grafana Cloud org,
then deterministically anonymised. Nothing in it identifies a real organisation, stack, person or
account, and no figure in it should be quoted as a measurement of anything.

It exists so the test suite and a dashboard build run with **no AWS, no network and no credentials**.
`python3 -m pytest -q` is offline by construction, and `bin/make_local_views.py` composes the full set
of published views from the committed fixture so `bin/dashboards.py --out` works the same way.

## What was changed, and what was not

**Replaced:** every stack slug, every user email, login and display name, every service-account name,
every dashboard and folder name, every URL and hostname, the org id, and the AWS account id.

**Preserved exactly:** analytical values such as series counts, user counts, dashboard counts, ingest
volumes, cardinality figures, latencies and timestamps. The shape of the estate is what the fixtures are
for, so a test that pins a percentile, ratio or "worst stack" ordering still exercises the captured
distribution. Deployment identifiers are not analytical values and are all synthetic.

**Deterministically replaced:** deployment identifiers use reserved namespaces so relationships stay
testable without retaining values from the source estate:

- stack/Grafana/Profile/Fleet ids: `5,000,000-5,999,999`
- metrics and Graphite ids: `6,000,000-6,999,999`
- logs ids: `7,000,000-7,999,999`
- traces ids: `8,000,000-8,999,999`
- Alertmanager ids: `9,000,000-9,999,999`
- k6 ids: `10,000,000-10,999,999`
- local datasource, Grafana-instance and user ids: `20,000-29,999`, `30,000-39,999` and
  `40,000-49,999`; synthetic org id: `900001`

The mapping preserves `id == hpInstanceId == agentManagementInstanceId`, the Graphite/Prometheus
adjacency cases and zero cross-stack collisions. Evidence fixtures reuse those same synthetic ids when
they refer to an inventory object. A source-only id with no inventory match stays in the appropriate
reserved signal namespace without inventing a stack relationship.

**Preserved deliberately, and they look like they should have been scrubbed:**

- **Grafana Cloud region and cluster slugs** (`prod-eu-west-2`, `prod-us-central-0`, the legacy `eu`
  and `us-azure` values). Public product names, and three traps depend on them: the hostname follows
  `clusterSlug` while the tenant follows `regionSlug`, and the legacy values break any code that
  munges one into the other.
- **The `test*` slug prefix.** `estate._is_test_leftover` reads it, so anonymising it away would
  silently disable the leftover-stack finding.
- **The `obs-hub` / `obs-hub-dev` prefix pair.** An unanchored dashboard filter on the shorter slug
  matches the longer one, which is a real defect this fixture reproduces.

## The files

| File | Used by |
|---|---|
| `gcom-instances-<date>.json` | the estate, cost, usage, maturity and risk pillars; most inventory tests |
| `t3-dataplane-<date>.json` | data-plane composition: cardinality, Adaptive, Fleet Management |
| `gcom-instance-users.json` | per-stack user and role fixtures |
| `gcom-instance-datasources.json` | the partial-datasource-listing trap |
| `region-map.json` | `collector/resolver.py`, the host-vs-tenant resolution tests |
| `otlp-floor.json` | the synthetic 2-series OTLP floor, so a `> 0` count is refused |
| `usage-datasource-signals.json` | `grafanacloud-usage` label cardinality, and the instant-vs-window evidence the dashboard tests read |
| `ui-instance-ids.json`, `ui-series-pairs.json` | id-collision and series-pair invariants |
| `views/` | the composed view set, so table panels build with no S3 |

Regenerate the composed views with `python3 bin/make_local_views.py`. The raw scan fixtures are not
regenerable from anything in this repo: they are a captured snapshot, and replacing one means capturing
a new scan against a real org and re-running the anonymiser.

## If you add a fixture

Anonymise it the same way, preserve analytical numerics where the distribution matters, replace every
identifier deterministically inside the reserved namespaces, and say here what it is for and who reads
it. A fixture nothing references is dead weight, and a fixture carrying an unscrubbed identifier is a
leak that ships.
