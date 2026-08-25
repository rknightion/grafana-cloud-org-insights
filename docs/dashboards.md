# Dashboards and alerts

Ten surfaces, published as ordinary Grafana dashboards on the nominated write stack. All of them use `dashboard.grafana.app/v2`.

## The ten surfaces

| Dashboard | Pillar | Answers |
|---|---|---|
| `estate` | A | what stacks exist, their region, status, age, drift, delete protection and who is left over |
| `cost` | B | consumption and its drivers: cardinality outliers and the Adaptive Metrics action queue |
| `usage` | C | consumer behaviour, including datasource query cost attribution |
| `maturity` | D | a composite maturity score, with every dimension's contribution in a table |
| `risk` | E | admin share, plugin version drift, service accounts and tokens, alert routing, org membership, configured public dashboards |
| `value` | F | business value and unit economics, priced where a rate card is supplied |
| `operations` | - | panels only, over `grafanacloud-usage` |
| `commercial` | - | panels only, over `grafanacloud-usage` |
| `ai` | I | Assistant adoption, tenant configuration, token outliers and credential coverage |
| `dashboards` | J | what people actually open, and which datasource types panels actually query |

`operations` and `commercial` need no collector code, no credential and no series at all. `grafanacloud-usage` is a Prometheus datasource already provisioned on every Grafana Cloud stack, so those two are pure panels.

That is the rule worth carrying into any new surface: **if the data is already a datasource on the target stack, a panel beats a pipeline.** It costs no collector calls, no credential lifecycle and no emitted series. The collector is for what no datasource exposes.

## Publishing

The builder needs live views, because Infinity's backend parser needs an explicit column spec and an empty one returns HTTP 500 for the whole panel.

Compose views from the synthetic fixture first:

```bash
python3 bin/make_local_views.py
export GCINSIGHT_VIEWS_DIR=testdata/views
```

For a live build, set `GCINSIGHT_WRITE_STACK_URL`, `GCINSIGHT_WRITE_STACK_ID` and `GCINSIGHT_GRAFANA_TOKEN`. The builder resolves the insights folder by title.

```bash
python3 bin/dashboards.py --publish all
```

Publish one dashboard or `all`, read it back, and verify the v2 query, viz and link envelopes.

A newly implemented view must be published by its owning tier before a table panel references it. Legitimately empty finding views use explicit schemas; a never-published view remains a build failure, which is the point - it separates "this table is correctly empty" from "this table was never wired up".

**That separation is the intent and the implementation does not currently hold it up.** A zero-row view is not written to S3 at all, and the explicit schema has to be threaded to each call site by hand, which not every call site does - so on a small or clean estate a build fails on views that are correctly empty. See *Empty views on a small estate* in the runbook for which dashboards, and why the test suite never caught it.

## Coverage gates

Every published view must be rendered, and every declared metric must be rendered or alerted. Table schemas cover legitimately empty finding views without turning a not-yet-published view into a silent blank panel.

## Alerts

```bash
python3 bin/alerts.py --list
python3 bin/alerts.py --publish
```

**New rules publish paused and unrouted.** Going live is a deliberate step that requires naming a receiver:

```bash
python3 bin/alerts.py --activate --receiver <contact-point-name>
```

Activation refuses an omitted receiver, and the reason is worth stating plainly: the write stack is a real stack whose notification policy may route hundreds of rules that are not yours, some of them to production ticketing. An unpaused rule with no `notification_settings` inherits that policy.

Activate only after every scheduled tier has landed. A plain publish preserves an existing rule's pause and routing state.

Alert identity is the uid, not the title. Use `--migrate-titles --dry-run` before the one-time historical title migration; it edits the live rule body by uid and preserves routing and pause state.

After publishing, verify every expected uid exists exactly once, is in the intended folder and group, and has the expected health, pause state and receiver, with no old-title duplicate.
