---
id: GCI-0014
title: 'Collect Adaptive Metrics recommendation config as a view, not a metric'
status: To Do
assignee: []
created_date: '2026-08-25 13:00'
labels:
  - cost
  - adaptive-metrics
dependencies: []
priority: low
type: enhancement
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The declared scope `adaptive-metrics-config:read` has exactly one working route, now verified across a full estate: `GET {hmInstancePromUrl}/aggregations/recommendations/config`, 270 of 270 stacks HTTP 200.

## Measured response shape - only two bodies exist estate-wide

| stacks | body |
|---|---|
| 269 | `{"keep_labels": []}` |
| 1 | `{"auto_apply": {"enabled": true}, "keep_labels": []}` |

- `keep_labels` is empty on every single stack. It carries zero information and must not be collected.
- `auto_apply` appears on one stack only, and is ABSENT rather than `false` elsewhere - so the API omits defaults and you cannot distinguish "explicitly off" from "never configured". Say that in the view rather than rendering a false boolean.

## Why it is still worth collecting

`auto_apply` is decision-relevant out of proportion to its rarity: a stack that applies Adaptive Metrics recommendations with no human review changes how every savings figure for that stack should be read. The one stack carrying it also held several hundred adaptive rules, so it is a real configuration rather than a stray flag.

## Therefore: a view, never a metric

A boolean set on one stack in 270 must not become 270 series. Per the project rule, anything point-in-time is a view and costs nothing. Add it as a column on the existing adaptive-metrics view, with three explicit states - enabled, absent, and unreadable - so an omitted default is not rendered as disabled.

## adaptive-metrics-exemptions:read stays reserved

34 distinct candidate paths have now been probed and every one returns a plain-text `404 page not found`, byte-identical to two deliberate control paths that do not exist. No candidate returned 401, 403 or 405, so this is a router with no such path rather than a permission or feature gate. Record the count in CAPABILITIES.md so nobody repeats the hunt.

One route remains genuinely unresolved: the Grafana stack plugin path under `grafana-adaptive-metrics-app`. An org token cannot test it - it returns an invalid-api-key 401 on every stack Grafana API path, which says nothing about the route. Settling it requires a stack service-account token, i.e. a mint on a live customer system, so it is a deliberate decision and not a gap to close casually. If exemptions do live behind the plugin then the org-realm scope can never reach them and should be dropped from READER_SCOPES rather than left declared.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 auto_apply collected as a view column with enabled/absent/unreadable states
- [ ] #2 keep_labels is not collected
- [ ] #3 No new metric series are emitted
- [ ] #4 CAPABILITIES.md records the 34 probed exemption paths and the control-path method
- [ ] #5 A decision is recorded on whether to keep or drop adaptive-metrics-exemptions:read
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
