---
id: GCI-0133
title: >-
  Publish an org-wide AI token cost model: monthly collector view plus dashboard
  tab
status: To Do
assignee: []
created_date: '2026-10-12 10:04'
labels:
  - ai
  - dashboards
dependencies: []
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
