"""Rate limiting and Retry-After. Both exist because of a measured failure, not a hypothetical one:
an unpaced 271-stack sweep drew 77 HTTP 429s from grafana.com and covered 71.6% of the estate.
"""

from __future__ import annotations

import unittest
import urllib.request

from collector.httpclient import RateLimiter, ReadOnlyClient, Response


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class RateLimiterTest(unittest.TestCase):
    def test_burst_is_allowed_then_paced(self):
        clock = FakeClock()
        lim = RateLimiter(rate_per_sec=2.0, burst=2, clock=clock, sleep=clock.sleep)
        lim.acquire()
        lim.acquire()
        self.assertEqual(clock.slept, [], "the burst must not sleep")
        lim.acquire()
        self.assertTrue(clock.slept, "past the burst it must pace")
        self.assertAlmostEqual(sum(clock.slept), 0.5, places=3)

    def test_tokens_refill_over_time(self):
        clock = FakeClock()
        lim = RateLimiter(rate_per_sec=10.0, burst=1, clock=clock, sleep=clock.sleep)
        lim.acquire()
        clock.now += 1.0
        lim.acquire()
        self.assertEqual(clock.slept, [])

    def test_penalise_drains_the_bucket_for_everyone(self):
        """A 429 must back off concurrent callers too, not just the one that saw it."""
        clock = FakeClock()
        lim = RateLimiter(rate_per_sec=100.0, burst=10, clock=clock, sleep=clock.sleep)
        lim.penalise(9.0)
        lim.acquire()
        self.assertTrue(clock.slept)
        self.assertGreaterEqual(sum(clock.slept), 9.0)

    def test_rate_must_be_positive(self):
        with self.assertRaises(ValueError):
            RateLimiter(rate_per_sec=0)


class RetryAfterTest(unittest.TestCase):
    def test_retry_after_is_parsed(self):
        self.assertEqual(Response(429, b"", "u", {"Retry-After": "9"}).retry_after(), 9.0)
        self.assertEqual(Response(429, b"", "u", {"retry-after": "8"}).retry_after(), 8.0)
        self.assertIsNone(Response(429, b"", "u", {}).retry_after())
        self.assertIsNone(Response(429, b"", "u", {"Retry-After": "Wed, 21 Oct"}).retry_after())

    def test_client_waits_the_advised_interval_not_its_own_backoff(self):
        clock = FakeClock()
        statuses = [429, 200]

        def transport(req: urllib.request.Request, timeout: float) -> Response:
            status = statuses.pop(0)
            headers = {"Retry-After": "9"} if status == 429 else {}
            return Response(status=status, body=b"{}", url=req.full_url, headers=headers)

        client = ReadOnlyClient(
            transport=transport,
            backoff_base=0.5,  # would have slept ~0.5s; Retry-After says 9
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertTrue(client.get("https://grafana.com/api/x").ok)
        self.assertGreaterEqual(clock.slept[0], 9.0)

    def test_advised_delay_is_capped(self):
        clock = FakeClock()

        def transport(req: urllib.request.Request, timeout: float) -> Response:
            return Response(429, b"{}", req.full_url, {"Retry-After": "3600"})

        client = ReadOnlyClient(
            transport=transport, max_attempts=2, backoff_cap=30.0, clock=clock, sleep=clock.sleep
        )
        client.get("https://grafana.com/api/x")
        self.assertLessEqual(clock.slept[0], 45.0, "cap plus jitter")


if __name__ == "__main__":
    unittest.main()
