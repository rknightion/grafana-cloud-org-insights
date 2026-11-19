#!/usr/bin/env bash
set -euo pipefail

readonly tofu_version=1.13.9
readonly bin=.venv/bin

if [[ -x "$bin/tofu" && "$("$bin/tofu" version | sed -n '1p')" == "OpenTofu v$tofu_version" ]]; then
    exit 0
fi

case "$(uname -m)" in
    x86_64)
        arch=amd64
        checksum=bc44eb6b06446ba83bd4072114891987f590f66cca712737a7f1147c50c539ce
        ;;
    aarch64)
        arch=arm64
        checksum=04f7c93828b859d420269ed30f923ffebf09157b5d7fb95bf8d88a4d208b7fa3
        ;;
    *)
        echo "Unsupported OpenTofu architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

scratch="$(mktemp -d "$bin/.tofu.XXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
archive="tofu_${tofu_version}_linux_${arch}.zip"
curl -q --fail --silent --show-error --location --retry 3 \
    --proto '=https' --proto-redir '=https' --output "$scratch/$archive" \
    "https://github.com/opentofu/opentofu/releases/download/v${tofu_version}/${archive}"
printf '%s  %s\n' "$checksum" "$scratch/$archive" | sha256sum --check --strict -
unzip -p "$scratch/$archive" tofu > "$scratch/tofu"
chmod 0755 "$scratch/tofu"
mv -- "$scratch/tofu" "$bin/tofu"
