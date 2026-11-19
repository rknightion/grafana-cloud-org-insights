#!/usr/bin/env bash
set -euo pipefail

install_dir=${1:?AWS CLI install directory required}
bin="$PWD/.venv/bin"
arch="$(uname -m)"
case "$arch" in
    x86_64) digest_arg=AWSCLI_SHA256_X86_64 ;;
    aarch64) digest_arg=AWSCLI_SHA256_AARCH64 ;;
    *) echo "Unsupported AWS CLI architecture: $arch" >&2; exit 1 ;;
esac

# Reuse the exact version and archive checksums from the runtime Dockerfile.
version="$(sed -nE 's/^ARG AWSCLI_VERSION=([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' Dockerfile)"
checksum="$(sed -nE "s/^ARG ${digest_arg}=([0-9a-f]{64})$/\\1/p" Dockerfile)"
if [[ ! $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ || ! $checksum =~ ^[0-9a-f]{64}$ ]]; then
    echo 'Could not read the AWS CLI pins from Dockerfile' >&2
    exit 1
fi

binary="$install_dir/v2/$version/bin/aws"
if [[ ! -x "$binary" ]]; then
    scratch="$(mktemp -d "$bin/.aws-cli.XXXXXX")"
    trap 'rm -rf -- "$scratch"' EXIT
    archive="$scratch/awscli.zip"
    curl -q --fail --silent --show-error --location --retry 3 \
        --proto '=https' --proto-redir '=https' --output "$archive" \
        "https://awscli.amazonaws.com/awscli-exe-linux-${arch}-${version}.zip"
    printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --strict -
    unzip -q "$archive" -d "$scratch"
    "$scratch/aws/install" --bin-dir "$bin" --install-dir "$install_dir" --update
fi
test -x "$binary"
ln -sfn -- "$binary" "$bin/aws"
