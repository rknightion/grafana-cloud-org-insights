---
id: GCI-0101
title: Decide whether to read Loki index volume for top log producers per stack
status: Done
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-09 14:46'
labels:
  - owner-decision
  - cost
dependencies: []
priority: medium
type: task
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gap 9: Loki GET /loki/api/v1/index/volume or index/stats on hlInstanceUrl would answer which service drives log ingest cost. Existing logs:read, but a new route outside AGENTS.md's Loki label/limits reads; never read log content. Org-realm token reachability unverified.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner decision recorded on the route and the stream-label dimension allowed
- [x] #2 If approved, a live staff witness of the route and response shape precedes any implementation task
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop20 D-VOL20: witness robk GET index/volume first; implement default-off source plus synthetic public-client checks; independent review; root land; composed gate and exact CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop14: D-LBL6 covers Loki /series, index/stats and index/volume routes for labelling purposes after recorded staff witnesses; the top-producers dimension remains open and is not admitted in this loop.

loop20 D-VOL20 (Rob 2026-10-09): approved exact Loki index/volume route, service_name top-100 bytes over 86400s; raw values private S3 only, not Loki/metric labels/stdout/--out. Staff robk exact200 values-free witness: /Users/rob/repos/grafana-cloud-org-insights/codex/loop20-evidence/W-route/shapes.json. Source 9d3453879a84d9be24f94b0f2c0859745a4eee7a; independent review PASS; CodeRabbit complete zero findings. Composed fd6d2150f1f3b60a447202d30e1a692bbb57fa78 just check exit0: 2582 passed, 2 existing skips, tofu32 passed; CI37945144826 all jobs success. Unknown total/remainder remains null, never derived from query-work stats. End-to-end wiring remains L-wire (new-source integration), not claimed live. loop20: 1 implementation attempt, 0 review-repair rounds; source accepted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Approved/witnessed route and landed bounded unwired source. Exact source tests and composed gate/CI passed; no live collector or deployment proof claimed.
<!-- SECTION:FINAL_SUMMARY:END -->
