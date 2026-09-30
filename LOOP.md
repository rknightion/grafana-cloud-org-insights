# LOOP.md

This file holds loop-specific facts for this repository, so loop goals cite it instead of restating
them. Read it at loop preparation.

## Gates and commands

- `just check` is the gate, exactly what CI enforces: `fmt-check` + `lint` + `test` + `tf-validate` +
  `check-identifiers` + `no-em-dashes`. It runs with no AWS credentials, no network and no live
  estate, so run and rerun it freely (justfile: `check`; AGENTS.md "Task interface").
- `just setup` creates a repo-local virtualenv and installs the pinned pytest runner (justfile:
  `setup`).
- `just test [filter]` runs pytest offline through a guarded wrapper that terminates the process tree
  above 2 GiB RSS or 9 minutes (justfile: `test`).
- `just lint` refuses any stray Python dependency file (`requirements*.txt`, `pyproject.toml`,
  `Pipfile`, `poetry.lock`) - the collector ships stdlib-only by design; adding a dependency needs a
  Dockerfile change and review (justfile: `lint`).
- `just tf-validate` validates the reusable Terraform module and its standalone example and checks
  formatting (justfile: `tf-validate`).
- `just check-identifiers [--history]` scans tracked files, and with `--history` all reachable git
  history, for leaked customer identifiers; needs `GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN` in the
  environment, supplied only as a CI secret (justfile: `check-identifiers`).
- `just no-em-dashes` refuses em dashes in shipped text; private gitignored codex state is excluded
  (justfile: `no-em-dashes`).
- `just publish-image` is `[confirm]`-gated and pushes a real image to the configured registry. Never
  pass `--yes` or `JUST_YES=1` to bypass that gate (justfile: `publish-image`; AGENTS.md).
- `just check-tags [--fix]` audits or repairs one cost-allocation tag on a live deployment; needs
  `NAME_PREFIX` and `GCINSIGHT_S3_BUCKET` in the environment (justfile: `check-tags`).
- `just image` builds the collector image locally without pushing, for a parity check (justfile:
  `image`).
- Completion claims carry evidence: the completing SHA and the hosted CI run ID (AGENTS.md). A green
  local `just check` alone is not "Done".

## Release rules

No per-loop release cap; release per fan-out protocol §7. A release is instead
gated by explicit in-wave conditions (every planned feature push landed and its CI is green at the
refreshed PR head) and a wave can fail to complete it: one wave's release stayed Parked because the
live dev proof it depended on failed (`goal-2026-09-23-wave2.md` §"R6 release"; corresponding
`report-2026-09-23-wave2.md`: release Parked, "Stable v0.3.0 was not released").

## Environments and credential conventions

- Two estate tiers, never mixed: a write-capable internal deployment tier where a loop mints,
  deploys, publishes dashboards/alerts and runs live proof, and a separate customer estate reached
  strictly read-only (`GET` only, or existing read-only RPC routes). No write of any kind lands on a
  customer resource (`goal-2026-09-23-wave1.md`, items 5-8 of the external-write-authority list).
- The per-stack reader token stays pinned to basic role `None` and a single fixed datasource scope;
  role drift is compared as action/scope pairs, never as overall shape, and a post-change readback
  must show only the approved pairs added, with nothing else changed (AGENTS.md "Hard rules";
  `goal-2026-09-23-wave2.md` step 5 of the provisioner procedure).
- Minting or rotating a service account or reader token is a live write on the estate: take a fresh
  pre-run witness (role, token, parameter-store version) immediately before the run, because an
  earlier witness goes stale within the same run, then confirm by readback afterward
  (`goal-2026-09-23-wave2.md` step 5).
- Before any manual or scheduled-task run against the live deployment, re-confirm no natural
  scheduled run is currently active or imminent, to avoid a collision (`goal-2026-09-23-wave2.md`
  step 5).
- A promoted container image is pinned by immutable digest, never a mutable tag
  (`goal-2026-09-23-wave2.md` §"D2 ... approach").
- Env vars used by loop tooling (names only, no values): `NAME_PREFIX` and `GCINSIGHT_S3_BUCKET` for
  the tag-audit recipe; `GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN`, a CI-only secret, for the
  identifier-leak scan (justfile comments on `check-tags` / `check-identifiers`).

## Standing route exceptions

A confirm-bypass grant seen once (two live-deployment steps, one wave) was explicitly
bounded to that single wave and lapsed automatically at its end; it never applies to any other
recipe. Treat any future ask the same way, not as a precedent (`goal-2026-09-23-wave1.md` §"D5 Dev
rollout in-wave").

## Known traps

- A green release-please pull request read at an old head SHA proves nothing about a refreshed head;
  always re-read the head SHA before judging its CI (`goal-2026-09-23-wave2.md`, "A green
  release-please PR at an old head SHA proves nothing about the refreshed head").
- An automated merge authored by a bot/App token triggers no downstream push-triggered GitHub Actions
  workflows; cutting a tag, Release or image afterward needs a separate explicit dispatch of the
  release workflow (`goal-2026-09-23-wave2.md` §1 of the external-write-authority list, citing the
  same behaviour in a sibling repo's prior release).
- A generated `CHANGELOG.md` can copy old commit subjects verbatim, including characters a
  shipped-text gate forbids; fix by normalizing the generated file in a workflow step, never by
  rewriting historical commits or exempting the file from the gate (`goal-2026-09-23-wave2.md`
  §"D2 ... approach").
- Schema-validation "skipped" results (e.g. resources with no matching schema) are unproven, not
  passing; never count them as evidence (`report-2026-09-23-wave1.md`).
- A single instant/zero-lookback read returning empty is not evidence a metric series is absent; read
  over the tier's real lookback window before concluding a gap (`report-2026-09-23-wave1.md`;
  consistent with AGENTS.md "a gap is an absent series, never a zero").

## Cross-harness eligibility

None approved; ask at preparation.

## Resource mutexes

- The live deployment account (its infra-state lock included) and its write-capable Grafana stack are
  a single serial resource; only the root process touches them, never a lane in parallel
  (`goal-2026-09-23-wave1.md` §"Shared resources"; `goal-2026-09-23-wave2.md`: "Worktrees isolate
  files only. They do not isolate the [cloud] account, the OpenTofu state lock, the [dev] stack, Git
  refs or credentials; those stay serial on the root").
- Publishing (commit/push to a release-eligible branch, tagging, releasing) is root-only; lanes never
  write a tag or release by hand (`goal-2026-09-23-wave2.md` §"Forbidden everywhere").

## Grafana stacks

Named per goal at preparation. This file does not name a stack. The original wave default is no
customer writes. A later owner goal can authorize a narrow customer rollout; follow its explicit
write fence, not a blanket interpretation of Terraform apply authority. Reader-role, image and
publication grants do not implicitly authorize bucket lifecycle changes. Treat each authorized live
deployment and its write stack as the serial resource described under Resource mutexes.

## Verified loop3 operational lessons

- Raw label-risk matches need the dedicated current-object expiry under the reserved full-filename
  prefix `views/risk_label_hygiene.json`, in addition to scan and noncurrent-version expiry. Verify
  the actual bucket policy, versioning, encryption, public/TLS controls and effective view/task IAM
  before running a daily collector. A source gate is not that deployment proof. Adopted buckets need
  their owner's equivalent rule; do not add a competing lifecycle resource or infer new write rights.
- Rollback is the saved old manifest/module/immutable-image triplet with matching old tooling. The
  target-schema guard rejects incompatible projections before recovery writes; it is not a general
  downgrade converter. Never regenerate the saved old manifest blindly with new tooling.
- A real Logs Drilldown frontend control emitted generic `app` events. A backend query alone does
  not prove frontend analytics, human adoption or per-app attribution. Keep the service-account and
  before/after-discriminator limits explicit; datasource type is not an app identity.
- A safe IRM counter response does not make its credential narrow: captured integration read
  permissions also cover configuration, and client-side URL masking is not server-side redaction.
  Defer a new grant until its broader credential reach is proven safe.
- Run consumer publication with a supported Python executable. A login shell can resolve the system
  Python rather than the verified Homebrew Python. Commit deployment pins before starting a consumer
  build; the build correctly refuses uncommitted wiring.
- Capture ECS task descriptors promptly. Stopped-task records can disappear before a delayed
  readback; retain the exact immutable definition, task ID, live terminal output and S3 advancement,
  and name any missing descriptor proof instead of restarting a completed task.
