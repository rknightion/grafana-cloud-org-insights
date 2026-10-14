---
id: GCI-0132
title: >-
  Enable the library-panels reader and the auditing retention policy on the
  customer deployment
status: Done
assignee:
  - '@codex'
created_date: '2026-10-12 09:48'
updated_date: '2026-10-14 18:06'
labels:
  - customer
  - rollout
dependencies: []
priority: medium
ordinal: 169000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision D-CUST23 (Rob, 2026-10-12). The customer consumer stays on v0.11.0 source. Add library-panels to the provisioner and scan product reads and set the expected retention policy {kind="auditing"} minimum 120d, both already running on dev. One provisioner run adds only library.panels:read and folders:read on folders:* to the existing reader role (no re-mint), then one saved-plan apply and one T2.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dev readback shows library-panels and retention-policy views for every live dev stack before customer changes
- [x] #2 After the approved initial repair and bounded fix-forward, all customer readers retain basic-role None, durable SA/role/token IDs, live token sets and SSM metadata; changes are only library folder-read pairs plus separately witnessed reconciliation of an already-enabled Synthetic opt-in to its single regex-valid live datasource UID and empty-scope probes read
- [x] #3 Customer overlay changes are limited to the two product-read lists and expected auditing retention policy, with the approved released source/image update; exact scoped saved plan applied and final targeted plan has no resource or output changes
- [x] #4 One original customer T2 exits 0 with version-specific native byte-bound publication; library-panels and auditing policy views represent every scannable stack or provide explicit unavailable reasons
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-CUST23 implementable packet: after GCI-0119.15 (prove labelling live on dev) is accepted, fresh STS and dev view/live-inventory readback, customer pre-role/token/SSM witness, exactly one provisioner adding only two folder-scope read pairs with zero mint/rotation, post-role readback, isolated overlay changes to two read lists and auditing 120d expected policy, reviewed saved targeted plan exact apply, exactly one T2 after no active/imminent natural run, adopt ARN on timeout, immutable publication/view evidence and no-change plan. Source stays v0.11.0; no schedule/policy/bucket writes; fix forward only.

2026-10-14 owner replaced the natural 48-hour prerequisite with one successful fresh full-estate dev scan and authorized autonomous fix-forward and manual scans. Resume only after that revised dev proof. Use the actual current released source, never downgrade to the historical v0.11 wording. Preserve durable reader SA/role/token IDs and SSM versions; existing recorded transient Admin repair authority is separate and must be cleaned up. Expected auditing policy assesses 120d, it does not change customer Loki retention.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: zero implementation/live mutation attempts; dependency parked on GCI-0119.15 (prove labelling live on dev), whose historical natural task/memory artifact proof failed. Dev library inventory and policy-status views each publish six rows; policy statuses unreadable, not compliance. Customer untouched. Resume at fresh STS and required dev/live inventory witnesses after prerequisite accepted.

loop23 evidence-boundary clarification: the retained dev view reads show six rows against the latest captured T2 scan population at 2026-10-12T04:37:44Z, not an independent fresh Grafana.com inventory witness at read time. AC #1 remains unchecked. After GCI-0119.15 (prove labelling live on dev) is accepted, resume with fresh inventory and both view readbacks before any customer mutation; current policy statuses are unreadable, never compliance.

2026-10-13 owner explicitly preserved the existing 48-hour natural labelling prerequisite while authorizing other deployments now. Library reader/auditing retention rollout remains dependent, no scope expansion or customer reader/policy mutation from the observer/query-image updates.

2026-10-14 single fresh manual dev prerequisite accepted under owner regrade, preserving explicit execution-sampled memory boundary and original 3-day verifier unproved. Fresh independent dev visible inventory/library/retention row sets match6scannable stacks, AC1proved; unknown retention statuses are not compliance. Customer before-reader snapshot is read-only in progress; no customer apply or reader repair yet.

2026-10-14 customer v0.13.6 library/auditing consumer deployed: exact image a45bbb954e7e7fe5796ba8ce490cba9525950e114287272b8d8fdb7ceaba6dfc; exact saved plan1093219b82e7754edbea7b7ad69cd1ece3fbc183033d25b52c5e8297627c5cb9 applied0 and physical six-definition/schedule/effective IAM/filter/retention/observer-birth/customer-CI-off readback passed. Scoped overlay adds only two library opt-ins and expected auditing120d assessment plus derived digests. Original provisioner task53e004b27159430a9b1e3af6cb786d23 started12:18UTC with no-prune remains running; latest fully paginated15:12 logs show256/316 patch starts and no cleanup warnings, not completion. Before snapshot complete316/316 existing durable readers/basicNone, folders read already held; expected only library.panels:read@folders:* addition. AC2 awaits after snapshot/token/SSM preservation and independent full transient Admin absence; AC3 awaits final no-change plan; AC4 awaits one original-ARN customer T2/versioned scan and views. Root-local proof helper review caught and fixed false retention compliance acceptance by re-deriving output from immutable Loki config through exact released compositor; no actual Loki retention changed.

2026-10-14 initial customer provisioner exited1:307 repaired,7 service-account-list HTTP500 and2 transient-Admin-create HTTP500. Original task/logs retained. Fresh proxy reads subsequently200; authorized fix-forward used one bounded root batch targeting only nine missed stacks through the exact released operator, with working-identity/no-durable-mint, existing-role-UID, exact library-pair delta, existing-SA assignment and no-unrecorded-cleanup guards. All nine final probes passed. Independent full316 after-read audit confirms every reader basicNone/library pair, all SA/role/token IDs/live token sets/SSMversions and timestamps unchanged, no transient Admin matches. One additional existing Synthetic opt-in was reconciled by the standard initial operator: one same-token exact200 uniquely discovered regex-valid Synthetic datasource UID query pair and empty-scope probes read, plus automatic effective-read scope. Both Synthetic opt-ins were already enabled before library, under standing S-SM/D-CUST11 authorization; no new flag, wildcard or family grant. Factual scope is library additions plus that separately witnessed standing reconciliation, not globally only-library deltas. Strict final-reader-delta receipt binds all316 snapshots and witness. One manual customer T2 started16:38UTC after schedule/active guards; its original ARN is retained. AWS CLI credential retrieval failed around16:46 while task was running; root cloud validation stops pending user login refresh, no restart/retry. Last accepted T2 publication verifiedOct13 04:13UTC,36.5hours old; stale alert remains accurate until successful fresh publication/alert clearance. No final no-change or fresh customer publication proof yet.

2026-10-14 final acceptance: owner-authorized fix-forward and standing S-SM/D-CUST11 reconcile the historical one-run/only-library expectation with actual audited behavior, without a new family, query wildcard, token rotation or scope authority. Original failed task and nine bounded corrections retained separately. Full316 final reader/cleanup audit and strict single-existing-SM witness comparator pass. Original manual customer T2 ced2659ef8f249398fd554ae829dd210 stopped17:27UTC exit0, immutablea45/sourcee791,316scannable/0failed, scan and allsource health true, collection2787.93seconds. Native30MB timestampedS3 object is unique in task window, version-specificSSE-S3/fourpart lengths+multipartMD5 binding matches; altered byte refuses. Original singlepart checker failed closed and is retained; original natural verifier untouched. Two authentic versionedT2 views have matching timestamp/inventory and byte checksums; library counts316/316 and auditing assessment80compliant/236unreadable, no actual retention write. Exact released compositor re-derives retention rows from immutableLoki input. Final customer targetedplan resource/outputNOOP; staleT2 rule exactUID currentlyinactive/healthy/notpaused evaluatedafterpublication, no rule/routingchange. Exact sourcefullgate/45Tofu/current+publishedhistory identifiers/em-dash passed; exactinfra/sourceconsumer startup/projection/config checks passed. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261014/tempo142/customer-library/.
<!-- SECTION:NOTES:END -->
