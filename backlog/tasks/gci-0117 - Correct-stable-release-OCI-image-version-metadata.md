---
id: GCI-0117
title: Correct stable-release OCI image version metadata
status: Done
assignee:
  - '@loop25-root'
created_date: '2026-10-06 11:19'
updated_date: '2026-10-13 12:17'
labels:
  - release
  - owner-decision
dependencies: []
priority: medium
type: bug
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v0.7.0 readback established exact release manifest/tag/source SHA and source-bound cosign identity, but both platform OCI version labels were main rather than 0.7.0. An extra version-label assertion failed and is not claimed green. Root did not retag or republish; the pinned shared publisher generated this metadata and its repository is outside the loop13 write envelope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner grants the bounded publisher/caller change; future stable image platform configs have the exact semantic release version while source/revision and signing SHA remain pinned.
- [x] #2 Real published artifact readback verifies both platforms; no historical tag deletion, movement or source-witness relaxation is used to get green.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-OCI23: isolated shared publisher candidate, semantic stable version label preserving immutable source/revision/signing. Root security review, land and shared release, then caller-pin integration. Final two-platform readback only after project stable release.

Implementable remainder after completed guarded source/caller work: obtain primary patched stable Debian package/base evidence for all eight gated CVEs and both architectures, preserving actual Python3.14/AWS runtime, or owner-approved explicit security/runtime policy re-grade. Then fresh source-bound stable release CI with unchanged agreed HIGH/CRITICAL gate; capture exact OCI index/child digests, both semantic version/source/revision configs and matching signing/attestation identities. No historical tag moves/deletions or inferred green. Current exceptions are expired; no authorized renewal or blind retry.

loop25 D-IMG25: isolated new minimal-base candidate, unchanged both-platform runtime/Trivy proof; root security review then CodeRabbit, serial composed gate and exact hosted CI, accepted-set stable release and artifact readback. No exception renewal; cumulative prior implementation2 retained.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: shared publisher implementation attempt1 security PASS and CodeRabbit complete0 findings on exact patch7662bfb2; local just check0 and pinned actionlint1.7.12/zizmor1.29.0 lint0 (only existing unchanged secret-action findings). Root landed shared source361f19e703843ef04b5db97e11cfd673b3eaa6ef. Integrated shared gate and exact required CI pending; shared release/caller pin and future project two-platform stable artifact readback remain unaccepted.

loop23: shared fix361f19e passed local gate/security/CodeRabbit0 and exact CI38245685269; stable sharedv1.25.7 at1a8cf1f published by one root recovery dispatch38246126077 after existing bot auto-merge suppressed push automation. Twelve caller pins landedb704880; required integrated CI38254439412 and composed gate at4310826 green. Separate edge publisher38254440160 failed both platform Trivy gates:44HIGH results/eight unique CVEs, exceptions expired2026-10-11, fixed versions absent in captured SARIF. Not a demonstrated label-code regression; no ignore extension or blind retry. Fresh Debian/base availability research active; stable two-platform OCI artifact acceptance still open. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/oci/.

loop23 terminal disposition for this row: implementation cycles2 (shared core, root caller integration), no source review-repair rounds; local/required integrated source proof green, artifact acceptance open. Eight HIGH CVEs remain vulnerable in stable trixie/bookworm; testing/unstable fixed source packages are not compatible stable binary proof, Alpine/AWS runtime unverified. Park owner security/runtime policy re-grade; recommend unchanged baseline and verified stable patch rather than exception renewal. Actual Dockerfile runtime is Python3.14, not the separate CI Python3.15. Full fresh citations /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/oci/image-security/findings.md.

loop25 candidate implementation3 cumulative, security review PASS on exact Dockerfile d051e769bd72afbf8deae7640e2ae59cf0c8796aa12f19c6ae34192bf0951501; independent both-platform actual-image checks verified copied source/no-network startup. No critical/major. Nonblocking builder package trust, overridable trusted version/checksum args and writable /app parent retained, not hermetic/read-only-rootfs proof. CodeRabbit active before root landing. Stable release proof remains open.

loop25 final: cumulative image implementation3 (prior2+newminimalbase1), no code repair; reviewed local exact bothplatform builds/unchanged HIGHCRITICAL Trivy0/runtimeAWS+collectorhelp and justcheck0. Root landedc8ce783, then accepted provenance4d203b8; composedgatesgreen, exactCI38376341598/38391090549green and bothautoRCpublishgreen. RefreshedPR63head62459a86 exactCI38391177994green; literalrootmerge produced5e215a9878a325045e0fe168bc8f91180d49a810 with authenticpublicationreceipt. Stablev0.12.0 source5e exactCI38393137342green/publish38393137855 botharch+merge/sign/SBOMgreen. Actualindexsha256:7e26af2db34d11d4dd19f35d05a57bd2230143f72e12f9966415b1bdacfd4685 and bothchild/configbytehashes verified; bothversionlabels0.12.0, source/revisionexact5e. Cosignexactpinnedreusable@1a8cf1f+Actionsissuer+repo+sourceSHA verifiedsignedINDEX binds bothplatforms; no independentchildsignatureclaim. Final5ecomposedjustcheck0/1100.462s Python2727pass/27626subtests/2skip; ToFu37pass+remaininggatesclean. No ignoreextension/gateweakening/historicaltagmove/livecustomerchange. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop25-evidence/image/stable-oci/verified.json and /Users/rob/repos/grafana-cloud-org-insights/codex/loop25-evidence/image/release-composed-gate.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed stable OCI metadata/security acceptance in v0.12.0 at exactsource5e215a9878a325045e0fe168bc8f91180d49a810. Pinned minimal glibc Python runtime with official AWSCLI2 retains nonroot stdlib collector; unchanged both-platform HIGHCRITICAL gate and actualpublished semversion/source/byte-hash/signing binding verified. Signer coversmergedindex cryptographically binding bothplatform descriptors/configs. Local integrated and exacthostedgatesgreen;2 existingpytest skips remain separate. No historicaltagmovement or vulnerabilityexception renewal.
<!-- SECTION:FINAL_SUMMARY:END -->
