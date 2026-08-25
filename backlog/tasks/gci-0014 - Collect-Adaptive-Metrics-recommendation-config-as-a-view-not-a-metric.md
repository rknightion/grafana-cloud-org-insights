---
id: GCI-0014
title: 'Collect Adaptive Metrics recommendation config as a view, not a metric'
status: To Do
assignee: []
created_date: '2026-08-25 13:00'
updated_date: '2026-08-25 13:51'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
SETTLED on a lab stack after 316 Adaptive Metrics rules were applied, auto_apply enabled and a segment configured. Three outcomes.

1. EXEMPTIONS: dropped from READER_SCOPES. Over forty candidate paths return a plain-text 404 identical to deliberate control paths, across two independent stacks, INCLUDING the stack with applied rules and a live segment. That rules out the only remaining benign explanation - that the route materialises once there is data. A scope existing is not evidence of a route: scope families are minted per resource type, so an unexposed or plugin-internal resource still gets a public scope name. The plugin proxy cannot settle it either, returning 500 for every resources path including a control.

   Working hypothesis, still inference: an exemption is expressed as `keep_labels` on
   /aggregations/recommendations/config - literally the labels exempted from aggregation. That would
   explain the absence of a separate route and mean adaptive-metrics-config:read is the scope that
   actually reaches the data. ONE UI-created exemption plus a config re-read confirms or kills it.

2. CONFIG is richer than the earlier estate sweep suggested, and worth more than a single boolean. With
   auto_apply on, the body was {"keep_labels": [], "auto_apply": {"enabled": true, "gate": {"policy":
   "unbounded"}}}. The nested gate.policy field appeared on no stack in the earlier 270-stack sweep, so
   the shape varies with configuration rather than being fixed. Collect the whole object as view
   columns - enabled, gate policy, and keep_labels presence - not just an auto_apply boolean.

3. SEGMENTS are a new surface this project did not know existed, and they change savings arithmetic.
   /aggregations/rules/segments lists them with id, name and a PromQL selector, and both
   /aggregations/rules and /aggregations/recommendations accept ?segment=<id>. A stack with a segment
   has rules scoped to a selector rather than applying estate-wide, so summing its recommendations as
   though they were global overstates the reduction. Note /aggregations/rules/segments/<id> is NOT a
   route - only the list and the query parameter exist.

   This deserves its own collection: segment count per stack as a bounded metric, and segment name plus
   selector as view columns. A stack with segments should carry a marker on any savings figure saying
   the arithmetic is per-segment.

RESOLVED - we were declaring the wrong kind of permission. Documentation plus a live role enumeration settled it.

Grafana docs state the Adaptive Metrics plugin provides granular roles for rules, exemptions, segments and configuration. Enumerating a live stack with GET /api/access-control/roles?includeHidden=true and filtering for the plugins: prefix returned five Adaptive Metrics roles and their underlying actions:

- exemptions-reader -> grafana-adaptive-metrics-app.exemptions:read + .plugin:access
- rules-reader      -> .rules:read, .recommendations:read, .plugin:access
- segments-reader   -> .segments:read, .config:read, .plugin:access
- config-reader     -> .config:read, .plugin:access
- plugin-access     -> .plugin:access, plugins.app:access scoped plugins:id:grafana-adaptive-metrics-app

So exemptions is a STACK plugin RBAC resource, not an org access-policy resource. The org scope
adaptive-metrics-exemptions:read can never reach it, which is why forty-plus paths 404 including on a
stack with applied rules, auto_apply on and a live segment. Dropping it from READER_SCOPES was correct;
the reason recorded earlier ("no route exists") was incomplete - the route exists, on a surface that
credential cannot address.

TO ACTUALLY READ EXEMPTIONS, add to collector/provision.py DESIRED_PERMISSIONS as action/scope pairs:
  grafana-adaptive-metrics-app.exemptions:read
  grafana-adaptive-metrics-app.plugin:access
  plugins.app:access  scoped to  plugins:id:grafana-adaptive-metrics-app
This is the same shape already used for Adaptive Logs and stays within the read-only reader role. It
widens the per-stack reader, not the org credential, so it needs the usual role-drift comparison as
action/scope pairs rather than action names.

WHY IT IS WORTH HAVING: an exemption is a metric or label a team has deliberately protected from
aggregation. That is the "we were told no" list, and it caps the achievable saving - a savings figure
that ignores exemptions overstates what can actually be applied. It also names the teams who have
engaged with Adaptive Metrics enough to push back, which is a different and more useful signal than
rule counts.

BLOCKER ON VALIDATION: the plugin resource proxy returned 500 for every path on the lab stack, for both
the Adaptive Metrics and Adaptive Logs apps, including /resources/health and the bare /resources/. The
proxy is down there, so the route cannot be exercised on that stack at all. CAPABILITIES.md records the
Adaptive Logs plugin proxy as the WORKING route in the production deployment, so validation belongs
there, against a per-stack reader once the actions above are added. Probe /resources/health first: if it
500s, the proxy is down and no route conclusion can be drawn.

SEGMENTS remain the immediately actionable find and need no plugin role - see the earlier note.
<!-- SECTION:NOTES:END -->
