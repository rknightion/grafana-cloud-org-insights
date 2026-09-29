---
id: GCI-0050
title: Re-verify provisioner repairs at the end of the run before failing them
status: Done
assignee: []
created_date: '2026-09-29 23:23'
updated_date: '2026-09-29 23:41'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The GCI-0045 re-probe backoff (5, 15, 30 seconds) is too short when a run repairs many roles at once. A product-reads change on a 306-stack production estate on 2026-09-29 patched roughly 300 reader roles; 61 stacks were reported verification_failed with 'post-repair probe still needs patch_role' and the task exited 1, which also published gcinsight_stacks_missing_credential = 62. A read-only probe of every reader's effective permissions about an hour later found 305 of 306 complete; the 61 were propagation delay, not drift. The one real gap was a new stack whose admin service account creation hit a Cloudflare 522. Separately, the failure summary prints only the first 20 failures with no count of the rest, so the other 41 were not visible in the logs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A stack that fails post-repair verification is re-verified once more after every other stack has been processed, read-only and without a re-mint, and is reported verification_failed only if that final probe still finds drift
- [x] #2 A stack that verifies on the final probe counts as provisionable/ok and does not raise gcinsight_stacks_missing_credential
- [x] #3 The failure summary says how many failures it omitted when it truncates the list
- [x] #4 A test proves a stack failing every in-run probe but passing the final one exits 0, and one failing the final probe still exits 1
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
A repair still propagating after the in-run backoff is recorded with its clock time; after the stack loop the store is re-read and each gets one read-only _verify_reader_once with its stored credential, at least FINAL_VERIFY_MIN_AGE_SECONDS (300) after its repair. Waits overlap, so a run grows by at most 300s; a test pins that bound and was seen failing against cumulative waits. An unreadable store at that point keeps the in-run verdicts. The summary prints '... and N more' past 20 failures. Live context: the production rerun after the long night exited 0 at 306/306 ok, 308 gcom reads and 5 writes (one new reader).
<!-- SECTION:NOTES:END -->
