---
id: GCI-0021
title: Migrate the repo task surface to just and retire Makefiles and ad-hoc scripts
status: To Do
assignee: []
created_date: '2026-08-28 19:32'
labels: []
dependencies: []
priority: medium
type: chore
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
# Migrate grafana-cloud-org-insights to `just`

Consistent with the frozen fleet standard (`JUST-FLEET-STANDARD.md`). Do not re-litigate anything
marked FROZEN there; this task instantiates it for this repo.

## 1. Outcome

A top-level `justfile` is the repo's task surface. `just --list` shows every dev/CI task. `just check`
is the exact local equivalent of what `.github/workflows/ci.yml` enforces (pytest, the stdlib-only
dependency-file guard, the customer-identifier scan, the em-dash scan, and OpenTofu validate/fmt on
both `terraform/` and `terraform/examples/standalone/`). There is **no Makefile to delete** - this
repo never had one. The five real shell scripts under `bin/` all stay as files (each is a KEEP under
§6 - argument parsing, loops, or a deployment-scoped audit) but are only ever invoked through a `just`
recipe from here on. `ci.yml`'s three jobs (`tests`, `identifiers`, `terraform`) each call `just`
instead of inlining shell. `AGENTS.md` gets the standard Task interface section. `backlog/config.yml`'s
`definition_of_done` names `just` recipes instead of raw commands.

This repo is Python, stdlib-only by deliberate design (`Dockerfile:5-8`, enforced by
`ci.yml`'s "Refuse a dependency file" step) - there is no `pyproject.toml`, no lockfile, no linter, no
formatter, no type checker anywhere in the repo. `pytest==9.1.1` is CI/dev-only tooling, pinned by
version string in `ci.yml:30`, never a committed dependency file. The justfile below reflects that
reality: `lint` and `fmt`/`fmt-check` exist (mandatory vocabulary) but `lint` is the dependency-file
guard (there is no other static analysis in this repo) and `fmt` only formats the justfile itself.
`typecheck`, `build`, `gen`/`gen-check`, `docs` are deliberately omitted - the repo has none of them.

## 2. The complete justfile

Create `justfile` at the repo root:

```just
set shell := ["bash", "-euo", "pipefail", "-c"]

# show the task surface
default:
    @just --list

# create a repo-local virtualenv and install the pinned pytest test runner (idempotent)
setup:
    python3 -m venv .venv
    .venv/bin/pip install --disable-pip-version-check --quiet pytest==9.1.1

# format the justfile itself (this repo has no Python formatter - it ships zero third-party deps)
[group('check')]
fmt:
    just --fmt

# verify the justfile is formatted
[group('check')]
fmt-check:
    just --fmt --check

# refuse a stray Python dependency file - this collector is stdlib-only by design
[group('check')]
[script('bash')]
lint:
    for f in requirements.txt requirements-dev.txt pyproject.toml Pipfile poetry.lock; do
      if [ -e "$f" ]; then
        echo "error: $f exists - this project ships a stdlib-only collector; the container image" >&2
        echo "error: installs nothing. Adding a dependency needs a Dockerfile change and a review." >&2
        exit 1
      fi
    done
    echo "no dependency files present"

# run the pytest suite (offline by construction - no AWS, no network, no credentials)
[group('check')]
[no-exit-message]
test filter="":
    .venv/bin/python3 -m pytest tests -q {{ if filter == "" { "" } else { "-k " + quote(filter) } }}

# validate the reusable terraform module and the standalone example, and check formatting
[group('infra')]
[no-exit-message]
tf-validate:
    cd terraform && tofu init -backend=false && tofu validate
    cd terraform/examples/standalone && tofu init -backend=false && tofu validate
    tofu fmt -check -recursive terraform

# scan tracked files (and, with --history, all reachable git history) for leaked customer identifiers
# requires GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN in the environment (a repository secret in CI)
[group('check')]
check-identifiers:
    bin/check-customer-identifiers --history

# refuse em dashes in shipped text - house style is a spaced hyphen
[group('check')]
[script('bash')]
no-em-dashes:
    set -uo pipefail
    hits=$(grep -rIn $'—' . \
      --exclude-dir=.git --exclude-dir=backlog --exclude-dir=testdata \
      --exclude-dir=__pycache__ --exclude-dir=.terraform || true)
    if [ -n "$hits" ]; then
      echo "em dashes present, use a spaced hyphen:"
      echo "$hits"
      exit 1
    fi
    echo "clean"

# THE GATE - exactly what CI enforces
[group('check')]
check: fmt-check lint test tf-validate check-identifiers no-em-dashes

# audit (or, with --fix, repair) the one Cost Explorer allocation tag on a live deployment
# needs NAME_PREFIX and GCINSIGHT_S3_BUCKET in the environment - see bin/check-tags.sh header
[group('infra')]
check-tags *args:
    bin/check-tags.sh {{ args }}

# build the collector image locally without pushing (parity check)
[group('build')]
image:
    bin/build-and-push.sh --no-push

# build and push the collector image to ECR as an immutable sha-<commit> tag
# needs GCINSIGHT_ECR_REPOSITORY (or pass --repo via args); see bin/build-and-push.sh header for flags
[group('release')]
[confirm('push a new collector image to the configured ECR repository?')]
publish-image *args:
    bin/build-and-push.sh {{ args }}

# build and verify a local immutable consumer candidate (never pushes)
[group('build')]
consumer-build manifest deployment_root terraform:
    bin/consumer-build --manifest {{ quote(manifest) }} --deployment-root {{ quote(deployment_root) }} --terraform {{ quote(terraform) }}

# execute a tool under one validated non-secret consumer projection
[group('dev')]
consumer-exec manifest deployment_root terraform kind *args:
    bin/consumer-exec --manifest {{ quote(manifest) }} --deployment-root {{ quote(deployment_root) }} --terraform {{ quote(terraform) }} --kind {{ quote(kind) }} -- {{ args }}

# remove the local virtualenv (setup can always recreate it)
[group('dev')]
clean:
    rm -rf .venv
```

Notes on choices baked into the file above (do not change without a new fact):

- `setup` targets a repo-local `.venv` rather than a user/global site-packages, per §1's "no global
  installs" rule. `test` invokes `.venv/bin/python3` directly rather than assuming an activated shell,
  because each recipe line/script is its own process.
- `lint` and `no-em-dashes` use `[script('bash')]` because both have real control flow (a `for` loop
  and an `if` guarding a multi-line `grep`) - §10's documented fix for "extra leading whitespace" on
  multi-line constructs in a line-based recipe.
- `test`'s `filter` param mirrors the mandatory contract in §1 ("optional `filter=""` param where the
  runner supports it") and uses `quote()` to avoid the `{{arg}}` interpolation-loses-quoting trap
  (§10).
- `tf-validate` chains `cd dir && tofu ...` on one line per directory because each recipe line is a
  separate shell (§10) - a bare `cd terraform` on its own line would not persist to the next line.
- `check-tags`, `publish-image`, and `consumer-exec` pass through `*args`/positional params rather than
  inventing a fixed just-side flag set, because the underlying scripts already have their own
  documented flags (see their `--help`/header comments) and duplicating that surface in the justfile
  would drift.
- No `typecheck`, `build`, `gen`, `gen-check`, `run`, or `docs` recipe: this repo has no type checker,
  no compiled build artifact, no generated file with a regeneration script (`VIEW_INPUTS` in
  `collector/emit/hydrate.py` is hand-written and verified by a test that re-derives it, per
  `AGENTS.md:104-109` - there is no `gen` script to wrap), and no local docs build tool.

## 3. Makefile disposition

None. `find . -not -path '*/vendor/*' ... -iname Makefile -o -iname GNUmakefile` returns nothing.
**No Makefile step is needed** - do not create one to satisfy a template; this repo never had one.

## 4. Script disposition

| Script | Disposition | Recipe | Why |
|---|---|---|---|
| `bin/build-and-push.sh` (136 lines) | KEEP | `image` (no-push variant), `publish-image` (`[confirm]`) | Argument parsing (`--repo`, `--no-push`, `--allow-dirty`, `--publish-latest`), conditional git-dirty checks, `set -euo pipefail` control flow. A real deployment tool, not a thin wrapper. |
| `bin/check-tags.sh` (200 lines) | KEEP | `check-tags` | Loops over AWS resources (ECS cluster, 4 task-definition tiers, S3, Secrets Manager, Firehose), conditional `--fix` mode, requires deployment-identifying env vars with no defaults (`NAME_PREFIX`, `GCINSIGHT_S3_BUCKET`). Audits one live deployment; cannot be inlined into a generic recipe. |
| `bin/check-customer-identifiers` (101 lines) | KEEP | `check-identifiers` | Argument parsing (`--history`, `--patterns-file`), a `while read` loop over `git rev-list --all` with per-commit `git grep`/`git show`/`git ls-tree` calls. Real control flow. |
| `bin/consumer-build` (68 lines) | KEEP | `consumer-build` | Argument parsing over 5 flags (`--manifest`, `--deployment-root`, `--terraform`, `--tag`, `--platform`) with a docker build/verify sequence. |
| `bin/consumer-exec` (37 lines) | KEEP | `consumer-exec` | Argument parsing including a `--` passthrough separator for an arbitrary wrapped command. |

No script in this repo qualifies for ABSORB. There is no thin sequencer script (a `plan.sh`/`init.sh`/
`setup.sh` that only chains a couple of commands) anywhere in `bin/` - every shell script here does
real argument parsing, loops, or both.

`bin/*.py` files (`alerts.py`, `cost_model.py`, `dashboards.py`, `provision.py`, `trace.py`,
`consumer_manifest.py`, `probe_*.py`, `make_local_views.py`, `make_compose_fixture.py`) are real
Python programs invoked directly (`python3 bin/foo.py ...` / `./bin/foo.py ...`), documented that way
in `README.md` and `RUNBOOK.md` with their own multi-flag CLIs. They are out of scope for this
migration (§6's KEEP category, "real programs") - do not wrap them in `just` recipes; that would
either duplicate their `--help` output in the justfile or force a narrowed shape onto tools with
larger CLIs than the mandatory/optional vocabulary anticipates. `scan.py` at the repo root is the same
category.

## 5. CI changes

### `.github/workflows/ci.yml`

Add a `setup-just` step to each job that will call `just` (`tests`, `identifiers`, `terraform`).
Pin by SHA matching this repo's existing convention (see `actions/checkout` and `actions/setup-python`
pins already in this file for the exact style):

```yaml
      - uses: extractions/setup-just@<pin-to-current-release-sha> # v4
        with:
          just-version: '1.58.0'
```

**`tests` job** - replace the "Refuse a dependency file", "Install test runner", and "Tests" steps:

```yaml
  tests:
    name: pytest
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: '3.14'
      - uses: extractions/setup-just@<pin> # v4
        with:
          just-version: '1.58.0'
      - name: Lint (refuse a dependency file)
        run: just lint
      - name: Set up test runner
        run: just setup
      - name: Tests
        # Offline by construction - no AWS, no network, no credentials. If this needs either, the
        # fixture wiring has regressed and the suite has stopped being reproducible.
        run: just test
```

**`identifiers` job** - replace "Scan" and "No em dashes in shipped text":

```yaml
  identifiers:
    name: no leaked identifiers
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: extractions/setup-just@<pin> # v4
        with:
          just-version: '1.58.0'
      - name: Scan
        env:
          GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN: ${{ secrets.CUSTOMER_IDENTIFIER_PATTERN }}
        run: just check-identifiers
      - name: No em dashes in shipped text
        run: just no-em-dashes
```

**`terraform` job** - keep the `opentofu/setup-opentofu` step (the recipe still needs `tofu` on PATH;
`just` orchestrates, it does not install tools), replace the three `run:` bodies:

```yaml
  terraform:
    name: tofu validate
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: opentofu/setup-opentofu@a1320f892987e89d278cc92dc5adc984fb93aca4 # v2.0.2
      - uses: extractions/setup-just@<pin> # v4
        with:
          just-version: '1.58.0'
      - name: Validate and check formatting
        run: just tf-validate
```

**`ci-success` job**: do not touch. Same `needs: [tests, identifiers, terraform]`, same job name, same
`if: always()` logic.

### Other workflow files - do NOT touch

`actionlint.yml`, `zizmor.yml`, `docker-security.yml`, `publish.yml`, `ghcr-cleanup.yml`,
`arm-automerge.yml`, `auto-rc.yml`, `trigger-docs-sync.yml`, `release-please.yml`, `codeql.yml`,
`dependency-review.yml`, `scorecard.yml` contain no build/test/lint `run:` logic to migrate (verified:
`grep -n 'run:'` across all of them returns nothing except `publish.yml`'s one-line
`git rev-parse HEAD` output-capture and `ghcr-cleanup.yml`'s `dry-run` input plumbing - neither is
task logic). These are GitHub-native workflows (release automation, security scanning, dependency
review, cleanup) per §8 - leave every one exactly as-is.

## 6. Docs and agent-contract changes

- `README.md:122` - `./bin/make_local_views.py # compose views from the committed fixture` stays
  as-is (a direct Python program invocation, not a `make`/script-path reference this migration
  touches - see §4 above on why `bin/*.py` programs are out of scope).
- `README.md:136` (AGENTS.md's Testing section actually - the anchor is `AGENTS.md:131-137`):
  ```
  The suite runs with no AWS credentials, no network and no live estate:

  ```bash
  python3 -m pytest tests -q
  ```
  ```
  Replace the fenced command with:
  ```bash
  just test
  ```
- No file in this repo references `make <target>` anywhere (`grep -rn 'make [a-z-]\+' AGENTS.md
  README.md CLAUDE.md` returns nothing but unrelated prose hits like "would make a broken gatherer
  look..." - verified by hand, not a `make` invocation).
- Add a `## Task interface` section to `AGENTS.md` (place it near the existing `## Testing` section)
  reading exactly the block from §9 of the fleet standard:

  ```markdown
  ## Task interface

  This repo's task surface is a `justfile`. Discover it, don't guess it:

      just --list                        # human-readable
      just --dump --dump-format json     # machine-readable
      just --show <recipe>               # what a recipe actually runs

  - `just check` is the full gate and is exactly what CI enforces. It must pass before you commit.
  - Prefer `just <recipe>` over the underlying tool. If you are typing `pytest`, you want `just test`.
  - Run `just` with stdin from /dev/null. Recipes marked `[confirm]` are destructive - stop and ask
    before running one; never pass `--yes` or `JUST_YES=1`.
  - If a task you need does not exist, add a recipe with a `#` doc comment and a `[group(...)]`
    rather than running a bare command.
  ```

  Do not paste the recipe list itself into `AGENTS.md` - it rots (§9).
- `CLAUDE.md` (26 bytes - almost certainly a pointer to `AGENTS.md`) - read it and, if it duplicates
  any task-running instructions rather than just pointing at `AGENTS.md`, apply the same edit there.

## 7. `backlog/config.yml`

Current `definition_of_done`:

```yaml
definition_of_done:
  - "python3 -m pytest tests -q"
  - "tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/"
  - "customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean"
```

Replace with:

```yaml
definition_of_done:
  - "just test"
  - "just tf-validate"
  - "just check-identifiers and just no-em-dashes both return clean"
```

Edit this file only through the `backlog` CLI's config path if one exists for this field; if the CLI
has no config-editing subcommand for `definition_of_done`, this is one of the rare fields edited by
hand in `backlog/config.yml` itself (it is project configuration, not a tracked task/doc record) -
confirm the CLI's own docs before hand-editing, since `[[operating-model]]`'s "never hand-edit a
tracker's markdown" rule targets tasks/docs, not this settings file.

## 8. Order of work

1. Add `justfile` at the repo root (§2), exactly as specified.
2. Add `.venv/` to `.gitignore` (currently absent - `setup` will create `.venv/` and it must not be
   tracked or picked up by the customer-identifier / em-dash scans).
3. Run `just --fmt --check` locally to confirm the file as authored is already formatted (or run
   `just fmt` once and commit the result).
4. Run `just setup && just check` locally end-to-end. Fix anything that does not reproduce the
   current CI behavior exactly before touching CI.
5. Update `.github/workflows/ci.yml` per §5. Push and confirm the `tests`, `identifiers`, `terraform`,
   and `ci-success` jobs all go green on a PR/branch before merging - do not edit CI and delete
   nothing else in the same step.
6. Update `AGENTS.md` (§6) and `backlog/config.yml` (§7).
7. Only once CI is green on the new recipes: there is nothing to delete (no Makefile, no ABSORB
   scripts). This migration adds a justfile and repoints CI/docs/config at it; it does not remove any
   existing file. Confirm this explicitly in the PR description so a reviewer does not go looking for
   a deletion step that does not exist.

## 9. Traps specific to this repo

- **This repo is genuinely Makefile-free and ABSORB-free.** Do not invent a Makefile-deletion step or
  force a script into ABSORB to satisfy the general shape of a migration task - the CI guard at
  `ci.yml`'s "Refuse a dependency file" step is itself evidence of how deliberately minimal this repo's
  tooling is kept; matching that minimalism in the justfile is correct, not incomplete.
- **`check-identifiers` requires a secret that is not present in a normal local checkout.**
  `GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN` is a GitHub repository secret (`bin/check-customer-identifiers`
  exits 2 without it or `--patterns-file`). `just check` will fail locally for a developer with no
  access to that secret - this matches current CI-only behavior exactly and is not a regression, but
  say so if anyone reports "`just check` fails on my machine".
- **`no-em-dashes` and `lint` need `[script('bash')]`, not a plain recipe body.** Both have multi-line
  `if`/`for` control flow, which hits the documented "extra leading whitespace" parse error in a
  normal line-based recipe (standard §10). Do not try to flatten them with `&&` chains - the original
  CI logic (a `for` loop in `lint`'s dependency-file guard, an `if` in `no-em-dashes`) is clearer kept
  as real shell.
- **`tf-validate`'s two `cd` invocations must stay on the same line as their `tofu` calls.** Each
  recipe line is its own shell (§10); a bare `cd terraform` on its own line would silently not affect
  the following line's `tofu validate`, which would then run against the repo root and fail confusingly.
- **`bin/check-tags.sh` and `bin/build-and-push.sh` are deployment-mutating and credential-gated** -
  `check-tags --fix` mutates live AWS tags, `build-and-push.sh` pushes to ECR by default. The
  `publish-image` recipe carries `[confirm]` for exactly this reason; `check-tags` does not, because
  its default (no `--fix`) mode is a read-only audit and the mutating path is opt-in via the script's
  own `--fix` flag passed through `*args` - do not add `[confirm]` to `check-tags` itself, since that
  would force a confirmation prompt on the common read-only audit path too.
- **No formatter or type checker exists in this repo.** Do not add `ruff`/`black`/`mypy` recipes or a
  dependency on them "to complete the vocabulary" - that would contradict the stdlib-only design this
  repo's own CI actively guards (`ci.yml`'s "Refuse a dependency file" step, mirrored as `just lint`).
- **`.venv` must be added to `.gitignore`** before or in the same change as the justfile - it does not
  exist there today and nothing else in this repo currently creates a local virtualenv.

## 10. Out of scope

- Every `bin/*.py` program (`alerts.py`, `cost_model.py`, `dashboards.py`, `provision.py`, `trace.py`,
  `consumer_manifest.py`, `probe_datasources.py`, `probe_regions.py`, `probe_usage_signals.py`,
  `make_local_views.py`, `make_compose_fixture.py`) and root `scan.py` - real programs with their own
  documented multi-flag CLIs, invoked directly per `README.md`/`RUNBOOK.md`. Do not wrap in `just`
  recipes.
- All five KEEP shell scripts stay as files: `bin/build-and-push.sh`, `bin/check-tags.sh`,
  `bin/check-customer-identifiers`, `bin/consumer-build`, `bin/consumer-exec`. They get recipes as
  entry points; they are never absorbed or deleted.
- Every GitHub-native workflow: `actionlint.yml`, `zizmor.yml`, `docker-security.yml`, `publish.yml`,
  `ghcr-cleanup.yml`, `arm-automerge.yml`, `auto-rc.yml`, `trigger-docs-sync.yml`, `release-please.yml`,
  `codeql.yml`, `dependency-review.yml`, `scorecard.yml`. Do not fold any of these into `just`, and do
  not touch `release-please-pat`/OpenBao-broker auth wiring in `release-please.yml` or
  `trigger-docs-sync.yml`.
- `ci-success`'s aggregator logic, `permissions:` blocks, `concurrency:` groups,
  `persist-credentials: false`, and every SHA-pinned `uses:` step in `ci.yml` - preserve verbatim
  except for the `run:` body replacements and the added `setup-just` steps specified in §5.
- `terraform/` module content itself - only the CI invocation of `tofu` changes (from inline `run:` to
  `just tf-validate`), not the module or its examples.
- `Dockerfile`, `docs.toml`, and the zensical/m7kni.io docs-hub wiring - no local docs build tool is
  referenced anywhere in this repo, so no `docs`/`docs-serve` recipe is added.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Top-level justfile exists with all seven mandatory recipes (default, setup, fmt, fmt-check, lint, test, check) plus tf-validate, check-identifiers, no-em-dashes, check-tags, image, publish-image, consumer-build, consumer-exec, clean
- [ ] #2 just check passes locally and is exactly what ci.yml's tests/identifiers/terraform jobs enforce (pytest, dependency-file guard, customer-identifier scan, em-dash scan, tofu validate/fmt for terraform/ and terraform/examples/standalone/)
- [ ] #3 just --fmt --check passes on the justfile
- [ ] #4 just --list shows a doc comment and a group for every public recipe
- [ ] #5 No Makefile exists in the repo (none existed before this migration either - confirmed absent, not deleted)
- [ ] #6 All five KEEP shell scripts (bin/build-and-push.sh, bin/check-tags.sh, bin/check-customer-identifiers, bin/consumer-build, bin/consumer-exec) remain as files and are each reachable only via a just recipe
- [ ] #7 ci.yml's tests, identifiers, and terraform jobs call just recipes (just lint, just setup, just test, just check-identifiers, just no-em-dashes, just tf-validate) via a pinned extractions/setup-just step, and ci-success still gates on the same three job names
- [ ] #8 AGENTS.md (and CLAUDE.md if it duplicates the instruction) references just --list / just --dump / just --show instead of make or a raw command, and includes the Task interface section from the fleet standard
- [ ] #9 backlog/config.yml's definition_of_done names just test, just tf-validate, and just check-identifiers/just no-em-dashes instead of raw python3/tofu/ci.yml-gate references
- [ ] #10 .venv/ is added to .gitignore before or alongside the justfile
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
