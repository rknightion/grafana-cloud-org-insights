---
id: GCI-0057
title: Audit and refresh operator documentation across the product
status: In Progress
assignee:
  - '@loop6-root'
created_date: '2026-10-01 09:58'
updated_date: '2026-10-01 12:01'
labels:
  - documentation
  - operations
dependencies: []
references:
  - README.md
  - RUNBOOK.md
  - docs/configuration.md
  - terraform/variables.tf
  - consumer/MIGRATION-RUNBOOK.md
priority: medium
type: docs
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner requested a dedicated documentation freshness audit during loop5 on 2026-10-01 after asking which scan tier is hourly versus six-hourly and requesting a complete scheduled-job timetable. Tier cadence exists in README but operator references need to agree with current code, CLI and deployment contracts. Review documentation across the product, including stale historical limitations and command examples, without publishing deployment identifiers. This is future work, not a new implementation lane in the ongoing rollout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README, RUNBOOK, SPEC, configuration, infrastructure and consumer upgrade/rollback documentation are checked against current supported behavior; every discrepancy is corrected or explicitly tracked
- [ ] #2 All five scheduled jobs have a consistent purpose, cadence and timezone-aware schedule explanation, clearly distinguishing module defaults from deployment-specific overrides
- [ ] #3 Operator command examples and publication/credential/privacy/rollback constraints match current CLI contracts and named authority gates
- [ ] #4 Documentation changes contain no customer identifiers and pass proportionate documentation/text/link validation, with exact evidence and remaining gaps recorded
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Audit three disjoint documentation sets in isolated lanes; each owns final local gate, landing and hosted CI. Independently review the integrated docs for schedule, CLI, rollback, authority and privacy contradictions. Track code discrepancies as To Do only and reconcile exact evidence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop6 L-docspec accepted: fb5803aac17251403f02d06c4a939374bd148ef3, exact CI36856773020 success, eight owned files audited and seven changed. Non-description Terraform content unchanged; all58 inputs/18 outputs documented; catalogue re-derived9654. Existing2 tests skipped, not passed. Remaining CLI/output prose discrepancies tracked in GCI-0059 (refresh CLI help and task-role output), unverified segmented savings in GCI-0060 (establish segment-aware Adaptive Metrics coverage), and preventive RPC guard hardening in GCI-0061 (exact legacy read routes). These To Do tasks are not admitted. Cross-document acceptance awaits other doc lanes and independent review.

Loop6 L-docops accepted2698d251f1d31eeb26184c023d8164cceae074a1, exact CI36856913186 success, all6 owned files corrected, gate1659passed/2existing skipped. Lane disclosed rebase-triggered local gate ran after push rather than before; exact landed gate subsequently passed without repair, sequencing deviation retained in report. Probe help/output safety discrepancy is a separate To Do follow-up, not admitted. Private saved-plan wrappers were root-inspected in dev parity path; docs use deployment-owned placeholders.

Loop6 L-docref accepted4f0b5fa53a60317b39f9f7fc9cdefd54846aade6 CI36857820932 success; substantive364a101ec5b082aea66cc8de4696247a40641fb6 CI36857366914 success. All9 owned files audited and11 dashboards built offline. Gate1659passed2existing skipped. New discrepancies tracked To Do: GCI-0063 (explicit staff ownership-exclusion consumer policy), GCI-0064 (documented incomplete-configuration CLI exit). Existing help/probe findings reuse GCI-0059 (CLI/output description refresh) and GCI-0062 (safe usage-probe help/output). R-xdoc independent review now in flight over integrated4f0b5fa; no live docs publication or screenshot/browser renewal claimed.

R-xdoc at4f0b5fa reviewed24/24files and found2must-fix contradictions: obsolete Adaptive Traces absence in credential guide and claiming unused ruler/Alertmanager routes as current calls in credential/security guides. L-docref-a2 repair commissioned on those2files only. Schedule/default/timezone/rollout/privacy detailed contracts otherwise consistent. Note on excluded docs/traps fixed90day wording explicitly tracked separately To Do; no broad extra implementation admitted.
<!-- SECTION:NOTES:END -->
