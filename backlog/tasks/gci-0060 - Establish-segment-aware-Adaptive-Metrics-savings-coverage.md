---
id: GCI-0060
title: Establish segment-aware Adaptive Metrics savings coverage
status: To Do
assignee: []
created_date: '2026-10-01 11:45'
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
- [ ] #1 Current supported segmented and unsegmented API contracts and completeness limits are established with authoritative evidence
- [ ] #2 Savings do not silently present a partial unsegmented result as complete where segmented coverage is required
- [ ] #3 Any implemented route preserves read-only access, bounded labels and live inventory joins and is proved across its public boundary
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
