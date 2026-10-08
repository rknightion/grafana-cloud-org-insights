---
id: GCI-0129
title: >-
  Converge consumers on upstream for v0.10.0 (adopted bucket config,
  manifest-driven module input, default omission)
status: In Progress
assignee: []
created_date: '2026-10-08 18:57'
updated_date: '2026-10-08 18:57'
labels:
  - consumer
  - handover
dependencies: []
priority: high
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decisions 2026-10-08 (Rob), preparing the customer deployment for handover so its overlay differs from the reference deployment as little as possible. (1) manage_adopted_bucket_config manages an adopted bucket's public-access block, versioning, encryption, four lifecycle rules and TLS-deny policy, never the bucket; landed 7ba5172. Trigger: the customer adopted bucket lacked noncurrent-version expiry under state/ and locks/. (2) Core module consumer_manifest input replaces the hand-copied manifest glue in both consumers. (3) The manifest may omit keys equal to the module default; digests stay over the effective projection. Ship in v0.10.0 with the maturity labelling-score change, roll out to dev with one manual dev T2, then customer saved-plan rollout verified by natural runs. Fix forward, no rollback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 manage_adopted_bucket_config and bucket_policy_source_json shipped with tofu tests
- [ ] #2 consumer_manifest module input and default omission shipped; explicit-wiring consumers and full manifests keep identical digests
- [ ] #3 Dev consumer migrated to manifest mode on v0.10.0; one manual dev T2 exits 0 with immutable publication; no-change plan
- [ ] #4 Customer consumer migrated to manifest mode with manage_adopted_bucket_config, its own TLS policy resource moved into the module, default-equal keys pruned and dated narration removed; saved-plan exact apply, readback incl. effective lifecycle, natural T2 verified; no-change plan
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
