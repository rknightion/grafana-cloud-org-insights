---
id: GCI-0085
title: Inventory published data against dashboard panels and remediate the gaps
status: Done
assignee:
  - '@loop10-root'
created_date: '2026-10-02 13:50'
updated_date: '2026-10-02 19:54'
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
- [x] #1 An inventory maps every published view field and every CATALOGUE metric to the panel(s) that render it, derived from the composed fixture and the assembled dashboards rather than hand-listed, with each unrendered item classified as gap, deliberate (reason) or alert-only
- [x] #2 Every gap is either given a panel or recorded as a deliberate omission with its reason; stale EXEMPT entries whose views now publish are removed
- [x] #3 A field-level coverage gate (or an extension of the existing view gate) fails when a published view field is rendered nowhere and not explicitly exempted, seen failing once before the fix
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
L-dash a1 afterprimaryAdaptive/Syntheticlanded atstable0.5.0: derive field/metric inventory from composedfixture/actualassembleddashboards, classify gaps/deliberate/alertonly, failingfirstfieldcoveragegate, boundedpanelremediation; candidateonlywhile rootlive/release freeze, no source/fixture/grant changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root public vendor source/runtime proof jsonframer v1.3.0: original metadataobject selector workswhenpresent butmissingpreupgrade metadata errors (JSONata noresults), contrary to blankpromise. Optional $exists(meta.rules_coverage) ? [meta.rules_coverage] : [] yields1rowwhenpresent/0whenmissing. Reserve rootreviewrepairGCI-0085-r1: truthfulrules-read title vs savingscoverage, optionalrootselector andexactsemanticfieldlineagenormalization ininventory, finalcurrentIRM+SEG rederive/gate/CodeRabbit. No live/browser/deployedbinary proof (robkInfinityversion4.1.0GETmetadata, publictagabsent). Firecrawlkeyless429terminalnotretried; officialGitHubsource retrieved instead, builtinweb unavailable. a1consumed/infra0, no allowance reset.

Root repaired missing-metadata selector using real upstream framing API and truthful rules-read labels; field-lineage gate watched fail then pass. Final rebase over ML and documentation-only canonical publication, just check1796pass2skips8339subtests, CodeRabbit all3changed files complete0findings. Landed845321c64c9af410baa70b96e6cac231e76eda38; exact hosted CI pending. Generated final-field-inventory.json from published fixture envelopes and assembled dashboards, explicitly records empty/unobserved and live-only provenance limits. No browser/deployed-plugin proof or live dashboard publish claimed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixture-derived field/metric inventory and assembled-dashboard gate delivered845321c64c9af410baa70b96e6cac231e76eda38; exact hosted CI succeeded, identity in L-dash/ci-terminal.json. Final gate1796passed2skipped8339subtests. Three-file root repair CodeRabbit complete zero findings. Inventory86views4975observedfields:675rendered4300reasoned deliberate0gaps;203catalogue entries151rendered52deliberate0gaps. Optional published rules-read metadata panels preserve empty-detail denominators; real upstream framing API verifies present values and missing metadata0rows, no falsezero. Stale fixture view exemptions removed; field gate watched failing before adaptation. Empty row schemas and live-only provenance variants explicitly unobserved, not claimed covered; no live dashboard/browser/installed-binary proof. a1implementation, rootreviewrepairr1, infra0.
<!-- SECTION:FINAL_SUMMARY:END -->
