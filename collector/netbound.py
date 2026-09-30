"""Caller wall-time fence for blocking stdlib HTTP, including uninterruptible DNS.

This is NOT hard cancellation. A timed-out running operation keeps its worker and
admission slot until it finishes. At most MAX_WORKERS daemon operations can survive;
when exhausted, new calls time out in admission instead of growing threads/queues.
Only read transports belong here. A survivor may continue its read after caller exit.
"""
from __future__ import annotations

import math
import queue
import threading
import time
from concurrent.futures import Future
from typing import Callable, TypeVar

T = TypeVar("T")
MAX_WORKERS = 32


class _Workers:
    def __init__(self):
        self.slots = threading.BoundedSemaphore(MAX_WORKERS)
        self.jobs = queue.Queue(maxsize=MAX_WORKERS)
        self.lock = threading.Lock()
        self.threads: list[threading.Thread] = []

    def _work(self):
        while True:
            operation, future = self.jobs.get()
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(operation())
                    except BaseException as exc:
                        # Do not lose a worker/slot when an injected edge raises.
                        future.set_exception(exc)
            finally:
                self.slots.release()
                self.jobs.task_done()
                # Do not retain credentials, response bytes or tracebacks while idle.
                del operation, future

    def run(self, operation: Callable[[], T], timeout: float) -> T:
        if not math.isfinite(timeout) or timeout <= 0:
            raise TimeoutError("HTTP wall-time deadline")
        end = time.monotonic() + timeout
        if not self.slots.acquire(timeout=timeout):
            raise TimeoutError("HTTP worker admission deadline")
        submitted = False
        try:
            if not self.lock.acquire(timeout=max(0.0, end - time.monotonic())):
                raise TimeoutError("HTTP worker admission deadline")
            try:
                # Fixed pool, lazy startup; never replace a stuck worker.
                while len(self.threads) < MAX_WORKERS:
                    if time.monotonic() >= end:
                        raise TimeoutError("HTTP wall-time deadline")
                    thread = threading.Thread(target=self._work, name="collector-http", daemon=True)
                    thread.start()
                    self.threads.append(thread)
            finally:
                self.lock.release()
            if time.monotonic() >= end:
                raise TimeoutError("HTTP wall-time deadline")
            future: Future[T] = Future()
            self.jobs.put_nowait((operation, future))
            submitted = True
        finally:
            if not submitted:
                self.slots.release()
        try:
            result = future.result(timeout=max(0.0, end - time.monotonic()))
            if time.monotonic() >= end:
                raise TimeoutError("HTTP wall-time deadline")
            return result
        finally:
            # Queued operations must not start after abandonment. Running operations
            # cannot be cancelled and retain their slot until the worker returns.
            future.cancel()


_WORKERS = _Workers()


def bounded_call(operation: Callable[[], T], timeout: float) -> T:
    """Wait at most timeout seconds, including admission, for a read operation."""
    return _WORKERS.run(operation, timeout)
