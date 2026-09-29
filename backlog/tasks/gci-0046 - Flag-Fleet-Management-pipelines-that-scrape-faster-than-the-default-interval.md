---
id: GCI-0046
title: Flag Fleet Management pipelines that scrape faster than the default interval
status: Done
assignee: []
created_date: '2026-09-29 16:18'
updated_date: '2026-09-29 16:36'
labels: []
dependencies: []
priority: high
type: enhancement
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
High-DPM stacks bill across the whole organisation. Fleet Management pipelines can set a scrape interval shorter than the organisation's default (60s unless the deployment overrides it), and that raises DPM. The FM API has no manual_scrape_interval field: intervals live in pipeline contents as Alloy scrape_interval assignments or OTel prometheus receiver scrape_interval keys. T1 already fetches ListPipelines hourly and discards contents, so parsing it in memory adds zero FM API calls. Local Alloy and collector configs outside FM are out of scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The Fleet source parses Alloy and OTel scrape intervals from pipeline contents in memory, keeps only parsed durations and counts, and never retains contents
- [x] #2 Non-literal intervals are counted as unparsed, never guessed, and an implicit prometheus.scrape block reads as Alloy's 60s default
- [x] #3 The default interval is a deployment tunable (GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL, Terraform var) defaulting to 60s
- [x] #4 Per-stack metrics count enabled, reaching pipelines scraping faster than the default and give the shortest interval, and are absent where Fleet was not read
- [x] #5 A risk_fleet_scrape_intervals view lists every non-default pipeline interval with direction and reach, and feeds a Findings kind
- [x] #6 A paused, unrouted alert rule fires on any stack with a faster-than-default pipeline
- [x] #7 The risk dashboard's Fleet tab renders the metrics and the view, and just check passes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
No manual_scrape_interval field exists in the FM pipeline.v1 proto or in any of the 69 pipelines on the five lab stacks; the literal name is still matched if a template introduces it. Decisions (Rob, 2026-09-29): parse contents; piggyback the hourly T1 ListPipelines (zero added FM calls); count only faster-than-default intervals; place on the Risk dashboard Fleet tab. Live proof: fleet.probe_all + risk.build against robknight and robk returned 19 and 0 fast pipelines, matching a grep of the raw contents. DoD 3: no-em-dashes is clean; check-identifiers passes on tracked files but fails --history on eight pre-existing historical commits, which is GCI-0043, not this change. The alert rule adds a RULE_UIDS key, so a consumer that sets GCINSIGHT_ALERT_RULE_UIDS_JSON must add fleet_fast_scrape. The new scan env GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL changes the scan runtime projection digest.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fleet pipeline contents are parsed in memory for Alloy and OTel scrape intervals and never retained. The hourly tier publishes per-stack faster-than-default pipeline counts, estate totals, the configured default and an unparsed count, plus a risk_fleet_scrape_intervals view, a fleet_fast_scrape finding kind, a paused unrouted alert rule and Risk dashboard Fleet tab panels. The default comes from GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL / Terraform fleet_default_scrape_interval (60s).
<!-- SECTION:FINAL_SUMMARY:END -->
