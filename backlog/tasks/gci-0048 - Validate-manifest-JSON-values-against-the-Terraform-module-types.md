---
id: GCI-0048
title: Validate manifest JSON values against the Terraform module types
status: In Progress
assignee:
  - '@loop3-root'
created_date: '2026-09-29 17:05'
updated_date: '2026-09-30 13:00'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0045 review F2/F5: Terraform coerces JSON values through module variable types. list(object({selector, minimum_period})) drops extra attributes, the weights object turns a string '2' into 2, and very large integral floats lose precision in Python's int(). A manifest holding any of these hashes differently from the rendered task environment and the task refuses to start, while the wiring preflight passes because the key is wired. The preflight also does not check that an assignment reads the local of the right projection.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 validate() rejects or normalises retention items to exactly selector and minimum_period strings and weights to numbers
- [ ] #2 A contract test proves the normalised manifest digest equals the tofu-rendered task env digest for each coerced case
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop3 P-0048: reproduce JSON coercion/digest mismatch against real module variable types; reject or normalize values and prove offline tofu-rendered task-env parity; gate, CodeRabbit, exact-SHA CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.

loop3 a1 landed 5a899807e6d749949c40649d5b8c98942346576d with exact local gate green and completed CodeRabbit; two duplicate minor test-skip suggestions rejected. Exact-SHA CI36715866853 failed: pytest job lacks tofu for required offline console contract. This is integration red, not infra retry. Root authorises bounded a2 CI-only setup repair using existing action pin; no test skip/weakening. Original red remains historical failure and will be disclosed, not claimed green. Sequencing deviation: post-rebase gate was after push, though exact-SHA gate passed.

loop3 P-0048-a2 landed4b3114315a1b56519f29677389efa39ba5542d92, CI36717430157 failed tofu console30s timeout after missing executable was fixed. Root uses granted root-rescue attempt P-0048-a3 (specialist a4 remains). Discriminating local proof with exact pinned bundled wrapper08b20fba177640b274943044d4b22d78127a63381199daacb9734346f2d39199: pipe-driven console timed out5s; real binary same input returned2 immediately. Pinned action README documents tofu_wrapper:false; source wrapper omits stdin forwarding. Root disables wrapper in pytest only, no test timeout increase/skip/weakening, no version change. CI failure is not an infra retry. Evidence P-0048-ci/wrapper-discriminant.json and source/doc captures.
<!-- SECTION:NOTES:END -->
