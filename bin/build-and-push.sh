#!/usr/bin/env bash
# Build the collector image and push it. One command, because the platform ships as a single package that
# builds and runs its own image  -  a README list of docker steps is how the code and the running image
# drift apart.
#
#   just publish-image                           # confirm, then build + push an immutable sha-<commit> tag
#   just publish-image --repo <uri>              # somewhere else (a customer's registry)
#   just image --repo <uri>                      # build only, for a local parity check
#   just publish-image --allow-dirty             # push from a dirty tree, deliberately
#   just publish-image --publish-latest          # ALSO move :latest (live deployment opt-in)
#
# TAGS: `:sha-<short>` by default. `:latest` only with `--publish-latest`.
#
# The production task definitions are pinned to a commit-addressed tag. Normal invocation publishes the
# next immutable candidate without changing production; deployment is the separate Terraform pin/apply.
# `--publish-latest` exists only for compatibility with an invocation that deliberately still uses that
# mutable tag and is not the production deployment path.
#
# The SHA tag supports an immutable Terraform `var.image` pin and rollback without rebuilding. It also
# makes a failing task attributable to a commit. By contrast, two Fargate tasks an hour apart can run
# different code under the same `:latest` task definition.
#
# ARM64 always. Fargate ARM64 is ~20% cheaper for identical work and the collector is pure Python. An x86
# image on an ARM64 task definition fails at RUNTIME with `exec format error`, not at plan time.

set -euo pipefail

REPO="${GCINSIGHT_ECR_REPOSITORY:-}"
REGION="${AWS_REGION:-eu-west-1}"
PUSH=1
ALLOW_DIRTY=0
PUBLISH_LATEST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --no-push) PUSH=0; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --publish-latest) PUBLISH_LATEST=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$REPO" ]; then
  echo "error: set GCINSIGHT_ECR_REPOSITORY or pass --repo with the ECR repository URI" >&2
  exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# A pushed image must be attributable to a real commit. A local parity build may run from an exported
# source tree, where `sha-nogit` is explicit and harmless because nothing leaves the machine.
if FULL_SHA="$(git rev-parse HEAD 2>/dev/null)" && SHA="$(git rev-parse --short HEAD 2>/dev/null)"; then
  :
elif [ "$PUSH" -eq 1 ]; then
  echo "error: cannot determine a git commit; refusing to push an unattributable image" >&2
  exit 2
else
  SHA="nogit"
  FULL_SHA="unknown"
fi
DIRTY=0
if [ -n "$(git status --porcelain --untracked-files=normal -- . 2>/dev/null)" ]; then
  DIRTY=1
  SHA="${SHA}-dirty"
fi

# A dirty tree REFUSES to push unless told explicitly. This is not fussiness: a `:latest` built from a
# dirty tree took the platform down for three hours on 2026-08-20. That image carried an `ai.py` which
# emitted a label its own `guard.py` rejected  -  a half-finished edit, built and pushed mid-change. It sat
# harmless until an input appeared that exercised the path, then every scheduled t1 run exited non-zero
# before publishing. The `-dirty` SHA tag recorded the provenance perfectly and nothing read it.
#
# `--allow-dirty` is the deliberate override, and it prints what is uncommitted so the choice is informed.
# Combining it with `--publish-latest` moves uncommitted code directly into the live task definitions.
if [ "$DIRTY" -eq 1 ] && [ "$PUSH" -eq 1 ] && [ "$ALLOW_DIRTY" -eq 0 ]; then
  echo "REFUSING to push from a dirty working tree." >&2
  echo "" >&2
  echo "Uncommitted changes:" >&2
  git status --short -- . >&2
  echo "" >&2
  echo "Commit first, or pass --allow-dirty if the tree is deliberately ahead of a commit and you" >&2
  echo "have run the tests. Adding --publish-latest would move that dirty image into production." >&2
  echo "  just publish-image --allow-dirty" >&2
  exit 3
fi
if [ "$DIRTY" -eq 1 ]; then
  echo "WARNING: uncommitted changes  -  tagging :sha-${SHA} (the SHA does NOT describe this image)" >&2
fi

IMAGE="${REPO}:sha-${SHA}"
echo "==> building ${IMAGE} (linux/arm64)"
docker build --platform linux/arm64 \
  --build-arg "GCINSIGHT_SOURCE_REVISION=${FULL_SHA}" \
  -t "$IMAGE" .

if [ "$PUSH" -eq 0 ]; then
  echo "==> --no-push: built only. Local parity check:"
  echo "    docker run --rm -e GCINSIGHT_READ_TOKEN -e AWS_REGION=${REGION} ${IMAGE} --tier t1 --dry-run"
  exit 0
fi

registry="${REPO%%/*}"
echo "==> logging in to ${registry}"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$registry"

echo "==> pushing immutable commit tag"
docker push -q "$IMAGE"

if [ "$PUBLISH_LATEST" -eq 1 ]; then
  echo "==> --publish-latest: moving compatibility tag (production remains immutably pinned)"
  docker tag "$IMAGE" "${REPO}:latest"
  docker push -q "${REPO}:latest"
fi

cat <<EOF

Pushed:
  ${IMAGE}
EOF

if [ "$PUBLISH_LATEST" -eq 1 ]; then
  cat <<EOF
  ${REPO}:latest

WARNING: :latest moved. Any separately configured mutable-tag deployment will pick it up at task start;
the production task definitions remain on their immutable Terraform pin.
EOF
else
  cat <<EOF

This did not update :latest or change what the live task definitions run.
Deploy immutably by setting var.image to ${IMAGE} and applying Terraform.
EOF
fi
