"""Producing-signal evidence must preserve the source window and absence semantics."""

import unittest

from collector.pillars import producing_signals
from collector.sources import capability_adoption


class ProducingSignalsTest(unittest.TestCase):
    def test_each_signal_uses_an_explicit_window_and_documented_unit(self):
        self.assertEqual(producing_signals.WINDOW, capability_adoption.WINDOW)
        self.assertEqual(set(producing_signals.SIGNALS), {"metrics", "traces"})
        for signal in producing_signals.SIGNALS.values():
            self.assertEqual(signal.window, "24h")
            self.assertTrue(signal.unit)
            self.assertTrue(signal.meaning)
            self.assertTrue(signal.source_url.startswith(("https://grafana.com/", "https://github.com/grafana/")))
        for key in producing_signals.SIGNALS:
            self.assertIn(f"[{producing_signals.WINDOW}:", capability_adoption.QUERIES[key])

    def test_live_inventory_left_join_distinguishes_missing_zero_and_positive(self):
        stacks = [
            {"slug": "one", "id": 1, "status": "active"},
            {"slug": "two", "id": 2, "status": "active"},
            {"slug": "three", "id": 3, "status": "active"},
        ]
        usage = {"available": True, "window_start": "start", "window_end": "end", "values": {
            "metrics": {"1": 0.0, "2": 10.0, "999": 99.0},
            "traces": {"1": 5.0, "2": 0.0},
        }}
        metrics, views = producing_signals.build(stacks, usage)
        self.assertEqual(metrics, [])
        rows = views[producing_signals.VIEW]
        self.assertEqual(len(rows), 6)
        by_key = {(r["Stack"], r["Signal"]): r for r in rows}
        self.assertNotIn("999", repr(rows))
        self.assertEqual(by_key["one", "Metrics"]["State"], "measured zero")
        self.assertEqual(by_key["two", "Metrics"]["State"], "producing")
        self.assertEqual(by_key["two", "Traces"]["State"], "measured zero")
        self.assertEqual(by_key["three", "Metrics"]["State"], "missing")
        self.assertIsNone(by_key["three", "Metrics"]["Value"])

    def test_failed_source_withholds_whole_view(self):
        self.assertEqual(producing_signals.build([{"slug": "one", "id": 1}],
                                                 {"available": False}), ([], {}))
        self.assertEqual(producing_signals.build([], {"available": True, "values": {}}),
                         ([], {}))


if __name__ == "__main__":
    unittest.main()
