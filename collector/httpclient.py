"""Read-only HTTP client for the estate scan.

Two properties the rest of the collector depends on (SPEC §5.2, §8):

- **GET only.** Any other method raises. The credential the collector carries is not itself
  read-only, so this is the construction-level guard that a collector bug cannot write to a
  customer's estate.
- **Per-host concurrency, not global.** gcom is one shared control plane for all 271 stacks; the
  data plane is 271 separate tenants. A single global cap is simultaneously too aggressive for gcom
  and too conservative for the data plane.
"""

from __future__ import annotations

import base64
import http.client
import io
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Mapping

RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class DeadlineExceeded(RuntimeError):
    """The tier's wall-clock budget ran out. Raised instead of starting another attempt."""


class MethodNotAllowed(ValueError):
    """Something tried to use a method other than GET."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)

    def retry_after(self) -> float | None:
        """gcom answers 429 with `Retry-After: 8-10`. Obeying it beats guessing a backoff."""
        raw = next((v for k, v in self.headers.items() if k.lower() == "retry-after"), None)
        if raw is None:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            return None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.body)


@dataclass
class Attempts:
    """Per-run counters, so a scan can report how much of its budget went on retries."""

    requests: int = 0
    retries: int = 0
    by_status: dict[int, int] = field(default_factory=dict)

    def record(self, status: int) -> None:
        self.by_status[status] = self.by_status.get(status, 0) + 1


class RateLimiter:
    """Token bucket, so we stay under a host's limit instead of discovering it with 429s.

    Measured 2026-08-17: an unthrottled 271-stack T2 sweep (813 calls) drew 77 HTTP 429s from
    grafana.com and covered only 71.6% of the estate. gcom is one shared control plane; proactive
    pacing is cheaper than 245 retries.
    """

    def __init__(self, rate_per_sec: float, burst: float | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        self._rate = rate_per_sec
        self._capacity = burst if burst is not None else max(1.0, rate_per_sec)
        self._tokens = self._capacity
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self, *, deadline: float | None = None) -> None:
        while True:
            with self._lock:
                now = self._clock()
                if deadline is not None and now >= deadline:
                    raise DeadlineExceeded("rate limiter deadline")
                self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
                if deadline is not None:
                    wait = min(wait, deadline - now)
            self._sleep(wait)

    def penalise(self, seconds: float) -> None:
        """Drain the bucket after a 429 so concurrent callers also back off, not just this one."""
        with self._lock:
            self._tokens = 0.0
            self._last = self._clock() + seconds


def _basic_auth(user: str, password: str) -> str:
    raw = f"{user}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode()


class ReadOnlyClient:
    """GET-only HTTP client with per-host concurrency caps, bounded retries and a deadline.

    `transport` exists so tests do not need a network. It takes a `urllib.request.Request` and
    returns a `Response`.
    """

    def __init__(
        self,
        *,
        host_concurrency: int = 8,
        host_concurrency_overrides: Mapping[str, int] | None = None,
        host_rate_limits: Mapping[str, float] | None = None,
        max_attempts: int = 6,
        backoff_base: float = 0.5,
        backoff_cap: float = 30.0,
        timeout: float = 30.0,
        deadline: float | None = None,
        transport: Callable[[urllib.request.Request, float], Response] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if host_concurrency < 1:
            raise ValueError("host_concurrency must be >= 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._host_concurrency = host_concurrency
        # gcom is one shared control plane and needs a lower cap than a per-tenant data-plane host.
        self._host_overrides = {h.lower(): n for h, n in (host_concurrency_overrides or {}).items()}
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._rate_config = {h.lower(): r for h, r in (host_rate_limits or {}).items()}
        self._limiters: dict[str, RateLimiter] = {}
        self._timeout = timeout
        self._transport = transport or _urllib_transport
        self._sleep = sleep
        self._clock = clock
        self._started = clock()
        self._deadline = deadline
        self._sem_lock = threading.Lock()
        self._semaphores: dict[str, threading.Semaphore] = {}
        self.attempts = Attempts()

    # -- public API ----------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        bearer: str | None = None,
        basic: tuple[str, str] | None = None,
        guarded: bool = False,
        status_only: bool = False,
    ) -> Response:
        return self.request("GET", url, params=params, headers=headers, bearer=bearer, basic=basic,
                            guarded=guarded, status_only=status_only)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        bearer: str | None = None,
        basic: tuple[str, str] | None = None,
        guarded: bool = False,
        status_only: bool = False,
    ) -> Response:
        if status_only and not guarded:
            raise ValueError("status_only requires guarded transport")
        if method.upper() != "GET":
            raise MethodNotAllowed(
                f"{method} refused: this collector is read-only by construction (SPEC §8)"
            )
        full = _with_params(url, params)
        req = urllib.request.Request(full, method="GET")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        if bearer:
            req.add_header("Authorization", f"Bearer {bearer}")
        if basic:
            req.add_header("Authorization", _basic_auth(*basic))
        if guarded:
            return self._send_guarded(req, _host_of(full), status_only=status_only)
        return self._send_with_retries(req, _host_of(full))

    def remaining(self) -> float:
        if self._deadline is None:
            return float("inf")
        return max(0.0, self._deadline - (self._clock() - self._started))

    # -- internals -----------------------------------------------------------------

    def _limiter(self, host: str) -> RateLimiter | None:
        rate = self._rate_config.get(host)
        if rate is None:
            return None
        with self._sem_lock:
            lim = self._limiters.get(host)
            if lim is None:
                lim = RateLimiter(rate, clock=self._clock, sleep=self._sleep)
                self._limiters[host] = lim
            return lim

    def _semaphore(self, host: str) -> threading.Semaphore:
        with self._sem_lock:
            sem = self._semaphores.get(host)
            if sem is None:
                limit = self._host_overrides.get(host, self._host_concurrency)
                sem = threading.Semaphore(limit)
                self._semaphores[host] = sem
            return sem

    def _send_guarded(self, req: urllib.request.Request, host: str, *, status_only: bool) -> Response:
        """One fixed-route attempt, with one total budget including the host queue.

        No retry on schema/size/time failures or on health status: callers report a gap.
        The normal client's retry policy and transport defaults remain unchanged.
        """
        end = self._clock() + min(self._timeout, self.remaining())
        remaining = lambda: end - self._clock()
        limiter = self._limiter(host)
        if limiter is not None:
            limiter.acquire(deadline=end)
        sem = self._semaphore(host)
        wait = remaining()
        if wait <= 0 or not sem.acquire(timeout=wait):
            raise DeadlineExceeded("guarded GET deadline")
        try:
            wait = remaining()
            if wait <= 0:
                raise DeadlineExceeded("guarded GET deadline")
            self.attempts.requests += 1
            if self._transport is _urllib_transport:
                resp = _guarded_transport(req, remaining, status_only=status_only)
            else:
                # Injected network edge is trusted; enforce the output fences as well.
                resp = self._transport(req, wait)
                if status_only or not resp.ok:
                    resp = Response(resp.status, b"", resp.url, resp.headers)
                elif len(resp.body) > MAX_GUARDED_BYTES:
                    raise ValueError("guarded GET response too large")
            if remaining() <= 0:
                raise DeadlineExceeded("guarded GET deadline")
            self.attempts.record(resp.status)
            return resp
        finally:
            sem.release()

    def _send_with_retries(self, req: urllib.request.Request, host: str) -> Response:
        last: Response | Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            if self.remaining() <= 0:
                raise DeadlineExceeded(f"tier deadline reached before {req.full_url}")
            limiter = self._limiter(host)
            if limiter is not None:
                limiter.acquire()
            sem = self._semaphore(host)
            sem.acquire()
            try:
                self.attempts.requests += 1
                resp = self._transport(req, self._timeout)
            except Exception as exc:  # transport-level: connection reset, DNS, timeout
                last = exc
            else:
                self.attempts.record(resp.status)
                if resp.ok or resp.status not in RETRY_STATUSES:
                    return resp
                last = resp
            finally:
                sem.release()

            if attempt == self._max_attempts:
                break
            self.attempts.retries += 1
            # A server that tells us how long to wait is more reliable than our own backoff curve.
            advised = last.retry_after() if isinstance(last, Response) else None
            if advised is not None:
                delay = min(self._backoff_cap, advised)
                if limiter is not None:
                    limiter.penalise(delay)
            else:
                delay = min(self._backoff_cap, self._backoff_base * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay / 2) if delay else 0
            if delay >= self.remaining():
                raise DeadlineExceeded(f"backoff would exceed tier deadline for {req.full_url}")
            self._sleep(delay)

        if isinstance(last, Response):
            return last
        raise RuntimeError(f"GET {req.full_url} failed after {self._max_attempts} attempts: {last}")


def _with_params(url: str, params: Mapping[str, object] | None) -> str:
    if not params:
        return url
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(v)) for v in value)
        else:
            pairs.append((key, str(value)))
    sep = "&" if urllib.parse.urlparse(url).query else "?"
    return f"{url}{sep}{urllib.parse.urlencode(pairs)}"


def _host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


MAX_GUARDED_BYTES = 2 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _DeadlineReader(io.RawIOBase):
    """Clamp every socket receive, including header reads, to the total budget."""

    def __init__(self, raw, sock, remaining):
        self.raw, self.sock, self.remaining = raw, sock, remaining

    def readable(self):
        return True

    def readinto(self, buffer):
        wait = self.remaining()
        if wait <= 0:
            raise DeadlineExceeded("guarded GET deadline")
        self.sock.settimeout(wait)
        result = self.raw.readinto(buffer)
        if self.remaining() <= 0:
            raise DeadlineExceeded("guarded GET deadline")
        return result

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class _DeadlineSocket:
    def __init__(self, sock, remaining):
        self.sock, self.remaining = sock, remaining

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def makefile(self, mode, buffering=None):
        # HTTPResponse uses rb; retain socket.makefile's ownership/reference counting.
        if mode != "rb":
            raise ValueError("unexpected guarded socket mode")
        raw = self.sock.makefile("rb", buffering=0)
        return io.BufferedReader(_DeadlineReader(raw, self.sock, self.remaining))


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, remaining):
        super().__init__()
        self.remaining = remaining

    def https_open(self, req):
        remaining = self.remaining

        class Connection(http.client.HTTPSConnection):
            def connect(self):
                super().connect()
                if remaining() <= 0:
                    self.close()
                    raise DeadlineExceeded("guarded GET deadline")
                self.sock.settimeout(remaining())
                self.sock = _DeadlineSocket(self.sock, remaining)

        return self.do_open(Connection, req, context=self._context)


def _guarded_transport(req, remaining, *, status_only):
    """No redirect or error body. Read at most 2 MiB plus one overflow sentinel.

    DNS resolution and the initial TCP/TLS connect are platform blocking operations;
    their socket timeout is clamped at entry, but DNS is not interruptible by urllib.
    Header/body socket receives use the remaining total budget, not a renewed timeout.
    JSON parsing is subsequent bounded local work, not part of the network deadline.
    """
    if urllib.parse.urlsplit(req.full_url).scheme != "https":
        raise ValueError("guarded GET requires HTTPS")
    opener = urllib.request.build_opener(_NoRedirect(), _GuardedHTTPSHandler(remaining))
    try:
        response = opener.open(req, timeout=remaining())
    except urllib.error.HTTPError as exc:
        response = exc
    with response as fh:
        status = fh.code
        if status_only or not 200 <= status < 300:
            return Response(status, b"", req.full_url, dict(fh.headers))
        # read1 deliberately does not wait to fill its buffer, but unlike read() it
        # does not enforce Content-Length completeness itself. Preserve that fence.
        raw_length = fh.headers.get("Content-Length")
        expected = None
        if raw_length is not None:
            if not raw_length.isascii() or not raw_length.isdigit():
                raise ValueError("invalid guarded GET content length")
            expected = int(raw_length)
            if expected > MAX_GUARDED_BYTES:
                raise ValueError("guarded GET response too large")
        body = bytearray()
        while True:
            if remaining() <= 0:
                raise DeadlineExceeded("guarded GET deadline")
            chunk = fh.read1(min(64 * 1024, MAX_GUARDED_BYTES + 1 - len(body)))
            if remaining() <= 0:
                raise DeadlineExceeded("guarded GET deadline")
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_GUARDED_BYTES:
                raise ValueError("guarded GET response too large")
        if expected is not None and len(body) != expected:
            raise ValueError("incomplete guarded GET response")
        return Response(status, bytes(body), req.full_url, dict(fh.headers))


def _urllib_transport(req: urllib.request.Request, timeout: float) -> Response:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return Response(status=fh.status, body=fh.read(), url=req.full_url, headers=dict(fh.headers))
    except urllib.error.HTTPError as exc:
        # An HTTP error status is data, not an exception - retry logic decides what to do with it.
        return Response(status=exc.code, body=exc.read(), url=req.full_url, headers=dict(exc.headers))
