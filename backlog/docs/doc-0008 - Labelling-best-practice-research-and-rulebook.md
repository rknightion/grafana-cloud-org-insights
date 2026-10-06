---
id: doc-0008
title: Labelling best-practice research and rulebook
type: specification
created_date: '2026-10-06 14:43'
updated_date: '2026-10-06 14:43'
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
| T-46 | Scanner caveat: tag-listing completeness. Tag lists/values are capped by `limit`, `maxStaleValues`, time window (`start`/`end`) and `max_bytes_per_tag_values_query` (default 1 MB); an `intrinsic` scope exists | I | API params | Det | n/a | https://grafana.com/docs/tempo/latest/api_docs/ : scopes `resource|span|intrinsic|event|link|instrumentation`; `limit` "Sets the maximum number of tags names allowed per scope". Treat a truncated list as "at least N", never as full |

### Cross-signal (X)

| ID | Rule | Sev | Input | Det/Judge | Threshold | Source and quote |
|---|---|---|---|---|---|---|
| X-01 | Service identity string matches across signals: trace `resource.service.name` = Loki `service_name` = Pyroscope `service_name` = metric `service_name`/`job` | H | trace service values, Pyroscope `service_name` values, Loki/Mimir values (other scanners) | Det (set comparison) | exact string match | https://grafana.com/docs/grafana-cloud/telemetry-signals/use-signals-together/key-concepts/ : "Correlation works by matching labels and attributes across different signals"; "`service="api"` doesn't match `service_name="api"`, it fails because the name is different". "For profiles, use consistent `service_name` labels to enable trace-to-profile correlation" |
| X-02 | `job` = `${service.namespace}/${service.name}` and `instance` = `service.instance.id` are derived the same way everywhere | M | trace attrs vs metric `job`/`instance` | Det | match | Grafana resource-attributes page; OTLP page: "`service.namespace/service.name` added to the `job` label. If `service.namespace` is empty, only `service.name`"; these three attrs are excluded from `target_info` by default |
| X-03 | K8s correlation attrs identical across signals (`k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name` -> `k8s_cluster_name` etc.) | M | trace values vs Loki/Mimir | Det | match | Loki OTel page default index labels include `k8s.cluster.name`, `k8s.namespace.name`, `service.name`, `service.namespace`, `deployment.environment.name`; Mimir promotion list in Cloud OTLP page (below). Quality report purpose: link App O11y and K8s Monitoring |
| X-04 | Environment attr consistency across signals | M | see T-05 | Det | match | KG prerequisites (quoted in T-05). INFERENCE: Loki OSS default index-label list contains `deployment.environment.name` but not `deployment.environment`, while the Cloud Mimir list has both, so legacy-name logs land as structured metadata, not an index label (verify per stack; Cloud log mappings are support/self-serve configurable) |
| X-05 | Default Cloud OTLP->metric-label promotion list (reference set for "which resource attrs become labels"): `service.instance.id`, `service.name`, `service.namespace`, `service.version`, `cloud.availability_zone`, `cloud.region`, `container.name`, `deployment.environment`, `deployment.environment.name`, `k8s.cluster.name`, `k8s.container.name`, `k8s.cronjob.name`, `k8s.daemonset.name`, `k8s.deployment.name`, `k8s.job.name`, `k8s.namespace.name`, `k8s.pod.name`, `k8s.replicaset.name`, `k8s.statefulset.name` | I | n/a | reference | n/a | https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/ ("automatically promotes the following OTel resource attributes to labels, with periods replaced by underscores") |
| X-06 | Do not use `k8s.pod.name`/`service.instance.id` as Loki index labels (move to structured metadata); mind Loki label caps | L | Loki config (other scanner) | Det | Loki: 15 index labels max per stream | Loki OTel page: "Because of the potential for high cardinality, `k8s.pod.name` and `service.instance.id` are no longer recommended as default labels." Conflict: Cloud metrics promotion still includes them. Key-concepts: "Keep metrics labels under 30 per series (40 maximum allowed...)", "Keep logs labels under 15 per stream (hard limit)" |
| X-07 | Trace to profile link: spans that can have a profile carry `pyroscope.profile.id` (value = span id); profile samples carry `span_id`/`trace_id` labels (legacy `profile_id`) | L | span tags (`span.pyroscope.profile.id`), Pyroscope label names | Det | n/a | https://grafana.com/docs/pyroscope/latest/configure-client/trace-span-profiles/ : "Spans that can have a profile are marked with the `pyroscope.profile.id` span attribute, whose value is the span ID despite the name." |
| X-08 | Logs carry `traceid`/`spanid` for trace to logs | L | Loki (other scanner) | Det | n/a | App O11y configure page: "Your logs must include the trace ID and/or span ID fields, typically as `traceid` and `spanid` attributes". |
| X-09 | One histogram type per service (native vs classic); only native shown if mixed | M | metrics | Det | n/a | Quality report: "If a service uses both types, only data from the native histogram appears." |

### Profiles (P)

| ID | Rule | Sev | Input | Det/Judge | Threshold | Source and quote |
|---|---|---|---|---|---|---|
| P-01 | `service_name` is a label name present on the stack's profile series | H | Pyroscope LabelNames | Det | present | https://grafana.com/docs/pyroscope/latest/configure-client/grafana-alloy/java/ : "The special label `service_name` is required and must always be present." |
| P-02 | No `service_name` value `unspecified` (Alloy fallback when not set/inferred); also no `unknown_service*` | H | LabelValues(`service_name`) | Det | any hit | Same page: "If `service_name` isn't specified and couldn't be inferred, then it's set to `unspecified`." |
| P-03 | `service_name` values equal trace service names (see X-01); report profile-only and trace-only names | M | LabelValues(`service_name`) vs trace values | Det | set difference | key-concepts quote in X-01 |
| P-04 | Label names valid: `[a-zA-Z_][a-zA-Z0-9_]*`, no dots | L | LabelNames | Det | any dotted name | https://grafana.com/docs/pyroscope/latest/configure-client/ : "It must match the regex `[a-zA-Z_][a-zA-Z0-9_]`. In Pyroscope, a period (`.`) isn't a valid character inside of tags and labels." (published regex lacks `*`; API can return UTF-8 names only with `Accept: */*; allow-utf8-labelnames=true`) |
| P-05 | Label name length <=1024 bytes; value length <=2048 bytes | M | LabelNames/LabelValues | Det | 1024 / 2048 | Pyroscope reference config: `max_label_name_length` default 1024, `max_label_value_length` default 2048 |
| P-06 | Label names per series <=30; proxy: total distinct label names | L | LabelNames count (proxy only; per-series count not visible via LabelNames) | Det for proxy, Judge | per-series default 30 (`max_label_names_per_series`). A high total of distinct names (INFERENCE threshold >~50) hints at dynamic label names | Pyroscope reference config |
| P-07 | High-cardinality labels: distinct value counts for non-`service_name` labels; ID-like regex on values; names like `pod`, `instance`, `request_id`, `user*`, `uuid`, `session*`. Exempt `span_id`, `trace_id`, `profile_id` (documented per-sample labels) | M | LabelValues per label | Judge (count) / Det (regex) | NO published value-count threshold. Related documented limit: `max_global_series_per_tenant` default 5000 (v1 storage only, OSS config; Cloud value unpublished). Generic Grafana guidance: "Don't use user IDs/request IDs/timestamps/UUIDs as labels"; "Use low-cardinality labels for correlation (service, environment, cluster)" | key-concepts page https://grafana.com/docs/grafana-cloud/telemetry-signals/use-signals-together/key-concepts/ ; Pyroscope intro: "high-cardinality tag/label handling" is a feature of the Advanced Analysis UI (no number) |
| P-08 | Enrichment labels exist for correlation: version, region, environment (match `service.version`, `cloud.region`, `deployment.environment(.name)` spelled with underscores) | I | LabelNames | Det | present | Pyroscope configure-client: "Commonly used tags include version, region, environment, and request types." Alloy `pyroscope.scrape` auto-injects `job`, `instance`, `service_name` (from search results, not re-verified) |
| P-09 | Quality report check: service has profiles at all | L | Pyroscope series per service_name | Det | n/a | Quality report: "Your service is missing profiles." |

## 3. Deprecated -> current semantic-convention names (lookup table; semconv v1.44.0, extracted from model/*/deprecated yaml, versions from CHANGELOG/release notes)

Stability of replacements in v1.44.0: HTTP and `server.*`/`url.*`/`error.type`/`network.peer.*` stable; `db.system.name`, `db.namespace`, `db.collection.name`, `db.operation.name`, `db.query.text`, `db.query.summary`, `db.response.status_code` stable; `deployment.environment.name`, `service.name|namespace|version|instance.id`, `k8s.cluster|namespace|pod|node|container|deployment|statefulset|daemonset|job|cronjob|replicaset.name` stable (k8s promoted v1.42.0); `rpc.*` release_candidate; `messaging.*` and `cloud.*`, `host.*`, `service.peer.name` development.

| Deprecated | Current | Since / note |
|---|---|---|
| deployment.environment | deployment.environment.name | renamed v1.27.0; new name stable v1.41.0 |
| http.method | http.request.method | HTTP stable v1.23.0 |
| http.status_code | http.response.status_code | v1.23.0 |
| http.url | url.full | v1.23.0 |
| http.target | url.path + url.query | split, v1.23.0 |
| http.scheme | url.scheme | v1.23.0 |
| http.client_ip | client.address | |
| http.server_name | server.address | |
| http.host | (no direct; use `server.address`/`url.*`; "uncategorized") | |
| http.user_agent | user_agent.original | v1.19.0 |
| http.request_content_length | http.request.header.content-length | |
| http.response_content_length | http.response.header.content-length | |
| http.request_content_length_uncompressed | http.request.body.size | |
| http.response_content_length_uncompressed | http.response.body.size | |
| http.resend_count | http.request.resend_count | |
| http.flavor | network.protocol.name + network.protocol.version | |
| net.peer.name | server.address (client spans) / client.address (server spans) | net.* renamed v1.21.0 |
| net.peer.port | server.port (client) / client.port (server) | |
| net.peer.ip, net.sock.peer.addr | network.peer.address | |
| net.sock.peer.port | network.peer.port | |
| net.host.name | server.address | |
| net.host.port | server.port | |
| net.host.ip, net.sock.host.addr | network.local.address | |
| net.sock.host.port | network.local.port | |
| net.protocol.name / net.protocol.version | network.protocol.name / network.protocol.version | |
| net.transport | network.transport | |
| db.system | db.system.name | v1.30.0 (values also changed); DB stable v1.33.0 |
| db.name | db.namespace | v1.26.0 |
| db.statement | db.query.text | v1.26.0 |
| db.operation | db.operation.name | |
| db.sql.table, db.cassandra.table, db.mongodb.collection, db.cosmosdb.container | db.collection.name | |
| db.redis.database_index | db.namespace | |
| db.elasticsearch.cluster.name | db.namespace | v1.27.0 |
| db.user, db.connection_string, db.mssql.instance_name, db.instance.id | (removed, no replacement) | |
| db.cosmosdb.status_code | db.response.status_code | |
| db.client.connections.* metrics | db.client.connection.* | |
| rpc.system | rpc.system.name | v1.39.0 (value renames: `connect_rpc`->`connectrpc`, `apache_dubbo`->`dubbo`) |
| rpc.grpc.status_code, rpc.connect_rpc.error_code, rpc.jsonrpc.error_code | rpc.response.status_code | v1.39.0 |
| rpc.service | merged into fully-qualified `rpc.method` | v1.39.0 |
| rpc.grpc.request.metadata / rpc.connect_rpc.request.metadata | rpc.request.metadata | v1.39.0 (same for response.metadata) |
| rpc.jsonrpc.request_id / rpc.jsonrpc.version | jsonrpc.request.id / jsonrpc.protocol.version | v1.39.0 |
| rpc.client.duration / rpc.server.duration (metrics, ms) | rpc.client.call.duration / rpc.server.call.duration (s) | v1.39.0 |
| messaging.operation | messaging.operation.type (value `publish` -> `send`, v1.28.0) | v1.26.0 |
| messaging.client_id | messaging.client.id | v1.26.0 |
| messaging.kafka.consumer.group, messaging.eventhubs.consumer.group | messaging.consumer.group.name | v1.27.0 |
| messaging.servicebus.destination.subscription_name | messaging.destination.subscription.name | v1.27.0 |
| messaging.kafka.message.offset | messaging.kafka.offset | v1.27.0 |
| messaging.kafka.destination.partition | messaging.destination.partition.id | |
| messaging.destination_publish.name / .anonymous | (removed) | |
| peer.service | service.peer.name (+ service.peer.namespace) | deprecated v1.39.0; Tempo service-graph defaults still use `peer.service` |
| enduser.role | user.roles | |
| enduser.scope | (removed) | |
| error.message | domain-specific message attr (e.g. `feature_flag.error.message`) | deprecated v1.40.0 |
| exception.escaped | (removed) | exception recording on span events being replaced by logs (v1.40.0 `OTEL_SEMCONV_EXCEPTION_SIGNAL_OPT_IN`) |
| k8s.pod.labels | k8s.pod.label.<key> | |
| gen_ai.* | moved to separate semantic-conventions-genai repo | v1.42.0 |
| graphql.document | still defined but Opt-In (sensitive/high cardinality) | v1.41.0 |

Tempo-side observations tied to renames (from the Tempo/Grafana docs read): span-metrics example dimensions still list `http.method`, `http.status_code`; service-graph `peer_attributes` default `peer.service, db.name, db.system, db.system.name`; Tempo best-practices page examples use `http.url`, `k8s.namespace`, `k8s.cluster`, `k8s.container_name` (stale, undated).

## 4. Gaps (nothing published, or only partial)
- No Grafana-published numeric thresholds for: distinct values per attribute, distinct span names per service, distinct tag names per scope, label values per Pyroscope label, active series per dimension. Only qualitative ("high", "low", "handful") and the tag-values 1 MB query cap. Any threshold chosen is INFERENCE.
- No Grafana/Tempo statement of which `service.name` values count as "unknown" for traces or App O11y (only the semconv SDK fallback and Loki's `unknown_service` label default).
- Traces Drilldown: only "Tempo 2.6+ with TraceQL metrics configured"; no required attribute list.
- Adaptive Traces: no statement whether span metrics are computed before or after sampling; no rule about required attributes beyond the diversity fingerprint list.
- Cloud Traces: no published per-stack list of dedicated columns, no self-serve procedure found for Cloud (INFERENCE: via support/overrides), no published tag-count limits. "Maximum number of resource attributes / span attributes: Limits are on the size of the traces."
- No Grafana doc stating the migration deadline for `deployment.environment` -> `.name`; App O11y accepts both.
- Pyroscope: no published cardinality threshold or tag-count guidance beyond limits in the reference config; Cloud's profile limits are not in the usage-limits page (only metrics/logs/traces tables).
- PII/sensitive-attribute guidance from Grafana is thin (Tempo OOM page and reduce-trace-size page); semconv only flags `enduser.id`, `url.full`, `db.query.text`, `exception.message` as sensitive. Name/regex lists in T-20/T-21 are INFERENCE.
- Messaging semconv is still "development" in v1.44.0, so no stable compliance target exists; RPC is release_candidate.
- No published way to read per-attribute block size via the HTTP API (dedicated-column candidate selection needs `tempo-cli analyse blocks`).

## 5. Conflicts and version notes
- Max trace size in Cloud: usage-limits page lists `max_bytes_per_trace` 3,000,000 (https://grafana.com/docs/grafana-cloud/billing-and-usage/usage-limits); OTLP format page says "5 megabytes (MB) per trace, ingest rate of 15 MB/s and bursts of 20 MB/s"; Tempo OSS default 5,000,000; ingestion rate in usage-limits table is 500,000 B/s. Treat the per-stack live limit (`grafanacloud_traces_instance_limits`) as authoritative.
- `max_attribute_bytes`: distributor config default 2048 and Cloud docs say truncation at 2 KB; the per-tenant ingestion override block in the same configuration reference says `default = 0` (unlimited). Do not infer truncation is off from the override alone.
- Dedicated columns: vParquet4 10 string per scope (Tempo 2.x/older docs, e.g. v2.8) vs vParquet5 20 string + 5 int (default in Tempo 3.1). Block version per stack decides the limit.
- Environment attribute: older Grafana pages list only `deployment.environment`; newer quality/KG pages prefer `.name`. Semconv: deprecated v1.27.0, new name stable v1.41.0 (2026-04-28).
- Tempo/Grafana docs lag semconv: `peer.service` (deprecated v1.39.0, 2026-01-12) remains a Tempo default; Adaptive Traces diversity list has `rpc.grpc.status_code` (deprecated v1.39.0).
- Loki OSS default index labels list only `deployment.environment.name`; Cloud Mimir promotion list has both names.
- Grafana "metrics labels under 30 per series" vs Loki "15 index labels" vs Pyroscope default 30 label names: different limits per signal.

## 6. Source index
- App O11y instrumentation quality: https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability/setup/instrumentation-quality/
- App O11y resource attributes: https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability/setup/resource-attributes/
- KG instrumentation (required metrics/labels): https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/application-observability-kg/setup/instrumentation.md
- KG prerequisites (environment): https://grafana.com/docs/grafana-cloud/platform/knowledge-graph/get-started/prerequisites/
- Cloud OTLP format considerations (promoted attrs, trace attr limits): https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/
- Tempo span metrics: https://grafana.com/docs/tempo/latest/metrics-from-traces/span-metrics/span-metrics-metrics-generator/
- Tempo service graphs: https://grafana.com/docs/tempo/latest/metrics-from-traces/service_graphs/
- Tempo cardinality: https://grafana.com/docs/tempo/latest/metrics-from-traces/metrics-generator/cardinality/
- Tempo metrics-generator troubleshooting: https://grafana.com/docs/tempo/latest/troubleshooting/metrics-generator/
- Tempo dedicated columns: https://grafana.com/docs/tempo/latest/operations/dedicated_columns/ ; schema: https://grafana.com/docs/tempo/latest/operations/schema/
- Tempo configuration reference: https://grafana.com/docs/tempo/latest/configuration/ ; API: https://grafana.com/docs/tempo/latest/api_docs/
- Tempo OOM / large attributes: https://grafana.com/docs/tempo/latest/troubleshooting/out-of-memory-errors/
- Tempo best practices: https://grafana.com/docs/tempo/latest/getting-started/best-practices/
- Cloud Traces metrics-generator: https://grafana.com/docs/grafana-cloud/send-data/traces/configure/metrics-generator/ ; reduce trace size: https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/traces/configure/reduce-trace-size/
- Adaptive Traces diversity/volumetric: https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-traces/manage-recommendations/diversity-policy/
- Signals together / key concepts: https://grafana.com/docs/grafana-cloud/telemetry-signals/use-signals-together/key-concepts/
- Loki labels and OTel: https://grafana.com/docs/loki/latest/get-started/labels/ , https://grafana.com/docs/loki/latest/send-data/otel/
- Pyroscope: https://grafana.com/docs/pyroscope/latest/configure-client/ , .../configure-client/grafana-alloy/java/ , .../configure-client/trace-span-profiles/ , .../configure-server/reference-configuration-parameters/ , .../reference-server-api/
- Traces Drilldown access: https://grafana.com/docs/grafana/latest/visualizations/simplified-exploration/traces/access/
- OTel semconv v1.44.0 (https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.44.0): docs/general/naming.md, docs/http/http-spans.md, docs/db/database-spans.md, docs/rpc/rpc-spans.md, model/service/registry.yaml, model/*/deprecated/*.yaml; migration guides https://opentelemetry.io/docs/specs/semconv/non-normative/http-migration/ and .../db-migration/; span-name guidance https://opentelemetry.io/docs/specs/otel/trace/api/

# Part 5: Professional Services best-practice-guides mining

Repo: /Users/rob/repos/best-practice-guides (read-only mining; nothing edited). Root for all paths below: /Users/rob/repos/best-practice-guides/guides

## 1. TL;DR

- The repo is ~1,100 files, 2 trees: `public/` (customer-facing PDFs) and `internal/` (PS-only). Only ONE labelling guide is internal: `internal/loki/label-analyzer-skill/`. Everything else relevant is public.
- Git history is a single squashed commit (2026-10-01) so `git log -1 --format=%cs` is 2026-10-01 for every file and tells you nothing about freshness. Use content staleness cues instead (e.g. "Grafana Agent Flow", "only Grafana Agent supports structured metadata").
- The label-analyzer-skill guide is NOT the methodology itself. It is a how-to-run-it wrapper. The methodology lives upstream in the public `grafana/skills` repo (`skills/grafana-cloud/loki-label-analyzer/SKILL.md` + 4 reference files, last commit 2026-07-24), which I read read-only with `gh api`. It is a prompt/skill (no scripts, no numeric scoring, no code). Scoring is a qualitative banded table (cardinality band -> keep/evaluate/demote/never).
- Upstream also has `prometheus-label-strategy`, `prometheus-cardinality-troubleshooter`, `adaptive-metrics`, `cost-management`, `dpm-finder` skills (only first ~260 lines of the first two read). `prometheus-label-strategy` is the metrics twin and CONTRADICTS the PS cost-optimization guide on label dropping (see section 3 "Conflicts").
- PS guidance is strongest and most checkable for Loki (labels, structured metadata, stream/chunk diagnostics) and for Prometheus cardinality (series maths, thresholds 100/1,000 values). It is thin or absent for profiles (Pyroscope dir is empty), Tempo attribute design, OTel semantic-convention compliance (one line each), Adaptive Logs/Traces label guidance, and any numeric cardinality thresholds for traces.
- Numbers that exist and are scanner-usable: label value counts 100+ (investigate) / 1,000+ (likely problematic); focus on metrics with 1,000+ series / top 10 by series; dynamic Loki label values "single digits or tens"; Loki chunk-size diagnostic `total_bytes / cache_chunk_req` (KB not MB = over-split); histogram multiplier 10-20x (PS) or bucket+3 (upstream); attribution tracker defaults max_cardinality 10000 (Tempo, Mimir) and 2000 (Loki example), max 2 Mimir attribution labels.

## 2. Inventory

All dates are 2026-10-01 (single-commit repo) unless stated.

### Internal
| Path | Summary |
|---|---|
| /Users/rob/repos/best-practice-guides/guides/internal/loki/label-analyzer-skill/ (00-metadata, 01-intro, 02-prep-context, 03-claude-code, 04-grafana-assistant, 05-customer-handoff, 98-appendix-tools, 99-references) | SA runbook for running the `loki-label-analyzer` skill (Claude Code or Grafana Assistant): when to use, inputs to gather, invocation prompts, report format, handoff/sequencing, verification metrics. |
| /Users/rob/repos/best-practice-guides/guides/internal/datadog/migration/12-tags.md | PS tooling (`tags-download`, `tags-mappings`) that extracts Datadog tags from dashboards/monitors into `tagmap.csv`. Tooling doc, little guidance. |

### Public: Loki
| Path | Summary |
|---|---|
| /Users/rob/repos/best-practice-guides/guides/public/loki/label-strategies/ (01-intro, 02-label-best-practices, 03-common-labels, 04-log-metadata, 05-practical-label-example) | THE core PS label guide that the skill encodes. Cardinality/selectivity, 12 best-practice headings, common label set, k8s good/bad labels, structured metadata and embedding, 98.4% worked example. |
| .../public/loki/query-administration/02-limits-config.md, 04-lbac.md, 06-logcli.md | `cardinality_limit`, `required_labels`, `minimum_labels_number`; LBAC; `logcli series --analyze-labels` label cardinality discovery. |
| .../public/loki/query-logs/01-intro.md, 04-query-stages.md | `metrics.go` fields; chunk size diagnostic tied back to labels. |
| .../public/loki/log-optimizations/01-log-best-practices.md, 04-metrics.md | Remove duplicated level from line once it is a label; `stage.metrics` inherits all labels (cardinality risk). |
| .../public/loki/helm-install/03-helm-values.md | Persona limits (`max_global_streams_per_user: 10e3`, `minimum_labels_number: 2`), `allow_structured_metadata`. |
| .../public/loki/cost-attribution/ (01-intro, 02-custom-usage-tracker) | Enterprise `custom_usage_trackers` per-label usage. |
| .../public/grafana/datasource-strategies-and-best-practices/01-lbac.md, 03-loki.md | LBAC via access policies; `X-Loki-Query-Limits` requiredLabels (commented out in source, API-only). |

### Public: metrics / cost / alerting
| Path | Summary |
|---|---|
| .../public/grafana-cloud/cost-optimization/06-metrics-cardinality-optimization.md | Core metrics cardinality guide: thresholds, dangerous labels, drop vs aggregate, Cardinality Management dashboards, scenarios (pod, path, tenant, span_name, http_route). |
| .../public/grafana-cloud/cost-optimization/02,03,05,07,08,09 | Active series, Adaptive Metrics (40-60%), histograms (native, 80-90%), strategies, logs (Adaptive Logs, level policy), traces (Adaptive Traces 75-90%, sampling). |
| .../public/irm/alerting/alerting-on-high-cardinality/ (01-04, 99-cardinality-rules.md) | Queries and cardinality API (`/api/v1/cardinality/label_names|label_values`) plus alert-rule JSON with example thresholds. |
| .../public/metrics/query-strategies/05-high-cardinality-metrics.md, 02-utilizing-specific-label-filters.md | Query-side cardinality and selector guidance. |
| .../public/mimir/cost-attribution/ (01-intro, 02-cost-attribution), .../public/tempo/cost-attribution/ (01-intro, 02-cost-attribution) | Built-in cost attribution config for Mimir and Tempo. |
| .../public/cloud-providers/aws/aws-metrics-collection/ (03, 06, 07-cost-and-cardinality, 08) and .../aws/ec2-tag-label-mapping/ (01-04) | AWS tag to label policy: small approved set, required tag set, relabel at scrape vs join at query. |
| .../public/collectors/servicenow-cmdb-into-alloy/ (01-04) | CMDB fields to labels; choosing labels, labeldrop of raw columns, normalization, fail-safe. |
| .../public/migrations/datadog/migration-overview/08-mappings.md | Datadog tag vs Prometheus label semantics (case, curly braces), tag injection. |

### Public: traces / OTel / collectors / correlation
| Path | Summary |
|---|---|
| .../public/grafana/correlations-metrics-logs-traces/ (01-08) | Correlation: identical labels from same SD, exemplars, trace ID in logs, traces-to-logs tag mapping, span metrics. |
| .../public/migrations/apm-migration/03-telemetry-collection.md, 05-faq.md, 06-troubleshooting.md | Minimum resource attributes, span-metrics series limit, normalizing `http.route`/`span.name`, metrics-generator limits and PromQL to monitor them. |
| .../public/collectors/alloy/instrumentation-playbooks/03-runbook-opentelemetry.md | OTLP via Alloy: resource attribute pruning, copying resource attrs to datapoint attrs, `resource_to_telemetry_conversion` warning, `disable_high_cardinality_metrics`. |
| .../public/collectors/otel/multistack_app_o11y/02-collector_setup.md | otelcol-contrib: spanmetrics/servicegraph dimensions list, resource attribute deletes. |
| .../public/collectors/otel/instrumentation_guides/python/01-python.md | Semantic attributes, baggage, log-trace correlation (generic). |
| .../public/grafana-cloud/app-o11y/02-java.md, 03-dotnet.md | Resource attribute env examples (.NET one is malformed, see conflicts). |
| .../public/tempo/traceql/01-best-practices.md | Explicit `span.`/`resource.` scope is ~4x faster; follow semantic conventions. |
| .../public/collectors/agent/helm-install/08-logs-overview.md, 02-methodology.md | Legacy (Agent/Promtail) log pipeline: labelallow default list, filename normalization, level default `unknown`. |
| .../public/collectors/k8s-meta-monitoring-overview/03-k8s-configuration.md | k8s-monitoring `labelsToKeep` and `k8sattributes` metadata list (meta-monitoring context). |
| .../public/collectors/alloy/ha-deployment/03-clustering-concepts.md | Target labels must be identical across cluster nodes. |
| .../public/collectors/alloy-vs-otel-collector/03,04 | Preserve job/instance labels; `prometheusreceiver` translation can alter names/labels; audit cardinality at migration. |
| .../public/kubernetes/k8s-monitoring-openshift/01-overview.md | `dropEmptyImageLabels` default silently drops `container_network_*`. |

## 3. Checkable rules

Signals: L=logs, M=metrics, T=traces, P=profiles, O=OTel generic, A=attribution/cost. Short quotes are verbatim.

### Logs (Loki)
| ID | Sig | Rule | Threshold | Source and quote |
|---|---|---|---|---|
| PS-01 | L | Dynamic label values must be bounded and small | "single digits or tens"; 1,000 hosts acceptable for a static-ish label like instance | /Users/rob/repos/best-practice-guides/guides/public/loki/label-strategies/02-label-best-practices.md "Keep the set of possible values for any dynamic label small, ideally within single digits or tens." |
| PS-02 | L | Never unbounded IDs as labels (user_id, request_id) | n/a | same file: "unique identifiers (user_id, request_id), can drastically increase the size of your index" |
| PS-03 | L | A dynamic label earns its place only if used in most queries | "used 9 out of 10 queries" | .../loki/label-strategies/03-common-labels.md "Will this label be used 9 of out 10 queries consistently?" |
| PS-04 | L | Label names and values must be consistent and case-normalized; enforce in CI/pipeline | `level` normalized to info/warn/error/debug | 02-label-best-practices.md "Case sensitivity ... prevent increased cardinality"; 03-common-labels.md normalize_log_level pipeline |
| PS-05 | L | `pod` must not be an index label; use `workload` = `{controller_kind}/{controller_name}`; keep pod as structured metadata or embedded in line | n/a | 03-common-labels.md "Using `pod` as a label is a poor choice, due to the high-cardinality and transient nature of pods" |
| PS-06 | L | `filename`: drop or normalize on k8s (strip pod name suffix/uid/rotation); strip date suffixes on hosts | target form `/var/log/pods/{namespace}/{controller_name}/{container}.log` | 03-common-labels.md "the `filename` label should be dropped or at the very least normalized" |
| PS-07 | L | Journal logs: keep only `systemd_unit` (as `unit`) plus `instance` | 16 `__journal__*` labels, 1 kept | 03-common-labels.md "the only recommended label to keep would be 'systemd_unit'" |
| PS-08 | L | End every `loki.process` with `stage.label_keep` allowlist | n/a | 03-common-labels.md "best practice to use `stage.label_keep` as the final step" |
| PS-09 | L | Recommended common set | app, classification, source, cluster, datacenter, env, job, level, region, squad, team | 03-common-labels.md "Recommended Common Labels" |
| PS-10 | L | k8s good labels: container, namespace, service, workload; bad: pod, raw filename | n/a | 03-common-labels.md Good/Bad Labels |
| PS-11 | L | Static aggregate labels (owner/squad/category/classification/source) are the LBAC selector, avoid per-file allowlists and regex | n/a | 02-label-best-practices.md "Use Static Labels"; 04-lbac.md |
| PS-12 | L | Soft enforcement: inject `unknown` for missing required labels before hard rejecting | n/a | 02-label-best-practices.md "Inject missing labels with placeholder values like unknown" |
| PS-13 | L | Structured metadata for high-card, occasionally queried fields (pod, node, process_id, version, restarted, image, tag, trace IDs, user IDs); needs `allow_structured_metadata`; embed in line (`stage.template`/`stage.pack`) when unavailable | Loki 2.9+ (skill) | .../loki/label-strategies/04-log-metadata.md. STALE: "only the Grafana Agent has support for writing structured metadata" |
| PS-14 | L | Level label default `unknown` when undetectable; TRACE/DEBUG dropped by default, INFO kept | n/a | .../collectors/agent/helm-install/08-logs-overview.md steps 6, 10-12 |
| PS-15 | L | Legacy Agent pipeline allowlist (starting point only) | cluster, component, container, deployment, env, filename, instance, job, level, log_type, namespace, region, team, service | 08-logs-overview.md step 19. NOTE includes `filename`, which PS-06 says to drop/normalize. |
| PS-16 | L | Remove duplicated data from the line once extracted to a label/SM (e.g. level) | n/a | .../loki/log-optimizations/01-log-best-practices.md "Remove Duplicate Values" |
| PS-17 | L | `stage.metrics` copies all stream labels onto metrics; `label_keep` first; budget series as labels x values x instances | n/a | .../loki/log-optimizations/04-metrics.md; internal/.../02-prep-context.md |
| PS-18 | L | Chunk size diagnostic: avg chunk = `total_bytes / cache_chunk_req`; KB/hundreds of bytes means labels over-split streams | MB range healthy | .../loki/query-logs/04-query-stages.md "a low average value (a few hundred bytes or kilobytes instead of megabytes)" |
| PS-19 | L | Discover candidate high-card labels with `logcli series --analyze-labels --since 1h '{}'` (Label Name, Unique Values, Found In Streams) | example flags pod 8,673, version 472 | .../loki/query-administration/06-logcli.md |
| PS-20 | L | Query-side guardrails | `minimum_labels_number: 2`; `required_labels` e.g. cluster,namespace,container (k8s), instance,filename (VM), level | .../loki/query-administration/02-limits-config.md; .../loki/helm-install/03-helm-values.md; datasource-strategies/03-loki.md (commented out in source) |
| PS-21 | L | Stream limits / index cardinality limit | `cardinality_limit` default 100000; `max_global_streams_per_user` 10e3 for 20MB/s persona; customer example 150k/user | 02-limits-config.md; helm-install/03-helm-values.md; internal/.../03-claude-code.md |
| PS-22 | L | Alerts need their own label strategy | n/a | 02-label-best-practices.md "Include Alerts in Label Strategy" |

### Metrics
| ID | Sig | Rule | Threshold | Source and quote |
|---|---|---|---|---|
| PS-23 | M | Prioritise by impact: top 10 metrics by active series; metrics with 1,000+ series; labels with 100+ values on high-volume metrics | 1,000+ series; 100+ values | .../grafana-cloud/cost-optimization/06-metrics-cardinality-optimization.md "Focus your efforts on: ... Metrics consuming 1,000+ active series; Labels with 100+ unique values" |
| PS-24 | M | Red flags per label | 100+ values = investigate; 1,000+ = likely problematic; continuously growing = unbounded | same file, Dashboard 2 "Red Flags" |
| PS-25 | M | Dangerous label patterns: user/customer ID, request ID, IP, email, timestamp, full URL, error message, span_name, http_route with IDs | n/a | same file "Dangerous Label Patterns" |
| PS-26 | M | Safe alternatives: status codes, path templates (`/api/users/:id`), bounded categories/tiers (`tenant_tier`), exemplars | n/a | same file "Safe Alternatives", Scenario 3 |
| PS-27 | M | Series = product of label cardinalities; histograms multiply by bucket count (10-20+/combination); native histograms 80-90% reduction | 15 buckets x 100 combos = 1,500 | .../cost-optimization/05-metrics-histogram-optimization.md; 06 "Total series = 4 x 100 x 10 = 4,000" |
| PS-28 | M | Label drop caveat: dropping a label that distinguishes series creates duplicates; aggregate with a recording rule instead | n/a | 06 "Removing a label can cause duplicate series, which Prometheus will reject" |
| PS-29 | M | Remediation order: fix instrumentation > relabel labeldrop (only if no dupes) > recording rules > normalize values > Adaptive Metrics | n/a | 06 "Optimization Strategies"; 07-metrics-strategies.md "Fix at Source (Recommended)" |
| PS-30 | M | Adaptive Metrics expectation and unused-metric prioritisation | 40-60% active series reduction; integrations 60-80%; `mimirtool` cardinality > 100 first; 20-60% of metrics used in dashboards | 03-metrics-active-series-optimization.md |
| PS-31 | M | Count per-label unique values / top metrics by label with PromQL or cardinality API | `count(count by(label)({__name__=~".+"}))`; `/api/v1/cardinality/label_names|label_values` | 06; .../irm/alerting/alerting-on-high-cardinality/03-count-labels-queries.md |
| PS-32 | M | Example alert thresholds for the cardinality API/alerts (illustrative, sample JSON) | label_names count > 100; metric count > 500; series > 30,000; monthly active-series budget sample 200 | .../alerting-on-high-cardinality/99-cardinality-rules.md |
| PS-33 | M | DPM > 1 per series per stack = investigate scrape interval | DPM > 1 | .../alerting-on-high-cardinality/04-usage-insights.md |
| PS-34 | M | Metric names: single-word app prefix, unit suffix, one logical quantity across labels | n/a | .../correlations-metrics-logs-traces/02-metrics-to-logs.md |
| PS-35 | M | AWS/CMDB-sourced labels: small approved set; avoid request IDs, deployment IDs, full names, timestamps, random suffixes, owner emails; required set environment, team, service, application, cost_center, owner; review cardinality after first rollout | n/a | .../aws-metrics-collection/07-cost-and-cardinality.md, 06-large-scale-multi-account.md |
| PS-36 | M | "A label exists to find series, an attribute exists to explain them"; bounded enumerations only; never sys_id, timestamps, free text, ip_address; lowercase + synonym-collapse values; `labeldrop` raw columns; fallback `unknown` | n/a | .../servicenow-cmdb-into-alloy/04-validation.md "Choosing Labels" |
| PS-37 | M | Target labels identical across Alloy cluster nodes (no node-specific label in discovery) | n/a | .../alloy/ha-deployment/03-clustering-concepts.md |
| PS-38 | M | Preserve integration-expected `job`/`instance` labels when migrating collectors | n/a | .../alloy-vs-otel-collector/04-migration-path.md |
| PS-39 | M | `cadvisor.metricsTuning.dropEmptyImageLabels` default true silently drops container_network_* on OpenShift | n/a | .../k8s-monitoring-openshift/01-overview.md |

### Traces / OTel / attributes
| ID | Sig | Rule | Threshold | Source and quote |
|---|---|---|---|---|
| PS-40 | O | Minimum resource attributes | service.name, deployment.environment, service.instance.id, service.version (examples also service.namespace) | .../migrations/apm-migration/03-telemetry-collection.md "At a minimum, Grafana Cloud recommends `service.name`, `deployment.environment`, `service.instance.id`, and `service.version`" |
| PS-41 | O | `service.name` is the most important: populates App O11y and correlates traces to logs | n/a | same file |
| PS-42 | O | Prune noisy resource attributes at collector | delete k8s.pod.start_time, os.description, os.type, process.command_args, process.executable.path, process.pid, process.runtime.description/name/version | .../alloy/instrumentation-playbooks/03-runbook-opentelemetry.md; .../otel/multistack_app_o11y/02-collector_setup.md |
| PS-43 | O | Do not enable `resource_to_telemetry_conversion`; copy only chosen resource attrs (deployment.environment, service.version) to datapoint attrs via transform | n/a | runbook-opentelemetry.md "Setting `resource_to_telemetry_conversion` to true would convert all of them to Prometheus labels, which may not be what you want" |
| PS-44 | O | `otelcol.exporter.prometheus` `disable_high_cardinality_metrics` strips IP/port attributes | n/a | same file |
| PS-45 | T | Span-metrics dimension set | service.namespace, service.version, deployment.environment, k8s.cluster.name, k8s.namespace.name, cloud.region, cloud.availability_zone | .../otel/multistack_app_o11y/02-collector_setup.md |
| PS-46 | T | Span-derived metric labels: normalise `span.name` and `http.route` (do not drop); use `http.route` template; strip query strings; drop user.id/request.id/instance.id | n/a | .../apm-migration/05-faq.md "Key attributes like `span.name` and `http.route` should be normalized rather than dropped" |
| PS-47 | T | Monitor generator series limit | `grafanacloud_instance_active_spanmetrics_series`; `grafanacloud_traces_instance_metrics_generator_series_limit_percentage_used`; error `metrics_generator_active_series limit reached` | .../apm-migration/06-troubleshooting.md |
| PS-48 | T | Metrics-generator: only SERVER/CLIENT/PRODUCER/CONSUMER spans counted; INTERNAL-only services invisible | n/a | 06-troubleshooting.md |
| PS-49 | T | Use explicit `span.`/`resource.` scope in TraceQL | ~4x faster (100 ms vs 400 ms) | .../tempo/traceql/01-best-practices.md |
| PS-50 | O | Use OTel semantic-convention names and matching types; baggage only for essential attrs | n/a | tempo/traceql/01-best-practices.md section 5; otel python guide "Use Semantic Attributes" (generic, no checks) |
| PS-51 | T | Large span attributes (HTTP bodies, SQL, serialized objects) removed/truncated | Tempo rejects trace payloads > 50 MB | 06-troubleshooting.md |
| PS-52 | O | k8sattributes metadata set | k8s.namespace/pod/deployment/statefulset/daemonset/cronjob/job/node name, pod.uid, container.name, container.image.name/tag | .../k8s-meta-monitoring-overview/03-k8s-configuration.md |

### Correlation
| ID | Sig | Rule | Source and quote |
|---|---|---|---|
| PS-53 | M/L | Prometheus and Loki labels must be identical (same SD/relabeling) so metric -> logs works | .../correlations-metrics-logs-traces/02-metrics-to-logs.md "use the auto discovery feature ... same labels as for the metrics" |
| PS-54 | M/T | Exemplars carry trace ID; Time series panel + `histogram_quantile` needed | 04-metrics-to-traces.md |
| PS-55 | L/T | Trace ID must be in log lines; Loki derived fields link to Tempo | 05-logs-to-traces.md |
| PS-56 | T/L | Trace-to-logs default tags cluster, hostname, namespace, pod; map `service.name` to `service` | 06-traces-to-logs.md |
| PS-57 | T/M | Trace-to-metrics via span metrics; tags map span attribute to label name | 07-traces-to-metrics.md |

### Attribution (cost)
| ID | Sig | Rule | Threshold | Source and quote |
|---|---|---|---|---|
| PS-58 | A/T | Tempo `cost_attribution` | `max_cardinality: 10000`, `stale_duration: 15m0s`, dimensions `service.name` | .../tempo/cost-attribution/02-cost-attribution.md |
| PS-59 | A/M | Mimir `cost_attribution_labels` (experimental) | example "namespace"; `max_cost_attribution_labels_per_user: 2`; `max_cost_attribution_cardinality_per_user: 10000`; cooldown 0s; endpoint `/usage_metrics`; alt `active_series_custom_trackers` | .../mimir/cost-attribution/02-cost-attribution.md |
| PS-60 | A/L | Loki Enterprise `custom_usage_trackers` | `max_cardinality: 2000`, `stale_timeout: 10m`, labels [job]; `purge_period: 10m` | .../loki/cost-attribution/02-custom-usage-tracker.md ("isn't officially documented") |
| PS-61 | A | Standardise team/environment/cost labels before onboarding; use cost attribution per team and set budgets | n/a | .../cost-optimization/07-metrics-strategies.md "Team-Based"; AWS 07 |

### Conflicts, contradictions and stale items
1. labeldrop of distinguishing labels. PS .../cost-optimization/06 Strategy 2 and Scenario 1 recommend `labeldrop` of `pod|pod_name` (with a duplicate-series warning). Upstream `prometheus-label-strategy` and `prometheus-cardinality-troubleshooter` skills say NEVER drop a label that makes a series unique (counter-reset merge, inflated DPM); aggregate with Adaptive Metrics instead. Upstream is stricter. Treat PS-28/PS-29 as superseded by the stricter rule for any scanner recommendation.
2. `pod` for logs vs metrics. Loki guide says `pod` is a bad index label (PS-05). Metrics skill (upstream) says keep `pod` for k8s metrics. k8s meta-monitoring `labelsToKeep` includes `pod` for logs (.../k8s-meta-monitoring-overview/03-k8s-configuration.md). Rule must be signal-specific.
3. `filename`: PS-06 says drop/normalize; PS-15 default allowlist includes it.
4. Stale: "only the Grafana Agent" supports structured metadata (04-log-metadata.md); Grafana Agent/Flow/Promtail naming throughout; "Loki ... structured metadata 2.9+".
5. .../public/grafana-cloud/app-o11y/03-dotnet.md sets `OTEL_RESOURCE_ATTRIBUTES=service_name:webmvc,service_namespace:eshop,deployment_environment:dev`, wrong OTel format (needs dotted keys and `=`). Java example is correct.
6. .../apm-migration/06-troubleshooting.md "normalize" snippet uses `merge_maps(attributes, {"user.id": "{user_id}"}, "upsert")`, which writes a literal constant; works only as a dimension collapse, not real normalisation.
7. .../cost-optimization/06 "Actual: 50,000 active series due to Prometheus limits" is unsupported; .../09-traces-optimization.md example math ($2.15k -> $750 but "Savings: $350/month"). Do not copy these numbers.
8. .../ec2-tag-label-mapping/02 example promotes the AWS `Name` tag to `instance_name`, which conflicts with AWS 07's "avoid full names".
9. Alerts on cardinality: Grafana Cloud Cardinality dashboards cannot be alerted on (PS .../alerting-on-high-cardinality/01-introduction.md); must use queries/API.
10. I did not compare against Grafana product docs. No PS text explicitly says it is stricter than or differs from Grafana docs; the only explicit disagreements found are internal to PS/upstream skills (items 1-3).

## 4. label-analyzer-skill methodology (detailed)

### What the internal guide is
/Users/rob/repos/best-practice-guides/guides/internal/loki/label-analyzer-skill/ is a 7-chapter SA runbook for operating a published skill (`loki-label-analyzer` in `grafana/skills` marketplace, plugin `grafana-cloud@grafana-skills`). It contains NO scripts and no scoring code. It references only: `logcli`, Loki HTTP API, `helm template`, Claude Code plugin commands, Grafana Assistant, Logs Drilldown, `grafanacloud-usage` datasource, three PS Ops dashboards on ops.grafana-ops.net (Customer Dashboard / Datasource Managed (Ruler) / Grafana Managed Alerts LogQL Query Insights). Use cases: health check, "why is Loki slow", pre-migration design (Datadog/Splunk/ELK), cost or stream blowup, post-incident.

### Inputs (02-prep-context.md)
Required: (1) label set per log source (`logcli labels` or `GET /loki/api/v1/labels`); (2) cardinality per label (`logcli labels <name>`, `logcli series '{sel}'`, Logs Drilldown table); (3) 3-5 sample log lines per source (redacted); (4) access patterns (which labels dashboards/alerts filter on; derive from query logs or the PS Ops dashboards).
High value: full Alloy pipeline (render with `helm template ... --show-only templates/alloy-logs/configmap.yaml`), a slow query plus its `metrics.go` line, `limits_config` (`allow_structured_metadata`, `max_global_streams_per_user`, `cardinality_limit`), Loki version (>=2.9 for SM), business goals (cost, speed, LBAC).
Env: LOKI_ADDR, LOKI_USERNAME (numeric tenant), LOKI_PASSWORD (CAP token with `logs:read`). Optional Grafana MCP with a Viewer service account in `--disable-write`.
Guardrail: do not evaluate without cardinality data; do not paste PII.

### Heuristics (public SKILL.md, read via gh api; guide 04 summarises as "Good / Acceptable / Avoid / Never")
Source: https://github.com/grafana/skills/blob/main/skills/grafana-cloud/loki-label-analyzer/SKILL.md (last commit 2026-07-24).
- Core: stream = unique label set. "Dual impact": ingest path (more streams, bigger index) and query path (a high-card label absent from the selector forces a scan of all matching streams).
- Key question: "Will this label be used in 9 out of 10 queries?" If no, not a label, EXCEPT protected correlation labels.
- Cardinality scoring table:
  - `service_name` / `deployment_environment` / `job`: any cardinality -> keep key, remediate values
  - `env` 2-5 values: good; `level` 3-6: good; `namespace` tens: acceptable
  - `instance`/`hostname` hundreds-thousands: evaluate access patterns
  - `pod` thousands + transient: demote to structured metadata (migrate selectors first)
  - `user_id`, `request_id`: unbounded, never a label
- Access-pattern checklist: on protected allowlist? used in most queries? segments data as users think? would demotion break alerts/dashboards/LBAC/correlation? force scanning more data?
- Static vs dynamic: static values cost nothing relative to scope; dynamic values must be single digits to low tens.
- Consistency: case-sensitive names, normalised values, one naming convention (snake_case or camelCase).
- Protected labels (references/protected-labels.md): `service_name` (OTel service.name), `deployment_environment` (deployment.environment), `job`. Never drop or omit from `label_keep`; fix values (UUID/ephemeral service_name -> stable service identity). `app`/`service` are aliases: align to `service_name`, do not delete without migration plan. Downstream-dependency guardrail required before any demote/rename.
- Labels-to-avoid table: pod, user_id, request_id/trace_id, raw k8s filename, unnormalised level, UUID service_name values, any dynamically-named label key.
- Performance diagnosis from `metrics.go`: 4 stages: queue (`queue_time`), index (`chunk_refs_fetch_time`), storage (`store_chunks_download_time`), execution (`duration - chunk_refs_fetch_time - store_chunks_download_time`); ideal is mostly execution time. Avg chunk size = `total_bytes / cache_chunk_req` (KB = over-split). `post_filter_lines << total_lines` = low selectivity.
- 80/20 rule: demote `pod`; add `level` and always query it (can cut 94%+ scanned); normalise label values; normalise/demote k8s `filename`.
- Quick wins also: add `container`/`workload`, `|=` over `|~`.
- Recommended common labels: service_name, deployment_environment, job, app/service (legacy), env, cluster, region, level, team/squad, source, classification; k8s: service_name, namespace, container, workload; host: instance, filename (normalised); journal: instance, unit.
- Enforcement: `stage.label_keep` as final stage always including protected labels; soft enforcement via `stage.template` injecting `unknown`.
- Sequencing (internal guide 05): normalise level -> normalise filename -> add workload -> remove pod (last, after dashboards/alerts updated) -> enforce `label_keep` (lock schema, roll out behind flagged config). Non-prod first, watch a full day for value drift.

### Scoring
There is no numeric score. Output is a per-label verdict (Keep / Evaluate / Demote / Never; emoji tiers) with Used-in-Queries and Action columns. The Assistant paste-prompt names the four grades "Good / Acceptable / Avoid / Never".

### Output format (fixed)
`## Loki Label Strategy Audit` with sections: Disclaimer (mandatory verbatim text from references/disclaimer.md, must contain "Confidential Information of Raintank, Inc."), Summary, Downstream dependency check, Label Analysis table (Label | Cardinality | Used in Queries? | Verdict | Action), Estimated Impact (stream reduction, query perf, storage, correlation impact), Cost Impact Analysis, Recommended Label Set (must include protected labels), Migration Notes (Alloy stages, dual-write). Internal guide 05 adds a 3-doc handoff: `label-audit.md`, `label-audit-summary.md`, `label-migration-plan.md`.

### Cost impact (references/cost-impact.md)
Label hygiene alone gives $0 direct ingest savings (billing is compressed bytes); it reduces streams/index/query cost. Scenarios: A labels only (streams -65 to -90%), B + approved debug/trace drop (~15-30% volume, customer-approved, env-scoped), C + log-line compaction (additional ~5-15%; Istio example 38% ceiling). Monthly GB = bytes/s x 86400 x 30 / 1e9. Measurements (Grafana Cloud usage datasource): `grafanacloud_logs_instance_active_streams`, `grafanacloud_logs_instance_billable_bytes_received_per_second`, `grafanacloud_org_logs_overage{monetary="true"}`, `sum by (<attr_label>) (grafanacloud_logs_instance_attributed_bytes_received_per_second)` (unattributed share shows as `__missing__`; Cloud attribution uses up to two customer-configured labels). Verification metrics in internal guide 05: `loki_ingester_streams_created_total` rate down, `loki_distributor_lines_received_total` unchanged, chunk size up, p95 latency, grep dashboard JSON for removed labels. Most `loki_*` metrics are not visible to Cloud customers: use `grafanacloud-usage` and PS Ops dashboards.
Log-line optimisation (references/log-line-optimization.md): strip inline timestamps (~30-34 bytes, ~6%), `stage.decolorize`, duplicate level, JSON nulls/placeholders/empties.

### Reusable by an automated estate-wide scanner
- Deterministic checks that map directly from the skill/guides, all read-only API:
  - Loki `GET /loki/api/v1/labels` + `/label/<n>/values` (or `logcli series --analyze-labels '{}'` equivalent via `/loki/api/v1/series`): per-label unique value count and stream count; compare to bands (<=6 good, tens acceptable, hundreds-thousands evaluate, thousands/unbounded flag).
  - Flag-by-name: pod, filename, user_id, request_id, trace_id, case-variant duplicates (`Level` vs `level`), level value set not in {info,warn,error,debug,...}, UUID-shaped `service_name` values, absence of `service_name`/`deployment_environment`/`job`.
  - Total active streams vs limit: `grafanacloud_logs_instance_active_streams` against `grafanacloud_logs_instance_limits`.
  - Unattributed share: `__missing__` in attributed bytes metric.
- Metrics twin: per-label unique value counts via Mimir cardinality API `/api/v1/cardinality/label_names|label_values` and TSDB status; thresholds 100/1,000 values, 1,000+ series per metric; histogram `_bucket` amplification; churn (`created/removed`).
- Traces: `grafanacloud_instance_active_spanmetrics_series` and `grafanacloud_traces_instance_metrics_generator_series_limit_percentage_used`.
- Judgement-only (not scannable without access patterns): "used in 9 of 10 queries", downstream dependency (needs query logs/dashboard JSON). A scanner should emit these as "needs access-pattern input" rather than a verdict.
- Do not copy: the Disclaimer text (Raintank confidential) is part of PS report output, not a scanner concern.

### Upstream adjacent skills worth reading before building (outside this repo)
`grafana/skills` `skills/grafana-cloud/prometheus-label-strategy/SKILL.md` (cardinality bands: env 2-5, job 5-50, cluster/region tens, namespace tens-low hundreds, instance hundreds-low thousands evaluate, pod keep, path only templated, version/image_tag churn -> info metric, user_id/request_id/trace_id/error_message never; histogram multiplier bucket+3, 11 default buckets -> 14x; "The One Rule" never labeldrop distinguishing label), `prometheus-cardinality-troubleshooter` (tsdb status endpoint, any label with >10K unique values is almost certainly a bug, growth > a few % per day red flag), `adaptive-metrics`, `cost-management`, `dpm-finder`. Only partially read.

## 5. Gaps

- Profiles: `/Users/rob/repos/best-practice-guides/guides/public/pyroscope/` is empty. Only a .NET env example `PYROSCOPE_LABELS=namespace:eshop,environment:dev` in .../grafana-cloud/app-o11y/03-dotnet.md. No profile label guidance.
- Tempo/trace attributes: no guidance on span attribute cardinality, dedicated columns, `generic_dimensions`, or which attributes to index; only span-metrics dimension examples and TraceQL scoping.
- OTel semantic conventions: one-line exhortations only; no registry/Weaver, no attribute-placement rules (resource vs span vs metric), no compliance checks. OTLP-to-Loki index label promotion (Grafana Cloud default promoted resource attributes) not covered.
- Adaptive Logs / Adaptive Traces: cost-level only (Strategy 1), no label/attribute requirements or exemptions, no guidance on how labels affect Adaptive Logs patterns.
- Mimir/Prometheus: no limits discussion beyond sample alert JSON (no per-metric series limit, `max_label_names_per_series`, label value length), no churn thresholds, no recording-rule label guidance.
- Structured metadata: no cardinality/size limits, no guidance on SM key count, bytes (only `total_bytes_structured_metadata` field described).
- K8s Monitoring Helm: only OpenShift and meta-monitoring pages touch labels; no recommended `labelsToKeep`/`podLogs` label policy for general use beyond the legacy Agent allowlist.
- No machine-readable assets: no scripts, schemas, CSVs or code for label analysis anywhere in the repo (`tools/` is lint/build only).
- No freshness signal (single squashed commit); the internal skill guide's own claims (e.g. "Alloy rather than legacy Agent") are consistent with upstream, but several public guides are Grafana-Agent-era.
- Upstream SKILL.md changed after the internal guide was written (protected labels, mandatory disclaimer, cost-impact scenario cards are not described in the guide's 01-intro). Re-read upstream, not the guide, for current behaviour.
