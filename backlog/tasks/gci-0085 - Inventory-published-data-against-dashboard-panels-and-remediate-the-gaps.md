---
id: GCI-0085
title: Inventory published data against dashboard panels and remediate the gaps
status: To Do
assignee: []
created_date: '2026-10-02 13:50'
labels:
  - dashboards
dependencies: []
priority: medium
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The coverage gates in tests/test_dashboards.py prove every composed view is referenced by some panel and every CATALOGUE metric appears on a dashboard or in an alert. They do not prove field-level coverage: a bound view can gain columns (for example rules_coverage) that no panel shows, a view absent from the compose fixture escapes the gate, a metric referenced only by an alert counts as covered, and the three first-publication EXEMPT views (insights_dashboard_opening_31d, insights_datasource_query_cost, risk_org_members, exempted since 2026-08-24) may now publish. Inventory and fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An inventory maps every published view field and every CATALOGUE metric to the panel(s) that render it, derived from the composed fixture and the assembled dashboards rather than hand-listed, with each unrendered item classified as gap, deliberate (reason) or alert-only
- [ ] #2 Every gap is either given a panel or recorded as a deliberate omission with its reason; stale EXEMPT entries whose views now publish are removed
- [ ] #3 A field-level coverage gate (or an extension of the existing view gate) fails when a published view field is rendered nowhere and not explicitly exempted, seen failing once before the fix
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
