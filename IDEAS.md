# Insight menu

This is the decision record for insight candidates. Shipped items name their source. Rejected items stay
recorded so a plausible but disproved panel is not repeatedly proposed. Any deployment-specific figure
belongs in dated evidence, not here.

## Source preference

1. Use `grafanacloud-usage` directly from a dashboard when the signal already exists there.
2. Use the org-realm reader for fresh control-plane and data-plane inventory.
3. Use the stack-local reader only for stack APIs and datasource proxies the org reader cannot reach.
4. Emit a metric only when a trend, alert or dashboard time range changes a decision. Otherwise publish
   a point-in-time S3 view.

## Shipped

### Pillar A - estate

- estate size, status, region, dashboard/rule/user populations and creation/change trends;
- dormant and billing-active leftover candidates;
- version drift, delete-protection exposure and feature flags;
- one-day and seven-day comparable-population diffs.

### Pillar B - cost

- active series and usage by signal;
- cardinality outliers;
- Adaptive Metrics rule adoption and verbose marginal reductions;
- the subset of remediable series with no observed rule, query or dashboard reference;
- Adaptive Logs pending recommendations, ranked without inventing a time window;
- optional rate-card currency with incomplete pricing disclosed.

### Pillar C - usage

- stickiness, role mix, plugin adoption and user recency;
- protocol adoption, data loss, unread logs and capability use from `grafanacloud-usage`;
- negative-result guard against reintroducing a metrics write-only panel.

### Pillar D - maturity

- versioned 0-100 composite score;
- per-stack explanation, estate distribution and dimension means;
- explicit unscored reasons so missing data cannot look like a bad score.

### Pillar E - risk

- admin and access-policy sprawl;
- per-stack service-account and token-hygiene inventory;
- public-dashboard configured inventory with measured-stack denominator;
- alert rules inheriting policy or naming missing/unverified receivers;
- org membership and staff-access-window states;
- Fleet collector activity, pipeline reach and locally evaluated matchers;
- plugin drift and deletion-risk drill-down.

### Pillar F - value

- unit economics, adoption and internal benchmarks;
- remediable-series trend and optional priced value;
- named views behind leadership counters.

### Pillars G and H - operations and commercial

- OnCall engagement and response outcomes with population-matched denominators;
- data-loss and alert-delivery health;
- commitment, run-rate and product-cost composition, with currency/period marked as derived where the
  datasource does not declare them.

These are panel-only surfaces over `grafanacloud-usage` and add no collector series.

### Pillar I - Assistant and AI

- billing-period Assistant/AI aggregates from `grafanacloud-usage`;
- rolling-window per-stack Assistant usage and tenant-scoped configuration through stack readers;
- category/surface remainder, machine-driven share and token-per-active-user outliers;
- reader-credential coverage and oldest-gap alert.

The billing and plugin windows are intentionally separate and never used to validate one another.

### Pillar J - dashboard usage

- dashboard opens, distinct viewers, panels queried, request errors and cache ratio;
- top dashboards and datasource types observed in use;
- public-dashboard activity, distinct from the configured inventory on Risk;
- full dashboard-opening inventory and datasource query-cost views;
- explicit coverage for every measured stack.

## Rejected or negative results

- **Quota headroom:** org inventory quotas can be unlimited and the real limits can have ample headroom.
  Recheck with a new estate fact before building a panel.
- **Config booleans as adoption:** `customAuth`, `customDomain` and `ssl` can have no
  variance across an estate.
- **Metrics write-only stacks:** after requiring active ingest and a matched 24-hour query window, the
  reference finding dissolved. A test refuses the panel.
- **Unidentifiable-target series:** the reference volume was negligible despite broad presence.
- **One stack per usage-insights region:** cheaper, but it uses one stack's credential to attribute
  another stack's activity and breaks coverage honesty.
- **Regional usage-insights datasources on the write stack:** they are not a reliable cross-region
  credential shortcut.
- **Adaptive Logs applied saving from recommendation volume:** volume is residual and windowless. Use
  the existing applied-drop datasource metric instead.
- **Quota or feature flags as paid waste:** an enabled/disabled inventory field does not prove the
  contract includes or charges for the capability.
- **Raw Assistant objects and Adaptive recommendation records:** bodies can be large or secret-bearing.
  Store bounded aggregates and metadata only.

## Open opportunities

Each candidate still needs a credential, request/series cost and a decision owner before implementation:

- Synthetic Monitoring check results through a verified unattended read route;
- Adaptive Profiles and read-only Adaptive Traces recommendations;
- k6 execution use rather than `k6OrgId` provisioning;
- per-team response-time distributions within the OnCall histogram's finite bucket limit;
- dashboard duplication and consolidation scoring;
- a per-tenant receipt, if the audience expands beyond the central platform team;
- natural-language access to already-published insight data without widening collection scope.

Prefer a panel over an existing datasource whenever possible. Do not add a pipeline merely because the
collector can fetch the same signal.
