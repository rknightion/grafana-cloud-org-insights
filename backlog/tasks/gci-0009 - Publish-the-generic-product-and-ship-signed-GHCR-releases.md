---
id: GCI-0009
title: Publish the generic product and ship signed GHCR releases
status: Parked
assignee:
  - '@codex'
created_date: '2026-08-24 15:15'
updated_date: '2026-08-24 16:35'
labels: []
dependencies: []
priority: high
type: task
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make the customer-neutral generic product repository public only after a working-tree and full-history privacy and secret audit, then add the standard rknightion CI, Release Please and multi-architecture GHCR publication contract without changing any live customer deployment.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Repository visibility is public only after the privacy gate passes
- [x] #2 CI uses the standard SHA-pinned rknightion shared workflows and retains the complete product test and identifier gates
- [x] #3 Release Please uses a short-lived repository-scoped GitHub App token from OpenBao and no durable PAT
- [ ] #4 GHCR publishes linux/amd64 and linux/arm64 images with immutable revision and release tags, provenance, SBOM and signing
- [x] #5 Local workflow, container and product validation passes and hosted runs are inspected without treating billing failure as code failure
- [x] #6 Documentation states how an ECS consumer pins a public GHCR digest, and any deployment repository edit is limited to a reviewed immutable source or image pin with no live apply
- [ ] #7 The full repository and reachable Git history contain no customer identifiers, customer-specific configuration, credentials or secret material according to the externally supplied pattern gate and independent scans
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
- [x] #4 Before visibility changes, retain in task notes the clean output of `bin/check-customer-identifiers --history` and the audited result of `detect-secrets scan --all-files`
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Freeze the current clean source revision and adversarially scan the working tree plus every reachable Git object for customer identifiers, identity-shaped data and secrets; stop before visibility changes on any unexplained match.
2. Compare current callers of the refreshed standard rknightion workflow hub, choose SHA-pinned reusable workflows, and preserve the existing full Python/consumer/Terraform validation gate.
3. Add Release Please configuration, container publication callers, supply-chain/security callers, provenance documentation and Renovate pin maintenance; build locally for both supported architectures without pushing a live/customer image.
4. Provision the repository-scoped OpenBao broker permission set, policy and GitHub OIDC role for Release Please, verify least privilege, then revoke the temporary admin session.
5. Run actionlint, zizmor, the full product suite, denylist/history scans and a local OCI build/label inspection; adversarially review the final diff and resolve Critical/Warning findings.
6. Replace the private lineage with one clean root commit, force-push while private, update the customer deployment source pin without applying it, rerun the clean-history audit, then make the generic repository and GHCR package public.
7. Inspect hosted workflows and package provenance, and record the exact public source SHA and GHCR digest while leaving all live runtime resources unchanged.

Leak remediation addendum:
8. Treat the committed denylist as a public-data leak and stop publication handoff work.
9. Move the customer-pattern set into a GitHub Actions secret and change the gate to accept only an external environment value or caller-supplied file; keep synthetic tests with invented sentinels.
10. Remove the denylist file and every customer-derived string from the replacement tree, then run targeted tests, the full suite, shipped-text, external-pattern tree/history scan and a pristine detect-secrets audit.
11. Create a brand-new root commit from the verified sanitized tree, remove or replace every public ref that reaches the disclosed lineage, close the obsolete release PR, and force-push main.
12. Re-run hosted CI and the privacy/secret gates on the rewritten public history; inspect public refs before resuming GHCR provenance handoff.
13. Record the incident and exact evidence in this task and preserve the separately validated deployment pin without any apply or live mutation.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Privacy audit found customer-derived identifiers only in the initial two private commits; the current tree and fixtures are clean. Rob explicitly authorised dropping the entire lineage, so publication will use a new clean root commit and update the deployment pin before visibility changes. Added standard SHA-pinned CI, signed multi-arch GHCR, Release Please, RC, cleanup and security workflows. Provisioned the repository-scoped OpenBao broker objects and the two Tailscale WIF identifier secrets; the temporary admin login was revoked. Direct anonymous GHCR-by-digest is the documented default, with ECR pull-through cache as an optional deployment policy that owns its required upstream credential.

Clean-lineage validation at 016fe73d706144c7094bb8f664bda511b1c4702e:
- Complete Python 3.13 suite: 1,337 passed, 2 skipped, 6,570 subtests in 65.22s.
- `bin/check-customer-identifiers --history`: working tree clean and all reachable history clean; exactly one reachable commit.
- `detect-secrets scan --all-files`: 13 heuristic findings audited as false positives - 12 secret-keyword example/test sentinels and pytest cache metadata; no credential material. The cache-only result disappears from a pristine checkout.
- Shipped-text gate, actionlint and zizmor --pedantic: clean; zizmor reported no findings.
- `tofu fmt -check -recursive terraform` plus fresh-data init/validate for the module and standalone example: passed with AWS provider 6.61.0.
- Local no-push builds succeeded for linux/amd64 image sha256:5ac1596d0328d29599768c850580a14b69b035d84c195b03c143622877b5359d and linux/arm64 image sha256:5fe117bd19b7883971f42ef60871d8c6a6c95892136f7e9aa5da14570ec0b59c. Both run as collector, use the expected entrypoint, and record exact revision 016fe73d706144c7094bb8f664bda511b1c4702e; `--help` ran successfully on both architectures. No registry login or push occurred.

Concurrent product documentation advanced the clean lineage before this evidence commit. The final pre-publication scan therefore covers four reachable commits, all clean; no unrelated work was discarded.

Publication gate completed at 3101797cab23f85f00fe836221f302ecb3a85357: the repository is public and the deployment repository is committed at 41d34c317de9a2e1554fc2e2f134ae40a2b2b48e with the identical immutable module/manifest pin. Fresh root validation and a read-only targeted plan passed; the plan remains the previously classified five task-definition replacements plus scheduler policy/target refreshes, and no apply occurred. Hosted runs were inspected: every runner-backed job failed before producing a single step or log, matching the account-level GitHub Actions billing condition. This is not a code failure and billing was not changed. Consequently no GHCR package, digest, signature, provenance or SBOM exists yet; acceptance criterion 5 remains deliberately unchecked. Resume by rerunning the hosted workflows after billing is restored, then verify the public package and complete this task.

Publication review found that the committed customer identifier denylist disclosed the exact strings it was intended to prevent. Rob explicitly requested deletion plus history rewrite and force-push. The replacement gate receives the sensitive pattern set externally so the public tree cannot reveal it.

CodeRabbit found one valid fail-open case: recursive grep errors were treated like no matches. The gate now accepts status 1 only as clean and fails closed on invalid patterns, read errors, or any other grep failure. Its task wording was also corrected so the public repository does not claim to ship a denylist.

Correction after acceptance-criterion reordering: the historical note about missing GHCR artifacts refers to criterion 4. Criterion 5 remains complete.

Post-rewrite GitHub ref audit:
- main is a clean root at 9cba9a0d5fba016b8686c28dec67daca475b7198; the committed denylist path is absent.
- all normal old branches and tags were overwritten or deleted.
- GitHub-owned refs/pull/1/head is read-only and its ancestry fails the external customer-pattern history gate. The REST delete attempt returned HTTP 422 refs/pull/* is read-only.
- repository visibility was immediately returned to PRIVATE so that residual PR ref is no longer publicly exposed.
- GitHub documentation requires Support to dereference affected pull requests, remove cached views and run garbage collection. Do not return the repository to public until Support confirms that purge and a ref audit passes.
- no customer deployment, image tag, ECS task definition, schedule, dashboard, alert, token, role, policy, or S3 object changed.
<!-- SECTION:NOTES:END -->
