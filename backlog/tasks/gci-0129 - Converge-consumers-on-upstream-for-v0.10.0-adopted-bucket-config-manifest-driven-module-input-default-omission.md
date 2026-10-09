---
id: GCI-0129
title: >-
  Converge consumers on upstream for v0.10.0 (adopted bucket config,
  manifest-driven module input, default omission)
status: In Progress
assignee: []
created_date: '2026-10-08 18:57'
updated_date: '2026-10-09 17:13'
labels:
  - consumer
  - handover
  - 'verify:2026-10-09'
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
- [x] #2 consumer_manifest module input and default omission shipped; explicit-wiring consumers and full manifests keep identical digests
- [x] #3 Dev consumer migrated to manifest mode on v0.10.0; one manual dev T2 exits 0 with immutable publication; no-change plan
- [ ] #4 Customer consumer migrated to manifest mode with manage_adopted_bucket_config, its own TLS policy resource moved into the module, default-equal keys pruned and dated narration removed; saved-plan exact apply, readback incl. effective lifecycle, natural T2 verified; no-change plan
- [x] #5 Customer dashboards republished from the v0.10.0 source after the customer rollout, with a readback diff
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-08: customer dashboards were 1-3 weeks behind and labelling had never been published. With owner approval all 12 were republished from the deployed v0.9.1 source (11 updated, labelling created). Readback diff against the offline build shows only server normalisation (transformation spec.id dropped). Earlier non-service-account edits were the owner's own. Republish again after the v0.10.0 customer rollout for the maturity change.

2026-10-08/09 v0.10.0 (tag c498570, PR 60; public image sha256:7ca7bd46 cosign-verified against the pinned container-publish identity and source SHA; contains 317465c, 7ba5172, a97b0d4). Manifest mode a97b0d4: independent adversarial review found two majors (tag precedence reversed vs real consumers; explicit arguments silently accepted beside a manifest), both fixed with failing-first tests, delta review accepted; explicit mode proven byte-identical to 7ba5172 by full mock-apply state diff. Dev (R-dev9): consumer moved to manifest mode, 29 keys pruned with digests unchanged, saved targeted plan classified image-only, exact apply 5/5/5, readback PASS, one manual dev T2 exit 0 (6/6 stacks, labelling 22/24, all sources healthy), maturity rubric v2 labelling dimension published, no-change plan PASS, dev dashboards republished. Customer (R-cust6): manifest mode with aws.manage_adopted_bucket_config, 18 keys pruned, TLS policy moved into the module, public-access block/versioning/encryption imported with no change, lifecycle replaced by the module's four rules (adds noncurrent expiry for every prefix), t1 schedule description to the module default; strict classifier accepted, exact apply (4 imported, 5 added, 6 changed, 5 destroyed), readback PASS, privacy before and after PASS (after asserts the module lifecycle), no-change plan PASS, one-time import/moved blocks then removed with plan still no-change. All 12 customer dashboards republished from v0.10.0; readback diff shows only server normalisation. Pending for AC4: the natural customer T2 on the new image (03:30 UTC).

loop20:0 implementation attempts; natural2026-10-09 03:30:26 scheduler launch matched exact deployed manifest consumer task definition and ARN, but stopped descriptor aged out and no ECS terminal event archive found. Healthy publication never substitutes for exit0. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop20-evidence/GCI-0129/. Later natural timer cancelled on D-AUTH20 SSO-expired failure during dev init; no login/auth retry permitted. AC4 remains unchecked; resume after auth restored at first later natural T2 exact-ARN capture with immutable timestamped/versioned publication.
<!-- SECTION:NOTES:END -->
