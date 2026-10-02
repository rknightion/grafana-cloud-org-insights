---
id: GCI-0060
title: Establish segment-aware Adaptive Metrics savings coverage
status: Done
assignee:
  - '@loop10-root'
created_date: '2026-10-01 11:45'
updated_date: '2026-10-02 19:01'
labels:
  - adaptive-metrics
  - accuracy
dependencies: []
references:
  - collector/sources/dataplane.py
  - CAPABILITIES.md
priority: medium
type: enhancement
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 reference audit at fb5803a found collector/sources/dataplane.py:293 reads only unsegmented Adaptive Metrics routes. Current docs now disclaim verified segment-aware savings, but an estate with segmentation may have incomplete savings attribution. GCI-0014 (Adaptive Metrics recommendation view) is already Done and does not establish segmented route coverage. No live tenant or scope change is implied by this follow-up.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Current supported segmented and unsegmented API contracts and completeness limits are established with authoritative evidence
- [x] #2 Savings do not silently present a partial unsegmented result as complete where segmented coverage is required
- [x] #3 Any implemented route preserves read-only access, bounded labels and live inventory joins and is proved across its public boundary
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.

Loop10 positive selectedrecommendation/deployedreader witness releases a1: root freezes discovery-aware conservative suppression, explicit unsegmented/segmented/unknown state and cost/value/maturity eligibility, no additive/global saving or scopechange. Candidateonly during releasefreeze; failing-first public source->compose->S3/dashboard/carry proof then gate/CodeRabbit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop7 AC1 evidence: authoritative Grafana Adaptive Metrics API and segmentation docs establish omitted/empty segment = default only, GET /aggregations/rules/segments discovery and per-segment rules/recommendations. M-seg-a1 inspected 4f652f2305c4e7ff1eb4cf6d4da97ea56d5303b5. Root staff-only GET probe 2026-10-01T13:59:53Z to 13:59:55Z: fresh inventory, seven GET responses all 200, stable empty segment enumeration, 681 default verbose recommendations, grouped rules one entry; shapes/counts only retained. This proves nonsegmented route behavior with existing broad staff CAP, not segmented arithmetic or deployed narrow reader authorisation. Conditional L-seg not admitted: no positive segmented verbose/fallback witness and declared reader lacks segments-read scope. A blanket fail-closed suppression fix could remove savings everywhere under the current reader without demonstrating the desired segmented public contract. AC2/AC3 remain open, no scope expansion or segment creation granted by this research. Evidence is local codex/loop7-evidence/M-seg and R-segprobe; public sources https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/additional-configuration/adaptive-metrics-rule-segmentation/ and https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/manage-as-code/adaptive-metrics-api/.

Loop7 committed AC1 accepted; conditional L-seg not admitted and AC2/AC3 explicitly parked. Resume boundary: verified positive segmented recommendation/fallback semantics and authorised discoverability for deployed reader, followed by a frozen owned source-to-consumer packet. This loop does not change collector scopes or fabricate a segment.

Loop9 one owner-granted robk segment created and retained: ID01M3XYKP465FR8C1Q2P189FFS2, fallback_to_default true, auto-apply disabled. Fresh inventory and modest live namespace population1107 selected. At creation segments list200 count1, grouped rules200 count2, selected rules/recommendations200 count0. Actual deployed read CAP segments-list200, correcting prior unverified reader-discoverability premise. Positive segmented recommendations not yet observed; +2h and final witnesses pending. AC2/AC3 not checked; no code reserve admission. DELETE by recorded ID owed next loop, never name matching.

Loop9 creation/+2h/final GET witnesses retained one segment01M3XYKP465FR8C1Q2P189FFS2, fallbackdefault true/autoapplyfalse. All live GET200, selectedrules0/recs0 throughout; deployed actualread CAP list200. No positive segmented recommendation, so reserve notadmitted and AC2/AC3 remain parked. Delete byrecordedID owed nextloop. Root+2h witness4m35late after recordedroottoolgap, not claimed exactclock compliance.

Root M-seg-contract currentpublicquotes confirm defaultonly/asynchronous/fallback semantics and no outputsummationproof. Chosen narrow reversible suppression incl legacy/adoption guard; no7022global saving claim. Knownsegmented distinguished from HTTPunknown. L-seg-a1 reserved (prior loops notadmitted), no implementationattemptreset. Oldloop9segmentabsence confirmed; no deletion owed/no segmentwrites.

Root finaldiff caught newlyauthoredtest using recordedoldstaffsegmentID instead ofsynthetic fixture ID. No commit/push/publication occurred. Reserve bounded reviewrepairr1 root: replace literal with synthetic-segment-a preserving regex/behavior, rerun affectedpublic tests and finalgate; do not weaken identityminimization assertion. Existing a1candidate rebasedclean stabledb4b260 andgatepass,13filesCRcomplete0findings/infra1; target remainsnextstable notv0.5.0live.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Loop10 honestdiscovery-aware defaultonlysuppression landed9caaebee40127f58001a6b49ac9c60032b567904 CI37044380347success: explicitunsegmented/segmented/unknown/legacyguard, cost/value/maturity/carry publicproof, sourceGETno scopes/additiveclaims,13fileCRcomplete0findings. Finalrootfixtureidentitysanitation+rebaseoverIRM justcheckpassed. a1implementation/reviewrepairr1/infra1; no global7022or livecollectorsegmentedproof, notincludedstable0.5.0.
<!-- SECTION:FINAL_SUMMARY:END -->
