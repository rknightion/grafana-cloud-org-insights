"""The dead-man's switch must be emitted by EVERY tier, unconditionally (PLAN 1.8).

Found while about to activate the alerts: `t4` had no
`gcinsight_scan_completed_timestamp_seconds` series at all, so its staleness rule sat on NoData and
would have fired the moment routing was attached.

The cause is that `run_t4` only sets `_emit` when it produced views, and a run that legitimately finds no
baseline - scans less than a day apart, or a freshly deployed platform - produces none. So the tier ran
fine, exited 0, and recorded nothing to say it had run. A tier that cannot prove it ran is exactly what
this switch exists to detect, which made the gap self-concealing.
"""

from __future__ import annotations

import unittest

import scan as scanmod
from collector import config


class FakeWriter:
    """Captures what would be pushed. Both emitters share this shape."""

    last_metrics: list = []
    last_events: list = []

    def __init__(self, *a, **kw) -> None:
        self.url = "https://example.invalid"

    def push(self, payload):
        if payload and isinstance(payload[0], tuple) and len(payload[0]) == 3:
            FakeWriter.last_metrics = list(payload)
        else:
            FakeWriter.last_events = list(payload)
        return len(payload)


def cfg_for(tier: str) -> config.Config:
    return config.Config(
        cap="x", write_token="x", org_id="1", tier=tier, dry_run=True, limit=None, stack=None,
        concurrency=1, deadline_seconds=900, write_stack="s",
        mimir_url="https://m.invalid", mimir_tenant="1",
        loki_url="https://l.invalid", loki_tenant="1",
    )


class Args:
    out = None
    ignore_lock = True
    deadline_seconds = None


class TestEveryTierEmitsTheSwitch(unittest.TestCase):
    def setUp(self) -> None:
        self._runners = {}
        FakeWriter.last_metrics = []
        self._mimir, self._loki = scanmod.mimir.RemoteWriter, scanmod.loki.LokiWriter
        scanmod.mimir.RemoteWriter = FakeWriter
        scanmod.loki.LokiWriter = FakeWriter

    def tearDown(self) -> None:
        scanmod.mimir.RemoteWriter = self._mimir
        scanmod.loki.LokiWriter = self._loki

    def _run(self, envelope: dict, tier: str = "t4") -> list:
        original = scanmod.run_t4
        scanmod.run_t4 = lambda client, cfg: envelope
        try:
            rc = scanmod.run(None, cfg_for(tier), Args())
        finally:
            scanmod.run_t4 = original
        self.assertEqual(rc, 0)
        return FakeWriter.last_metrics

    @staticmethod
    def _envelope(with_emit: bool) -> dict:
        env = {
            "meta": {"tier": "t4", "generated_at": "2026-08-18T00:00:00+00:00", "coverage_ratio": 1.0,
                     "stacks_failed": 0, "stacks_total": 0},
            "data": {"diff": {}},
        }
        if with_emit:
            env["_emit"] = {"metrics": [], "views": {"estate_diff": [{"a": 1}]}}
        return env

    def test_a_tier_that_produced_nothing_still_records_that_it_ran(self):
        """T4's real case: no baseline, so no views and no metrics - but it DID run."""
        names = {n for n, _, _ in self._run(self._envelope(with_emit=False))}
        self.assertIn("gcinsight_scan_completed_timestamp_seconds", names)
        self.assertIn("gcinsight_scan_duration_seconds", names)

    def test_the_switch_is_labelled_with_the_tier_that_ran(self):
        """One series per tier. An unlabelled or wrongly-labelled one makes four rules watch one tier."""
        metrics = self._run(self._envelope(with_emit=False))
        stamp = [m for m in metrics if m[0] == "gcinsight_scan_completed_timestamp_seconds"]
        self.assertEqual(len(stamp), 1)
        self.assertEqual(stamp[0][1], {"tier": "t4"})

    def test_a_tier_that_did_produce_views_still_emits_it(self):
        """The path that already worked must keep working."""
        names = {n for n, _, _ in self._run(self._envelope(with_emit=True))}
        self.assertIn("gcinsight_scan_completed_timestamp_seconds", names)

    def test_the_timestamp_is_a_plausible_unix_epoch(self):
        """A millisecond value or a zero would make `time() - stamp` nonsense in the alert expression."""
        metrics = self._run(self._envelope(with_emit=False))
        value = next(v for n, _, v in metrics if n == "gcinsight_scan_completed_timestamp_seconds")
        self.assertGreater(value, 1_700_000_000)   # after 2023
        self.assertLess(value, 4_000_000_000)      # before 2096


if __name__ == "__main__":
    unittest.main()
