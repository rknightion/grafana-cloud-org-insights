---
id: doc-0003
title: 'Consumer manifest, provenance, and immutable upgrade contract'
type: guide
created_date: '2026-08-24 12:02'
updated_date: '2026-08-24 12:38'
---
# Consumer manifest, provenance, and immutable upgrade contract

## Manifest contract

Each deployment repository owns one non-secret manifest. The manifest records:

- schema version;
- generic repository URL and full commit revision;
- deterministic overlay digest;
- deterministic per-runtime projection digests;
- runtime projections for collector, provisioner, dashboards, and alerts;
- deployment infrastructure choices; and
- explicit customer policy choices.

The reusable schema and validator live in this repository. The validator rejects unknown fields, missing explicit runtime values, moving revisions, credential-shaped values, projection drift, source-checkout mismatch, and a Terraform module ref that disagrees with the manifest.

The overlay digest is the SHA-256 of canonical JSON containing only `schema_version`, `runtime`, `aws`, and `policy`. Generated identity fields are excluded from their own digest. Each runtime projection digest is the SHA-256 of the exact declared manifest map for that runtime. Launcher controls emitted by the execution tool, including `GCINSIGHT_REQUIRE_EXPLICIT_CONFIG` and `GCINSIGHT_RUNTIME_CONFIG_DIGEST`, are outside the recorded map: the first selects fail-closed verification and the second carries the expected digest, so including either would make the digest self-referential. The runtime verifier hashes only the declared projection and compares it with that expected value.

## Build provenance

A candidate image is built only from a clean generic checkout whose `HEAD` equals the manifest revision. Customer configuration is not copied into the image. The build records OCI labels for:

- exact generic source revision and repository;
- exact deployment-repository revision; and
- `sha256:` overlay digest.

The build command verifies all runtime projections against the built image and never pushes. Registry publication is a separate, approval-gated action. Production wiring uses an immutable registry digest; a convenience tag is never sufficient identity.

## Upgrade procedure

1. Choose a reviewed full commit in this repository.
2. Fetch the commit and inspect the product diff and release notes.
3. Run the generic upgrade command against the deployment manifest and Terraform root. It updates the manifest revision and exactly one Terraform module `ref`, then regenerates all digests.
4. Check out that exact revision in a clean generic worktree.
5. Run the consumer drift check, complete product suite, customer-identifier gate, manifest tests, local image build, and isolated Terraform validation and plan.
6. Review generated catalogue, view, dashboard, alert, permission, schedule, and rate-card contracts against the previous candidate.
7. Commit the product and deployment repositories independently.
8. Publish and deploy only after a separate live-change approval.

The upgrade command never checks out branches, resolves a moving tag, copies generic source into the deployment repository, builds or pushes an image, or applies infrastructure.

## Mechanical drift proof

The consumer check must prove all of the following in one command:

- generic checkout `HEAD`, origin, cleanliness, and manifest source agree;
- manifest schema and all deterministic digests agree;
- runtime keys exactly match the product projection contract;
- Terraform module source uses the same full commit;
- the deployment contains no standard collector, scan, dashboard or alert core, and the deployment wrapper declares every historical Docker, test and Terraform-module path that must remain absent; and
- the product customer-identifier denylist is clean.

A green check establishes source and configuration identity. It does not authorize a deployment or prove current live state.
