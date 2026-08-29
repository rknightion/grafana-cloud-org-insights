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
`bin/check-customer-identifiers --patterns-file`; the pattern set must never be committed to the public
product repository. A deployment wrapper passes
each historical fork path with `--forbidden-core-path`; the checker also rejects the product's standard
collector, scan, dashboard, and alert paths automatically. `bin/consumer-build` creates and verifies a
local candidate without registry access.
`bin/consumer-exec` runs product tooling under one exact runtime projection. None of these commands
deploys anything.
