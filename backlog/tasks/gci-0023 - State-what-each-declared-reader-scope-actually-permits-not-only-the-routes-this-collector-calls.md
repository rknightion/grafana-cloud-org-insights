---
id: GCI-0023
title: >-
  State what each declared reader scope actually permits, not only the routes
  this collector calls
status: Done
assignee:
  - '@codex'
created_date: '2026-09-11 11:07'
updated_date: '2026-09-11 13:43'
labels:
  - security
  - docs
  - capabilities
dependencies: []
priority: medium
type: docs
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`CAPABILITIES.md`'s org-realm reader table has a "Verified route" column, and for `logs:read` it lists
`/loki/api/v1/labels` and `/loki/api/v1/label/<name>/values`. Read in isolation that reads as the
scope's boundary. It is not. It is the list of routes this collector calls.

Measured 2026-09-11 with a throwaway org-realm policy carrying `logs:read` and nothing else, on a
control organisation, minted and deleted inside one probe: `GET {lokiUrl}/loki/api/v1/query_range`
returned **HTTP 200 and a real log line**. `logs:read` is a full Loki read scope.

## The scope is retained deliberately. This task records why, it does not narrow anything

Decision, 2026-09-11 by Rob, now a standing decision in `doc-0002`:

- The four-signal label inventory requires it, and **there is no narrower Grafana Cloud scope** that
  reaches Loki label names and values.
- **Planned log analytics will require log reads outright**, so narrowing now would only have to be
  reversed.
- **Deployments run only against organisations that have explicitly consented to that access.** The
  consent basis, not the scope width, is what makes this sound.

So the deliverable is candour about a declared capability, not a disclosure of a problem. Write it as
a capability the product has and a reason it has it. Do not write it as a risk being mitigated, and do
not hedge it - a reader who cannot tell whether the breadth is intentional will assume it is not.

## Why it is a documentation defect and not a code defect

`docs/security.md` is accurate as written: the credential is read-only by scope and the HTTP client
rejects every method except GET. Neither sentence claims log content is unreachable, and neither is
wrong.

The gap is that `query_range` is itself a GET, so the method restriction does not bound it. The
property that keeps this collector away from log content today is narrower and should be stated as
what it is: **the code only ever calls label endpoints.** That is a property of the implementation,
enforced by review and by the source list, not by the credential.

This matters because `AGENTS.md` makes the read-only posture load-bearing in what this platform can
tell an organisation about what it runs. An org security review that reads the capability table and
concludes "this credential cannot read our logs" has been misled by a table that was only ever
claiming something else - and the correct answer, "it can, here is why it is granted, here is what the
code actually calls, and you consented to it", is a better answer than the one the table implies.

## What to change

- Give the reader table a column heading that says what it means - routes this collector calls - and
  a separate statement, per scope, of what the scope itself permits where that is materially wider.
- State the `logs:read` case explicitly: full Loki read scope; the collector calls label endpoints
  only; the restraint is implementation, not credential; retained for the three reasons above.
- State the consent basis in `docs/security.md` beside the read-only-by-scope sentence, so the two are
  read together rather than the first being read alone.
- Audit the other scopes in the same table for the same shape. `metrics:read` is already documented as
  "the Mimir cardinality API **and the whole Prometheus query API**", which is the honest form and is
  the model to follow. `traces:read` and `profiles:read` each list two narrow routes and are the most
  likely to have the same understatement.
- `alerts:read` already carries a paragraph about `config.original` exposing raw Alertmanager
  configuration including `http_config`. That is the right level of candour, it should not be weakened,
  and it is evidence the table can carry this kind of statement.

## Deliberately NOT in scope

Removing or narrowing any scope, and adding any log-content read to the collector. This task changes
what is documented, not what is granted and not what the code calls. A future analytics feature that
reads log content is its own task with its own review; nothing here authorises it.

Establishing the real breadth of a scope requires minting a token, which is a write. `logs:read` is
settled. For any scope where that probe has not been run, say so explicitly and name the probe rather
than asserting a boundary in either direction - an unverified claim of narrowness is the exact defect
this task exists to remove.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The reader table route column is headed so it cannot be read as the scope boundary
- [x] #2 `logs:read` is documented as a full Loki read scope, with fixed label and effective-limit routes stated as implementation properties and no log-query endpoint added
- [x] #3 The reason `logs:read` is retained is recorded beside it: the label inventory needs it, no narrower Grafana Cloud scope reaches label names and values, and planned log analytics will require log reads outright
- [x] #4 `docs/security.md` states the explicit-consent basis beside its read-only-by-scope sentence, so the two are read together
- [x] #5 `traces:read`, `profiles:read` and `rules:read` are each audited for the same understatement and either corrected or marked explicitly unverified with the probe named
- [x] #6 No declared scope is removed or narrowed, and no log-content read is added to the collector
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Audit declared reader scopes in CAPABILITIES.md, state verified breadth and explicit unverified boundaries without narrowing any scope, update docs/security.md with the consent basis, then validate documentation gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Tracker reconciliation 2026-09-11: criterion 2 now includes the effective-limit GET added by GCI-0022. The security boundary remains no Loki log-query endpoint; calling the new non-content limits route does not restore the stale label-endpoints-only statement.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
CAPABILITIES.md now separates routes this collector calls from the broader permissions of each declared scope. logs:read is documented as full Loki read with the consent and retention rationale; effective limits are included without adding a log-content query; traces and profiles remain explicitly unverified with the required probe named; rules breadth is recorded. No scope was narrowed. Final gate at b6cf849614054894e2bea49d0154d958fc016d7b passed.
<!-- SECTION:FINAL_SUMMARY:END -->
