---
id: GCI-0030
title: >-
  Publish per-stack expected-retention-policy status, compliant as well as
  non-compliant
status: Done
assignee:
  - '@loop3-root'
created_date: '2026-09-23 08:35'
updated_date: '2026-09-30 22:51'
labels:
  - retention
  - dashboards
dependencies:
  - GCI-0022
priority: high
type: enhancement
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Requested by Rob on 2026-09-23 for a consumer deployment's audit-retention finding. Today the Logs retention tab shows a gap COUNT (gcinsight_risk_retention_policy_gap_stacks) and a 'Configured retention policy gaps' table listing only stacks BELOW policy (view risk_retention_policy_gaps). Nothing lists the stacks that DO satisfy the configured expectation, so a reader cannot see the compliant set or tell compliant from unmeasured.

Add a per-stack status view produced by collector/pillars/retention.py alongside the existing three, one row per stack per configured expectation entry, with a Status column taking exactly three values: compliant, below policy, unreadable. A stack whose Loki dataplane or plugin route failed is unreadable and never compliant or below policy (GCI-0022 AC9 semantics). Add a table panel for it on the Logs retention tab in bin/dashboards.py, beside the existing gap row, and a compliant-count stat so the coverage row reads measured / compliant / below policy / unreadable.

Generic mechanism only: no expectation value, selector or stack identity is hardcoded, and the selector stays a view column, never a metric label (GCI-0022 AC6). An empty expectation list produces no status rows rather than a table of false compliance. Any new metric is declared in budget.py CATALOGUE.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A new view lists every measured stack against each configured expectation entry with Status exactly one of compliant, below policy or unreadable, and its schema is declared in VIEW_SCHEMAS
- [x] #2 Unreadable stacks are never reported compliant or below policy, and an empty expectation list yields no status rows
- [x] #3 The Logs retention tab carries the status table and a compliant-count stat beside the existing measured and gap stats, and the generated dashboards match a fresh render
- [x] #4 No expectation value, selector or stack identity is hardcoded, the selector is never a metric label, and any new metric is in budget.py CATALOGUE
- [x] #5 Released as a signed auto-RC whose digest a consumer can pin
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement generic status view and aggregate coverage metrics with unreadable kept separate; test the mixed readable/unreadable case, render dashboard, run just check including private identifier pattern, review, then release by exact SHA and signed auto-RC.

loop3 P-0030-a1 owner fresh grant: recover preserved patch read-only, reproduce selector-priority, malformed-stream and absent-status-view regressions; correct one retention contract; full gate and CodeRabbit candidate, root landing/CI/release.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 8 parked by owner before commit or push. Local staged implementation and unstaged attempt-4 regression tests remain in checkout. Two new tests currently fail: malformed retention_stream leaks a partial row; dashboard assembly fails when the status view is absent. Resume with fixes for those two cases, targeted tests and full just check, then exact-SHA CI and release. CodeRabbit slice used two passes; do not call those findings resolved without fixes.

Wave 2 exhausted the two authorised attempts without shipping. The recovered patch and the second correction pass are preserved in the isolated L1 worktree and private codex backup; no GCI-0030 code was committed. Focused tests passed (242 passed, 2 skipped), but CodeRabbit found a remaining major accuracy issue: a lower-priority overlapping Loki selector is classified unreadable even when it cannot govern retention. Do not count AC1-5 or release proof as complete. Resume from that exact selector-priority case with a new explicit attempt budget.

loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.

loop3 P-0030-a1 candidate accepted locally: selector winner precedes overlap ambiguity, malformed lists atomic, missing status view assembles. CodeRabbit terminal zero findings/all8 files; patch ef9ed0dce986f6c52a63a5cb891fba8a329bf581faacc572e59eeaa13fbf7610. Root exact diff reviewed and integration just check passed (1588 passed,2 existing skipped). Local root commit prepared, push/hosted CI held for independent pytest OpenTofu prerequisite repair. AC5 signed release/digest and live rollout not claimed. Request queue and effective Loki limits are independent per newer docs/traps: request-route failure alone does not invalidate readable limits. Existing tests changed to reflect newly requested per-stack unreadable statuses and confirmed-readable gap count rather than suppressing the whole partial population. Fresh a2 remains unused, infra retries0.

Loop3 dev image/source6eb verified, actual status view5 rows all unreadable for configured expectation, never false compliance. New status panel GET-rendered. Old gap/stream empty copies remain visibly stale rather than claiming current zeros. V-dev six-hour Mimir range found historical measured/unreadable/change-request series but current gap/compliant outcomes and fresh retention gauges remain unproved. AC5 signed auto-RC/stable release not claimed; release remains gated by incomplete full dev proof. No new source attempt used after accepted a1.

Release proof remainsblocked: v0.4.0-rc.8 GitHub prerelease exists fromb60e19c(code6ebancestor), but advertised GHCR0.4.0-rc.8 image verification returned MANIFEST_UNKNOWN; no digest/signature consumer pin proved. First cosign shim failedno configuredversion; retry used existinginstalled3.1.3withoutinstall/pin/authmutation and failedexit11 missingimage. No unchangedretry/no signedautoRCAC5check. Livepartialfreshmetric/unreadable limits retained.

loop4 V-ret source and dev 26h read: every successful limits record omits retention_stream; unreadable/null policy rows and absent gap/compliant gauges are correct-by-design, stale stream/gap copies deliberately retained. Root live task config confirms nonempty expectation and deployed image, schedule witness retained. No repair indicated; signed digest AC5 pending.

loop4 AC5 proved using same RC.11 at a589c4b and signed verified GHCR digest sha256:19ae79eb8e5e64e764f9a56491daaadbbaa754c02864f3b4fec427c598943d6d, auto-rc36786981438. Correct-by-design unreadable/absent gauges independently disposed, no repair attempt. Stable rollout is separate from this signed auto-RC criterion.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Generic per-stack retention status and dashboard criteria previously met; signed pinnable RC.11 digest independently verified in loop4 closes remaining AC5. Undisclosed per-stream limits stay unreadable with gauges absent and prior views visibly stale, never false zero/compliance.
<!-- SECTION:FINAL_SUMMARY:END -->
