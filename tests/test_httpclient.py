from __future__ import annotations

import io
import threading
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

from collector.httpclient import (
    DeadlineExceeded,
    MAX_GUARDED_BYTES,
    MAX_SYNTHETIC_BYTES,
    MAX_SYNTHETIC_READS,
    MethodNotAllowed,
    ReadOnlyClient,
    Response,
)


def responder(*statuses: int):
    """Transport returning the given statuses in order, repeating the last one."""
    seen: list[str] = []

    def transport(req: urllib.request.Request, timeout: float) -> Response:
        idx = min(len(seen), len(statuses) - 1)
        seen.append(req.full_url)
        return Response(status=statuses[idx], body=b"{}", url=req.full_url)

    transport.seen = seen  # type: ignore[attr-defined]
    return transport


class ReadOnlyTest(unittest.TestCase):
    def test_non_get_is_refused(self):
        client = ReadOnlyClient(transport=responder(200))
        for method in ("POST", "PUT", "PATCH", "DELETE", "post"):
            for guarded in (False, True):
                with self.assertRaises(MethodNotAllowed):
                    client.request(method, "https://example.test/x", guarded=guarded)

    def test_get_returns_body(self):
        client = ReadOnlyClient(transport=responder(200))
        resp = client.get("https://example.test/x")
        self.assertTrue(resp.ok)
        self.assertEqual(resp.json(), {})

    def test_params_are_appended_and_lists_repeat_the_key(self):
        transport = responder(200)
        client = ReadOnlyClient(transport=transport)
        client.get("https://example.test/s", params={"match[]": ["{a=1}", "{b=2}"], "limit": 5})
        url = transport.seen[0]  # type: ignore[attr-defined]
        self.assertIn("match%5B%5D=%7Ba%3D1%7D", url)
        self.assertIn("match%5B%5D=%7Bb%3D2%7D", url)
        self.assertIn("limit=5", url)

    def test_params_respect_an_existing_query_string(self):
        transport = responder(200)
        client = ReadOnlyClient(transport=transport)
        client.get("https://example.test/s?a=1", params={"b": 2})
        self.assertIn("?a=1&b=2", transport.seen[0])  # type: ignore[attr-defined]

    # -- retries -------------------------------------------------------------------

    def test_retries_then_succeeds(self):
        client = ReadOnlyClient(transport=responder(429, 503, 200), backoff_base=0, sleep=lambda _: None)
        self.assertTrue(client.get("https://example.test/x").ok)
        self.assertEqual(client.attempts.requests, 3)
        self.assertEqual(client.attempts.retries, 2)

    def test_retries_are_bounded_and_last_response_returned(self):
        client = ReadOnlyClient(
            transport=responder(429), max_attempts=3, backoff_base=0, sleep=lambda _: None
        )
        resp = client.get("https://example.test/x")
        self.assertEqual(resp.status, 429)
        self.assertEqual(client.attempts.requests, 3)

    def test_non_retryable_status_returns_immediately(self):
        client = ReadOnlyClient(transport=responder(403), backoff_base=0, sleep=lambda _: None)
        self.assertEqual(client.get("https://example.test/x").status, 403)
        self.assertEqual(client.attempts.requests, 1)

    def test_transport_exception_is_retried_then_raised(self):
        def boom(req, timeout):
            raise OSError("connection reset")

        client = ReadOnlyClient(transport=boom, max_attempts=2, backoff_base=0, sleep=lambda _: None)
        with self.assertRaises(RuntimeError):
            client.get("https://example.test/x")
        self.assertEqual(client.attempts.requests, 2)

    # -- deadline ------------------------------------------------------------------

    def test_deadline_stops_further_attempts(self):
        now = [0.0]
        client = ReadOnlyClient(
            transport=responder(429),
            deadline=10.0,
            backoff_base=0,
            sleep=lambda _: None,
            clock=lambda: now[0],
        )
        now[0] = 11.0
        with self.assertRaises(DeadlineExceeded):
            client.get("https://example.test/x")

    def test_backoff_longer_than_remaining_deadline_raises(self):
        client = ReadOnlyClient(
            transport=responder(429), deadline=0.01, backoff_base=100.0, sleep=lambda _: None
        )
        with self.assertRaises(DeadlineExceeded):
            client.get("https://example.test/x")

    def test_guarded_rate_wait_and_socket_budget_share_caller_deadline(self):
        now = [0.0]
        waits = []
        def transport(req, timeout):
            waits.append(timeout)
            return Response(200, b"{}", req.full_url)
        client = ReadOnlyClient(
            transport=transport, timeout=30, deadline=0.5,
            host_rate_limits={"example.test": 1}, clock=lambda: now[0],
            sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        assert client.get("https://example.test/x", guarded=True).ok
        with self.assertRaises(DeadlineExceeded):
            client.get("https://example.test/x", guarded=True)
        assert waits == [0.5]
        assert now[0] == 0.5

    # -- concurrency ---------------------------------------------------------------

    def test_per_host_cap_serialises_one_host_but_not_another(self):
        """The property a global cap would get wrong: hosts must not throttle each other."""
        inflight: dict[str, int] = {}
        peak: dict[str, int] = {}
        lock = threading.Lock()
        gate = threading.Event()

        def transport(req: urllib.request.Request, timeout: float) -> Response:
            host = req.full_url.split("/")[2]
            with lock:
                inflight[host] = inflight.get(host, 0) + 1
                peak[host] = max(peak.get(host, 0), inflight[host])
            gate.wait(0.5)
            with lock:
                inflight[host] -= 1
            return Response(status=200, body=b"{}", url=req.full_url)

        client = ReadOnlyClient(host_concurrency=1, transport=transport)
        threads = [
            threading.Thread(target=client.get, args=(f"https://{host}/x",))
            for host in ("a.test", "a.test", "b.test", "b.test")
        ]
        for t in threads:
            t.start()
        threading.Timer(0.05, gate.set).start()
        for t in threads:
            t.join(2)

        self.assertEqual(peak["a.test"], 1, "per-host cap of 1 was exceeded")
        self.assertEqual(peak["b.test"], 1, "per-host cap of 1 was exceeded")

    def test_host_concurrency_must_be_positive(self):
        with self.assertRaises(ValueError):
            ReadOnlyClient(host_concurrency=0)


SYNTHETIC_PATHS = (
    "/api/datasources",
    "/api/datasources/proxy/uid/synthetic-sm/sm/check/list",
    "/api/datasources/proxy/uid/synthetic-sm/sm/probe/list",
)


@pytest.mark.parametrize("path", (*SYNTHETIC_PATHS, "/api/search", "/api/playlists"))
def test_ordinary_guarded_get_retains_two_mib_even_on_synthetic_routes(path):
    assert MAX_GUARDED_BYTES == 2 * 1024 * 1024
    body = b"x" * (MAX_GUARDED_BYTES + 1)
    client = ReadOnlyClient(transport=lambda req, _: Response(200, body, req.full_url))
    with pytest.raises(ValueError, match="response too large"):
        client.get("https://example.test" + path, guarded=True)


@pytest.mark.parametrize("url", [
    "https://example.test/api/search",
    "https://example.test/api/datasources/",
    "https://example.test/api/datasources?limit=1",
    "https://example.test/api/datasources#fragment",
    "http://example.test/api/datasources",
    "https://user:pass@example.test/api/datasources",
    "https://example.test/api/datasources/proxy/uid/bad%2Fuid/sm/check/list",
    "https://example.test/api/datasources/proxy/uid/bad:uid/sm/check/list",
    "https://example.test/api/datasources/proxy/uid/" + "a" * 41 + "/sm/check/list",
    "https://example.test/api/datasources/proxy/uid/sm/sm/check/list/extra",
    "https://example.test/api/datasources/proxy/uid/sm/sm/check/other",
])
def test_larger_body_profile_refuses_other_urls_before_transport(url):
    transport = mock.Mock()
    client = ReadOnlyClient(transport=transport)
    with pytest.raises(ValueError, match="invalid Synthetic GET route"):
        client.get(url, guarded=True, synthetic=True)
    transport.assert_not_called()


def test_larger_body_profile_requires_guarded_get():
    client = ReadOnlyClient(transport=mock.Mock())
    with pytest.raises(ValueError, match="requires guarded"):
        client.get("https://example.test/api/datasources", synthetic=True)
    with pytest.raises(MethodNotAllowed):
        client.request("POST", "https://example.test/api/datasources", guarded=True, synthetic=True)
    client._transport.assert_not_called()


@pytest.mark.parametrize("synthetic", [False, True])
@pytest.mark.parametrize("length_header", [False, True])
@pytest.mark.parametrize("overflow", [False, True])
def test_native_guarded_body_cap_and_overflow_sentinel(synthetic, length_header, overflow):
    """Exercise the actual chunk reader, with and without an early length fence."""
    cap = MAX_SYNTHETIC_BYTES if synthetic else MAX_GUARDED_BYTES
    assert MAX_SYNTHETIC_BYTES == 32 * 1024 * 1024
    size = cap + int(overflow)
    fh = io.BytesIO(b"x" * size)
    fh.code = 200
    fh.headers = {"Content-Length": str(size)} if length_header else {}
    fh.read1 = mock.Mock(wraps=fh.read)
    with mock.patch("collector.httpclient.urllib.request.build_opener") as opener:
        opener.return_value.open.return_value = fh
        client = ReadOnlyClient()
        if overflow:
            with pytest.raises(ValueError, match="response too large"):
                client.get("https://example.test/api/datasources", guarded=True, synthetic=synthetic)
            if length_header:
                fh.read1.assert_not_called()
        else:
            resp = client.get("https://example.test/api/datasources", guarded=True, synthetic=synthetic)
            assert len(resp.body) == cap
    assert fh.closed


def test_injected_larger_profile_also_enforces_cap():
    client = ReadOnlyClient(transport=lambda req, _: Response(
        200, b"x" * (MAX_SYNTHETIC_BYTES + 1), req.full_url))
    with pytest.raises(ValueError, match="response too large"):
        client.get("https://example.test/api/datasources", guarded=True, synthetic=True)


def test_oversized_slots_are_global_across_hosts_and_clients():
    assert MAX_SYNTHETIC_READS == 2
    release, two_started = threading.Event(), threading.Event()
    lock = threading.Lock()
    active, peak, started = 0, 0, 0
    def transport(req, timeout):
        nonlocal active, peak, started
        with lock:
            active += 1
            started += 1
            peak = max(peak, active)
            if started == 2:
                two_started.set()
        try:
            assert release.wait(2)
            return Response(200, b"x" * (MAX_GUARDED_BYTES + 1), req.full_url)
        finally:
            with lock:
                active -= 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(ReadOnlyClient(transport=transport).get,
                               f"https://host{i}.test/api/datasources", guarded=True, synthetic=True)
                   for i in range(8)]
        try:
            assert two_started.wait(1)
            # Ordinary guarded traffic is not forced to wait on the larger-profile slots.
            ordinary = ReadOnlyClient(transport=responder(200))
            assert ordinary.get("https://other.test/api/search", guarded=True).ok
            with lock:
                assert started == 2
        finally:
            release.set()
        assert all(f.result(timeout=3).ok for f in futures)
    assert started == 8 and peak == 2 and active == 0


def test_timed_out_workers_keep_oversized_slots_until_transport_exits():
    release, two_started = threading.Event(), threading.Event()
    started = 0
    lock = threading.Lock()
    def stalled(req, timeout):
        nonlocal started
        with lock:
            started += 1
            if started == 2:
                two_started.set()
        assert release.wait(2)
        return Response(200, b"{}", req.full_url)
    clients = [ReadOnlyClient(transport=stalled, timeout=0.1) for _ in range(2)]
    def read(client):
        with pytest.raises(DeadlineExceeded):
            client.get("https://example.test/api/datasources", guarded=True, synthetic=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(read, client) for client in clients]
        try:
            assert two_started.wait(1)
            for future in futures:
                future.result(timeout=1)
            edge = mock.Mock(return_value=Response(200, b"{}", "https://third.test/api/datasources"))
            with pytest.raises(DeadlineExceeded):
                ReadOnlyClient(transport=edge, timeout=0.1).get(
                    "https://third.test/api/datasources", guarded=True, synthetic=True)
            edge.assert_not_called()
        finally:
            release.set()
    # A following read succeeds once the surviving transports have exited.
    assert ReadOnlyClient(transport=responder(200)).get(
        "https://next.test/api/datasources", guarded=True, synthetic=True).ok


if __name__ == "__main__":
    unittest.main()
