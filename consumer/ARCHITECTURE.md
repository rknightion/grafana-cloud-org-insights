# Generic core and deployment overlay

This repository is the only editable product implementation. A deployment consumes one immutable Git
commit and owns one non-secret manifest. The deployment does not contain a collector, dashboard builder,
alert builder, container definition, product test suite, or reusable Terraform module copy.

The deployment manifest preserves customer-specific metric and object identities, stack and tenant
details, cloud names, schedules, policy identities, rate-card choices, adopted-resource choices, and
secret selectors. Credentials remain in the deployment secret stores and never enter the manifest or
this repository.

The source relationship is one way:

```text
generic Git commit ---> pristine generic image ---> immutable registry digest
        |
        +-----------> generic Terraform module at the same commit

deployment manifest ---> validated runtime projections ---> ECS, dashboards, and alerts
        |                                               +-> deployment Terraform values
        +-----------> overlay digest and deployment Git revision in image provenance
```

From v0.10.0 the deployment passes the decoded manifest to the module as `consumer_manifest` (manifest
mode) instead of copying its keys into module arguments. The module reads every key it represents,
falls back to its own default for an absent key, renders both task projection digests, and applies the
manifest's Purpose and Namespace tag values over the deployment's own `tags` (the manifest wins).
`terraform/consumer_manifest.tf` is the one table of which key feeds which input. The manifest may omit
any key whose value is the module default; `bin/consumer_manifest.py` validates and digests the
effective manifest, so omission changes no digest. Explicit wiring still works for a deployment that
has not moved.

The image contains generic source only. Infrastructure is the runtime configuration source. Each task
receives a digest of exactly the non-secret fields it consumes; the loader recomputes that digest and
refuses a mismatch. The full overlay digest is provenance for the complete customer contract and is not
something a narrow task projection can recompute.

Core keeps `gcinsight_*` and `GCINSIGHT_*` identities. Configured external identities are applied only at
the emission and resource-generation seams. Labels are never rewritten or widened. Provider selection
remains owned by the Terraform consumer's root lock file.

`bin/consumer_manifest.py check` proves the manifest, generic checkout, Terraform ref, deterministic
digests, externally supplied customer-identifier patterns, and declared retired-core paths agree. Set
`GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN` or pass a private file to
`just check-identifiers --patterns-file`; the pattern set must never be committed to the public product
repository. A deployment wrapper passes
each historical fork path with `--forbidden-core-path`; the checker also rejects the product's standard
collector, scan, dashboard, and alert paths automatically. In manifest mode it also refuses, by name, an
explicit module argument for any input the manifest represents (only the `schedules_enabled` and
`provisioner_enabled` kill switches may sit beside it). `just consumer-build` creates and verifies a
local candidate without registry access.
`just consumer-exec` validates the consumer and runs the supplied command under one exact runtime
projection (`scan`, `provisioner`, `dashboards` or `alerts`). It is not a dry-run boundary: the command
can publish or provision if those flags or defaults are selected. Live operations need separate authority.

For example, building alert JSON locally requires all four positional consumer inputs and a command:

```bash
just consumer-exec /path/to/deployment/consumer.json /path/to/deployment \
  /path/to/deployment/consumer.tf alerts python3 bin/alerts.py --out /tmp/alerts
```

`consumer_manifest.py check` validates locally and `just consumer-build` never pushes. Neither
validation nor local image verification grants deployment authority.
