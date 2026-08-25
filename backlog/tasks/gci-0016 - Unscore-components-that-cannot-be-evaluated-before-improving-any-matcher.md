---
id: GCI-0016
title: 'Unscore components that cannot be evaluated, before improving any matcher'
status: To Do
assignee: []
created_date: '2026-08-25 13:11'
labels:
  - pillar-k
  - coverage
  - honesty
dependencies: []
priority: high
type: bug
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The coverage score divides by 7 unconditionally. Measured across a 270-stack estate, three of those seven components are structurally unsatisfiable on almost every stack, so the score reports absent product adoption as failed coverage. THIS is the dominant defect, not the dashboard matcher.

## Measured effect, and why matcher work must come second

| change | estate mean completeness |
|---|---|
| current (dashboard always no, denominator always 7) | 17.7% |
| + a fully working dashboard matcher, denominator still 7 | **18.1%** (+0.4pp) |
| + unscored scheme, matcher unchanged | **26.4%** (+8.7pp) |
| + machine-generated identities row-unscored | 27.3% |

A perfect matcher is worth less than a twentieth of what honest unscoring is worth. Do the unscoring first.

## The three structural zeros

- `profiles`: 269 of 270 stacks returned zero service names from a SUCCESSFUL Pyroscope read. The product is not in use; that is not a coverage gap.
- `slo`: 267 of 270 stacks own zero SLOs. Only four stacks in the estate own any.
- `alert`: 150 of 270 stacks have an available alert inventory reporting zero rules.

Scoring these as `no` is the same defect as the dashboard tag, three times over, and it is exactly what the sibling maturity pillar already refuses to do with its explicit unscored reasons.

## Unscoring rules

| Component | Unscored when | Reason enum |
|---|---|---|
| `profiles` | Pyroscope read SUCCEEDED and returned zero services | `signal_not_in_use` |
| `slo` | stack owns zero SLOs | `product_not_in_use` |
| `alert` | alert inventory available and rules_total == 0 | `product_not_in_use` |
| `alert` | alert inventory unavailable | `inventory_unavailable` |
| `dashboard` | dashboard inventory unavailable | `inventory_unavailable` |
| `dashboard` | query-detail fetch failed for the stack | `evidence_unavailable` |
| `metrics` / `logs` / `traces` | NEVER | - |

Metrics, logs and traces are the observation itself. A service present in one signal and absent from another is a real finding and must keep scoring `no`.

`dashboard` is NOT unscorable merely for a stack having no dashboards: zero of 270 stacks have no tenant-authored dashboards. Where a stack has dashboards and the service has none, `no` is honest.

## Row-level unscoring: one class only

A register row whose identity is machine-generated gets `unscored_reason = ephemeral_identity`, is excluded from aggregates, and STAYS VISIBLE in the view. Detected from the name alone, no config, no maintained list:

```
\.(scope|service|slice|socket|mount|timer|target|device)$
^session-\d+
^user-\d+
\d{8,}
[0-9a-f]{8}-[0-9a-f]{4}-
```

Measured: 425 of 3,566 published rows (11.9%), and 12,459 of 18,376 in the full canonical set (67.8%). The `\d{8,}` rule is a heuristic and will catch a legitimately numbered service, so publish the count as its own metric and keep the rows visible with the reason attached rather than dropping them.

## Denominator and disclosure

- Denominator = count of APPLICABLE components. Never divide by 7 when a component was withheld.
- Mirror `MIN_WEIGHT_COVERED`: withhold the row percentage entirely below four applicable components.
- Emit `coverage_unscored{component, reason}` - both bounded enums, budget-safe. Declare it in CATALOGUE or `tests/test_budget.py` fails.
- **A mean-completeness stat panel MUST sit beside a mean-denominator panel.** A score rising because the denominator shrank and a score rising because coverage improved are indistinguishable otherwise, and this pillar would publish the second reading of the first event.
- The estate summary needs a plain sentence naming the top unscored reason and its count. "N stacks own no SLOs, so slo is unscored for M services" is the finding the org needs; it is currently rendered as a column of "no".
- Bump `Score version`. The number changes meaning, and a trend crossing a silent definition change is worse than a gap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 profiles, slo and alert unscore on measured product absence with a bounded reason enum
- [ ] #2 metrics, logs and traces never unscore
- [ ] #3 denominator is the applicable-component count, and the row percentage is withheld below four
- [ ] #4 machine-generated identities are row-unscored, excluded from aggregates, still visible in the view
- [ ] #5 coverage_unscored{component,reason} declared in CATALOGUE and rendered
- [ ] #6 mean completeness is never rendered without mean denominator beside it
- [ ] #7 Score version bumped
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
