---
id: GCI-0138
title: Preserve temporary Container Insights settings during consumer upgrades
status: Done
assignee: []
created_date: '2026-10-13 20:16'
updated_date: '2026-10-13 22:11'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 176000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The dev deployment has owner-held Container Insights enabled for labelling evidence. The generic module hardcodes disabled, so an otherwise image-only upgrade plans to switch it off. Add an explicit default-off policy input and preserve old consumer digests; dev can retain its already-enabled setting without overriding pinned module code or changing customer policy.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Default module plans Container Insights disabled, explicit manifest policy enabled preserves enabled without changing runtime digests.
- [x] #2 Old full/pruned manifests remain digest-compatible; invalid policy types are refused.
- [x] #3 Dev query-suppression rollout preserves live Container Insights and all other non-image settings.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Dev saved plan exposed only enabled-to-disabled Container Insights drift beyond the image/default-off env changes. Add default-false AWS manifest policy and additive false digest normalization; pin actual cluster setting from this policy. Prove disabled default, enabled explicit and enabled manifest plans plus legacy full/pruned/invalid type contracts. Preserve golden fixtures. Review/gate/release fix, upgrade both sources, set dev true only to preserve existing hold, rebuild bound images, and apply plans only when no cluster setting or other unrelated action is present.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Original dev plan rejected before apply due cluster enabled->disabled update. Fail-first mock test confirmed old module ignores requested enabled policy; new three mock plans pass. Full consumer suite58tests/89subtests pass. CodeRabbit complete all9files, two duplicate major findings concern synthetic secret_name=null fixture, corrected to actual defaultempty and three mock plans pass. No runtime source finding. Full gate running; fixture was corrected before its Terraform stage, so initial beforehash differs onlyfixture and cannot be claimed unchanged. Preserve both failure logs and verify final Terraform artifact separately. No deployments changed.

Final unchanged candidate just check passed: 2784 tests, 27922 subtests, two existing skips, 44 OpenTofu plans; format/lint/identifier current and history checks clean. Initial unrelated DNS exercise failure passed unchanged on focused rerun; final full gate passed. CodeRabbit duplicate fixture findings corrected. Live preservation criterion remains pending rollout.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Explicit default-false Container Insights policy shipped in v0.13.1 source b5c2590f5c7db79e9ddb9fe2f09cd164f373249d. Legacy full/pruned digests preserved; true changes overlay only. Dev rollout applied exact classified saved plan, all5 task definitions/schedules and effective scheduler IAM read back equal to reviewed intent, live Container Insights still enabled, targeted no-change plan contains no resource/output changes. Full unchanged source gate:2784tests/27922subtests/2existing skips/44Tofu; exact source and release CI required jobs green; stable OCI twoarches/signature binding verified. Evidence retained under /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261013/adaptive/release131/dev.
<!-- SECTION:FINAL_SUMMARY:END -->
