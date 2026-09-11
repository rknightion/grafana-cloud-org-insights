---
id: GCI-0025
title: >-
  Verify what traces:read and profiles:read actually permit, with an isolated
  mint-and-delete probe
status: Parked
assignee: []
created_date: '2026-09-11 14:15'
updated_date: '2026-09-11 15:25'
labels:
  - security
  - capabilities
dependencies: []
priority: medium
type: task
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0023 documented every declared reader scope's breadth except two. `traces:read` and `profiles:read` are recorded in `CAPABILITIES.md` as explicitly unverified, with the necessary probe named rather than a narrow boundary asserted. This task runs that probe.

Authorised by the operator on 2026-09-11 for wave 2.

## The probe

Mint an access policy carrying `traces:read` and nothing else, on a control organisation. Call content-bearing Tempo routes with it and record what returns 200 and what returns 403. Repeat for `profiles:read` against Pyroscope. Delete both policies. Verify no residual object remains.

## Constraints

- **Single-scope policies only.** A policy carrying a second scope proves nothing about either one, because a 200 cannot be attributed.
- **Never touch an access policy this project did not create.** Surfacing the org's own teams' policies is the deliverable elsewhere; changing them is not.
- **Record the object IDs at mint time and key the teardown on them, never on a name pattern.** A name-matching teardown previously deleted a provisioning account and orphaned the custom role it was the only identity able to remove.
- **Verify the delete, do not assume it.** Re-read by ID and confirm absence. A 2xx on the delete call is not proof.
- Update `CAPABILITIES.md` from observed behaviour. Where a route's status is still ambiguous, say so rather than generalising from one call.
- Do not widen, narrow or remove any scope the collector actually declares as part of this task. The deliverable is documentation of what the scopes permit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A single-scope traces:read policy is minted on a control organisation and content-bearing Tempo routes are probed with it
- [ ] #2 A single-scope profiles:read policy is minted and content-bearing Pyroscope routes are probed with it
- [ ] #3 Both policies are deleted by recorded object ID and absence is verified by re-reading, not assumed from the delete response
- [ ] #4 CAPABILITIES.md records observed behaviour per route, and states where a result remains ambiguous
- [ ] #5 No access policy this project did not create was read-modified or deleted, and no declared collector scope changed
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 2 attended probe did not run because the operator did not supply the control-organisation identity. No organisation was inferred and no access policy was minted, read, modified or deleted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked without live mutation. The control organisation was not supplied, so traces:read and profiles:read remain explicitly unverified, no content-bearing route result was claimed, and CAPABILITIES.md was not changed.
<!-- SECTION:FINAL_SUMMARY:END -->
