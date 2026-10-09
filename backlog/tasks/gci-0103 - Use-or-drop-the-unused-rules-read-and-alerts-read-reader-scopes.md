---
id: GCI-0103
title: 'Use or drop the unused rules:read and alerts:read reader scopes'
status: Done
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-09 14:46'
labels:
  - owner-decision
  - security
dependencies: []
priority: medium
type: task
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment: config.py:86-87 declare rules:read and alerts:read but no source calls them (CAPABILITIES.md:26-27); they reach raw Alertmanager config with secrets and full firing label sets. Least privilege says drop them unless a bounded count needs them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner decision recorded: drop, or name the bounded count route that keeps them
- [x] #2 If dropped, the provisioner removes only recorded pairs and a staff readback shows the reduced role
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop20 D-RULE20: keep both scopes; witness five exact GET routes; implement count-only source with minimization and unknown route counts; independent review, root land, composed gate and exact CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop20 D-RULE20 (Rob 2026-10-09): keep rules:read and alerts:read only for Mimir rules/alerts, Loki rules, Alertmanager alerts/silences exact witnessed routes. Never status/config routes; no policy/scope change or re-mint. AC2 drop branch is not applicable because owner chose keep both. Staff robk exact200 shapes: /Users/rob/repos/grafana-cloud-org-insights/codex/loop20-evidence/W-route/shapes.json. Source 0dddad5366db85613f0b0bb4ecc19ac060d3e2bc; 87 synthetic public-client tests, independent review PASS; CodeRabbit complete zero majors, one minor declined because frozen empty source envelope is unwired and cannot erase carried state; L-wire (new-source integration) must fence unknown fresh estate. Composed fd6d2150f1f3b60a447202d30e1a692bbb57fa78 just check exit0:2582 passed,2 existing skips,tofu32; exact CI37945144826 all jobs success. loop20:1 implementation attempt,0 review-repair rounds; source accepted, live wiring not yet claimed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Owner chose bounded use of both scopes; count-only default-off unwired source landed and passed exact focused checks, composed gate and CI. Conditional drop criterion is NA; no policy write occurred.
<!-- SECTION:FINAL_SUMMARY:END -->
