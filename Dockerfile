# Collector image (PLAN 7.1).
#
# Two deliberate properties, both load-bearing:
#
#   1. NO PYTHON DEPENDENCIES. There is no requirements.txt and no pip install step, because the
#      collector has no third-party imports at all - `emit/mimir.py` hand-rolls protobuf and snappy
#      rather than pulling them in. So there is nothing to pin, nothing to audit and no supply chain.
#      If a future change adds an import, this image is where it becomes visible: the build keeps
#      working and the task fails at runtime, so `--dry-run` parity (below) is the gate that catches it.
#
#   2. The AWS CLI *is* a dependency, and a real one. `emit/s3.py`, `emit/lock.py`, `emit/carry.py`
#      and `emit/diff.py` shell out to `aws` rather than importing boto3 - that is what keeps
#      property 1 true. An image without it starts fine and then fails on the first S3 write.
#
# Build for the platform the task runs on. Fargate ARM64 is ~20% cheaper than x86 for identical work
# and the collector is pure Python, so there is no reason to pay for x86:
#
#   docker build --platform linux/arm64 -t gcinsight:dev .
#
# Local-parity check, which is the actual acceptance test for this image:
#
#   docker run --rm -e GCINSIGHT_READ_TOKEN -e AWS_* gcinsight:dev --tier t1 --dry-run

# Wolfi is glibc-based, unlike Alpine: the existing AWS CLI v2 distribution needs no libc shim.
# Keep download/install tools in a separate stage. The final Chainguard Python image has neither
# a shell nor a package manager, and both multi-platform bases are pinned by index digest.
FROM cgr.dev/chainguard/wolfi-base@sha256:88a20e2d017bd20cdc0cb3910de603e7bea9512a6c351a8dd3c9df212ab03d73 AS awscli

# The AWS CLI v2 zip is arch-specific and there is no `latest` alias that resolves per-arch, so the
# URL is selected from the build platform rather than hardcoded - a hardcoded x86 zip installs
# cleanly on ARM and then dies with `exec format error` on the first `aws` call.
ARG TARGETARCH
ARG AWSCLI_VERSION=2.36.28
ARG AWSCLI_SHA256_AARCH64=5e5013af7d1996d78a842ee8f8e5010bfd2ca663e5f5f9487d1f1cb2c290f327
ARG AWSCLI_SHA256_X86_64=1e050540227bc4dca8c2e9d503e358758dc4edd647f68e7f1a3899be6fc74bf6
RUN set -eux; \
    apk add --no-cache curl unzip; \
    case "${TARGETARCH}" in \
      arm64) awscli_arch=aarch64; awscli_sha256="${AWSCLI_SHA256_AARCH64}" ;; \
      amd64) awscli_arch=x86_64; awscli_sha256="${AWSCLI_SHA256_X86_64}" ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${awscli_arch}-${AWSCLI_VERSION}.zip" -o /tmp/awscli.zip; \
    echo "${awscli_sha256}  /tmp/awscli.zip" | sha256sum -c -; \
    unzip -q /tmp/awscli.zip -d /tmp; \
    /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli; \
    rm -rf /tmp/awscli.zip /tmp/aws

FROM cgr.dev/chainguard/python@sha256:b21d678dcbec131cb15da75685598924a498a865f07331ff55135b34632822e6
USER root

ARG GCINSIGHT_SOURCE_URL=https://github.com/rknightion/grafana-cloud-org-insights
ARG GCINSIGHT_SOURCE_REVISION=unknown
ARG GCINSIGHT_OVERLAY_DIGEST=none
ARG GCINSIGHT_CONSUMER_REVISION=none
LABEL org.opencontainers.image.source="${GCINSIGHT_SOURCE_URL}" \
      org.opencontainers.image.revision="${GCINSIGHT_SOURCE_REVISION}" \
      io.grafana.gcinsight.overlay.digest="${GCINSIGHT_OVERLAY_DIGEST}" \
      io.grafana.gcinsight.consumer.revision="${GCINSIGHT_CONSUMER_REVISION}"

COPY --from=awscli /usr/local/aws-cli/ /usr/local/aws-cli/
COPY --from=awscli /usr/local/bin/ /usr/local/bin/

# The stdlib-only runtime needs neither ensurepip nor its bootstrap wheel. Derive the stdlib
# path from Python rather than assuming a minor version. No third-party collector packages.
RUN ["python3", "-c", "import importlib.util, pathlib, shutil, sysconfig; shutil.rmtree(pathlib.Path(sysconfig.get_path('stdlib')) / 'ensurepip'); shutil.rmtree('/usr/share/python-wheels'); assert importlib.util.find_spec('pip') is None; assert importlib.util.find_spec('ensurepip') is None"]

WORKDIR /app

# Copy only what runs. Tests, evidence, drafts and the markdown are deliberately absent: the image is
# the collector, not the repo, and `testdata/` contains scan output that has no business in a registry.
COPY collector/ ./collector/
COPY bin/ ./bin/
COPY scan.py ./scan.py

# Unbuffered, so a task killed mid-scan still has its progress in CloudWatch Logs rather than losing
# the last buffer - which is exactly the run you most need to read.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Non-root. The collector reads the network and writes to S3; it needs nothing on the local
# filesystem beyond the temp dirs the emitters create, so there is no reason to run as uid 0.
# Use Python for image preparation because this runtime deliberately has no shell/useradd.
RUN ["python3", "-c", "import os, pathlib; p = pathlib.Path('/etc/passwd'); p.write_text(p.read_text() + 'collector:x:10001:10001:collector:/home/collector:/sbin/nologin\\n'); p = pathlib.Path('/etc/group'); p.write_text(p.read_text() + 'collector:x:10001:\\n'); pathlib.Path('/home/collector').mkdir(); os.chown('/home/collector', 10001, 10001); os.chown('/app', 10001, 10001)"]
ENV HOME=/home/collector
USER collector:collector

# Verify the official AWS distribution against the actual final-image libc, as the runtime user.
RUN ["aws", "--version"]

# The tier is an ARGUMENT, not an env var, because EventBridge Scheduler's ECS target has no
# container-override support - each tier gets its own task definition with its own `command`, and
# that command is appended to this entrypoint. See terraform/ecs.tf.
ENTRYPOINT ["python3", "/app/scan.py"]
CMD ["--help"]
