"""The traceability gate must actually catch a broken trace (PLAN 8.5).

`bin/trace.py` exists to prove every leadership-facing number reproduces from a named source field. A
verifier that cannot fail is worse than no verifier - it produces a clean table either way and buys
false confidence. So the tests here are mostly about making it FAIL: a wrong aggregation, a money figure
sourced from the wrong user count, a row for a metric nobody emits.
"""

from __future__ import annotations

import json
import pathlib
import unittest
from unittest import mock

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bin import trace  # noqa: E402

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


def _scan() -> dict:
    """A scan object in the shape S3 holds, built from the committed inventory fixture."""
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    paused = {str(s["slug"]): "paused" for s in stacks if s.get("status") != "active"}
    return {
        "meta": {
            "generated_at": "2026-08-17T20:00:00+00:00", "tier": "t1", "org_id": "900001",
            "stacks_total": len(stacks), "stacks_scanned": len(stacks) - len(paused),
            "coverage_ratio": 1.0, "skipped_stacks": paused, "failed_stacks": {},
        },
        "data": {"stacks": stacks, "access_policies": []},
    }


class TheTraceReproducesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scan = _scan()

    def test_every_declared_trace_reproduces_against_the_fixture(self):
        rows, failures = trace.run(self.scan, check_live=False)
        bad = [(r["metric"], r["status"]) for r in rows if r["status"] != "ok"]
        self.assertEqual(bad, [], f"traces did not reproduce: {bad}")
        self.assertEqual(failures, 0)

    def test_no_trace_is_declared_for_a_metric_nobody_emits(self):
        """A row whose metric was renamed would otherwise sit in the table reading 'NOT EMITTED'."""
        published = trace.emitted(self.scan)
        names = {n for n, _ in published}
        for t in trace.TRACES:
            self.assertIn(t.metric, names, f"{t.metric} is traced but never emitted")

    def test_the_table_renders_without_a_live_column_when_offline(self):
        rows, _ = trace.run(self.scan, check_live=False)
        table = trace.render(rows, self.scan, check_live=False)
        self.assertNotIn("On stack", table)
        self.assertIn("| Number | Source field | Recomputed | Published | Status |", table)

    def test_live_mode_requires_context_before_scan_io(self):
        with (
            mock.patch("sys.argv", ["trace.py", "--live"]),
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(trace, "load_scan") as load_scan,
            self.assertRaises(SystemExit) as stopped,
        ):
            trace.main()

        self.assertEqual(stopped.exception.code, 2)
        load_scan.assert_not_called()


class TheGateCatchesABrokenTraceTest(unittest.TestCase):
    """Each test breaks one thing and asserts the failure is reported."""

    def setUp(self) -> None:
        self.scan = _scan()
        self._saved = list(trace.TRACES)

    def tearDown(self) -> None:
        trace.TRACES[:] = self._saved

    def test_a_wrong_aggregation_is_a_mismatch(self):
        trace.TRACES[:] = [
            trace.Trace("gcinsight_estate_dashboards", {}, "sum(dashboardCnt)",
                        lambda st: 1.0)  # deliberately wrong
        ]
        rows, failures = trace.run(self.scan, check_live=False)
        self.assertEqual(failures, 1)
        self.assertIn("MISMATCH", rows[0]["status"])

    def test_a_money_row_not_sourced_from_the_billed_field_fails(self):
        """The single most consequential error this platform can make on a leadership panel."""
        trace.TRACES[:] = [
            trace.Trace("gcinsight_estate_active_users", {}, "sum(currentActiveUsers)",
                        lambda st: sum(trace._n(s, "currentActiveUsers") for s in st),
                        money=True)
        ]
        rows, failures = trace.run(self.scan, check_live=False)
        self.assertEqual(failures, 1)
        self.assertIn(trace.MONEY_SOURCE, rows[0]["status"])

    def test_a_trace_for_an_unemitted_metric_fails(self):
        trace.TRACES[:] = [
            trace.Trace("gcinsight_does_not_exist", {}, "nothing", lambda st: 0.0)
        ]
        rows, failures = trace.run(self.scan, check_live=False)
        self.assertEqual(failures, 1)
        self.assertEqual(rows[0]["status"], "NOT EMITTED")

    def test_a_trace_with_the_wrong_labels_fails(self):
        """Right metric, wrong label set - reads as NOT EMITTED, which is the honest answer."""
        trace.TRACES[:] = [
            trace.Trace("gcinsight_estate_stacks", {"status": "nonsense"},
                        "count", lambda st: float(len(st)))
        ]
        _, failures = trace.run(self.scan, check_live=False)
        self.assertEqual(failures, 1)


class MoneyRulesTest(unittest.TestCase):
    def test_the_money_rows_are_the_cost_ones_and_nothing_else(self):
        """If a new leadership metric becomes money-bearing it must be marked, not silently added."""
        money = {t.metric for t in trace.TRACES if t.money}
        self.assertEqual(money, {
            "gcinsight_cost_billed_users",
            "gcinsight_cost_series_per_billed_user",
        })

    def test_every_money_row_names_the_billed_field(self):
        for t in trace.TRACES:
            if t.money:
                self.assertIn(trace.MONEY_SOURCE, t.source, f"{t.metric} money source is not the billed field")

    def test_the_money_spread_is_computed_not_quoted(self):
        """A remembered percentage rots - the estate moved from 811/973 to 842/994 in one day."""
        rows, _ = trace.run(_scan(), check_live=False)
        table = trace.render(rows, _scan(), check_live=False)
        self.assertIn("In this scan the two differ by", table)
        self.assertNotIn("17%", table)


if __name__ == "__main__":
    unittest.main()
