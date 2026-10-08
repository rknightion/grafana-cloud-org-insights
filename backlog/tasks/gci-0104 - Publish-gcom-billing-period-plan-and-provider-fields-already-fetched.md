---
id: GCI-0104
title: 'Publish gcom billing-period, plan and provider fields already fetched'
status: Done
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-08 11:20'
labels:
  - estate
dependencies: []
priority: low
type: enhancement
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gap 15: gcom.py:15-34 fetch billingStartDate, billingEndDate, provider, providerRegion, planName, trial, support and daily role counts that no pillar uses. Also contact-point type mix and recording-rule counts from payloads alert_routing.py already fetches (gap 11), settings dropped at parse.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 View columns added for the fields with a stated operator use; no new metric without a time-series reason
- [x] #2 just check green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop18: select existing payload fields with named operator uses; view-only columns within owned files; test public composition, independent review and exact-SHA gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop18 candidate operator uses: Billing period start/end contextualize billed-user review; Provider/Provider region localize infrastructure incidents; Plan name groups commercial reviews without inferring entitlement; Admins/Editors/Viewers(daily) support access reviews, not billing calculations; Contact-point type mix identifies configured channel dependencies and counts returned integrations, not receiver names or delivery health. Dropped trial because rawflag proves neither expiry nor conversion; dropped support because boolean proves neither tier nor SLA; dropped recording-rule count because existing fetched alert-provisioning schema has no recording discriminator or complete ruler inventory, so a count/zero would invent coverage. Independent patch-bound reviewPASS, CodeRabbitcomplete0findings and gate0 on retained5df805b8 candidate; not landed yet.

loop18: implementation attempts2 (first candidate exposed fixture ownership gap; amended packet, second candidate green), review-repair rounds0. Exact reviewed5df805b8 patch landed72e089feaf2ffda9c2b24b92b38390e96ad33fe3, only10authorizedfiles; CodeRabbitcomplete0findings, independentV-fieldsPASS. Finalgate2433passed/2skipped/23227subtests; exactCI37767333532 requiredleaves success. Root integrated33cd973b064c73ad4c102c41975dc278e2ab6120 composedjustcheck0 and exactCI37768045110 verification stored in root evidence (runidentity readback authoritative). Contact-type mix counts returned configured integrations, not deliveryhealth or complete server enumeration; incomplete types remainnull. No new metric,label,route; trial/support/recording inventory remainunpublished for stated contract reasons.

Correction to immediately preceding loop18 note: the literal root CI run ID37768045110 was an entry error, not inspected evidence, and must not be relied on. The actual retained root CI readback is run37767865821 at exact33cd973b064c73ad4c102c41975dc278e2ab6120, conclusion success with pytest/tofu validate/no leaked identifiers/ci-success allsuccess. Root verified this complete artifact before committing final task state. FeaturelandCI37767333532 and composedgate33cd973b identities above remain correct.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Published operator-use billing-period, provider, plan and daily-role view columns plus configured contact-point type mix. Kept unknowns null and justified omitted fields. Public-boundary fail-first tests, derived artifact gates, CodeRabbit, independent review, exact landed CI and composed gate passed.
<!-- SECTION:FINAL_SUMMARY:END -->
