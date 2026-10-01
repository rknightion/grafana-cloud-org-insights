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
- Publishing is root-owned unless the current goal grants a bounded lane commit/push authority.
  A lane with that grant owns its exact landed-SHA CI through a terminal result; the root never
  pushes across an in-flight lane landing. Tags and releases remain root-only unless explicitly
  granted; no lane writes either by hand.

## Grafana stacks

Named per goal at preparation. This file does not name a stack. The original wave default is no
customer writes. A later owner goal can authorize a narrow customer rollout; follow its explicit
write fence, not a blanket interpretation of Terraform apply authority. Reader-role, image and
publication grants do not implicitly authorize bucket lifecycle changes. Treat each authorized live
deployment and its write stack as the serial resource described under Resource mutexes.

## Verified loop3 operational lessons

- The loop3 burn-fast home dispatches each lane as its own async subagent, never a workflow; keep
  the goal's frozen model/authority routes and one writer per worktree. It does not waive attempt,
  review, privacy or task-surface gates.
- Use `just plan-out` to save a reviewed plan and `just apply-plan-auto` to apply that same plan,
  never an implicit replan. Temporary dev schedule suspension must be restored to the saved states;
  verify them live and finish with a no-change plan. This recipe is not broader customer authority.

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

## Verified loop4 decisions and traps

- Rob ratified the bounded label-risk native Pyroscope read-POST exception on 2026-09-30:
  only `querier.v1.QuerierService/LabelNames` and `LabelValues` in
  `collector/sources/label_risk.py`, on freshly discovered inventory endpoints. The general client
  remains GET-only. This is not a template for any other POST permission.
- Rob's 2026-09-30 D-L1 grant was one additive lifecycle write preserving all existing rules on
  the named adopted deployment bucket, plus at most one restore. It was loop4-only, not standing
  bucket-write authority. That write did not authorize a bucket-policy addition. A fresh missing
  TLS-deny policy blocks raw-label publication even when versioning, encryption, public-access
  controls and targeted retention pass; park the rollout rather than inventing authority.
- A pinned Python base digest can still contain fixed-version Debian CVEs. In loop4 the upstream
  `python:3.14-slim` tag still resolved to the pinned pre-fix digest, so the reproducible fallback
  pinned the matching OpenSSL binary packages to the fixed version. Prove both image architectures
  through the unchanged real Trivy gate; never add a fixed CVE to the ignore file. Exact package
  versions can retire from a rolling repository, in which case the build fails closed.
- Use the installed cosign executable, not an unconfigured mise shim. Verification binds the
  immutable GHCR digest to the pinned reusable signing-workflow identity, GitHub OIDC issuer,
  expected repository and exact source SHA. A signing job's success is not that readback. An ECR
  consumer build has different content/provenance and is not thereby a signed image.
- `consumer-exec` requires the manifest, deployment root, Terraform file, kind and command. The
  abbreviated loop3 publication command omitted two required arguments and fails before writing.
  Use its current CLI help and a supported `python3` on PATH.
- Capture and validate the full ECS `run-task` response and task ARN before arming a watcher.
  `tasks[0]` can be absent while the CLI exits successfully. On a watcher timeout, inspect and adopt
  the same recorded ARN, never launch a second task. Preserve the original run deadline and capture
  the stopped-task descriptor within two minutes of watcher exit.
- The loop4 tool schema exposed a 3600-second `watch_start` ceiling despite Appendix C's stated
  no-ceiling contract. Record the effective tool cap instead of claiming a 70-minute observation.
- ECS readback adds empty optional arrays and a zero container CPU that the submitted definition
  can omit. Classify those defaults against deployed source and verify every other image, role,
  environment, secret selector, command and task resource unchanged. A computed scheduler-policy
  refresh also needs an actual post-apply semantic equality witness, not a permissive type check.
- Grafana effective permissions can include narrower datasource metadata reads and the
  `sharedwithme` folder grant already covered by approved metadata-read wildcards. Retain the full
  pre/post action-scope sets and compare them, rather than reminting a working reader or treating
  redundant read scopes as query widening. Datasource query UID pins remain exact.

## Verified loop5 decisions and corrections

- The upstream Python base still resolved to the existing pinned digest on 2026-10-01. The PCRE2
  fallback pins `libpcre2-8-0=10.46-1~deb13u3` beside the existing fixed OpenSSL packages.
  Both architectures read back the fixed versions and passed the unchanged real Trivy gate in
  auto-rc run `36831756263` at `32258533d7e2e1fa006460224dca53135d975e98`. Exact versions still
  fail closed if Debian retires them. A historical green scan is not current exposure proof.
- The actionlint failure was an unknown `ubuntu-26.04` runner label, not a harden-runner timeout.
  The latest shared reusable release, v1.25.3, pins actionlint 1.7.12. The repository's
  `.github/actionlint.yaml` declares that label without changing hosted job runners, permissions
  or steps; hosted actionlint run `36832334419` passed at `f767fad63ad92d9ca63ddea6777765125770e287`.
- The adopted deployment bucket's owner added and verified a Terraform-managed TLS-only policy
  during loop5 preparation. This is not standing bucket-write authority. A rollout must freshly
  witness the effective policy and all privacy prerequisites before apply and again after the
  provisioner, before daily raw-label publication; no bucket configuration write is granted in loop5.
- Loop4's root gap from 2026-10-01 03:13:59 to 06:08:19 UTC was shared with a concurrent pi root
  on the same Mac: their pending tool batches completed within 0.1 seconds at 06:07:48 UTC, and
  `pmset` showed no machine sleep. It was not established as a loop4-specific stall. If another
  gap occurs, record its UTC bounds and continue; do not diagnose it inside a rollout loop.
- Stable v0.4.1 source `ef2033b7d9711b150ae3aa7a6ba5ab3ce2907327` has signed, independently
  verified GHCR index `sha256:d029d6a5bd84b3829b274e646d5f8513cbef68a1058a6bffc99c238a12d13d6f`.
  Both dev and the owner-authorized customer rollout built separate unsigned ECR consumer images
  from that source. Each manual tier used one recorded ARN with prompt stopped-task capture;
  the customer provisioner preserved every live reader identity, token ID, SSM version, permission
  pair and query pin. Dev schedules were restored; customer schedules were never suspended.
  Customer dashboard and alert publication was read back, preserving existing rule routing and pause
  states without activation. Deployment-specific digests and identities stay in private records.
- IAM simulation groups multi-resource object decisions under `ResourceSpecificResults`; its
  top-level aggregate is not the individual resource decision. Inspect every resource/action pair,
  including version reads and deletes, and test bucket-list prefixes separately.

## Verified loop6 parity and audit decisions

- Dev mirrors the customer tier cadence, UTC timezone and caller deadlines. Staggered start times
  may remain when current shared-egress topology and observed durations justify them; offsets reduce
  coincident demand, never guarantee non-overlap. Smaller dev task sizing may remain when the live
  estate and healthy runs justify it. Record retained differences in the deployment source comments,
  rather than silently treating every unequal value as drift.
- A deliberate dev policy-validation case may differ from an undeclared customer policy. Preserve
  honest unreadable/null outcomes; neither false compliance nor a guessed customer policy is parity.
  Created versus adopted resource ownership is also intentional. Org, write stack, bucket, roles,
  secret selectors, reader credentials and consumer identities must remain isolated.
- A deadline-only apply can refresh scheduler targets and plan a computed scheduler IAM policy.
  Verify the actual post-apply policy against the prior semantic document. An unknown plan value is
  not evidence of equality. ECS compatibility enum order may vary; compare the full capability set,
  while retaining exact comparisons for image, environment, command, resources and role bindings.
- Closeout audit grants support a per-repository object with `refs` and `allow_non_fast_forward`.
  Explicitly grant expected release-please and dependency-bot branch rewrites under the latter,
  together with their permitted ref changes. This does not grant the root a force push or history
  rewrite, and it does not excuse an unlisted remote mutation.
- Documentation audit acceptance separates factual review, the offline gate, exact landed CI and
  live proof. A code or CLI discrepancy outside the doc lane is tracked for later work, not repaired
  implicitly. Shipped examples must describe both side effects and the separate authority gate;
  invoking help must not be assumed safe for a legacy live-probe script.
