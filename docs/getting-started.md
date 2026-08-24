# Getting started

The quickest useful thing is a dry-run inventory scan against your own org. It makes read-only calls, prints what it found, and writes nothing anywhere.

## Requirements

- Python 3.13 or a container runtime. The collector is stdlib-only - no third-party runtime dependencies.
- A Grafana Cloud access policy token with the **org realm** and the read scopes in `collector.config.READER_SCOPES`. [Credentials and permissions](credentials.md) lists them and what each one reaches.
- Your numeric org id.
- For anything beyond a dry run: one nominated write stack, its Mimir and Loki endpoints and tenant ids, and an S3 bucket.

## A dry-run scan

Nothing here has a default. A default org id or tenant would be one deployment's identifiers baked into everyone else's collector, and the failure mode is silent rather than loud: the scan authenticates, succeeds, and writes a plausible set of series into somebody else's tenant.

```bash
export GCINSIGHT_READ_TOKEN=...   # access policy token, org realm
export GCINSIGHT_ORG_ID=...       # the org to scan

./scan.py --tier t1 --dry-run     # inventory only; prints the meta block, writes nothing
```

## A publishing scan

```bash
export GCINSIGHT_WRITE_STACK=...        # the ONE stack results are published to
export GCINSIGHT_MIMIR_URL=...          # https://prometheus-prod-NN-<region>.grafana.net
export GCINSIGHT_MIMIR_TENANT=...       # the write stack's hmInstancePromId
export GCINSIGHT_LOKI_URL=...           # https://logs-prod-NNN.grafana.net
export GCINSIGHT_LOKI_TENANT=...        # the write stack's hlInstanceId
export GCINSIGHT_S3_BUCKET=...
export GCINSIGHT_STACK_TOKEN_PREFIX=/gcinsight/stack-token   # per-stack reader tokens in SSM

./scan.py --tier t1
./scan.py --tier t2 --limit 6           # a subset, for development
./scan.py --tier t3
./scan.py --tier t4                     # reads S3 only, makes no API calls
./scan.py --tier t2 --stack <slug>      # one stack, for debugging
```

`GCINSIGHT_WRITE_TOKEN` publishes, and falls back to the read token when unset, so a single-credential interactive run works. A real deployment sets both, and the write token's realm should be the write stack alone.

The daily provisioner uses a third org-realm token carrying only `stacks:read` and `stack-service-accounts:write`. The collector never receives it.

A run limited with `--stack` or `--limit` cannot publish. That is deliberate: a partial sweep published as a full one looks like an estate that shrank.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | fine |
| `1` | more than 10% of scannable stacks failed |
| `2` | configuration |
| `3` | the scan gathered everything but could not publish |
| `4` | lock collision - another scan holds the lock |

`3` is separate on purpose. "The estate is unreachable" and "we cannot write to the target stack" need different responses. `4` is not a failed scan; see [Running scans](operations.md).

## Build the dashboards without deploying anything

The dashboard builder needs published views, because Infinity's backend parser needs an explicit column spec - an empty one returns HTTP 500 for the whole panel. It reads views from S3, or from a local directory. Composing them from the committed synthetic fixture is the quickest way to see what a dashboard looks like before anything is provisioned.

```bash
./bin/make_local_views.py                    # compose views from the committed fixture
export GCINSIGHT_VIEWS_DIR=testdata/views
export GCINSIGHT_WRITE_STACK_URL=https://<slug>.grafana.net
export GCINSIGHT_WRITE_STACK_ID=<numeric-stack-id>
export GCINSIGHT_GRAFANA_TOKEN=<short-lived-build-token>
python3 bin/dashboards.py --publish all
```

That local path is also how the test suite runs.

## Tests

```bash
python3 -m pytest tests -q
```

No AWS credentials, no network, no live estate. `testdata/` holds a synthetic estate and `tests/fixtures/` a synthetic scan.

## Next

- [Architecture](architecture.md) - how the tiers compose, and why a missing input withholds output rather than publishing zero.
- [Configuration](configuration.md) - every environment variable, the optional rate card, and the optional Firehose log path.
- [Deployment](deployment.md) - Terraform, the signed image, and digest pinning.
