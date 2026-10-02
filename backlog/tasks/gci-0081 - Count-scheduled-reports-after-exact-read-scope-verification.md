---
id: GCI-0081
title: Count scheduled reports after exact read-scope verification
status: Done
assignee:
  - '@loop10-root'
created_date: '2026-10-02 09:25'
updated_date: '2026-10-02 21:29'
labels:
  - feature-usage
  - scope-decision
dependencies: []
references:
  - codex/loop9-evidence/L-fam/packets.md
priority: medium
type: task
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Historical Admin empty and reader403 do not establish full visibility. Exact reports:read scope, positive control and paging require proof; no report creation or sending. Owner decision GCI-0041 (product read scope approval) is conditional future authority, not a customer grant or loop9 implementation admission. Packet 8 in codex/loop9-evidence/L-fam/packets.md (sha256 e46afeb70fca8cd53ee0843c898c810a80cc05bc4238db02d8df2c6310eac6ad) holds exact routes/pairs, exclusions and outstanding witnesses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Fresh authorised dev evidence establishes exact action/scope pairs, permitted route/method and complete count visibility, or records the precise blocker without widening authority
- [x] #2 Any implemented source emits counts and bounded enums only; sensitive sentinels are absent from payloads, logs, errors and persisted envelopes; unavailable coverage remains absent
- [x] #3 Any implementation follows fresh inventory, exact selected read boundaries and offline public-boundary proofs with final just check and hosted CI; conditional blockers in the packet are resolved before build
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
R-wit basicNone exactreports:read@reports:* fromfreshlivefixedrolemetadata; never reports:send or settings grants. GET /api/reports count/controlpositiveorpreciseemptyblocker, IDrecordedteardown, no reportcreate/send.

Loop10a1 admitted from921279fa6942e18bf00d91270aa63260c40c15b1 after PDC accepted; default-offreports T2reports_inventory, exactreports:read@reports:* only/fixedGET/barearray/countonly/HTTP200, no send/settings/plugin/query grant. Publictokenvalidator/doc ownershipexplicit. SourceDetails/IDs transientthenDROP; fullselectedboundary/privacy/fixture/goldenretirements, lane gateCRCI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop10 fresh robk reports:read@reports:* basicNone witness GET/Admin200count1 same transientpopulation, no reports:send/settingsgrant; shapeonlykeysets not recipients/content. SA65/rolefg016k4fxxaf4c/token75 deletedtoken-role-SA200/404/postlistsabsence. Positive existingreport control nowestablished, no reportcreate/send/customergrant.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reports acceptedfd68c5c1f9e4472b86269ae0984dec10dde8312e/tree9bb88a3e34b943598f71b2d3cdd066b8365cdb7d: final1940pass2skip8633subtests/genuine localvenv/CR21complete0/exactCI37065992288success/independentR-sec-reportsPASS and151narrowtests. Exactone readpair/defaultoff/HTTP200/barearray/T2count-only, private details discarded, validempty vsunknown, fixture/golden assertions preserved. a1infra0, no customer/livecollector/universalvisibility/minimality/serverwriteisolation/memoryerasure claim.
<!-- SECTION:FINAL_SUMMARY:END -->
