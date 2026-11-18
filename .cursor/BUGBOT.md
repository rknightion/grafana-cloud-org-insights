# Grafana Cloud organization insights review

The collector composes results from a freshly discovered estate. Iterate the live stack
inventory and use source data as a lookup. A failed inventory request leaves the estate
unknown. Keep absent metrics absent and unsatisfied views stale. Preserve the scoped
run publication guard in `scan.py` and the different collection tier input ages.

Review source authorization and disclosures in `collector/httpclient.py`,
`collector/sources/` and `collector/emit/`. Source HTTP stays GET-only. Keep reader roles
query-scoped and verify action/scope pairs and datasource discovery before changing
permissions. Keep metric labels bounded and customer identifiers or credentials out of
telemetry and public artifacts. Keep raw label-inventory values transient. Bootstrap and
teardown must use explicit operations and recorded object IDs. New alerts stay paused
and unrouted. Changes to an existing rule preserve its pause and routing settings.

Review effective manifest digest compatibility when changing `terraform/consumer_manifest.tf`
or `bin/consumer_manifest.py`. The generated metric catalogue is owned by
`collector/emit/budget.py`. The pytest suite already checks the catalogue, dashboard
coverage, source guards and fixture contracts. `just check` adds OpenTofu and the
identifier gate. Report how a change can break an operator or publication boundary even
with those checks passing. Use the protected identifier check for the same-repository PR.
