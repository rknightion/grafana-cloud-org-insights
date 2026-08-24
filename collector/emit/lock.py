"""Single-run lock per tier (PLAN 1.7).

EventBridge and ECS `RunTask` do not deduplicate. A schedule that fires while the previous run of the
same tier is still going gives two scans writing `scans/<tier>/latest.json`, and the one that finishes
*second* wins regardless of which started later - so the estate can silently go backwards in time.
They also share the `grafana.com` rate-limit quota, which is per credential, so a double run does not
merely duplicate work, it halves the effective pacing and pushes both toward the 429 wall that cost
77 stacks of coverage once already.

The primitive is S3 itself, not DynamoDB: `put-object --if-none-match '*'` is an atomic create that
fails with 412 when the key exists, and `delete-object --if-match <etag>` is a compare-and-delete.
Both verified present in aws-cli 2.36.24. That keeps the lock in the bucket the collector already
owns, with no second service to provision, IAM or explain in the runbook.

**A lock is only as good as its expiry.** A Fargate task killed by OOM, a spot reclaim or `StopTask`
never runs its release, so a naive lock wedges that tier until a human deletes an object they have no
reason to know exists. Every lock therefore carries `expires_at`, and a contender past that point
breaks it and says so. The TTL is derived from the tier's own deadline plus a grace margin, so the
ordering is always: the scan is killed by its deadline *first*, and only then can its lock be
declared stale. A live run is never overtaken.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

LOCK_PREFIX = "locks/"

# Added to the tier deadline to get the lock TTL. It must be strictly positive so a scan that runs
# right up to its deadline still holds a valid lock when it is killed, rather than having already been
# overtaken by the next fire. Five minutes also covers ECS task-stop draining and clock skew between
# two Fargate tasks.
LOCK_GRACE_SECONDS = 300.0


class PreconditionFailed(RuntimeError):
    """S3 answered 412 - the key already existed on a conditional create."""


class LockHeld(RuntimeError):
    """Another run of this tier holds the lock and it has not expired."""


class LockBackendFailed(RuntimeError):
    """The lock could not be read or written at all. Distinct from `LockHeld`: this is an S3 or IAM
    problem, and it must not be mistaken for "someone else is running"."""


def ttl_for(deadline_seconds: float) -> float:
    return float(deadline_seconds) + LOCK_GRACE_SECONDS


def default_holder() -> str:
    """Identify the runner well enough to debug a stuck lock from the object alone.

    On ECS the task ARN is the only durable handle - the container hostname is the task id, which is
    what `ECS_CONTAINER_METADATA_URI_V2` would give more slowly. Falls back to host:pid locally.
    """
    task = os.environ.get("ECS_TASK_ARN") or os.environ.get("ECS_CONTAINER_METADATA_URI_V2")
    if task:
        return task.rstrip("/").rsplit("/", 1)[-1]
    return f"{socket.gethostname()}:{os.getpid()}"


class S3Backend:
    """The three aws-CLI calls the lock needs. Separated so the lock's decision logic is testable
    without AWS - the interesting behaviour is staleness and release-safety, not subprocess plumbing.
    """

    def __init__(self, bucket: str, region: str) -> None:
        self.bucket = bucket
        self.region = region

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["aws", "s3api", *args, "--bucket", self.bucket, "--region", self.region],
            capture_output=True,
            text=True,
        )

    def put_if_absent(self, key: str, body: str) -> str:
        # `--body` is a blob parameter and takes a FILE PATH ONLY - `--body -` fails with
        # `ParamValidation: Blob values must be a path to a file`, it does not read stdin. Verified
        # live against the real bucket, and invisible to any in-memory fake.
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "lock.json"
            src.write_text(body)
            proc = subprocess.run(
                ["aws", "s3api", "put-object", "--bucket", self.bucket, "--region", self.region,
                 "--key", key, "--if-none-match", "*", "--content-type", "application/json",
                 "--body", str(src)],
                capture_output=True,
                text=True,
            )
        if proc.returncode != 0:
            err = proc.stderr
            # 412. The CLI surfaces it as PreconditionFailed; match the HTTP prose too in case a
            # future CLI reshapes the error name.
            if "PreconditionFailed" in err or "pre-conditions you specified did not hold" in err:
                raise PreconditionFailed(key)
            raise LockBackendFailed(f"put {key}: {err.strip()}")
        try:
            return str(json.loads(proc.stdout)["ETag"])
        except (ValueError, KeyError) as exc:  # pragma: no cover - defensive
            raise LockBackendFailed(f"put {key}: no ETag in response ({exc})") from exc

    def get(self, key: str) -> tuple[str, str] | None:
        """Return `(body, etag)`, or None if the key is absent.

        `get-object` writes the body to its positional path argument and its metadata JSON to stdout,
        so the two are read from different places rather than teased apart from one stream.
        """
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "lock.json"
            proc = subprocess.run(
                ["aws", "s3api", "get-object", "--bucket", self.bucket, "--region", self.region,
                 "--key", key, str(dest)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                if "NoSuchKey" in proc.stderr or "Not Found" in proc.stderr or "404" in proc.stderr:
                    return None
                raise LockBackendFailed(f"get {key}: {proc.stderr.strip()}")
            body = dest.read_text() if dest.exists() else ""
        try:
            etag = str(json.loads(proc.stdout)["ETag"])
        except (ValueError, KeyError) as exc:
            raise LockBackendFailed(f"get {key}: no ETag in response ({exc})") from exc
        return body, etag

    def delete_if_match(self, key: str, etag: str) -> bool:
        proc = self._run(["delete-object", "--key", key, "--if-match", etag])
        if proc.returncode == 0:
            return True
        if "PreconditionFailed" in proc.stderr or "pre-conditions" in proc.stderr:
            return False
        raise LockBackendFailed(f"delete {key}: {proc.stderr.strip()}")


class ScanLock:
    """Mutual exclusion for one tier, with expiry.

    Use as a context manager so an exception in the scan cannot leave the tier locked:

        with ScanLock(tier="t1", ttl_seconds=ttl_for(cfg.deadline_seconds), backend=...):
            run_scan()
    """

    def __init__(
        self,
        *,
        tier: str,
        ttl_seconds: float,
        backend: Any,
        holder: str | None = None,
        now: Callable[[], float] = time.time,
        dry_run: bool = False,
    ) -> None:
        self.tier = tier
        self.ttl_seconds = float(ttl_seconds)
        self.backend = backend
        self.holder = holder or default_holder()
        self._now = now
        self.dry_run = dry_run
        self.key = f"{LOCK_PREFIX}{tier}.lock"
        self.held = False
        self.broke_stale_lock = False
        self._etag: str | None = None

    def _body(self) -> str:
        now = self._now()
        return json.dumps(
            {
                "tier": self.tier,
                "holder": self.holder,
                "acquired_at": now,
                "expires_at": now + self.ttl_seconds,
                "ttl_seconds": self.ttl_seconds,
            }
        )

    def acquire(self) -> None:
        # A dry run writes nothing, so it can neither collide with a real run nor be blocked by one.
        # Taking a lock here would let `--dry-run` on a laptop stall the scheduled scan.
        if self.dry_run:
            return
        try:
            self._etag = self.backend.put_if_absent(self.key, self._body())
            self.held = True
            return
        except PreconditionFailed:
            pass

        incumbent = self.backend.get(self.key)
        if incumbent is None:
            # Released in the window between our 412 and this read. That is a free lock.
            self._etag = self.backend.put_if_absent(self.key, self._body())
            self.held = True
            return

        body, etag = incumbent
        expires_at, holder = self._parse(body)
        if expires_at is not None and self._now() <= expires_at:
            raise LockHeld(
                f"{self.tier}: held by {holder} until "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(expires_at))} "
                f"({expires_at - self._now():.0f}s remaining) - refusing to start a second scan"
            )

        # Stale, or unreadable. Either way the alternative is wedging this tier forever.
        if not self.backend.delete_if_match(self.key, etag):
            # Someone else broke it first and now holds it; they win.
            raise LockHeld(f"{self.tier}: stale lock was taken over by another run")
        self._etag = self.backend.put_if_absent(self.key, self._body())
        self.held = True
        self.broke_stale_lock = True

    @staticmethod
    def _parse(body: str) -> tuple[float | None, str]:
        try:
            parsed = json.loads(body)
            return float(parsed["expires_at"]), str(parsed.get("holder", "unknown"))
        except (ValueError, KeyError, TypeError):
            # Truncated, hand-edited or written by an older version. Treat as stale rather than
            # letting a malformed object deadlock the tier.
            return None, "unparseable"

    def release(self) -> None:
        if not self.held or self._etag is None:
            return
        # ETag-guarded: if we overran and were declared stale, this lock is now someone else's and
        # deleting it would green-light a third run while the second is still scanning.
        self.backend.delete_if_match(self.key, self._etag)
        self.held = False

    def __enter__(self) -> "ScanLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
