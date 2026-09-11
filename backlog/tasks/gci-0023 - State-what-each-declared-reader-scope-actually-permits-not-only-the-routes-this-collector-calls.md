---
id: GCI-0023
title: >-
  State what each declared reader scope actually permits, not only the routes
  this collector calls
status: To Do
assignee: []
created_date: '2026-09-11 11:07'
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

## Why this is a documentation defect and not a code defect

`docs/security.md` is accurate as written: the credential is read-only by scope and the HTTP client
rejects every method except GET. Neither sentence claims log content is unreachable, and neither is
wrong.

The gap is that `query_range` is itself a GET, so the method restriction does not bound it. The
property that keeps this collector away from log content is narrower and should be stated as what it
is: **the code only ever calls label endpoints.** That is a property of the implementation, enforced
by review and by the source list, not by the credential.

This matters because `AGENTS.md` makes the read-only posture load-bearing in what this platform can
tell an organisation about what it runs. An org security review that reads the capability table and
concludes "this credential cannot read our logs" has been misled by a table that was only ever
claiming something else.

## What to change

- Give the reader table a column heading that says what it means - routes this collector calls - and
  a separate statement, per scope, of what the scope itself permits where that is materially wider.
- State the `logs:read` case explicitly: full Loki read scope; the collector calls label endpoints
  only; the restraint is implementation, not credential.
- Audit the other scopes in the same table for the same shape. `metrics:read` is already documented as
  "the Mimir cardinality API **and the whole Prometheus query API**", which is the honest form and is
  the model to follow. `traces:read` and `profiles:read` each list two narrow routes and are the most
  likely to have the same understatement.
- `alerts:read` already carries a paragraph about `config.original` exposing raw Alertmanager
  configuration including `http_config`. That is the right level of candour and it should not be
  weakened; it is evidence the table can carry this kind of statement.

## Deliberately NOT in scope

Removing or narrowing any scope. `logs:read` is required for the label inventory and there is no
narrower Grafana Cloud scope that reaches it. This task changes what is documented, not what is
granted. Do not "fix" it by dropping a scope the product needs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The reader table's route column is headed so it cannot be read as the scope boundary
- [ ] #2 logs:read is documented as a full Loki read scope, with the label-endpoints-only restraint stated as an implementation property rather than a credential property
- [ ] #3 traces:read, profiles:read and rules:read are each audited for the same understatement and either corrected or explicitly confirmed accurate
- [ ] #4 No declared scope is removed or narrowed by this task
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
