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
check-identifiers *args:
    bin/check-customer-identifiers --history {{ args }}

# refuse em dashes in shipped text - house style is a spaced hyphen
[group('check')]
[script('bash')]
no-em-dashes:
    set -uo pipefail
    hits=$(grep -rIn $'\342\200\224' . \
      --exclude-dir=.git --exclude-dir=backlog --exclude-dir=testdata \
      --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.terraform || true)
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
image *args:
    bin/build-and-push.sh --no-push {{ args }}

# build and push the collector image to ECR as an immutable sha-<commit> tag
# needs GCINSIGHT_ECR_REPOSITORY (or pass --repo via args); see bin/build-and-push.sh header for flags
[confirm('push a new collector image to the configured ECR repository?')]
[group('release')]
publish-image *args:
    bin/build-and-push.sh {{ args }}

# build and verify a local immutable consumer candidate (never pushes)
[group('build')]
consumer-build manifest deployment_root terraform *args:
    bin/consumer-build --manifest {{ quote(manifest) }} --deployment-root {{ quote(deployment_root) }} --terraform {{ quote(terraform) }} {{ args }}

# execute a tool under one validated non-secret consumer projection
[group('dev')]
consumer-exec manifest deployment_root terraform kind *args:
    bin/consumer-exec --manifest {{ quote(manifest) }} --deployment-root {{ quote(deployment_root) }} --terraform {{ quote(terraform) }} --kind {{ quote(kind) }} -- {{ args }}

# remove the local virtualenv (setup can always recreate it)
[group('dev')]
clean:
    rm -rf .venv
