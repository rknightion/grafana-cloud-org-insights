---
id: GCI-0133
title: >-
  Publish an org-wide AI token cost model: monthly collector view plus dashboard
  tab
status: Done
assignee:
  - '@codex'
created_date: '2026-10-12 10:04'
updated_date: '2026-10-15 01:34'
labels:
  - ai
  - dashboards
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/ai-token-packet/packet.md
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/telemetry/ai-120day-schema.json
priority: high
ordinal: 170000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision D-TOK23 (Rob, 2026-10-12). Rebuild the internal BI token-pricing analysis for the org a deployment covers, from data the org can reach. A T2 collector view computes calendar-month aggregates per org and per stack (seats from Grafana's active-user counts, tokens, users over the allowance, modelled seat and overage cost, billed overage for reconciliation) from grafanacloud-usage metrics. An AI dashboard tab renders the view, with live per-user tables read from the vendor per-user token metric (emails are displayed, never stored, labelled or linked). Pricing inputs (seat price, overage per 1M, monthly allowance) are dashboard variables. System pool, cache/input/output splits, internal model cost and sessions are stated as unavailable to the org. Do not copy the BI defects: one seat definition everywhere, the stack filter applied to every panel, and billing period distinguished from calendar month. Analysis: codex/scratch/bi-token-dashboard/analysis.md (gitignored).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Collector current/monthly org and per-stack aggregate views have empty schemas and mechanically derived VIEW_INPUTS; no email, user name or identity in any stored field, metric label or log.
- [x] #2 AI dashboard renders aggregate views plus transient live per-user tables, configurable seat price, overage rate, personal allowance and system pool; historical rows show their captured allowance basis, and coverage gates pass.
- [x] #3 Contract tests prove monthly-gauge dated MTD capture, org-wide identity deduplication and allowance deduction, rollover quarantine, separately dated customer-only BI backfill and native observations without double counting, and missing input remains absent rather than zero. Prospective history is accepted; no pre-existing exact closed-month feed is required.
- [x] #4 Reconciliation panel compares modelled org overage with separately qualified native billed-overage preview at a common capture time; absent billing data stays unavailable and period semantics are labelled.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop23 root accepts read-only bounded design packet, not implementation. Full build parks on B-TOK-LABEL/TIME/POPULATION/ATTRIBUTION/BILLING: approved robk four-metric 120-day reads returned zero series with 12-series control, so no live labels or producer/calendar/seat/billing/per-stack attribution witness. No synthetic labels or scaffold substitute. Resume R-TOK23 only after positive same-authority schema and bounded producer semantics witness plus serial field/link prerequisites. A different tenant/evidence surface requires an explicit grant.

Reviewed prospective implementation: separate default-off T2 ai_billing aggregate-only write-stack GET source, separate ai_cost view pillar, conditional bounded aggregate state history after publication admission, separate source-keyed BI bootstrap/native snapshots with no cross-source merging. Captured-month/source-period status distinguishes observed MTD from final invoices. Add configurable live dashboard model and separately labelled captured-allowance history; per-stack token/membership/excess observations carry no allocated seat currency. Native billed-overage comparison required. Correct legacy lifetime/high-water identity panels. Root corrections to independent review are in /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261014/backlog-zero/ai133/prospective-plan.md. Root owns shared wiring, tracker, integration and live writes; workers own bounded files only.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root engineering dispositions: mutable allowance must use upstream live aggregate recomputation while the persisted default-40M snapshot is separately labelled, contingent on witnessed bounded query semantics; never recompute arbitrary excess from a single stored threshold. One proved active-user seat definition, transient-email live tables only. A bounded ownership-omission correction for scan.py and budget/provenance wiring is necessary for the already-approved new T2 input, not new product/source authority; do not implement that correction before source proof. No org-only reduced-scope build accepted as full AC. Attempt count zero; no code or gate claimed.

2026-10-13 source-contract correction: versioned retained source describes the per-user AI token metric as a current-month gauge, contradicting the earlier unconditional non-resetting-counter premise. No deployed producer/version or positive schema witness has been established. Preserve the monthly-model objective, privacy fences and attempt count zero; do not implement delta or range-maximum arithmetic from either unverified assumption. Before implementation, resolve the deployed period/type contract, choose one proved seat population, and prove shared-user allowance attribution and billed-period/currency reconciliation. AC3 requires owner-consistent revision to test the witnessed producer contract; it is not satisfied by changing the test to match a guessed algorithm. Org and stack current-month active-user quantities do not automatically establish licensed seats. No new product scope follows.

Owner 2026-10-14 names BI dashboard mitn6pr in bi-ops as the build inspiration, authorizes read-only inspection and customer billing discovery, requests configurable customer pricing inputs. Use the dashboard data scope; no broader AI analysis required. Internal-only sections require a supported customer source or explicit unavailable handling.

Owner2026-10-14: omit internal-only BI sections entirely; generic seatprice20USD with customer override14USD, remainingdefaults2USD/million,40Muserallowance,500Msystemallowance all configurable. Exact historical monthly totals REQUIRED before shipping; snapshot-only currentmonth fallback is not accepted. Fresh customer positive data and pinned producer contracts captured; midnight/first-hour historical reads remain unchanged into02UTC and do not bind exact closing totals. No partial AI feature deployment authorized by this fallback proposal.

2026-10-14 bounded authorized read-only BI/customer investigation complete. Original BI dashboard available through explicitbi-ops; positivecustomer172identityseries/77categoryseries/currentmonthlyuser167+service1/systemallowance500M. ExactBI hourlySQL calendar aggregates July/Aug/Sepclosed+OctMTD returned7count-only rows without identity values, privatecomparison under /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261014/backlog-zero/ai133/exact-monthly-comparison.json. Current pinned producer source describes monthly gauges; observedcustomerhistory dropsOct1 07UTC, notmidnight. Historicalper-user billing excludes some investigation/agent usage beforeOct1 unlike rawBI hourly category data, so exactBI model cannot safely reconstruct from nativebillinggauges alone. A reliablecustomer-accessible exacthistorical feed/producer-period contract remainsrequired before shipping; no snapshotfallback or newBI credential/source route grant. ExistingAI identity panels retain legacy lifetime wording/high-water queries; correct that within this task using witnessed monthly-window semantics. Genericseat20USD/customer14USD,2USD/million,40Mpersonal/500Mgeneric-system configurable requirements retained; internal-only BI sections omitted. No implementation/featuredeployment claimed.

Owner2026-10-14 22UTC supersedes exact pre-existing historical feed shipping prerequisite: prospective aggregate history from now is accepted, and customer-only one-time BI aggregate backfill into S3 is authorized. Billing start October1 is an owner hypothesis, not a verified source fact. Preserve all aggregate privacy/source/role fences, configurable defaults20USD generic/14USD customer,2USDperM,40Mpersonal/500Msystem; omit internal-only sections. Reconcile monthly gauge period/cutover contract and historical default-basis versus live-variable model before code. No BI runtime credential or collector POST grant follows.

Implementation attempt1: separate default-off T2 ai_billing source/input and three aggregate AI cost views, conditional bounded source-separated history, configurable live and captured-history prices, captured allowances, direct transient identity/category tables, native preview reconciliation and corrected lifetime/high-water captions. Shared wiring,33input budget/8existing provenance combinations and mechanically derived dependencies integrated. Current customer source proved through14actual guarded GETs with existing stored reader; no scope/credential changes. Native and customer-only October BI completed-hour aggregates match; prepared71count-only rows, NO S3 write. Infinity backend validates14/20USD repricing and negative-input absence; original bad scientific filter and reconciliation failures retained. Focused27tests/4subtests and91hydrate/budget/8475subtests pass; limited-side-write guard mutation fails correctly and restored candidate passes. Full final gate, CodeRabbit, source commit/release and deployment remain pending; do not call feature shipped.

Final source validation: corrected justcheck exit0,2834tests/29128subtests/2existingempty-fixture skips and45OpenTofu tests. Test-runner RSS628.7MiB is not collector/ECS memory proof. Initial full gate failed six obsolete lifetime/tab/input-count expectations; changed only for the owner-approved scope/monthly contract/+8provenance budget and reran all. CodeRabbit complete all33initialfiles/1major corrected; delta complete0 on5changedcode/test files. Subsequent remaining corrections were declarative tab/budget expectations and captions, no unreviewed logic. All failed outputs retained. Source staged37ownedpublic paths, no customerdata/SQL/credentials/privateevidence uploaded; no featuredeployment yet.

Both consumers now v0.15.0 exactd5af source, both16scoped applies0, all6live definitions/schedules/effectiveIAM/filter/retention/CIoff/originalobserverbirth verified andbothresource/outputNOOP. DevnaturalT1fresh exactimageexit0/sourcehealthtrue7stacks/0fail. CustomerfullownerT2originaltaskrunning, no duplicate. Customer-onlyBIseedwritten/readback1aggregate record withoriginalcutoff/sourcehash andfreshinventory316. Found build-only default-off optionalAIobject404assembly failure; fail-firstreproduced, nowFileNotFoundonly explicitunknowntext withnoobjectquery, permissions/transportremainfatal. Narrow3tests/4subtests andCodeRabbitcomplete0all2files; fulljustcheck0/45Tofu tests, unchangedruntimecollector/IaC. Patchsourcecommit/CI andfinalAIpublication/customerownerproof remainpending.

Completed v0.15.1 rollout on dev and customer, immutable source e5b2c68ecdf7bd406abb4d6ea5f8ffa8911eb059 and infrastructure image-pin commit 17f11312aa31d22cd911c6007e6fb54f62c5a5b2. Both exact CI/release/publisher gates passed; public image platforms/source/version and eight Cosign signatures verified. Six task definitions and schedules, effective IAM, outcome exclusion, retention, Container Insights disabled state and original observer identity were read back; both consumer follow-up plans have all resources/outputs unchanged.

The first AI-owning customer T2 on v0.15.0 passed 316 scannable stacks, zero failures and healthy scan/source status. Its collector, gather, state schema and IaC are byte-identical in v0.15.1. Final v0.15.1 T1s also passed: dev seven/customer316, zero failures, exact images and healthy sources. Versioned S3 scan/history/three AI views passed checksum, task-window, content and mutation checks. History has two separate dated October MTD observations, original BI record unchanged, never summed. Billing start and exact closed-month totals are not claimed. The minimized inventory evidence cannot independently rederive Region; immutable view binding/shape and all other fields passed. Trace labelling remains partial at298/316, with18 missing_input observations; it clears its source floor without proving full trace coverage.

Both saved AI dashboards and frontend renders passed. Generic seat default USD20/customerUSD14, overageUSD2 per million, personal40M and system500M allowances configurable; captured historical allowance remains explicit. Saved customer query and frontend controls produced USD2338 at14, USD3340 at20 for167 observed user-category identities, and no result for negative pricing. Separate BI/native history and categories visibly render. Dev honestly shows No data and absent-snapshot text. No identity table queries/captures or stored identity rows were introduced. Repeat deployment price override on rebuilds; rebuild missing snapshot panels after first accepted publication.

Final source just check:2835 tests and29128 subtests passed, two existing empty-fixture skips,45 OpenTofu tests passed. Source and operator CodeRabbit reviews completed with findings resolved; final operator delta has zero findings. Operator controls reject plan/schema/role/AI-env/receipt drift and compare freshly rendered binary-plan JSON while preserving configuration-reference set semantics. All failed attempts retained privately. Full receipts: /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261015/ai151/release-receipt.json ; /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261015/ai151/native-proof/terminal-result.json ; /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261015/ai151/runtime-proof/verified.json ; /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261015/ai151/dashboard-verification/completion-receipt.json . Task association is timestamp/window based, not direct scan-to-ARN attestation; no collector memory proof is claimed. GCI-0137 (Adaptive metadata and supported Logs opt-out research) remains Parked as explicitly retained by the owner.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Delivered and validated the configurable AI cost dashboard and aggregate-only prospective history on dev and customer. Customer-only BI backfill is separately dated from native MTD observations. Defaults20USD, customer14USD; source/privacy, missing-data and rollover boundaries preserved. Exact release/CI, both deployment readbacks and no-change plans, first customer AI T2, final v0.15.1 runtime scans, backend arithmetic and rendered dashboards passed. Evidence and qualified limitations are recorded above.
<!-- SECTION:FINAL_SUMMARY:END -->
