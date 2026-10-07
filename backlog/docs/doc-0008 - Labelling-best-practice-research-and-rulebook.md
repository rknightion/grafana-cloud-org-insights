---
id: doc-0008
title: Labelling best-practice research and rulebook
type: specification
created_date: '2026-10-06 14:43'
updated_date: '2026-10-07 02:36'
---
# Labelling best-practice research and rulebook

Researched 2026-10-06 for the labelling best-practice pillar. Owner decisions D-LBL1 to D-LBL11 and the task plan are in Part 1. Quotes marked as obtained via page summaries must be re-verified (record URL and date) before any rule ships with provenance published.

# Part 1: Assessment, decisions and plan

- Context: /private/tmp/claude-503/-Users-rob-repos-grafana-cloud-org-insights/bbe8de11-8e49-4ace-92ce-67dc9d2c5e84/scratchpad/labelling-synthesis.md
- Lane briefs: research-traces.md and research-psguides.md, same directory. Task A copies them into a backlog doc because the scratchpad is temporary.
- v1 failed adversarial review. Every finding is addressed below.
- No customer name appears anywhere in this repository: `check-identifiers --history` gates it, and doc-0002:14 places customer identifiers in the deployment repo.

## Owner decisions (2026-10-06)

- **D-LBL1 Retention.**
  - `label_inventory` may persist the following in S3 views and the private `label_inventory` hydration input only:
    - label and attribute NAMES;
    - distinct-value counts (`exact` or `at_least`);
    - closed non-PII value-shape class counts (uuid, hex_id, epoch, url_with_id, long_value);
    - series and stream counts.
  - These items never go to Loki, finding events, metric labels, stdout, `--out` or errors.
  - A name over 512 bytes, or one matching a `pii` key or value class, persists only as a class and a count.
  - Raw values are transient and never written. The GCI-0018 raw-value exception is not widened.
- **D-LBL2 Deterministic only.** No LLM in the scanner or operator tooling. Judgement rules are catalogued and excluded from applicable weight.
- **D-LBL3 Layered, tunable thresholds.**
  - Published limits are hard rules.
  - The Professional Services bands are the defaults: metrics warn at 100, high at 1,000, critical at 10,000; Loki dynamic labels warn at 100+.
  - Everything else is policy.
  - Each threshold carries a provenance tag (`published`, `ps` or `policy`) and a source URL, and is overridable through the tunables.
- **D-LBL4 Presentation.**
  - Per stack and signal: findings by severity, rules evaluated vs passed, a 0-100 score, and the coverage figure.
  - The score is computed only at coverage of 0.8 or more; otherwise it is absent.
- **D-LBL5 Maturity.** The labelling score replaces `cardinality_discipline`. This waits for the dev proof.
- **D-LBL6 Routes.** Staff witnesses are approved for:
  - Mimir `cardinality/label_values` and `label_names` (limit/selector);
  - Loki `/series`, `index/stats` and `index/volume`;
  - Loki applied limits/OTLP config;
  - Tempo intrinsic `name` values and Tempo overrides.

  Each route is implemented only after its witness. A parked route's rules are excluded from applicable weight.
- **D-LBL7 Customer grant.** The customer deployment may enable `label-inventory` once it ships in a release and the task K dev proof is recorded. No further owner decision is needed. Routes without a passing witness are not covered. Every reader-role, route, privacy and publication rule is preserved.
- **D-LBL8 Fairness.**
  - Cardinality bands apply only to metrics and streams above a size floor (tunable, same pattern as `CARDINALITY_MIN_SERIES`).
  - A static-infrastructure allowlist (host, cluster, namespace, node and similar) has its own higher band.
- **D-LBL9 PII shapes.** Email, ip, phone, jwt and card shapes stay on label_risk's retention-governed path. The labelling register refers to `risk_label_hygiene` and does not duplicate them.
- **D-LBL10 Witness stacks.** Witnesses may query all five staff stacks and choose or combine evidence. Each recorded witness names the stack slug.
- **D-LBL11 Pre-approved read scopes.** When a witness shows the org reader lacks a READ scope for an approved route, the witness task may add that read-only scope to this project's own access policy.
  - The addition is recorded with its object ID, and CAPABILITIES.md is updated.
  - Write or admin scopes, other policies and the per-stack reader role are never covered.
  - A new scope can 401 for about 46 minutes; wait it out, never re-mint.

## Hard-rule amendments (land in task A, before B, C and D start)

- **(a) Pyroscope POST exception (AGENTS.md, GCI-0018 section)**, reworded so that:
  - `label_risk.py` and `label_inventory.py` may POST only the two exact Pyroscope read RPCs;
  - they do so only through `label_risk.profile_read`, which keeps the exact path set, the inventory HTTPS host, no redirects and the bounded body and response;
  - no other module, path or helper is granted, and `collector/httpclient.py` stays GET-only.
- **(b) Identity-bearing detail bullet.** Append the D-LBL1 text.
- **(c) doc-0002:45.** "calls label endpoints only" becomes:

  > calls Loki label-name and label-value, `/series`, `index/stats`, `index/volume` and limits/config endpoints only, never `query`, `query_range`, `tail` or any route returning log lines; each requires a recorded staff witness.
- **(d) New AGENTS.md section "Labelling inventory (D-LBL1..11)".** It lists each route by exact path with its witness-first rule, the D-LBL7 grant and the D-LBL11 scope rule.
- **Not amended:**
  - `MAX_PER_STACK_FANOUT` and the one-extra-label rule;
  - gap-is-absent;
  - the limited-run guard;
  - own-input hydration;
  - derived `VIEW_INPUTS`.

## Frozen contracts (task B)

- **Result enum:** `pass | fail | not_evaluated | not_applicable`. The reason is a closed enum: `missing_input`, `route_parked`, `truncated`, `deadline`, `no_signal_data`, `precondition_false`.
- **Unit:** one result per (rule, stack, signal). The evidence holds closed enums and numbers only: count of offending labels, worst band, `at_least` flag. Names go only in register rows.
- **Truncation:**
  - `at_least N` at or above a band is a fail at that band.
  - `at_least N` below the band is `not_evaluated(truncated)`.
  - A values-read byte-cap overflow is `fail(overflow)` at no less than the warn band.
  - A truncated name list makes every absence rule ("no X present") `not_evaluated(truncated)`.
- **Applicability:**
  - `not_applicable` covers a signal with no data (a measured-empty 200) and a false precondition.
  - Cross-signal rules need data on both signals.
  - Applicable weight excludes judgement rules and parked or unapproved routes. It includes `not_evaluated` results caused by `missing_input`, `truncated` and `deadline`.
- **Severity:** findings are `low | medium | high`, with weights 1 / 3 / 5. Band mapping: the PS warn band is medium; the high and critical bands are high, with critical recorded as the worst band in evidence. That makes the metric's severity enum 3.
- **Score:** `100 * passed_weight / evaluated_weight`, published only when `evaluated_weight / applicable_weight >= 0.8`.
- **Catalogue version:** `catalogue_version` is stamped in every view and in an estate-level gauge. Scores are comparable only within one version. Each later route-extension (E) task bumps it.
- **Rule-input registry:** extensible by E tasks without reopening the seam.

## Metrics (budget-shape compliant)

| Metric | Series per stack |
|---|---|
| `gcinsight_labelling_findings{stack,severity}` | 3 |
| `gcinsight_labelling_score{stack,signal}` | 4 |
| `gcinsight_labelling_rules_evaluated{stack,signal}` | 4 |
| `gcinsight_labelling_rules_passed{stack,signal}` | 4 |
| `gcinsight_labelling_catalogue_version` | estate-level, 1 in total |
| Provenance series for the new input | 8 |

- Signals are the 4 data signals; cross-signal results are views only.
- That is 15 series per stack, about 4,065 at `STACK=271`, plus the provenance series. `INPUT` goes from 29 to 30, as re-derived by the test.
- A per-severity count is emitted only when that severity's rules reached the coverage floor. Otherwise the series is absent.

## Tasks (parent + subtasks; IDs assigned at creation; no customer name in any text)

**P - Labelling best-practice pillar (parent).** Links the decisions, the research doc and the order. AC: all subtasks Done, or Parked with a reason.

**A - Record the labelling decisions and amendments.** First; blocks everything else.
- AC1: amendments (a) to (d) are landed in AGENTS.md and doc-0002, word for word.
- AC2: D-LBL1..11 are recorded in doc-0002 standing decisions, with D-LBL7 and D-LBL11 as conditional grants.
- AC3: a backlog doc "Labelling best-practice research and rulebook" holds:
  - the merged rulebook;
  - the deprecated-semconv table pinned to v1.44.0;
  - the Professional Services label-analyser bands;
  - every source URL.

  Quotes obtained through a summary are marked for re-verification, with a verification date column.
- AC4: GCI-0101 gets an appended note: D-LBL6 covers its route for labelling purposes, and its top-producers dimension stays open.
- AC5: `just check` passes, `check-identifiers` included.

**B - Rule catalogue and evaluator seam.** After A.
- `collector/label_rules.json` (versioned) plus a loader with schema validation.
- A pure `evaluate()` implementing the frozen contracts above.
- AC: tests for each truncation, overflow, `not_applicable` and coverage-floor case, plus a test that a rule with missing input can never pass. The schema test also rejects a non-enum evidence string.

**C1-C4 - Staff route witnesses.** After A; run in parallel, each read-only against all five staff stacks (D-LBL10).
- C1 Mimir cardinality `label_names?limit=500` with a selector, and `label_values` with `label_names[]`. Record the head-only window and the limit behaviour.
- C2 Loki `/series` over a bounded window, plus `index/stats` and `index/volume`. Record shapes and reachability. Check that no log lines come back and that `/series` stays within its bounds.
- C3 Loki applied limits: compare JSON `config/limits/applied` with the existing `/config/tenant/v1/limits`, and choose the one that needs no new YAML features. Fields: `otlp_config`, `discover_service_name`, `discover_log_levels`, `allow_structured_metadata`, `volume_enabled`, `max_label_names_per_series`.
- C4 Tempo intrinsic `name` values (truncation at the 1 MB cap), and whether the Tempo overrides are readable.
- AC each:
  - witness recorded in `docs/traps.md`, naming the stack slug or slugs;
  - route added to the AGENTS.md labelling section;
  - GET only;
  - a missing read scope is handled under D-LBL11 (record and update CAPABILITIES) or parked.

**D - `label_inventory` source.** After B; does not wait for C.
- Runs in tier T2, iterating `gcom.fetch_inventory`. It is default-off: its enable flag and its `config.py` entry belong to this task.
- An isolated `ReadOnlyClient` with its own deadline slice, at a stated number of seconds and a stated position in `run_t2`. Running out of budget gives `partial(deadline)`.
- Metrics: per-label distinct counts come from the proven `cardinality/label_names` route (one call per stack; head-only window recorded).
- Value reads per signal are capped like `Bounds.keys`. Priority is fixed: name-pattern hits first, then cardinality order.
- Loki and Tempo use the label-values routes. Pyroscope goes through `label_risk.profile_read` under amendment (a).
- Name minimisation follows D-LBL1. Non-PII shape classes only, per D-LBL9. Register rows per stack and signal are bounded.
- Coverage state per stack and signal: `complete | partial | unavailable`, with a reason enum.
- AC:
  - contract tests over recorded shapes;
  - zero calls when disabled;
  - a canary test: unique sentinel values through a fake transport are absent from the scan envelope, every view, Loki events, metrics, stdout, `--out` and error strings;
  - the limited-run guard holds;
  - the INPUT_OWNER entry is added;
  - each input records its window (head vs 24h).

**E1-E4 - Route extensions.** Each after its C witness and after D, run one at a time because they share `label_inventory.py`, `label_rules.json`, `budget.py` and `hydrate.py`.
- E1 Mimir series per value and per metric.
- E2 Loki labels per stream and the values-to-streams ratio.
- E3 Loki OTLP index-label set and Drilldown prerequisites.
- E4 Tempo span-name cardinality and override checks.
- Each bumps `catalogue_version`.

**F - Labelling pillar.** After B and D.
- Views:
  - `labelling_findings`, deliberately NOT a FindingSpec, so no label names reach Loki;
  - `labelling_stack_summary`;
  - `labelling_cross_signal`, which reuses `signal_inventory` service and cluster sets and publishes counts and set sizes only;
  - `labelling_label_register`, bounded or top-N.
- The metrics table above.
- AC:
  - a test that no label_inventory name appears in Loki events;
  - VIEW_INPUTS re-derived;
  - empty-view schemas;
  - gaps are absent series;
  - carry-forward drops departed stacks;
  - BUDGET.md regenerated;
  - each view carries `catalogue_version`.

**G - `labelling` dashboard.** After F.
- Registered in DASHBOARDS, BUILDERS and PILLAR_OF.
- Panels:
  - estate overview: worst severity, score with coverage, trend;
  - per-stack scorecard;
  - cross-signal consistency;
  - per-signal rule tables;
  - label register;
  - not-evaluated and coverage.
- The banner states the data is deterministic and comes from bounded samples.
- AC: coverage gates pass.

**I - Config, Terraform and docs.** After D.
- Threshold tunables, size floor, static allowlist, coverage floor, budget seconds.
- Updates to RUNBOOK, CAPABILITIES, SPEC and traps.
- AC: `just tf-validate`; the docs state what is and is not inspected.

**K - Dev live proof.** After D, F, G and I, plus whichever E tasks landed.
- Full staff-estate run.
- p95 per-stack runtime and total wall time, measured against the 3600 s T2 tier.
- Peak memory, against the 232.7 MiB recorded under GCI-0018.01.
- Raw-value absence: known staff label values are read separately and grepped across S3 objects and Loki.
- Score stability across two consecutive days.
- AC: evidence recorded; release cut.

**H - Maturity replaces `cardinality_discipline`.** After K.
- Bump `RUBRIC_VERSION`.
- Aggregation: the per-stack dimension is the weight-averaged score over signals with a published score. It is withheld if none has one.
- Re-derive the maturity view inputs.
- CHANGELOG note.
- AC: tests updated, with the reason named.

**L - Enable on the customer deployment under D-LBL7.** After K and the release.
- Done in the consumer deployment repo (doc-0003); the customer name lives only there.
- AC: first run verified; parked routes listed as not covered.

**M - Reconcile overlapping findings.** Owner-decision label; after K. Decide whether `labelling` supersedes or keeps:
- `risk_label_cardinality` (GCI-0018.01);
- the `cost_cardinality_outliers` worst-label finding;
- maturity `cardinality_discipline` as already replaced by H.

Both outputs stay unchanged until then.

**J - Share one names fetch with label_risk.** Parked until after K. label_risk's privacy behaviour changes only under its own decision. K's budget accounts for the double fetch in the meantime.

## Order

A first. Then B and C1-C4 in parallel.
D follows B; I follows D. E1-E4 follow their witness and D, in series.
F follows B and D; G follows F.
K follows D, F, G and I. H, L and M follow K. J stays parked.

# Part 2: Synthesis

Lane briefs on disk: research-traces.md, research-psguides.md (same directory). Metrics and logs briefs are summarised here.
Caveat: the metrics lane quoted via WebFetch summaries, so quotes are near-verbatim only. Re-verify any quote before it reaches customer-facing panel text.

## 1. Current coverage (verified against code)

- `collector/sources/label_risk.py` (T2 daily, GCI-0018) already reads label NAMES on all four signals (Mimir/Loki/Tempo GET, Pyroscope via the two named POSTs).
  - It samples up to 256 values for 64 keys per signal (`Bounds`, :36). Keys are selected PII-first, then lexically (:230), so most keys on a large stack are never value-sampled.
  - Names are transient. Only classified PII matches persist (S3 `risk_label_hygiene`), plus a `keys_returned` count.
- `dataplane.cardinality` (T3) keeps the Mimir top-20 label names with value counts. `label_cardinality.py` does an exact-name denylist over those 20 only.
- `signal_inventory` (T2) keeps service, cluster and metric-name lists. Adaptive Metrics recommendations are collected as totals plus a top-10 sample.
- `loki_config` fetches `/config/tenant/v1/limits` but keeps only `retention_stream`.
- Nothing scores labelling practice. The nearest thing is the maturity `cardinality_discipline` dimension (weight 0.10, values/series ratio).

Verdict: the user's instinct is right. We touch the right APIs but throw the data away. Most of the platform-operator value comes from persisting names and counts we already fetch, plus a few new bounded GET routes.

## 2. What best practice gives us (merged rulebook, deterministic subset)

Grafana publishes few numeric thresholds. Every threshold carries a provenance tag: `published` (Grafana/OTel limit or doc), `ps` (Professional Services guide) or `policy` (ours, tunable).

### Cross-signal (highest value for an org of many stacks)
- X1 Service identity present: Loki `service_name`; Tempo `resource.service.name`; Pyroscope `service_name`; metrics `service_name` or `job`. [published]
- X2 `unknown_service*` (traces/logs) or `unspecified` (profiles) share of service values. [published fallback; share threshold is policy]
- X3 Environment attribute: `deployment.environment.name` preferred. Legacy-only is a migration finding. Mixing the two splits Knowledge Graph environments. [published]
- X4 Same service set across signals. The set difference is the correlation gap. [published principle]
- X5 Same k8s identity labels across signals (cluster, namespace). [published]
- X6 Label-name synonym drift on one stack (`env`/`environment`/`deployment_environment`, `namespace`/`k8s_namespace_name`, case variants). [alias table is policy]
- X7 Cost-attribution label coverage, only if the configured attribution labels are readable. [published 2 labels / 1,000 combinations]

### Metrics
- M1 Name syntax and reserved `__` prefix. Dotted/UTF-8 names reported separately as an OTLP signal. [published]
- M2 Unbounded-identifier names (user/session/request/trace id, uuid, ip, email, timestamp, url/path), confirmed by value count. [published list + PS-25]
- M3 Value-shape classes on sampled values (uuid, ip, epoch, hex id, email, url-with-id). Only shape counts persist. [policy regexes]
- M4 Per-label distinct values: warn at 100+, high at 1,000+, critical at 10,000+. [ps bands; Prometheus under 10 / over 100]
- M5 Metrics with 1,000+ series; the top-N share of the series total. [ps]
- M6 Labels per series near 30/40. [published]
- M7 Value length near the 2,048 truncation point. [published]
- M8 Churny labels promoted by OTLP defaults (`k8s_pod_name`, `service_instance_id`) on high-series metrics. [inference]
- M9 `target_info` bloat and `resource_to_telemetry_conversion` symptoms (`process_*`, `telemetry_sdk_*`, `os_*` on datapoints). [ps + OTel]
- M10 Adaptive Metrics addressable waste, already collected; reuse it. [published]
- M11 Naming hygiene: base units, `_total`, no values embedded in names. Low severity. [published Prometheus]

### Logs
- L1 Labels per stream: 15 is a hard limit; warn above 10. [published]
- L2 Index labels with unbounded names (pod, trace_id, request_id, user_id, ip, timestamp). [published]
- L3 Distinct values per label: dynamic labels "tens"; warn at 100+, high at 1,000+; static-infrastructure allowlist (host, cluster, namespace). [published qualitative + policy]
- L4 Values-to-streams ratio, from Grafana's own `logcli --analyze-labels` method. [published method]
- L5 Active streams against the volume-scaled guidance and the stack limit. [published]
- L6 `level` as an index label: a soft finding, because Grafana's docs disagree with themselves. [published, conflicting]
- L7 OTLP defaults still indexing `k8s_pod_name` / `service_instance_id`. Grafana says these are "no longer recommended". [published]
- L8 Legacy LokiExporter format (`exporter="OTLP"`). [published, deprecated July 2024]
- L9 Drilldown prerequisites in applied limits (`discover_service_name` non-empty, `discover_log_levels`, `allow_structured_metadata`, `volume_enabled`). [published]
- L10 Structured metadata keys and size (128 entries / 64KB). Needs `detected_fields`. [published]

### Traces
- T1 Required resource attributes: service.name, service.namespace, deployment.environment(.name), service.instance.id, service.version. If any k8s attribute is set, the k8s cluster/namespace/pod triple. [published, App O11y quality report]
- T2 `/` in service.name or service.namespace values. [published]
- T3 Span-name cardinality and ID-shaped span names (intrinsic `name` values; a truncated list is itself evidence). [published principle, no threshold]
- T4 `http.route` values are templates. [published MUST]
- T5 Deprecated semconv names present (lookup table pinned to semconv v1.44.0). Low/medium severity, because Grafana's own defaults lag. [published]
- T6 Sensitive attribute names, and SQL with literals in `db.query.text`. Overlaps GCI-0018; route to the existing privacy source. [published]
- T7 Attribute key syntax (lowercase dotted snake_case; no custom keys under `otel.*` or semconv namespaces). [published]
- T8 Large-payload attribute names (bodies, headers, full SQL). [published]
- T9 Span-metrics/service-graph dimension risk. Needs the Tempo overrides, which may not be readable on Cloud. [published]

### Profiles
- P1 `service_name` present and not `unspecified`. [published]
- P2 No dotted names; name/value length limits. [published]
- P3 Distinct values per label (ID-like). No threshold published. [policy]

### Judgement-only rules (no deterministic answer)
- "Used in 9 of 10 queries" needs query logs or dashboard selectors.
- Span-name genericity beyond regex.
- Unusual synonym detection.
- The downstream-dependency check before advising a demote.

These are the only candidates for an LLM.

## 3. Proposed architecture (follows the golden rule)

- **New T2 daily source: `label_inventory`.**
  - Iterates the live inventory: per stack, per signal, it reads label names (Tempo scope-qualified, intrinsic `name` separately) and a bounded distinct-value count per label.
  - Values are fetched to count and shape-classify, then discarded. Persisted per label: name, scope, value count (or `at_least N` when truncated), shape-class counts, and the series/stream count where the API gives it.
  - Stays separate from label_risk so the privacy-reviewed source is untouched. Deduplicating the fetch is a later task.
- **Rule catalogue:** `collector/label_rules.json`, versioned like `label_patterns.json`. Each rule carries id, signal, severity, threshold, provenance, source URL and input requirement. A rule whose input is missing yields `not_evaluated`, never pass.
- **Pillar:** `collector/pillars/labelling.py` composes views:
  - `labelling_findings`: stack, signal, rule, severity, label, evidence.
  - `labelling_stack_summary`: per stack and signal, rules evaluated, passed and failed by severity, plus coverage state.
  - `labelling_cross_signal`: the service-set and env/k8s consistency matrix.
  - `labelling_label_register`: per stack, signal, label name, count, shape and series.
- **Metrics (time series justified by the trend):**
  - `gcinsight_labelling_findings{stack,signal,severity}`: 4 signals x 3 severities per stack.
  - `gcinsight_labelling_rules_evaluated{stack,signal}`.
  - Rule ids stay in views, not labels.
  - Both declared in budget.py; `VIEW_INPUTS` re-derived.
- **Dashboard:** a new `labelling` dashboard (DASHBOARDS + BUILDERS + PILLAR_OF):
  - estate overview: stacks by worst severity, trend;
  - per-stack scorecard;
  - cross-signal consistency;
  - per-signal rule tables;
  - label register drill-down.
  - The maturity dimension `cardinality_discipline` is fed by, or replaced with, a labelling dimension.
- **Hydration:** the input owner is t2; T1/T3 hydrate. Carry-forward uses the live stack set.
- **Customer:** the new reader is default-off. Customer enablement is pre-authorised by D-LBL7 once the dev proof (task K) is recorded.

## 4. New routes needing staff-stack witnesses before build

- Mimir `GET /api/v1/cardinality/label_values` (per-value series counts) and `label_names` with a higher `limit` (max 500) or a selector.
- Loki `GET /loki/api/v1/series` (bounded window) for labels-per-stream and the values-to-streams ratio, or `index/stats` / `index/volume`. That folds in GCI-0101 (top log producers per stack read, an open owner decision).
- Loki `GET /loki/api/v1/config/limits/applied` (Cloud self-serve: OTLP and Drilldown limits). Reachability with the org CAP is unverified. Alternative: retain more keys from the existing `/config/tenant/v1/limits`.
- Loki `GET detected_fields` (structured-metadata keys). Unverified on Cloud.
- Tempo intrinsic `name` values (an existing route family, new tag). Tempo overrides (span-metrics dimensions, dedicated columns) are likely not readable with a read token. Probe first, and park if not.

## 5. Open risks

- Large-estate scale vs the T2 budget. label_risk already takes up to 900s. The new source needs its own budget slice and a coverage state per stack.
- The value-count truncation semantics differ per signal (Loki and Pyroscope ignore `limit`). Use `at_least` semantics like the IRM counts.
- Grafana guidance conflicts (level label; the 15 vs 30 OTLP promotion cap; deprecated names in Grafana's own defaults). Severity stays low where Grafana contradicts itself.
- Label names are usually not personal data but can be (tenant names in keys, dynamic keys). Persistence is an owner decision.

# Part 3: Metrics and logs research
## Metrics lane (researched 2026-10-06; quotes via WebFetch summaries, re-verify before customer-facing use)

### Published thresholds

- Labels per series: 30 recommended, 40 max. Per-stack limit "varies by configuration".
- Label name: 1,024 characters max.
- Label value: 2,048 characters, truncated with an appended hash.
- Adaptive Metrics does not recommend aggregating a metric with fewer than 100 series.
- Unused metric: no query in 30 days and no dashboard, recording-rule or alert use.
- Cost attribution: at most 2 labels and 1,000 combinations.
- Learning Hub guidance is "tens of values, not thousands".
- Prometheus guidance is "below 10 typical, over 100 investigate".

### Rules (M-xx)

| id | rule | input | det | threshold / provenance | source |
|---|---|---|---|---|---|
| M-01 | label name matches `[a-zA-Z_][a-zA-Z0-9_]*`; dotted or UTF-8 names reported as an OTLP signal | names | det | published | grafana.com/docs/grafana-cloud/send-data/metrics/label-handling-and-limits ; prometheus.io/docs/concepts/data_model |
| M-02 | no user label starting `__` | names | det | published (Prometheus stricter than Grafana wording) | same |
| M-03 | name length <= 1,024; anomaly above about 64 | names | det | published / policy 64 | label-handling-and-limits |
| M-04 | value length <= 2,048; flag above about 256 as junk (stack traces, SQL, URLs) | sampled values | det | published / policy 256 | label-handling-and-limits ; send-data/metrics/troubleshoot |
| M-05 | labels per series <= 30 (40 max) | series sample | det | published | grafana-cloud/telemetry-signals/use-signals-together/key-concepts |
| M-06 | metric name syntax, lower snake_case, application prefix | metric names | det / judgement | published | prometheus.io/docs/practices/naming |
| M-07 | base-unit suffixes; counters end `_total` | names + type | det | published | prometheus naming ; OTel prometheus compatibility spec |
| M-08 | no label value embedded in the metric name | names | heuristic | published principle | prometheus instrumentation |
| M-09 | no unbounded identifier label names (user/customer/session/request/trace/span id, uuid, guid, ip, client_ip, remote_addr, email, timestamp, ts) | names + counts | det | published list | learning-hub/labeling-strategy/03-metrics-labeling/09-use-bounded-labels |
| M-10 | url/path/uri/query labels with raw ids (templates are fine) | names + values | det / judgement | inference | learning hub principle |
| M-11 | value-shape detection: uuid, ip, email, epoch, hex trace id | sampled values | det | published examples | key-concepts ; learning hub |
| M-12 | per-label distinct values: warn 100, high 1,000, critical 10,000 | counts | det | ps / policy; Grafana examples 3 / ~50 / millions | key-concepts ; prometheus instrumentation |
| M-13 | multiplicative cardinality: label share of the metric's series | per-metric series + counts | det | none | learning-hub .../10-before-you-add-a-label |
| M-14 | unused-label bloat via Adaptive Metrics `drop_labels` | AM verbose recommendations | det | published floor of 100 series | adaptive-metrics/understand-recommended-rules |
| M-15 | addressable waste = sum of positive marginal reductions for add/update | AM recommendations | det | published | adaptive-metrics-api |
| M-16 | unused metrics (30 days) | AM / usage | det | published | cardinality-management |
| M-17 | Adaptive Metrics rules on metrics used in alert or recording rules | rules + recommendations | det | published | understand-recommended-rules |
| M-18 | correlation labels present (service / service_name, env, cluster), names exact across signals | names + coverage | det / judgement | published principle | key-concepts ; learning hub 21 |
| M-19 | cost attribution coverage: at most 2 labels, 1,000 combinations, stable values | names + counts | det | published | cost-attributions/labels ; blog 2026-07-22 |
| M-20 | synonym and alias drift (namespace vs k8s_namespace_name, env variants, service vs service_name vs job) | names + values | det alias table + judgement | policy | key-concepts |
| M-21 | empty or constant-valued labels | counts | det | inference | prometheus data model |
| M-22 | churny labels (pod, container id, service_instance_id, pod_uid, build hash) | counts / active vs inmemory | det | published (AM aggregates the highest-churn label) | understand-recommended-rules ; mimir http-api |
| M-23 | histogram bucket multiplication | names + series | det | inference | otlp-format-considerations |
| M-24 | active series against `max_global_series_per_user` (default 150,000) | usage | det | published default | usage-limits |

### OTLP rules (O-xx)

- O-01 Grafana Cloud promotes 19 resource attributes to labels by default:
  - `service.instance.id`, `service.name`, `service.namespace`, `service.version`;
  - `cloud.availability_zone`, `cloud.region`, `container.name`;
  - `deployment.environment`, `deployment.environment.name`;
  - `k8s.cluster.name`, `k8s.container.name`, `k8s.cronjob.name`, `k8s.daemonset.name`, `k8s.deployment.name`, `k8s.job.name`, `k8s.namespace.name`, `k8s.pod.name`, `k8s.replicaset.name`, `k8s.statefulset.name`.

  Changing the list is "contact Support"; a `MimirOTLPConfiguration` reference is unverified. Source: grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations
- O-02 Translation: `job` is `service.namespace/service.name`, and `instance` is `service.instance.id`. `job=unknown_service*` is a coverage finding (inference). Source: mimir/latest/configure/configure-otel-collector
- O-03 Other resource attributes go to `target_info`. Flag bloat or churny attributes on it (inference).
- O-04 `resource_to_telemetry_conversion` symptoms on datapoints: `process_*`, `host_name`, `os_*`, `telemetry_sdk_*` (OTel UX research, 2025).
- O-05 Suffix translation conflicts (`_total_total`; foo_seconds vs foo_seconds_total).
- O-06 UTF-8: Prometheus 3 allows it, while Grafana Cloud docs describe underscore escaping. This is unresolved.
- O-07 A `;` in values signals a key collision (OTel spec concatenation rule).
- O-08 Always define `deployment.environment.name` and `service.namespace`. Adaptive Metrics rules aggregating `instance` need checking (blog 2025-05-20).

### Mimir API notes

- `cardinality/label_names` and `cardinality/label_values`:
  - parameters `selector`, `count_method=inmemory|active` and `limit` (default 20, max 500);
  - head-only (about 2h).
- `cardinality/active_series` may be disabled; verify per stack.
- Grafana advises using the plain `/labels` and `/label/<n>/values` routes unless counts are needed.

## Logs lane (researched 2026-10-06; Loki v3.7.x docs)

### Published thresholds

- 15 label names per stream, hard in Cloud ("aim for 10-15 at a maximum").
- Label name 1,024 bytes; value 2,048 bytes.
- Structured metadata: 128 entries and 64KB per line.
- Dynamic labels: "tens of values" ("single digits, or maybe 10's").
- Active streams: under 100,000 active and under 1M per 24h for tenants above 10 TB/day, scaled down proportionally for smaller tenants.
- Grafana Cloud stream limit starts at 5,000 per tenant, scales to 80,000, with a hard ceiling around 200,000.

### Rules (L-xx)

| id | rule | input | det | threshold | source |
|---|---|---|---|---|---|
| L-01 | at most 15 labels per stream; warn above 10 | series label sets | det | published 15; policy warn 10 | grafana-cloud/send-data/logs/loki-limits ; loki/latest/get-started/labels |
| L-02 | tenant-wide label-name sprawl (proxy only) | /labels | det | none | labels/cardinality |
| L-03 | distinct values per dynamic label: warn 100, high 1,000; static allowlist (host, cluster, namespace) | counts | det | published qualitative | labels/bp-labels |
| L-04 | active streams against volume-scaled guidance and the stack limit | index/stats, index/volume | det | published | bp-labels ; loki-limits |
| L-05 | no unbounded-name index labels (timestamp, ip, pod, user/customer/trace/order/request/session/span id) | names | det | published list | labels/cardinality |
| L-06 | distinct values close to the number of streams the label appears in (logcli analyze-labels method) | series aggregate | det | published example: requestId 24,653 values in 24,979 streams | bp-labels |
| L-07 | pod name / instance id / ephemeral hostname not indexed | names, otlp_config | det | published ("no longer recommend") | labels/modify-default-labels |
| L-08 | `level` not an index label; use `detected_level` | names, volume | det | published, but Grafana's own examples conflict | bp-labels ; config-self-serve (`severity_text_as_label` cannot be true) |
| L-09 | `service_name` present; small `unknown_service` share | names, values, volume | det | policy: warn 5%, high 25% | labels ; Drilldown troubleshooting |
| L-10 | service_name values bounded (no replica or hash suffixes) | values | judgement | inference | labels (fallback list) |
| L-11 | name regex `[a-zA-Z_:][a-zA-Z0-9_:]*`; no `__x__`; case and synonym duplicates | names | det | published | labels ; cost-attributions/labels |
| L-12 | value hygiene: uuid, ip, hash, epoch, ids in paths; over about 256 bytes is a smell | values | det | published 1,024 / 2,048; policy 256 | loki-limits ; bp-labels |
| L-13 | OTLP mapping deliberate: read `/loki/api/v1/config/limits/applied`, not `/otlp_config`, which returns only the pending config; cap; no broad regex index rules | applied limits | det | 15 vs 30 caps conflict | config-self-serve ; otlp-format-considerations |
| L-14 | structured metadata within 128 entries / 64KB; stacktrace attributes | detected_fields | det | published | labels/structured-metadata |
| L-15 | high-cardinality fields queried often belong in structured metadata, not labels | labels, detected_fields | judgement | published framework | learning-hub/labeling-strategy/04-logs-labeling/18-the-decision-framework |
| L-16 | Drilldown prerequisites: `volume_enabled`, `discover_log_levels`, `allow_structured_metadata` true; `discover_service_name` non-empty | applied limits | det | published | Drilldown troubleshooting ; configure reference |
| L-17 | cost-attribution label coverage by volume | volume by label | det | published 2 labels / 1,000 combinations; policy warn 10% unattributed | cost-attributions/labels |
| L-18 | Adaptive Logs recommendations vs configured drop rate | Adaptive Logs API | det | none | adaptive-logs-api |
| L-19 | label names aligned across signals; trace-to-logs needs an exact name match | names across datasources | det / judgement | published principle | learning hub 22 ; trace-to-logs docs |
| L-20 | legacy LokiExporter format (`exporter="OTLP"`, `job`/`instance`, `level` label) | names, values | det | published (deprecated July 2024) | otlp/adopt-new-logs-format |
| L-21 | streams over-split (tiny chunks) | index/stats | judgement | qualitative | bp-labels |
| L-22 | label combinations multiply stream count | series | det | published example (3 x 5 = 15, then 45) | labels/cardinality |
| L-23 | Faro `app_id`, `app_key` and `kind` are promoted in Cloud; not drift | otlp_config | det | published | labels tip |

### OTLP default index labels (Loki latest, 17 entries)

- `cloud.availability_zone`, `cloud.region`, `container.name`, `deployment.environment.name`;
- `k8s.cluster.name`, `k8s.container.name`, `k8s.cronjob.name`, `k8s.daemonset.name`, `k8s.deployment.name`, `k8s.job.name`, `k8s.namespace.name`, `k8s.pod.name`, `k8s.replicaset.name`, `k8s.statefulset.name`;
- `service.instance.id`, `service.name`, `service.namespace`.

`limits_config` also lists the legacy `deployment.environment`. Grafana Cloud additionally promotes the Faro `app_id`, `app_key` and `kind`. Everything else goes to structured metadata. Source: loki/latest/send-data/otel

### service_name fallback order

`service`, `app`, `application`, `app_name`, `name`, `app_kubernetes_io_name`, `container`, `container_name`, `k8s_container_name`, `component`, `workload`, `job`, `k8s_job_name`, then `unknown_service`.

### Conflicts

- The OTLP promotion cap is 15 on the format page and 30 on the self-serve page.
- The default list is 17 in one place and 18 in another.
- The `level` label: guidance says avoid it, yet Grafana's examples keep it.
- The stream guidance and the Cloud ceiling differ.
- "15 index labels" is per stream, not tenant-wide.

# Part 4: Traces, OTel attributes and profiles research

Method: raw .md of grafana.com docs (latest/current as of 2026-10-06) via curl plus WebFetch; OTel semantic-conventions v1.44.0 (released 2026-08-04) cloned and read from source (model/*.yaml, docs/*.md, CHANGELOG, GitHub release notes). Fetched content treated as data. "INFERENCE" = my deduction, not published text. Doc quotes are short verbatim excerpts.

## 1. TL;DR
1. Grafana publishes a short hard list for traces: resource `service.name`, `service.namespace`, `deployment.environment.name` (or legacy `deployment.environment`), `k8s.cluster.name` + `k8s.namespace.name` + `k8s.pod.name` (+ one k8s workload attr), a host id (`k8s.node.name` | `host.id` | `grafana.host.id`), no slashes in service name/namespace, low-cardinality span names. These come from the App Observability "Instrumentation quality" report and the Knowledge Graph prerequisites page.
2. Semconv is v1.44.0. `deployment.environment` was renamed to `deployment.environment.name` in v1.27.0 and the new name became STABLE in v1.41.0 (2026-04-28). HTTP is stable (since v1.23.0), DB is partly stable (`db.system.name`, `db.namespace`, `db.query.text`, `db.collection.name`, `db.operation.name` stable), RPC is release_candidate, messaging is still development. Many old names still circulate in Grafana's own docs and Tempo defaults (`http.method`, `peer.service`, `db.system`), so deprecated-name checks need severity "low/medium", not "high".
3. Cardinality is the cost lever: `span_name` is the largest driver of Tempo span-metrics series; each extra dimension multiplies series by its distinct values; Grafana publishes no numeric "too many values" threshold. Scorable proxies: distinct counts of `name` and `http.route` values, ID-like regexes, tag-values truncation at the 1 MB default query limit.
4. Tempo limits to check against: attributes truncated at 2048 bytes (values) / 1024 bytes (names) in Cloud; dedicated columns per scope are 10 string (vParquet4) or 20 string + 5 int (vParquet5, default from Tempo 3.1); Cloud max trace size is documented inconsistently (3 MB vs 5 MB).
5. Pyroscope: `service_name` is "required and must always be present" (fallback value `unspecified`); label names must match `[a-zA-Z_][a-zA-Z0-9_]` (no dots); defaults are 30 label names per series, 2048 byte values; no published per-label value-count threshold. Cross-signal correlation requires identical service names (`service.name` = `service_name`).

## 2. Checkable rules

Severity: H high, M medium, L low, I info. Det = deterministic; Judge = needs judgement.
"Tags" = /api/v2/search/tags by scope; "Values" = /api/v2/search/tag/<scope.tag>/values (sampled, subject to `max_bytes_per_tag_values_query`, default 1,000,000 bytes, so a long list may be truncated: treat truncation as "unknown", and high-cardinality evidence).

### Traces (T)

| ID | Rule | Sev | Input | Det/Judge | Threshold | Source and quote |
|---|---|---|---|---|---|---|
| T-01 | `service.name` exists in resource scope | H | resource tags | Det | present/absent | semconv v1.44.0 model/service/registry.yaml: "MUST be the same for all instances of horizontally scaled services." Grafana: https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability/setup/resource-attributes/ ("service.name: The application name") |
| T-02 | No `unknown_service` / `unknown_service:<exe>` values in `resource.service.name` | H | resource.service.name values | Det (regex `^unknown_service(:.*)?$`) | any hit; share of spans needs TraceQL metrics (INFERENCE) | semconv registry: "SDKs MUST fallback to `unknown_service:` concatenated with the process executable name, e.g. `unknown_service:bash`... the value MUST be set to `unknown_service`." Loki also uses it: "If no label is found matching the list, a value of `unknown_service` is applied." https://grafana.com/docs/loki/latest/get-started/labels/ . Grafana publishes no trace-specific rule (INFERENCE: this is the SDK default when OTEL_SERVICE_NAME/service.name is unset) |
| T-03 | `service.namespace` exists on resource | M | resource tags | Det | present | https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability/setup/instrumentation-quality/ : "Application Observability uses the `service.namespace` attribute to filter and group by a service's namespace." (flagged by "Add the missing service.namespace attribute") |
| T-04 | Environment attribute present: `deployment.environment.name` (preferred) or legacy `deployment.environment` | H | resource tags | Det | present | Quality report: "uses the `deployment.environment.name` resource attribute (or the older `deployment.environment`) to map each service to the correct environment... Without it, services can appear ungrouped... and the baselines feature does not work." Knowledge graph: "`deployment.environment.name` (preferred)... `deployment.environment` (fallback)... 'unknown' (if neither...)" https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/get-started/prerequisites/ |
| T-05 | Do not use both `deployment.environment` and `deployment.environment.name` across the estate's metrics/spans (pick one) | M | resource tags (both present), plus metrics labels | Det on tags; metrics check is outside traces | both present = flag | KG prerequisites: "Use the same environment attribute (`deployment_environment_name` or `deployment_environment`) consistently across all your metrics. Mixing both attributes causes the knowledge graph to place services in different environments depending on the metric." |
| T-06 | Prefer new name: only legacy `deployment.environment` present = low-severity migration finding | L | resource tags | Det | legacy present, new absent | semconv v1.44.0 deprecated registry: "Replaced by `deployment.environment.name`." New name stable since v1.41.0 (release notes: "Stabilize `deployment.environment.name`... promoted from development to stable"). Conflict: Grafana's resource-attributes page still lists only `deployment.environment`, and the App O11y configure page says it "uses ... `deployment.environment`" by default. Cloud Mimir promotion list includes both. |
| T-07 | Environment values are bounded and not `unknown`/empty; no slashes or per-deploy values | M | `resource.deployment.environment(.name)` values | Det (count) / Judge | semconv well-known values: Production, Staging, Test, Development (v1.41.0); Grafana span-metrics doc rates `deployment.environment` cardinality "Low: A handful of values" | https://grafana.com/docs/tempo/latest/metrics-from-traces/span-metrics/span-metrics-metrics-generator/ |
| T-08 | No `/` in `service.name` or `service.namespace` values | M | resource.service.name / service.namespace values | Det | any `/` | Quality report: "Don't use slashes (/) in the `service.name` or `service.namespace` attributes... The OpenTelemetry specification has a specific namespace attribute." (job label is `${service.namespace}/${service.name}`) |
| T-09 | `service.instance.id` present on resource (unique per instance) | M | resource tags | Det | present | Grafana: "The unique instance, e.g. the pod name"; becomes the `instance` label. semconv: "`service.namespace,service.name,service.instance.id` triplet MUST be globally unique"; recommends UUID. Do not make it a span-metrics dimension (see T-23). |
| T-10 | `service.version` present | L | resource tags | Det | present | Grafana: "The application version, to see if a new version has introduced a bug" |
| T-11 | K8s workloads: `k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name` all present when any `k8s.*` resource attr exists | M | resource tags | Det | all three | Quality report: "include the `k8s.cluster.name`, `k8s.namespace.name`, and `k8s.pod.name` Kubernetes resource attributes to link Application and Kubernetes Observability". All three are stable in semconv v1.44.0 |
| T-12 | K8s: at least one workload-type attr (`k8s.deployment.name`, `k8s.statefulset.name`, `k8s.daemonset.name`, `k8s.cronjob.name`, `k8s.job.name`, `k8s.replicaset.name`) | L | resource tags | Det | >=1 | Quality report (Pod navigation links): "Only one is needed." and "Extracting all of them is not required and may increase metric cardinality." |
| T-13 | Host identification: one of `k8s.node.name` > `host.id` > `grafana.host.id` | M (billing relevant) | resource tags | Det | >=1 | Quality report: "Without these attributes, the service isn't counted for host hours billing." |
| T-14 | Cloud attrs present where on a cloud (`cloud.provider`, `cloud.region`, `cloud.availability_zone`, `cloud.account.id`) | I | resource tags | Det | present | KG instrumentation page: `target_info` recommended labels "`cloud_*`: determines cloud provider metadata", "`k8s_*`", "`telemetry_sdk_*`". Note: cloud.* are still `development` in semconv v1.44.0 |
| T-15 | `telemetry.sdk.*` present (technology/SDK detection) | L | resource tags | Det | present | https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability-kg/setup/instrumentation.md : "`telemetry_sdk_*`: determines service technology and SDK metadata." |
| T-16 | Deprecated attribute names (lookup table, section 3) present in span or resource scope | M (L if only in `event`/`link` scope) | span/resource/event tags | Det | any hit; report count and family | semconv v1.44.0 `model/*/deprecated/*.yaml`. HTTP migration: https://opentelemetry.io/docs/specs/semconv/non-normative/http-migration/ ("Stable Version: v1.23.1" in that doc); DB: .../db-migration/ (stable target v1.33.0) |
| T-17 | Old and new names co-present (e.g. `http.method` and `http.request.method`) = dup-mode instrumentation (acceptable transition) | I | tags | Det | both present | Opt-in env var `OTEL_SEMCONV_STABILITY_OPT_IN` = `http`, `http/dup`, `database`, `database/dup`, `messaging/dup`, `rpc/dup` (docs/http/http-spans.md, docs/db/database-spans.md) |
| T-18 | Attribute key syntax: lowercase, dot-delimited namespaces, snake_case within components: regex `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$` (no uppercase, hyphen, space, double delimiters) | L | all tag names, all scopes | Det | any non-match | semconv docs/general/naming.md: "Names SHOULD be lowercase. Use namespacing. Delimit the namespaces using a dot character... separate the words by underscores (i.e. use snake_case)." Tooling rule: "Names must start with a letter, end with an alphanumeric character, and must not contain two or more consecutive delimiters". Allowed exceptions: K8s API names, `http.request.header.<key>` style keys (INFERENCE) |
| T-19 | Custom attributes must not squat reserved/semconv namespaces: any `otel.*` key not defined in the registry; custom keys under an existing semconv namespace (e.g. `http.my_flag`, `db.custom`) | L | tag names + semconv registry key list | Det given registry list | any hit | naming.md: "Attribute names that start with `otel.` are reserved to be defined by OpenTelemetry specification." and "It is not recommended to use existing OpenTelemetry semantic convention namespace as a prefix for a new company- or application-specific attribute name." Recommended: reverse-domain (`com.acme.shopname`) or unique app prefix |
| T-20 | Sensitive attribute names: password, passwd, secret, token, api_key, authorization, cookie, `enduser.id`, `user.id`, `user.email`, email, `http.request.header.authorization`/`cookie`, `session.id`, ssn, card | H | tag names (all scopes) | Det (name match) | any hit | semconv registry: `enduser.id` "This field contains sensitive (PII) information." `url.full`: "Sensitive content provided in `url.full` SHOULD be scrubbed"; default-redacted query keys (`AWSAccessKeyId`, `Signature`, `sig`, `X-Goog-Signature`) with value `REDACTED`. Tempo OOM page: oversized attrs come from HTTP bodies/headers, "Full database query statements", "Message bodies from queues" |
| T-21 | Sensitive VALUES in sampled values: emails, JWTs (`eyJ...`), bearer tokens, `AKIA...` keys, credit-card-like digit runs, URL `user:pass@`, query strings with `token=`/`sig=` not `REDACTED` | H | sampled values of `span.url.full`, `span.http.url`, `span.url.query`, `span.db.query.text`, `span.db.statement`, any string tag | Det regex (best effort, false negatives) | any hit | semconv url.full: "username and password SHOULD be redacted and attribute's value SHOULD be `https://REDACTED:REDACTED@www.example.com/`". Regex list is INFERENCE |
| T-22 | SQL with literals: `db.query.text`/`db.statement` values containing string/numeric literals (quotes, `= 123`, `IN (1,2,3)`) | H | sampled values | Det regex + Judge | any non-placeholder literal | semconv docs/db/database-spans.md: "Non-parameterized query text SHOULD NOT be collected by default unless there is sanitization that excludes sensitive data" and "Sanitization SHOULD replace all literals with a placeholder value." Parameterized text (`$1`, `?`) is fine. Tempo: large statements also drive OOM and 2048 truncation |
| T-23 | Raw URLs/paths with IDs: `url.full`, `http.url`, `url.path`, `http.target`, `url.query` values with numeric/UUID/hash segments | M | sampled values; distinct-count if the list is truncated | Det regex + Judge | any ID segment; truncation at the 1 MB tag-values limit = strong signal | Tempo config comment: tag-values limit "protects the system from tags with high cardinality or large values such as HTTP URLs or SQL queries." semconv: `http.route` "MUST be low-cardinality... with dynamic path segments represented with placeholders" and "Instrumentation MUST NOT default to using URI path as a `{target}`." |
| T-24 | `http.route` (span.http.route) values are templates, not raw paths: no digit/UUID/hex segment | M | `span.http.route` values | Det regex | any ID-like segment | semconv http.route (stable): "This MUST be low-cardinality". Span-metrics doc: `http.route` "High... Safe only if routes are templated, not raw paths." |
| T-25 | Span name cardinality: distinct values of intrinsic `name`; ID-like patterns (UUID, long digits, hex, email, query strings, `GET /users/123`) | M-H (H if it also feeds span metrics, see T-26) | `/api/v2/search/tag/name/values` (intrinsic scope; `name`/`span:name`), or TraceQL metrics `count_over_time() by (name)` (INFERENCE) | Det regex; count threshold = Judge | NO published numeric threshold. Practical proxy (INFERENCE): list truncated by tag-values limit, or >~hundreds distinct per service | Quality report: "High-cardinality span names drastically increase storage costs for metrics and prevent Application Observability from grouping operations effectively... Use generic patterns such as `GET /user/{id}` instead of specific values like `GET /user/123`." ("best-effort analysis"). OTel spec: prefer `get_account/{accountId}` over `get_account/42`. Tempo: "`span_name` is usually the largest cardinality driver" |
| T-26 | Span-name sanitization configured when span names are high-cardinality | M | overrides `metrics_generator.span_name_sanitization` (`""`, `dry_run`, `enabled`) | Det | value != `enabled` while T-25 fires | https://grafana.com/docs/tempo/latest/metrics-from-traces/metrics-generator/cardinality/ : "The `span_name_sanitization` option uses the DRAIN algorithm to automatically group similar span names" (`GET /users/123` -> `GET /users/<_>`) |
| T-27 | Span name format by kind: HTTP `{method} {http.route}` (fallback `{method}`); DB `{db.query.summary}` else `{db.operation.name} {target}`; RPC `{rpc.method}` else `{rpc.system.name}`; messaging per operation type (v1.44.0: span per operation type) | L | `name` values vs kind/attrs | Judge | n/a | docs/http/http-spans.md, docs/db/database-spans.md, docs/rpc/rpc-spans.md in v1.44.0 |
| T-28 | Attribute size: values near/at 2048 bytes (truncation), names near 1024 bytes | M | sampled values (length), tag names | Det | >=2048 bytes (value), >=1024 (name) | https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/ : names "1024 bytes", values "2048 bytes ... Grafana Cloud truncates". Reduce-trace-size page: "Attributes exceeding 2 KB (2048 bytes) are automatically truncated before storage." Tempo OSS `max_attribute_bytes` (distributor) default 2048; metric `tempo_distributor_attributes_truncated_total{tenant,scope}`. Conflict: the overrides section of the same config reference shows `max_attribute_bytes` default 0 (see section 5) |
| T-29 | Large-payload attributes (HTTP request/response bodies, headers, full SQL, message bodies) | M | tag names matching `*.body*`, `*payload*`, `db.query.text`, `http.request.header.*`, `messaging.*body*` | Det name match | any hit | Tempo OOM page (see T-20). Reduce-trace-size: "Record only what you need for debugging (for example, truncated URLs, status codes, error messages)." Recommended SDK limit `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT=2048` |
| T-30 | Attribute-count sanity: per-span default SDK limit 128; very large number of distinct tag names per scope suggests dynamic/ID keys (e.g. `header.<uuid>`, `metric.<id>`) | L | tag list per scope | Judge | no published tag-name-count threshold; per-span limit 128 | Tempo best practices https://grafana.com/docs/tempo/latest/getting-started/best-practices/ : "Keep the number of attributes to a minimum, as each attribute adds overhead"; "Default limit is 128 entries per span". Key-with-ID regex = INFERENCE |
| T-31 | Dedicated attribute columns: count per scope within block-version limit; each configured attribute actually exists in tag list; candidates are the largest attributes | I-L | overrides `parquet_dedicated_columns` (global + per tenant `*`), block version (vParquet4 vs 5), tag lists | Det for limit/existence; Judge for candidate choice (size needs `tempo-cli analyse blocks`, not available to a read-only API scanner) | vParquet4: <=10 string per scope (span, resource); vParquet5: <=20 string + <=5 int per scope incl. event; int columns only if attr present on >=5% of rows | https://grafana.com/docs/tempo/latest/operations/dedicated_columns/ : "good candidates for dedicated attribute columns are attributes that contribute the most to the block size, even if they aren't frequently queried." "As of Tempo 3.1, Tempo writes `vParquet5` by default." |
| T-32 | Dedicated columns that name deprecated attributes (e.g. `http.method`, `db.statement`) when instrumentation now emits new names (empty column), and vice versa (heavy new-name attr with no column) | L | overrides + tag lists | Det | mismatch | INFERENCE from dedicated-column doc + semconv renames. Schema doc: vParquet4 had built-in columns for `http.method`, `http.status_code`, `http.url`, `k8s.*`; "Resource-level dedicated columns (Cluster/Namespace/Pod/Container/K8s*) and span HTTP columns are removed; vParquet5 relies on dynamically assigned dedicated columns only." https://grafana.com/docs/tempo/latest/operations/schema/ |
| T-33 | Span-metrics dimensions: no ID-like/unbounded dimension. High-risk list: user/customer/session/request ids, `url.full`, `http.url`, `http.target`, `url.path` (unless templated), `service.instance.id`, `k8s.pod.name`, `code.function(.name)` (medium-high), raw `http.route` | H | overrides `metrics_generator.processor.span_metrics.dimensions`, `dimension_mappings[].source_labels`; or Cloud KG "Dimensions" tab | Det name match; value-count = Judge using tag values | no published numeric cap. Guide table: low = `http.method`, `http.status_code`/`http.response.status_code`, `deployment.environment`, `cloud.region`; low-medium = `cloud.availability_zone`, `k8s.cluster.name`; medium = `k8s.namespace.name`, `code.function`; high = `http.route` | https://grafana.com/docs/tempo/latest/metrics-from-traces/span-metrics/span-metrics-metrics-generator/ : "Each new dimension multiplies the number of active series by the number of distinct values that attribute has. Adding a high-cardinality attribute, such as one that contains user IDs or full URLs, can cause a cardinality explosion that exceeds your active series limit". Cardinality page: 100 customers could take "25,000 active series to 2.5M" |
| T-34 | Span-metrics intrinsic dimension settings: `span_name` true with unsanitized names; `status_message` true (default false) | M | overrides `intrinsic_dimensions` | Det | `status_message: true` flag; `span_name: true` + T-25 | Config reference: "The span status message may contain arbitrary strings and thus have a very high cardinality." Span-metrics doc: disabling `span_name` "is the most common intrinsic dimension to disable when reducing active series" |
| T-35 | `enable_target_info: true` without `target_info_excluded_dimensions`: every resource attribute becomes a label on `traces_target_info` | M | overrides span_metrics | Det | enabled and exclusion list empty | Span-metrics doc: "all resource attributes are included as labels on the `traces_target_info` metric. To reduce cardinality, you can exclude specific attributes using the `target_info_excluded_dimensions`". Default false |
| T-36 | Each configured dimension/mapping must exist as attribute on spans (else silently produces no label); `dimension_mappings.source_labels` must use dotted original names, not sanitized | M | overrides + tag lists (resource and span scopes) | Det | configured but absent in tags | Span-metrics doc: "A dimension can only surface an attribute that already exists on your spans... the generator produces no label and no error... Check both the exact attribute name and its scope". "The `source_labels` field must contain the original span or resource attribute names (with dots)" |
| T-37 | Dimension attribute renamed upstream (configured `http.method`/`http.status_code`/`db.system` but spans now emit `http.request.method`/`http.response.status_code`/`db.system.name`) | M | overrides dims vs tag lists | Det | dim in deprecated table and absent while replacement present | INFERENCE combining T-36 and the table in section 3. Note Grafana's own span-metrics table still lists `http.method` and `http.status_code / http.response.status_code` as examples, and duplicates are allowed: "you can configure both `deployment.environment` and `deployment_environment`" |
| T-38 | Service-graph edges possible: client/producer spans carry a peer identity (`peer.service`, `db.name`, `db.system`, `db.system.name`, `server.address`, `network.peer.address`+port; DB nodes also `db.namespace`) | M | span tags for client spans; overrides `service_graphs.peer_attributes`, `database_name_attributes` | Det (tag presence) + Judge | >=1 | https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/ : "The default peer attributes are `peer.service`, `db.name`, `db.system`, and `db.system.name`." DB node name precedence: "`peer.service`, `server.address`, `network.peer.address:network.peer.port`, and finally the first attribute from `database_name_attributes`". Messaging edges need producer and consumer span kinds |
| T-39 | Service-graph only evaluates CLIENT, SERVER, PRODUCER, CONSUMER spans; App O11y Cloud default generates metrics only for SERVER and CONSUMER spans (client-only apps like browsers/mobile need Filter rules widened) | L-M | filter rules / generator settings (Cloud config), span kind distribution via `kind` intrinsic values | Det/Judge | n/a | https://grafana.com/docs/grafana-cloud/send-data/traces/configure/metrics-generator/ : "By default, Application Observability configures the metrics-generator to only generate metrics for the `SERVER` and `CONSUMER` span kinds." |
| T-40 | `enable_client_server_prefix` doubles label count per extra service-graph dimension | L | overrides service_graphs | Det | true with extra dims | Service-graph doc: "doubles the label count for each configured dimension, which increases cardinality." default false |
| T-41 | Active-series headroom: no overflow/drops. `metric_overflow="true"` series exist, `series_dropped_per_second > 0`, active series near limit | H | usage datasource: `grafanacloud_traces_instance_metrics_generator_active_series`, `grafanacloud_traces_instance_metrics_generator_series_dropped_per_second`; Tempo OSS `tempo_metrics_generator_registry_active_series_demand_estimate` | Det | any drop/overflow | Troubleshooting: "the metrics-generator produces overflow series instead of dropping new data. These series have the label `metric_overflow="true"`". Cloud: "the active series limit is managed per tenant. To request an increase, contact Grafana Support." Per-label limiter replaces value with `__cardinality_overflow__` (`max_cardinality_per_label`, default 0 = off) |
| T-42 | Duplicate RED metrics: both eBPF/Beyla metrics and Tempo-generated span metrics for the same service, without `span.metrics.skip=true` | L-M | resource tag `span.metrics.skip`; metrics `traces_spanmetrics_*` vs `traces_span_metrics_*` | Det (needs metrics) | n/a | Quality report: "To prevent duplicate metrics, disable metric generation in Tempo by adding the resource attribute `span.metrics.skip=true`." |
| T-43 | Sampling vs span metrics: generated metrics need 100% sampling upstream of the generator; ratio-based head sampling or Adaptive Traces policies change counts | M | Adaptive Traces policies (drop/probabilistic/volumetric/diversity); collector config unavailable | Judge | n/a | Quality report: "This approach requires a 100% span sampling rate to ensure that all traffic is represented." Cloud generator doc: "If traces are down-sampled before reaching Tempo, the metrics will be lower than reality." Whether Adaptive Traces runs before or after the generator is not stated in the pages read (GAP) |
| T-44 | Adaptive Traces diversity fingerprint attributes present on server/consumer spans: `service.name`, `k8s.cluster.name`, `k8s.namespace.name`, `db.system.name`, `db.collection.name`, `http.route`, `http.response.status_code`, `rpc.method`, `rpc.grpc.status_code` | L | span/resource tags vs Adaptive Traces policies | Det (tag presence) | n/a | https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-traces/manage-recommendations/diversity-policy/ "The fingerprint is built from the following attributes". Note it still lists `rpc.grpc.status_code`, deprecated in semconv v1.39.0 for `rpc.response.status_code`. Volumetric policy groups by e.g. `service.name`, `http.method` |
| T-45 | Traces Drilldown readiness: TraceQL metrics query works on the stack | M | probe `{} | rate()` via TraceQL metrics API | Det | success/failure | https://grafana.com/docs/grafana/latest/visualizations/simplified-exploration/traces/access/ : "Traces Drilldown requires Grafana Tempo 2.6 or later with TraceQL metrics configured". Cloud: "TraceQL metrics can query metrics for a time range of 24 hours." Drilldown has no further attribute requirements published (it breaks down by `resource.service.name`, `span.name`, `span.status`, `span.http.status_code` in its example docs, so old HTTP names matter: INFERENCE) |
| T-46 | Scanner caveat: tag-listing completeness. Tag lists/values are capped by `limit`, `maxStaleValues`, time window (`start`/`end`) and `max_bytes_per_tag_values_query` (default 1 MB); an `intrinsic` scope exists | I | API params | Det | n/a | https://grafana.com/docs/tempo/latest/api_docs/ : scopes `resource|span|intrinsic|event|l
## Loop14 catalogue source re-verification (2026-10-07)

Current uncached full-page passages below were successfully retrieved. Firecrawl CLI reported Not authenticated, so usage was keyless rather than attributed to a per-home key. This is an attribution/runtime-wiring caveat, not a failed content retrieval; no credentials were created or changed. Root accepts the observed dated passages, not a claim of authenticated lookup. Unverified rules remain excluded.

| Rules | URL | Verified date | Passage and interpretation |
|---|---|---|---|
| P1 | https://grafana.com/docs/pyroscope/latest/configure-client/grafana-alloy/java/ | 2026-10-07 | The special label `service_name` is required and must always be present. Presence rule; source consumer counts missing required names. This passage is in Java profiling documentation, as in the frozen rulebook. |
| X_service | https://grafana.com/docs/grafana-cloud/telemetry-signals/use-signals-together/key-concepts/ | 2026-10-07 | Correlation works by matching labels and attributes across different signals. For two pieces of telemetry to correlate:; Names must match exactly (case-sensitive); Values must match exactly (case-sensitive) Only transient source-side exact comparisons; persist mismatch counts, never service values. Initial rule covers metrics/traces; other pair rules are additive catalogue extensions. |
| M6 | https://grafana.com/docs/grafana-cloud/telemetry-signals/use-signals-together/key-concepts/ | 2026-10-07 | Keep metrics labels under 30 per series (40 maximum allowed, but performance degrades) Warn threshold 30, high threshold 40 is a near-limit warning, not a claim that 40 labels is forbidden. Route remains parked. |
| L1 | https://grafana.com/docs/grafana-cloud/telemetry-signals/use-signals-together/key-concepts/ | 2026-10-07 | Keep logs labels under 15 per stream (hard limit); Logs allow only 15 labels per stream Maximum allowed 15, first forbidden integer 16. Threshold compares >=16. Route remains parked. |
| M4, M5 | https://github.com/grafana-ps/best-practice-guides/blob/80863e424aa565d831a4fbc64f30f6955cf7215d/guides/public/grafana-cloud/cost-optimization/06-metrics-cardinality-optimization.md | 2026-10-07 | Labels with 100+ unique values (investigate); Labels with 1,000+ unique values (likely problematic); Metrics consuming 1,000+ active series  |
| M4 critical band | https://github.com/grafana/skills/blob/f32d43dd9a682b7215cc2185c0340ba664f57c92/skills/grafana-cloud/prometheus-cardinality-troubleshooter/SKILL.md | 2026-10-07 | Any label with >10K unique values is almost certainly a bug. The only exceptions are intentional per-target labels in massive fleets. Do not invent an inclusive PS threshold: owner-requested >=10000 critical boundary is explicitly policy in threshold_sources. Static-infrastructure multiplier, population floor and all tunable overrides are also policy. |

The owner-requested inclusive 10,000 critical threshold is policy, not a misquotation of the published strictly-greater-than-10,000 PS band. Population floor, static-infrastructure multiplier and tunable overrides are policy. Successful retrieval does not prove source collector runtime, route scope or raw-value privacy; those remain separate source acceptance checks.
