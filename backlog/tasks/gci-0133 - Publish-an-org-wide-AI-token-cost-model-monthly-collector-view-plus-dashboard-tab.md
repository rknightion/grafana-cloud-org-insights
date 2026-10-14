---
id: GCI-0133
title: >-
  Publish an org-wide AI token cost model: monthly collector view plus dashboard
  tab
status: Parked
assignee:
  - '@codex'
created_date: '2026-10-12 10:04'
updated_date: '2026-10-14 21:41'
labels:
  - ai
  - dashboards
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/ai-token-packet/packet.md
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/telemetry/ai-120day-schema.json
priority: high
ordinal: 170000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision D-TOK23 (Rob, 2026-10-12). Rebuild the internal BI token-pricing analysis for the org a deployment covers, from data the org can reach. A T2 collector view computes calendar-month aggregates per org and per stack (seats from Grafana's active-user counts, tokens, users over the allowance, modelled seat and overage cost, billed overage for reconciliation) from grafanacloud-usage metrics. An AI dashboard tab renders the view, with live per-user tables read from the vendor per-user token metric (emails are displayed, never stored, labelled or linked). Pricing inputs (seat price, overage per 1M, monthly allowance) are dashboard variables. System pool, cache/input/output splits, internal model cost and sessions are stated as unavailable to the org. Do not copy the BI defects: one seat definition everywhere, the stack filter applied to every panel, and billing period distinguished from calendar month. Analysis: codex/scratch/bi-token-dashboard/analysis.md (gitignored).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Collector view with an empty-view schema, declared in VIEW_INPUTS by re-derivation, holding org and per-stack monthly aggregates only; no email, user name or identity in any stored field, label or log
- [ ] #2 AI dashboard tab renders the view plus live per-user tables, with variables for seat price, overage rate and allowance; coverage gates pass
- [ ] #3 Contract tests prove a cumulative per-user series that does not reset gives correct calendar-month deltas, one seat definition is used throughout, and a missing input stays absent rather than zero
- [ ] #4 Reconciliation panel compares modelled overage with the billed overage metrics and labels the period semantics of each
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop23 root accepts read-only bounded design packet, not implementation. Full build parks on B-TOK-LABEL/TIME/POPULATION/ATTRIBUTION/BILLING: approved robk four-metric 120-day reads returned zero series with 12-series control, so no live labels or producer/calendar/seat/billing/per-stack attribution witness. No synthetic labels or scaffold substitute. Resume R-TOK23 only after positive same-authority schema and bounded producer semantics witness plus serial field/link prerequisites. A different tenant/evidence surface requires an explicit grant.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root engineering dispositions: mutable allowance must use upstream live aggregate recomputation while the persisted default-40M snapshot is separately labelled, contingent on witnessed bounded query semantics; never recompute arbitrary excess from a single stored threshold. One proved active-user seat definition, transient-email live tables only. A bounded ownership-omission correction for scan.py and budget/provenance wiring is necessary for the already-approved new T2 input, not new product/source authority; do not implement that correction before source proof. No org-only reduced-scope build accepted as full AC. Attempt count zero; no code or gate claimed.

2026-10-13 source-contract correction: versioned retained source describes the per-user AI token metric as a current-month gauge, contradicting the earlier unconditional non-resetting-counter premise. No deployed producer/version or positive schema witness has been established. Preserve the monthly-model objective, privacy fences and attempt count zero; do not implement delta or range-maximum arithmetic from either unverified assumption. Before implementation, resolve the deployed period/type contract, choose one proved seat population, and prove shared-user allowance attribution and billed-period/currency reconciliation. AC3 requires owner-consistent revision to test the witnessed producer contract; it is not satisfied by changing the test to match a guessed algorithm. Org and stack current-month active-user quantities do not automatically establish licensed seats. No new product scope follows.

Owner 2026-10-14 names BI dashboard mitn6pr in bi-ops as the build inspiration, authorizes read-only inspection and customer billing discovery, requests configurable customer pricing inputs. Use the dashboard data scope; no broader AI analysis required. Internal-only sections require a supported customer source or explicit unavailable handling.

Owner2026-10-14: omit internal-only BI sections entirely; generic seatprice20USD with customer override14USD, remainingdefaults2USD/million,40Muserallowance,500Msystemallowance all configurable. Exact historical monthly totals REQUIRED before shipping; snapshot-only currentmonth fallback is not accepted. Fresh customer positive data and pinned producer contracts captured; midnight/first-hour historical reads remain unchanged into02UTC and do not bind exact closing totals. No partial AI feature deployment authorized by this fallback proposal.

2026-10-14 bounded authorized read-only BI/customer investigation complete. Original BI dashboard available through explicitbi-ops; positivecustomer172identityseries/77categoryseries/currentmonthlyuser167+service1/systemallowance500M. ExactBI hourlySQL calendar aggregates July/Aug/Sepclosed+OctMTD returned7count-only rows without identity values, privatecomparison under /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261014/backlog-zero/ai133/exact-monthly-comparison.json. Current pinned producer source describes monthly gauges; observedcustomerhistory dropsOct1 07UTC, notmidnight. Historicalper-user billing excludes some investigation/agent usage beforeOct1 unlike rawBI hourly category data, so exactBI model cannot safely reconstruct from nativebillinggauges alone. A reliablecustomer-accessible exacthistorical feed/producer-period contract remainsrequired before shipping; no snapshotfallback or newBI credential/source route grant. ExistingAI identity panels retain legacy lifetime wording/high-water queries; correct that within this task using witnessed monthly-window semantics. Genericseat20USD/customer14USD,2USD/million,40Mpersonal/500Mgeneric-system configurable requirements retained; internal-only BI sections omitted. No implementation/featuredeployment claimed.
<!-- SECTION:NOTES:END -->
