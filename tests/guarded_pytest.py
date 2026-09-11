"""Run pytest with repository-local wall-clock and resident-memory limits."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence


DEFAULT_MAX_RSS_MIB = 2048
DEFAULT_TIMEOUT_SECONDS = 540
POLL_SECONDS = 0.25
GROUP_GRACE_SECONDS = 5


def _positive_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"error: {name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise SystemExit(f"error: {name} must be positive, got {value}")
    return value


def _parse_process_table(output: str) -> dict[int, tuple[int, int]]:
    rows: dict[int, tuple[int, int]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            pid, ppid, rss_kib = (int(field) for field in fields)
        except ValueError:
            continue
        rows[pid] = (ppid, rss_kib)
    return rows


def _descendant_rss_kib(root_pid: int, rows: dict[int, tuple[int, int]]) -> int:
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss) in rows.items():
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sum(rows.get(pid, (0, 0))[1] for pid in descendants)


def _tree_rss_kib(root_pid: int) -> int:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss="],
        check=True,
        capture_output=True,
        text=True,
    )
    return _descendant_rss_kib(root_pid, _parse_process_table(result.stdout))


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.poll()
        return

    deadline = time.monotonic() + GROUP_GRACE_SECONDS
    while time.monotonic() < deadline:
        process.poll()
        if not _group_exists(process.pid):
            return
        time.sleep(POLL_SECONDS)
    if _group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=GROUP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    max_rss_mib = _positive_env("GCINSIGHT_TEST_MAX_RSS_MIB", DEFAULT_MAX_RSS_MIB)
    timeout_seconds = _positive_env(
        "GCINSIGHT_TEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", *args],
        start_new_session=True,
    )
    started = time.monotonic()
    peak_rss_kib = 0

    try:
        while process.poll() is None:
            rss_kib = _tree_rss_kib(process.pid)
            peak_rss_kib = max(peak_rss_kib, rss_kib)
            elapsed = time.monotonic() - started
            if rss_kib > max_rss_mib * 1024:
                print(
                    f"error: pytest process tree exceeded {max_rss_mib} MiB RSS "
                    f"({rss_kib / 1024:.1f} MiB observed); terminating",
                    file=sys.stderr,
                )
                _stop(process)
                return 137
            if elapsed > timeout_seconds:
                print(
                    f"error: pytest exceeded {timeout_seconds} seconds "
                    f"(peak RSS {peak_rss_kib / 1024:.1f} MiB); terminating",
                    file=sys.stderr,
                )
                _stop(process)
                return 124
            time.sleep(POLL_SECONDS)
    except (KeyboardInterrupt, subprocess.SubprocessError) as exc:
        print(f"error: pytest guard interrupted: {exc}", file=sys.stderr)
        _stop(process)
        return 2

    print(
        f"pytest guard: peak RSS {peak_rss_kib / 1024:.1f} MiB; "
        f"elapsed {time.monotonic() - started:.1f} seconds",
        file=sys.stderr,
    )
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
