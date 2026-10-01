# Getting started

The quickest useful live diagnostic is a dry-run T1 scan against your own org. It makes read-only
source calls, prints a bounded completion record, and publishes nothing. Dry-run does not mean
offline: hydration and rate-card reads can require S3 access. Start with the synthetic dashboard
build below if no live reads have been authorised.

## What the first run tells you

The dry run discovers the live stack inventory. Once all tiers and their inputs have published,
[eleven dashboards](dashboards.md) separate configured state, signal production and recorded human
activity. A dry-run inventory alone does not measure use. Usage insights sees dashboard opens and
panel requests over a rolling window; it cannot see a non-dashboard page visit without a request or identify
individual apps inside the `scenes` bucket. Check each dashboard's population and input age before
using its numbers.

## Requirements

- Python 3.14 (the CI and container version) or a container runtime. The collector is stdlib-only - no third-party runtime dependencies.
- A Grafana Cloud access policy token with the **org realm** and the read scopes in `collector.config.READER_SCOPES`. [Credentials and permissions](credentials.md) lists them and what each one reaches.
- Your numeric org id.
- Even for a dry run: one nominated write stack and its Mimir and Loki endpoints and tenant ids.
- An S3 bucket and AWS read access for S3-backed inputs. Publishing is allowed only through a verified
  deployed ECS task definition, not a local process.

## A dry-run scan

Nothing here has a default. A default org id or tenant would be one deployment's identifiers baked into everyone else's collector, and the failure mode is silent rather than loud: the scan authenticates, succeeds, and writes a plausible set of series into somebody else's tenant.

```bash
export GCINSIGHT_READ_TOKEN=...   # access policy token, org realm
export GCINSIGHT_ORG_ID=...       # the org to scan
export GCINSIGHT_WRITE_STACK=...
export GCINSIGHT_MIMIR_URL=...
export GCINSIGHT_MIMIR_TENANT=...
export GCINSIGHT_LOKI_URL=...
export GCINSIGHT_LOKI_TENANT=...
export GCINSIGHT_S3_BUCKET=...

./scan.py --tier t1 --dry-run     # inventory, org identities and Fleet; no publication
```

## Other local diagnostics

```bash
export GCINSIGHT_WRITE_STACK=...        # the ONE stack results are published to
export GCINSIGHT_MIMIR_URL=...          # https://prometheus-prod-NN-<region>.grafana.net
export GCINSIGHT_MIMIR_TENANT=...       # the write stack's hmInstancePromId
export GCINSIGHT_LOKI_URL=...           # https://logs-prod-NNN.grafana.net
export GCINSIGHT_LOKI_TENANT=...        # the write stack's hlInstanceId
export GCINSIGHT_S3_BUCKET=...
export GCINSIGHT_STACK_TOKEN_PREFIX=/gcinsight/stack-token   # per-stack reader tokens in SSM

./scan.py --tier t2 --limit 6 --dry-run # bounded diagnostic; publishing a subset is refused
./scan.py --tier t3 --dry-run
./scan.py --tier t4 --dry-run           # diff gathers from S3, not Grafana source APIs
./scan.py --tier t2 --stack <slug> --dry-run # one-stack diagnostic
```

`GCINSIGHT_WRITE_TOKEN` publishes, and falls back to the read token when unset, so a single-credential interactive run works. A real deployment sets both, and the write token's realm should be the write stack alone.

Production and manual publishing use deployed ECS task definitions; see
[Running scans](operations.md). Do not remove `--dry-run` from a local command to publish.

The opt-in provisioner (daily by module default) uses a third org-realm token carrying only `stacks:read` and `stack-service-accounts:write`. The collector never receives it. Deployment cadence overrides may differ; see the
[operator timetable](https://github.com/rknightion/grafana-cloud-org-insights/blob/main/RUNBOOK.md#scheduled-jobs)
for module-default times and UTC timezone.

A run limited with `--stack` or `--limit` cannot publish. That is deliberate: a partial sweep published as a full one looks like an estate that shrank.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | fine |
| `1` | primary stack coverage or an independently gathered owner input is below the publication floor |
| `2` | configuration, unsafe publication or lock-backend failure |
| `3` | the scan gathered everything but could not publish |
| `4` | lock collision - another scan holds the lock |

All `collector.config` configuration errors, including missing credentials, missing deployment
identifiers and invalid policy values, produce one stderr diagnostic and exit `2` before source,
metadata or publication calls. Unexpected exceptions are not configuration refusals: they retain
their traceback and non-`2` exit.

`3` is separate on purpose. "The estate is unreachable" and "we cannot write to the target stack" need different responses. `4` is not a failed scan; see [Running scans](operations.md).

## Build the dashboards without deploying anything

The dashboard builder needs published views, because Infinity's backend parser needs an explicit column spec - an empty one returns HTTP 500 for the whole panel. It reads views from S3, or from a local directory. Composing them from the committed synthetic fixture is the quickest way to see what a dashboard looks like before anything is provisioned.

```bash
./bin/make_local_views.py --out /tmp/gcinsight-views # keep generated views outside tracked files
export GCINSIGHT_VIEWS_DIR=/tmp/gcinsight-views
export GCINSIGHT_S3_BUCKET=gcinsight-test-bucket # synthetic URL placeholder only
python3 bin/dashboards.py --out /tmp/gcinsight-dashboards --ds-uid fixture-infinity
```

That local path is also how the test suite runs. It writes JSON offline; it does not render a Grafana
page. Do not publish the placeholder build. Live publication is a separate authorised write using
real published views, a configured Infinity datasource, `GCINSIGHT_WRITE_STACK_URL`,
`GCINSIGHT_WRITE_STACK_ID` and a short-lived `GCINSIGHT_GRAFANA_TOKEN`.

## Tests

```bash
just setup
just check
```

No AWS credentials, no network, no live estate. `testdata/` holds a synthetic estate and `tests/fixtures/` a synthetic scan.

## Next

- [Architecture](architecture.md) - how the tiers compose, and why a missing input withholds output rather than publishing zero.
- [Configuration](configuration.md) - runtime variables, consumer identity, the optional rate card, and the optional Firehose log path.
- [Deployment](deployment.md) - Terraform, the signed image, and digest pinning.
