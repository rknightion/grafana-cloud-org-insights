---
id: GCI-0139
title: Recognize bounded AWS CLI retry annotations in observer S3 errors
status: Done
assignee: []
created_date: '2026-10-13 23:12'
updated_date: '2026-10-14 02:24'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 177000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Live dev observer v0.13.2 fails safe bootstrap: shipped AWS CLI reports GetObject NoSuchKey with a reached-max-retries annotation between operation and colon, so strict error parser misses the exact service code and returns prior_read_failed. Actual release image against AWS reproduced rc254, no process failure, missing parsed code. Preserve exact service-code/operation parsing, privacy and conditional bootstrap; accept only the bounded witnessed retry-count annotation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Fail-first reproduction uses actual witnessed CLI stderr grammar, then missing/denied/conflict codes classify only for matching operation; arbitrary/malformed annotations stay unclassified.
- [x] #2 Actual release-image AWS boundary and dev observer produce validated conditional bootstrap/readback without broadening role or unconditional writes.
- [x] #3 Fixed source passes required gate/review/release and both deployments use immutable fixed images with live observer proof.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live release-image AWS boundary reproduced254/no process failure/parsedCodeNone on exact NoSuchKey retry annotation; fixed source bind-mounted read-only into same actual ARM64 release image parses NoSuchKey correctly without changing CLI, creds, policy or request. Fail-first fakeCLI production bootstrap3failed6passed reproduced all4prior_read_failed; full observer24tests pass. Only optional exact reached-max-retries numeric1..10digits annotation accepted; arbitrary/malformed/overlong/wrongoperation/deadline remain refused. Source gate16730 and CodeRabbit15351 running; customer observer not enabled until dev corrected live proof.

CodeRabbit COMPLETE0/all2sourcefiles. Natural devcollector already produced actual8typedrecords and5exactS3digestbindings; fixed observer will consume these dated records, never rebase their source/ack times. Fullgate still requiredhistorycheck running; no fixedsourcepush/deploy or customerobserverenablement claimed.

Final unchanged required just check passed, including published-history identifier gate. Source hashes bind tested2filecandidate. Actual ARM64 releaseimage+fixedsource mount interprets realAWSCLIGetObjectNoSuchKey error correctly; no IAM or conditional-write change. Release13.3fix-forward proceeds, thenactualdevbootstrap/secondpoll andcustomer fullplan/liveproof.

Released13.3 real ARM64 image parses actual AWS NoSuchKey annotation; dev natural observer stops exit0 and conditionally bootstraps/readbacks all4schema-valid objects, later poll uses conditional CAS. No IAM or unconditional-write broadening. Dev full6definition/schedule/effectiveIAM/filter/retention/nochange verified. Query completes only after separate recording-lifetime repair140; customer AC3 remains pending.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bounded AWS CLI retry annotations recognized with fail-first grammar proof; malformed/arbitrary/wrongoperation/deadline errors remain refused. Released13.3/13.4immutableimages usefixedparser. Both14deployments livefull6definition/schedule/role/IAM/filter/retention/nochange verified; originaldevandcustomerscheduled14T1 complete8typedrecords/fiveexactversionedS3bytebindings. Bothactual14observer tasks stop exit0, safeconditionalbootstrap/CAS/readback publishfourstrictcompleteprojections preservingnativecounts/acktimes/digests andunknownmembership. Separate141presentationbackendrepairremains open.
<!-- SECTION:FINAL_SUMMARY:END -->
