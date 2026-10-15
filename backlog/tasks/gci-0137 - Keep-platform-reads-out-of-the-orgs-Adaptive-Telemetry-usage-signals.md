---
id: GCI-0137
title: Keep platform reads out of the org's Adaptive Telemetry usage signals
status: In Progress
assignee:
  - '@codex'
created_date: '2026-10-13 17:19'
updated_date: '2026-10-15 11:51'
labels:
  - adaptive
  - cost
dependencies: []
references:
  - collector/sources/signal_inventory.py
  - collector/sources/label_inventory.py
  - collector/sources/label_risk.py
  - collector/sources/dataplane.py
  - collector/sources/loki_volume.py
  - collector/sources/capability_adoption.py
  - collector/sources/usage_insights.py
  - >-
    https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/manage-recommendations/understand-recommended-rules/
  - 'https://github.com/grafana/mimir/pull/14474'
priority: high
type: task
ordinal: 171000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Platform reads must avoid altering Adaptive Telemetry recommendations. A bounded customer incident investigation found only metadata reads by this collector; causality is unproved. Private incident identities and token metadata remain outside this public tracker.

Metrics: the documented empty __ignore_usage__="" matcher preserves results and excludes marked PromQL queries from Adaptive Metrics usage. Metadata label, series and cardinality tracking/suppression require an exact contract.

Logs: research recommendation tracking and any supported read opt-out. Traces: establish the current product model and record limitations instead of inventing a workaround.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every PromQL selector the collectors send to an org stack carries __ignore_usage__="", with a test that fails if a new data-plane metrics read omits it
- [ ] #2 The metadata endpoints in use (label values with match[], series, cardinality API) are classified as counted or not counted toward Adaptive Metrics usage, with the evidence cited, and covered where the matcher is accepted
- [ ] #3 Adaptive Logs: the docs research outcome is recorded; either an opt-out exists and every Loki read uses it, or none exists and the affected reads are listed
- [x] #4 Adaptive Traces: whether any opt-out exists is recorded; if none, the Tempo reads that could register usage are listed as a known gap
- [x] #5 CAPABILITIES.md states what the platform does and does not do to an org's Adaptive Telemetry usage signals
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Construct marked PromQL literals with fail-first HTTP-boundary proof; independently research metadata/Logs/Traces contracts and document unknowns. Run independent review, CodeRabbit and just check, then exact-source CI/release. Upgrade dev/customer immutable consumer pairs preserving configuration, review/apply saved targeted plans and verify live readback/no-change. Freshly pulled donor task duplicates provenance ID; backlog doctor safely renamed it to GCI-0137. Interim sanitized GCI-0136 is archived through CLI, preserving its evidence.

2026-10-15 owner explicitly accepts query-result differences and authorizes X-Loki-Disable-Pipeline-Wrappers:true through dev/customer rollout. Add header at all explicit Loki collector request seams, preserve non-Loki/auth/GET/route/privacy boundaries, prove HTTP-boundary regressions, review and run gate. Ship exact source release and immutable consumer images; scoped reviewed plans, dev then customer. Compare safe aggregate/metadata results and fresh full-estate source health. This acceptance changes result-equivalence requirement only; metadata applied-config classification remains separate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Leads from ~/repos/adaptive-telemetry-pm/knowledge/adaptive-logs/README.md: Adaptive Logs counts queries per pattern by query hash over 15 days (sampled), and already excludes broad bytes_over_time/bytes_rate queries from the recommendation algorithm (grafana/log-template-service pkg/recommendations/recommendations.go). No ignore-usage opt-out is documented there; check that source for one before concluding none exists. Per-metric Adaptive Metrics usage detail, including dashboard_uids, is at GET <prom url>/adaptive-metrics/api/v2/segments/default/metrics/<metric> (basic auth <prom instance id>:<CAP>); use it to verify the matcher works by watching usages_in_queries on a test metric.

All 27 expressions differ only by the empty ignore matcher. Fail-first boundary guard then 26 focused tests/351subtests pass; full final gate exit0,2747tests/27920subtests/2skips,37Tofu. Independent review PASS, CodeRabbitcomplete0/allfourfiles. Live marked staff query exact200/vector/fourpositive rows. Metadata usage tracking unknown; Logs opt-out unestablished; current official Traces model does not use query usage. Source hashes unchanged through full gate. Two donor commits newly fetched AFTER history-ref snapshot contain private identifiers; narrow exact-commit history check proves a release blocker. Current task sanitized; no source push or live rollout until published-history correction is authorized and verified.

Final integrated source candidate includes all27markedPromQL expressions plus default-off observer. Final semantic checks2783tests/27921subtests/2skips/41Tofupass, formatting/lint clean, CodeRabbitcomplete0. Root history repair revision2 prepared and verified: only incident-bearing task text/duplicateID differ; original research notes and all non-task bytes preserved. Await explicit atomicforcewithlease approval on originmain and releaseplease branch before publishing source/release/consumer rollouts. No ECRpush/apply or customer mutation occurred. Fresh existing ECR policy witness isMUTABLE for both consumers; publisher now uses unique128bitnonce tags and immutable verified runtime digests without changing ECR policy. Metadata/Logs tracking ACs remain unproven, never treated as absent.

Source 778dcd4794802cf63763ae07d6d31d8694069207 shipped v0.13.0: all27PromQL selectors carry empty ignore-usage matcher with fail-first real HTTP boundary guard. CAPABILITIES documents exact supported/unsupported tracking, current official Adaptive Traces model does not use query usage. Approved history correction completed and required current/origin history gate clean. Metadata and Logs tracking/suppression remain unproved; AC2/3 stay open. Dev/customer rollout continues on fix-forward Container Insights preserving release.

Adaptive Metrics PromQL suppression deployed to dev and customer at release0.13.1 source b5c2590f5c7db79e9ddb9fe2f09cd164f373249d. Both exact saved plans independently classified as image/default-off env only, applied, all5definitions/schedules and effective scheduler IAM read back equal, targeted no-change plans verified. Dev Container Insights preserved enabled. Customer first apply refused before mutation due natural task active; fresh zero-active witness and fresh reviewed plan preceded successful retry, original refusal retained. Exact merge CI38474744391 all4requiredsuccess, stable publisher38474745277/publicOCI twoarches/Cosign sourcebinding verified. AC1/4/5 done; metadata tracking and Logs opt-out AC2/3 remain externally unproved, now explicitly Parked after completing deployable work. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261013/adaptive/release131/.

2026-10-14 bounded primary-source followup: pinned Mimir request logger emits param_<actual request key>, configured usage-service ingestion selects/extracts param_query and excludes ignore marker. Currentcollector metadata requests use match[]/selector rather than query, so the reviewed source pipeline does not interpret them as PromQL query usage; appliedcustomer pipeline/version remains unwitnessed, no global deployed-suppression claim. Exactcollector route census finds only UsageInsights proxy LogQL query, on its dedicated datasource, with instance_id guard; no nativecustomer Loki log-line query is implemented. Reviewed log-template recommendation code excludes bytes_over_time/bytes_rate and overlybroad queries from recommendations, which is NOT a per-request optout or proof of no tracking. No supportedLogs optout established; no invented flag or source change. Retain originalmetadata/Logs acceptance open pending authoritative applied contract. Qualified privateproof paths /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261014/backlog-zero/adaptive137/. PromQL shield remains in deployed v0.14.0.

2026-10-15 research refresh: current official Adaptive Logs docs still state datasource-wide query evaluation regardless of origin and expose no supported per-request opt-out. Fresh log-template-service observation API accepts tenant/streams/query/sampling ratio; recommendation exclusions occur after observation. Fresh Mimir logger and usage-service configuration match retained source evidence: only param_query enters the reviewed PromQL usage pipeline; collector metadata uses other parameters. Exact applied customer configuration/version remains unverified. Do not invent a matcher or flag; authoritative applied-config/service-owner confirmation is the remaining useful evidence. Private source links remain outside this public tracker. Existing PromQL protection stays unchanged.

2026-10-15 deeper upstream followup found a concrete candidate missed by prior searches: LokiDisablePipelineWrappersHeader is X-Loki-Disable-Pipeline-Wrappers. Public Loki PR12327 introduced propagation; PR12903 confirms request-level disabling changes results and separates cache keys. Private pinned enterprise source shows Adaptive counting wired via pipeline/extractor wrappers. It also corrects the previous statement that byte-range query exclusions occur only after counting: wrappers skip bytes_over_time/bytes_rate and omit counting for special UI source tags before recommendations. Those tags are not generic collector identity and will not be spoofed. No header deployed: Cloud propagation/applied version and result-preserving suitability for Usage Insights remain unproved. Private seven-file pinned source/test evidence at /Users/rob/repos/grafana-cloud-org-insights/codex/adaptive137-20261015/receipt.json. Next useful witness is the service-supported contract for this exact header/path, not another search for an unnamed flag. Metadata applied-configuration gap remains. AC2/3 stay open.

Owner decision: query-result differences no longer block adopting the upstream wrapper-disable header; evaluate any problematic differences during dev/customer rollout. No grant to spoof UI query tags, broaden routes/scopes or persist raw logs/identities.

Owner-approved header implementation covers all explicit collector Loki seams, including scoped Usage Insights shared and legacy request paths; mixed-signal boundary tests prove absence from other signals and preserved authorization. Six regressions failed first, focused251tests276subtests passed. Full justcheck2847tests29128subtests2existing skips45Tofu plus identifiers/history/no-em-dashes passed. CodeRabbitcomplete0all14files. Fixed-time baseline/header comparisons for views, requests and request_errors on both deployed write stacks returned equivalent valid aggregate responses. This proves observed compatibility, not proxy forwarding or Cloud counting suppression. Preparing v0.15.2 and exact-source immutable dev/customer rollout.
<!-- SECTION:NOTES:END -->
