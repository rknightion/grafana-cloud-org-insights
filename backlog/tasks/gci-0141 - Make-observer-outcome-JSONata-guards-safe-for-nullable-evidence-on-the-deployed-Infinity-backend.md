---
id: GCI-0141
title: >-
  Make Infinity evidence guards and UTC ages safe for outcome and view metadata
  panels
status: In Progress
assignee: []
created_date: '2026-10-14 01:54'
updated_date: '2026-10-14 02:26'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 179000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Actual saved-model requests on customer14 returnHTTP400/fourInfinitybackend500errors on nullable age/count comparisons under logicaland. Underlying observer14fourS3strictschemas/nativecounts/5acktime-digest/fullIAM/filter/retention/nochange proof passes; savedDashboardJSONalso passes, showing why realdatasource execution is required. Make conditionals null-safe without changing privacy, count/staleness/future-skew semantics or data sources.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Actual deployed Infinity backend fails first on current nullable outcome rows; corrected age and count guards return Unknown rather than errors or fabricated zero, preserving future skew and stale-evidence semantics.
- [x] #2 Source presentation change passes focused regression checks, CodeRabbit and required release gates without any reader, credential, privacy, observer or collector source-contract expansion.
- [ ] #3 Both deployed Operations dashboards execute all four saved query models successfully with seven minimized rows and twelve fields, original evidence times and unknown membership; persisted contracts remain verified.
- [ ] #4 Actual backend outcome and view metadata expressions handle nullable ages, counts and coverage without errors or fabricated zero; canonical UTC normalization preserves timestamps, freshness, stale evidence and future-skew semantics.
- [ ] #5 Source presentation change passes focused regression checks, CodeRabbit and required release gates without any reader, credential, privacy, observer or collector source-contract expansion.
- [ ] #6 Both deployed Operations dashboards execute four saved outcome query models successfully with seven minimized rows and twelve fields, accurate ages, original evidence times and unknown membership; saved contracts remain verified.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Actual deployedbackendguard candidate4queries returns200; seven sourcegeneratedinlinecases reproducedmisreadISO+00:00 asUTCmidnight. ExplicitZ parsing preservesmilliseconds; canonicalUTCnormalization plusconditionalnullguards passesallseven null/current/stale/future/skew/badcount/zero cases(7rows12fields). Sharedviewmetadata nullablecomparison also actualbackendfail-first; sameboundedfixappliedto itspublicationage/inputage/coverage guards. No scope/schema/privacy/freshness-limit/source contract expansion.

Source-generated outcome7case actualbackend proof now passes null/current/stale/future/skew/badcount/zero: correctUTCage~60seconds, future600secondunknown, admitted60secondfutureclamped0, originaltimestamps preserved. Sharedmetadata5case actualbackend passes nullablepublication/inputage/coverage andaccurate anchoredage. Focused7tests/8subtests pass; CodeRabbit29048 running. No permanent implementation-mirroringtest added; actualbackendrepro/readback is externalcontractproof.

Final4filecandidate unchangedfulljustcheckPASS2800tests/27922subtests/2existingskips/45Tofu/currentandpublishedhistoryclean. CodeRabbit COMPLETE2minor/all4files/no majorcritical; bothcommentsquoteoldandguardbefore-imagealreadyremovedbyreviewedcandidate. Exactrecommendedconditionalguards present and12actualbackendedgecasesPASS; no extraunchangedreviewrerun. ActualFullUTC+00 suffix normalizationretainsdate/time/fractionanddisplaySourceTimes; sourceonlypresentation/docs. Release13.5andbothdeployedrealbackendqueriesstillpending.
<!-- SECTION:NOTES:END -->
