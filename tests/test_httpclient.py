from __future__ import annotations

import threading
import unittest
import urllib.request

from collector.httpclient import (
    DeadlineExceeded,
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
            with self.assertRaises(MethodNotAllowed):
                client.request(method, "https://example.test/x")

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


if __name__ == "__main__":
    unittest.main()
