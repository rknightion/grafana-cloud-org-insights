---
id: GCI-0133
title: >-
  Publish an org-wide AI token cost model: monthly collector view plus dashboard
  tab
status: Parked
assignee: []
created_date: '2026-10-12 10:04'
updated_date: '2026-10-12 19:40'
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
<!-- SECTION:NOTES:END -->
