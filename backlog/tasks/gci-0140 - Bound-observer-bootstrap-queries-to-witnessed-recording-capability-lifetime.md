---
id: GCI-0140
title: Bound observer bootstrap queries to witnessed recording capability lifetime
status: Done
assignee: []
created_date: '2026-10-13 23:49'
updated_date: '2026-10-14 02:24'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 178000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Live dev observer safely bootstraps4objects but 72-hour FilterLogEvents scans exhaust20pages on empty pre-feature logs before reaching real records. Recentonehour witness reaches8typedrecords in2completepages. Clip initial window at ownobserver IAM role AWScreationtime minus existing5minute clockskew; retain72hourmaximum, exactactualwindowmetadata, sourcecaps/deadline/privacy and unknown-on-cap. Make recording scan definitions depend on observer role so birth precedes recording for fresh deployments. Dev currentrolecreated23:08:18UTC precedes all4enabledscanregistrationdates23:08:18.xxx; no earlierrecordingcapability existed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Fail-first CLI/service-shape and mockplan proofs cover recentrolebirth/legacy72hours/futureorinvalidfloor rejection; published metadata uses actual window, caps remain fail-closed.
- [x] #2 Rendered observer receives own AWS role create_date, scan definitions depend on that role, without new IAM/API/manifest configuration or permissions.
- [x] #3 Both immutable released deployments produce validated dated native outcomes under the bounded observer, with full live IAM/filter/retention/schedule readback and nochange.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Use own observer role AWScreate_date (computed pinned-provider output) as optional observer recording-since argument. Observation start=max(now-72h, birth-300s), exactly published; legacyCLI noargument keeps72h, malformed/futurebirth refusesbeforeAWS. Add scanTDdependency on observerrole toguaranteebirth<=recording forfresh installs; no IAM/API/configstore/manifestkey. Fail-first CLIrequest/meta+mockplan tests; independentlyreviewcontract, fullgate/CodeRabbit, release13.4, build/pin/applydevfirst, actualnative8record/5acktime-digest continuity, thencustomerfullobserverplan/review/readback/nochange/liveproof/Operations.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live dev13.3parser/bootstrapcorrect: naturalobserverexit0 all4conditionallycreated/readbackobjects; secondmanualpoll exit0/CASpublishes but observationpartial/cap and no currentrecords because72hquery spends20pages scanningempty pre-featurehistory. Exactprefix-t witnesssame20empty; exactrecent1hrealservicewitness2pages/8records/complete, no arbitrarysourcecapincreaseaccepted. IAMrolebirth23:08:18UTC precedes firstfourenabledscanregistrations23:08:18.xxx; pinnedprovider6.62create_date computedschema/currentofficialsourcesupportsAWScreationdate. Contractindependentreviewpending; source/IAMnotchangedyet, customerfullplan reviewedPASS butheldforactualcontinuity.

Recording lifetime contract independently PASS; source implementation now optional validated recording-since from own AWS role create_date, scan dependency guarantees fresh-deployment ordering. CLI fail-first5failed1legacyPASS, final32focusedPASS; TFfail-first4PASS1failed then5PASS. Actual source/AWS CLI query clipped at witnessed role birth minus300 seconds reads8real records COMPLETE under unchanged caps; exact actual request interval persisted. Full gate and CodeRabbit in progress. No customer apply or immutable release proof yet.

Final unchanged candidate passes required just check:2800tests/27922subtests/2existing skips,45Tofu,fmt/lint/currentandpublishedhistoryidentifier/em-dash checks. Firstgate environmentalTMPDIRinsiderepocaused2Gitfallbacktests failures; reproducedsameenv, externalshort/tmp5focusedPASS thenfullgatePASS without source/test changes. CodeRabbit COMPLETE0/all8; independent finalboundary reviewPASS exactdiff3743cc2920c1480a411c09bb997860220a85e1bb9f7b68971672575904cfb45e. Actual clipped AWSquery8native records complete; immutable release andbothlive proofs stillpending.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Optional productionrecording-since boundtoownoriginalAWSrolecreate_date; query=max(now72h,birthminus300), actualintervalpublished. Legacy72h/defaultprivacy/caps/deadline/futureinvalidrefusal/72hconflictretention unchanged. Fail-firstCLIandmockplan proofs/requiredgate/CodeRabbit/exactCI/signed13.4releasepass. Bothdeployed14observers showfourstrictcompletequeryprojections withactualnativecounts/5originalacktime-digests; devoldernative8supportunchanged. All6TDs/schedules/effective3roleIAM/filter/target90global7/nochangeverified, rolebirth precedesfourrecordingregistrations. No currentmembershipauthorityclaim. Separate141presentationbackendrepair remainsopen.
<!-- SECTION:FINAL_SUMMARY:END -->
