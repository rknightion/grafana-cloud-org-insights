---
id: GCI-0061
title: Replace the legacy Connect-RPC substring guard with exact read routes
status: Done
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:45'
updated_date: '2026-10-01 17:27'
labels:
  - security
  - transport
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/sources/label_risk.py
priority: medium
type: chore
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 documentation audit at fb5803a found collector/sources/dataplane.py:70 permits POST based on Service/List or QuerierService substring matching. The only current callers are the exact Fleet ListCollectors and ListPipelines routes at lines343-344; the broader guard is not needed for them and is distinct from the ratified two-path label-risk exception. This is preventive boundary hardening, not evidence of a live mutating call. No new route or POST authority is granted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The helper admits only explicitly authorized exact read routes, with no substring or query-string bypass
- [x] #2 Current Fleet list reads still work while unapproved methods and paths are refused
- [x] #3 The general HTTP client remains GET-only and the dedicated label-risk POST exception remains separately bounded
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
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner correction Rob 2026-10-01: three current helper routes, not two: CollectorService/ListCollectors, PipelineService/ListPipelines, QuerierService/LabelValues (signal_inventory.py). Exact frozen S-RPC guard; GET-only general client and label-risk two-path exception unchanged. Published AGENTS wording is tracked separately, never hand-edited.

SR-guard-r1 at candidate 20dad3b8f61877139297cb7929208fd0761a486b FAIL: inherited urllib 301/302/303 redirect follows authenticated allowed POST as GET to nonallowlisted HTTP destination, forwarding Basic CAP cross-origin. Offline real-opener fake-wire proof, no live leak demonstrated. L-guard-a2 commissioned: helper-local redirect refusal preserving HTTPError code, plus HTTPS/nonempty authority/no userinfo, no hardcoded estate hosts. Root amended unaccepted seam on medium security judgment. Direct route tests/gate/CodeRabbit had passed a1; do not land until repair and r2 review.

Root rescue L-guard-a3 corrected only deadline-test RPC mock boundary, preserving blocked-read and timeout assertions. Committed and landed bd2d0cd5c9431f264951fd013927463fcb2bdd1c after SR-guard-r2 PASS/no must-fix and complete CodeRabbit zero findings all four files. Exact final just check passed 1676 tests, 2 existing skips, 8003 subtests plus Terraform/identifier/text gates. Resource retry1 had unchanged DNS-entry timing failures at host load180; isolated discriminators passed, full retry timed out after test/TF success at history scan; final resource retry2 full gate successful without weakening assertions. Exact landed hosted CI pending; dev guarded Fleet/profiles proof remains pending. No live credential leak demonstrated.

Exact landed CI 36879569443 at bd2d0cd5c9431f264951fd013927463fcb2bdd1c completed success, all four required jobs freshly read back by root. Code criteria/DoD proved; goal-specific live Fleet/profiles source-report comparison remains pending dev rollout, task remains In Progress until that proof is resolved.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Exact three-route HTTPS/no-redirect Connect-RPC guard landed bd2d0cd5c9431f264951fd013927463fcb2bdd1c with exact CI 36879569443, completed CodeRabbit zero findings four files, independent security r2 no must-fix and integrated review no must-fix. Root rescue preserves transport/body deadline assertions. Stable source b0d3b308c05d3fed3dd70990e217da2b81461ef0 CI 36883254984; v0.4.2 signed GHCR index verified independently. Dev image-only apply and live T1/T2 each exit 0, full stopped descriptors captured within 16s/15s of watcher exits, S3 advanced and Fleet/profiles remained 5/5 with no new refusal/ValueError. T1 observer had expired-SSO read failures until external cache became usable; task stopped earlier, lag disclosed, no relaunch. Scheduler restored and targeted final plan No changes.
<!-- SECTION:FINAL_SUMMARY:END -->
