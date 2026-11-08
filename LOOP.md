# Loop: grafana-cloud-org-insights
tier: guarded
gate: just check
ci-required: ci-success
release-on-push: yes
deploy-on-push: no
grafana-stack: none
tracker: github
landing: pr

Issues are public: no customer identifier, stack name, account id, hostname or home path in them.

The tracker working model is `~/repos/agent-docs/docs/github-tracker.md` (maintainers only).

## Queue

- The queue is `just tracker queue`: open issues at Project Status Ready on the rknightion Project.
- A charter selects by labels (`type:task`, `type:bug`, `type:feature`, `needs-owner`,
  `needs-triage`) and Project fields (Status, Priority, Effort, Lane). Never queue a `needs-owner` or
  `needs-triage` issue, or the Renovate Dependency Dashboard (#10).
- Only the root writes issues and the Project, through `just tracker`; a lane returns the status and
  AC ticks it wants.
- A queue row names `#N`. A legacy id (`GCI-0001`) resolves with `just issue <ID>` (map:
  `.github/tracker/id-map.json`). A bare `#N` below 143 is a pull request or #10; imported issues
  start at #143.

## Credentials
- `just check` needs no AWS credentials, network or live estate; run it freely.
- Names only: `NAME_PREFIX` and `GCINSIGHT_S3_BUCKET` for `just check-tags`;
  `GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN`, a CI-only secret, for `just check-identifiers`.
- The per-stack reader token stays basic role None with the fixed query scope. Compare role drift as
  action and scope pairs, with a readback showing only approved pairs added.
- Minting or rotating a service account or reader token is a live write: take a fresh pre-run witness
  (role, token, parameter-store version) immediately before, and read back after. Never re-mint a
  working credential; token names are org-wide unique, so a needless mint leaves an untracked one.
- A named stack is per charter. This file names none.

## Traps
- `just check` takes 413-696 s and `just test` self-limits at 540 s. Give a gate run at least
  900 s; a 600 s or 700 s outer watchdog fails a healthy run, and a null exit is not a pass.
- Every watcher (gate, CI, research), not only the gate run, gets the 1500 s deadline; say so in
  each watcher brief.
- Two estate tiers, never mixed: a write-capable internal deployment tier, and a customer estate
  reached read-only (GET or existing read-only RPC routes) unless the charter names an exact write fence.
  Reader, image and publication grants never imply bucket lifecycle or policy writes.
- `just publish-image` is `[confirm]`-gated and pushes a real image. Never pass `--yes` or
  `JUST_YES=1`; a bypass granted once covers that one step and is no precedent.
- A green release-please PR read at an old head SHA proves nothing; re-read the head before judging CI.
  A merge made with a bot or App token triggers no push workflows, so a tag, release or image needs an
  explicit dispatch. An automated RC tag is not authority to publish a stable release.
- A generated `CHANGELOG.md` can carry characters the shipped-text gate forbids: normalise it in a
  workflow step, never rewrite history or exempt the file.
- `no-em-dashes` (part of `just check`) scans the whole tree except `codex/` and `testdata/`, so the
  moved board history under `.github/tracker/history/` is scanned too. Write fetched or research
  files with em dashes under `codex/` or the scratchpad, never elsewhere in the repo, or the gate
  fails.
- Schema-validation "skipped" is unproven. One empty instant read is not an absent series; read the
  tier's real lookback window. A gap is an absent series, never a zero.
- Promoted images are pinned by immutable digest. Consumer images are separate and unsigned; verify the
  public image with cosign against the pinned reusable identity, issuer, repository and source SHA.
- Rollouts run in the deployment repo, not here: its `just plan-out` then `just apply-plan-auto`
  (not recipes in this justfile) apply the same saved plan, never an implicit replan.
  Restore suspended schedules to their saved states, verify live, and end with a no-change plan. An
  unknown plan value is not equality: compare the effective scheduler policy after apply.
- A binary or config rollback does not undo a hydration schema change; restore the matching retained
  scan version after a fresh equality check.
- Before a manual or scheduled-task run, confirm no natural run is active or imminent. Validate the
  full `run-task` response and ARN before watching; capture the stopped-task descriptor within two
  minutes of watcher exit. On a timeout or watcher exit 3, adopt the recorded ARN; never start a
  second task.
- A changed immutable module ref, or a fresh deployment-repo checkout, needs `tofu init` in the
  deployment repo's main module before its `just check` or the pre-push validation hook; a stale module
  cache fails a healthy gate.
- `gcx config view` redacts the token; a redacted value gives a 401. Use `--raw`, in memory only,
  with no login, mint or persistence.
- A multipart S3 object's ETag is not its MD5; a single-part checksum assertion fails on it. Verify
  with a part-aware linkage, never a bare exit 0.
- Use a real `.venv` directory from `just setup`, never a symlink; the gate must run on a clean tree.
  Run consumer publication with a supported `python3`, with deployment pins committed first.
- `ci-success` is the only required gate. Red release-please, auto-rc or publish runs do not override
  it; report image-publish failure or skip separately, never as one verdict.
- Lanes write check scripts and evidence under `codex/` or the scratchpad, never `/tmp`, so the root
  can re-run the exact check.

## Mutexes
- The live deployment account, its infra-state lock and its write-capable Grafana stack are one serial
  resource, touched by the root only, never by a lane in parallel.
- A land or push event records a SHA resolved with `git rev-parse`; never type or expand one by hand.
- Publishing, tags and releases are root-only unless the charter grants a lane bounded push authority; a
  lane with that grant owns its landed-SHA CI, and the root never pushes across an in-flight landing.
