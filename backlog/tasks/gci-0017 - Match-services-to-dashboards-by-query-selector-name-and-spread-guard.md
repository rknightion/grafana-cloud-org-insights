---
id: GCI-0017
title: 'Match services to dashboards by query selector, name and spread guard'
status: To Do
assignee: []
created_date: '2026-08-25 13:11'
labels:
  - pillar-k
  - coverage
  - matching
dependencies: []
priority: medium
type: enhancement
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Depends on the unscoring task, which is worth twenty times more. Do that first.

## The tag convention has zero adoption, and the source discards the alternative

Zero of 7,517 dashboards estate-wide carry any tag beginning `service:`. Worse, the source boundary in `collector/sources/stack_catalog.py` filters tags to that prefix and discards every other tag, so no other tag evidence reaches the pillar at all. What the source does keep and the pillar ignores is `title` and `folder`.

## Two disjoint identity namespaces - the governing fact

The register identity is `service_name`, from Mimir, Loki, Tempo and Pyroscope. Dashboards are keyed on the Prometheus/Kubernetes label set. Measured over 512 live dashboard payloads, literal selectors used: `job` 101, `service_name` 16, `container` 14, `namespace` 3, `component` 3, `service` 1.

The obvious bridge FAILS and was disproved live: `job` to `service_name` resolved zero of 35 literal job values across nine stacks. Metric-name uniqueness also fails - 26 of 28 dashboard-referenced metric names carry zero `service_name` values. Do not attempt either.

Loki is the one place a bridge works, because it derives `service_name` while keeping the source stream labels. Since 3,295 of 3,566 rows are log-derived that is the highest-headroom extension, but it needs the LogQL selectors, so it rides on the same dashboard-JSON fetch. Unmeasured; treat as follow-up.

## Tiered algorithm, measured

| Tier | Evidence | Yield | Precision |
|---|---|---|---|
| 1 `query_selector` | literal `<identity-label>="<service>"` inside a panel query | 19 of 193 rows on a 10-stack sample (9.8%) | 100% by construction |
| 2 `named` | service tokens are a contiguous subsequence of dashboard title or folder, with the spread guard | 97 of 3,566 (2.7%) | 97.9%, all 97 hand-checked |
| 3 `technology` | as tier 2 but the service name IS a technology-registry key | recovers the 10 true matches the guard costs | high |
| 4 `synthetic_monitoring_app` | the identity is a Synthetic Monitoring check name; the SM app IS its dashboard | 373 of 1,856 rows on the 20 largest log stacks (20.1%) | high |

Tier 1 finds 16 matches that titles and folders both miss entirely - integration and self-monitoring dashboards no naming convention would ever reveal. Conversely the three matches titles found and tier 1 missed were all generic-name false positives.

## The generic-name guard: use estate spread, not length

Root cause measured: 4,986 of 7,517 dashboards (66.3%) are Grafana-provided rather than tenant service dashboards, so a service literally named after a platform component matches every stack. Worst offenders by dashboard count: 321, 269, 246, 94, 84.

Guards compared:

| Guard | Matched | Cost |
|---|---|---|
| none | 128 | 18 false positives |
| require >= 2 tokens | 52 | kills 45 TRUE positives |
| tenant-authored dashboards only | 105 | kills 23 true positives - stock integration and SLO dashboards are legitimate evidence |
| curated stoplist | 92 | kills 4 true, needs maintaining forever, violates discover-never-configure |
| **estate spread <= 3 stacks** | **97** | kills 10, every one a technology-registry key and recoverable by tier 3 |

Use estate spread. It is derived from live inventory every run, self-maintaining, and drops all 18 false positives. Yield flattens at 3 (89/95/97/99/103 at spread <=1/2/3/5/10). **The spread index must be built from the LIVE stack set** or a departing stack silently drifts a name above the threshold and coverage falls for reasons unrelated to the estate.

## Two implementation invariants, both real defects in tested versions

- **Never raw-substring match.** It scored WORSE than token-subsequence on both axes (104 vs 119 matched) because it cannot bridge hyphen, underscore and space, while still admitting a short word inside a longer unrelated one. Casefold, split on non-alphanumerics, require a contiguous token subsequence.
- **Store evidence tier, not a merged boolean.** Only tier 1 supports "this dashboard queries this service". Tiers 2 and 3 support only "a dashboard is NAMED after this service". Publish a boolean plus a match count plus an evidence enum, never a merged yes. 97 service matches spanned 259 service-dashboard edges; two services matched 21 and 25 dashboards because a whole product shares their prefix.
- Even tier 1 does not prove anyone looks: 6,377 of 7,517 dashboards went unopened in 31 days and 108 of 274 stacks had zero opens. Carry an `opened_31d` qualifier from the existing insights window.

## Free win, unblocked by any of the above

`collector/sources/alert_routing.py` already holds every rule from the provisioning API - 11,070 estate-wide - and discards titles past a 100-findings-per-stack cap. Accumulate `rule_titles` before capping and apply tier-2 matching: the `alert` component goes from 53 to 70 rows, +32%, at zero extra API cost. Titles only; no queries, no folder uids. Rule QUERY matching was tested and yielded zero on 1,732 rules, so do not build it.

## Cost and permissions

Tier 1 needs one `GET /api/dashboards/uid/<uid>` per dashboard: +7,517 requests on the daily tier against a current 13,417, so +56%. The per-stack reader already carries `dashboards:read` at `dashboards:*` - no role change and no re-provisioning. Gate it behind a config flag so it can roll out per tier. A stack whose detail fetch fails reports detail-unavailable and its services unscore `dashboard`, never score `no`.

## Verified NOT broken - do not touch

The SLO read is already complete. On a stack with 27 SLOs all carrying a service label, the existing Mimir read returned exactly its 8 distinct values. The figure of 15 estate-wide is the truth, not a measurement failure.

## Incidental defect to fix while in this file

`rule_group` in the alert findings is padded with a long run of asterisks when a rule has no group. Cosmetic in the view, but it makes the field useless as a matching input and would inflate any string index built over it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tier 1 query-selector matching implemented behind a config flag, identity labels an explicit allow-list
- [ ] #2 Tier 2 uses token-subsequence matching, never raw substring
- [ ] #3 Generic-name guard is estate spread built from the live stack set, not a curated list
- [ ] #4 Evidence tier stored per row alongside match count; no merged boolean
- [ ] #5 Alert rule-title matching added at zero API cost; rule-query matching not built
- [ ] #6 A failed detail fetch unscores the dashboard component rather than scoring no
- [ ] #7 rule_group asterisk padding removed
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
