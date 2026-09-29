---
id: GCI-0047
title: Count OTel collection_interval on Fleet pipelines as a DPM driver
status: Done
assignee: []
created_date: '2026-09-29 16:36'
updated_date: '2026-09-29 16:44'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0046 compares only scrape_interval. OTel pull receivers such as hostmetrics use collection_interval, which also sets DPM. Lab stacks carry 10s and 15s collection_interval values that GCI-0046 does not see. Extend the same in-memory parser and view rather than adding a second surface.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 collection_interval on wired OTel pull receivers is parsed and compared with the default alongside scrape_interval
- [x] #2 The view states which attribute produced each interval
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Only explicit collection_interval on wired non-prometheus receivers is read; receiver defaults differ, so omission is not guessed. Live check on robknight OTel pipelines matched grep, and correctly skipped an unwired host_metrics/datadog receiver at 10s. Existing scrape_* record keys keep their names and now include collection intervals; interval_attributes names the source.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
OTel collection_interval now feeds the same faster-than-default comparison, metrics, view, finding and alert as scrape_interval, with an Interval attributes column in risk_fleet_scrape_intervals.
<!-- SECTION:FINAL_SUMMARY:END -->
