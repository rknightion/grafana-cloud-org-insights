"""Read the per-stack credential store. READ ONLY - the collector cannot write or delete a token.

The store is SSM Parameter Store `SecureString`, one parameter per stack at
`/gcinsight/stack-token/<slug>` (PLAN 17D). `bin/provision.py` owns every write; this module owns
the only read path the collector has, and deliberately exposes no `put` or `delete` so a collector bug
cannot reach them. The IAM split is the same shape: the collector task role holds
`GetParameter{,s,sByPath}` + `kms:Decrypt` and nothing else.

**One paginated sweep, never a call per stack.** `get-parameters-by-path` returns 10 per page, so the
estate costs ~27 `aws` invocations. The rejected alternative cost 269 fresh Python processes at roughly a
second each - 4.5 minutes of a Fargate task's life spent starting interpreters, measured 2026-08-20.

A parameter whose JSON will not parse is treated as **absent**, not as a crash: that is exactly the state
a half-finished provisioning write leaves behind, and the repair for it is for the provisioner to re-mint.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from collector import identity

SSM_PREFIX = identity.env("GCINSIGHT_STACK_TOKEN_PREFIX", "/gcinsight/stack-token")
SSM_REGION = os.environ.get("GCINSIGHT_SSM_REGION", "eu-west-1").strip() or "eu-west-1"


class StoreUnavailable(RuntimeError):
    """The credential store could not be read at all - not the same as 'no stacks have a token'.

    Distinguished on purpose. An empty sweep and a failed sweep look identical downstream, and treating
    an IAM or network failure as "the whole estate is missing its credential" would fire the coverage
    alert on all 273 stacks and publish an estate of zeros.
    """


def ssm_path(slug: str) -> str:
    return f"{SSM_PREFIX}/{slug}"


def load_all(*, runner=subprocess.run) -> dict[str, dict[str, Any]]:
    """Every stored credential record, keyed by slug, from one paginated sweep."""
    out: dict[str, dict[str, Any]] = {}
    token: str | None = None
    pages = 0
    while True:
        cmd = ["aws", "ssm", "get-parameters-by-path", "--path", SSM_PREFIX, "--recursive",
               "--with-decryption", "--region", SSM_REGION, "--output", "json"]
        if token:
            cmd += ["--next-token", token]
        proc = runner(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise StoreUnavailable(
                f"ssm get-parameters-by-path {SSM_PREFIX} failed after {pages} page(s): "
                f"{(proc.stderr or '').strip()[:200]}"
            )
        try:
            body = json.loads(proc.stdout or "{}")
        except ValueError as exc:
            raise StoreUnavailable(f"ssm returned unparseable JSON on page {pages}: {exc}") from exc
        for param in body.get("Parameters", []):
            slug = str(param.get("Name", "")).rsplit("/", 1)[-1]
            try:
                record = json.loads(param.get("Value") or "")
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("token"):
                out[slug] = record
        pages += 1
        token = body.get("NextToken")
        if not token:
            return out
