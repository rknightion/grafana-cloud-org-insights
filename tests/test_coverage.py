from __future__ import annotations

import unittest

from collector.coverage import Coverage, rollup


class CoverageTest(unittest.TestCase):
    def test_full_coverage(self):
        cov = Coverage(tier="t1", total=3)
        for stack in ("a", "b", "c"):
            cov.record_ok(stack)
        self.assertEqual(cov.ratio, 1.0)
        self.assertFalse(cov.should_abort)
        self.assertEqual(cov.failed, 0)

    def test_failures_are_recorded_by_reason_and_named(self):
        cov = Coverage(tier="t2", total=4)
        cov.record_ok("a")
        cov.record_failure("b", "http_429")
        cov.record_failure("c", "http_429")
        cov.record_failure("d", "timeout")
        self.assertEqual(cov.failed, 3)
        meta = cov.as_meta()
        self.assertEqual(meta["failures_by_reason"], {"http_429": 2, "timeout": 1})
        self.assertEqual(meta["failed_stacks"], {"b": "http_429", "c": "http_429", "d": "timeout"})

    def test_a_retried_stack_stops_being_a_failure(self):
        cov = Coverage(tier="t1", total=1)
        cov.record_failure("a", "timeout")
        cov.record_ok("a")
        self.assertEqual(cov.failed, 0)
        self.assertEqual(cov.as_meta()["failures_by_reason"], {})

    def test_abort_threshold_is_ten_percent(self):
        cov = Coverage(tier="t1", total=100)
        for i in range(10):
            cov.record_failure(f"s{i}", "http_500")
        self.assertFalse(cov.should_abort, "exactly 10% must not abort")
        cov.record_failure("s10", "http_500")
        self.assertTrue(cov.should_abort)

    def test_metrics_labels_stay_bounded(self):
        """Cardinality guard: only `tier` and a closed `reason` vocabulary may appear."""
        cov = Coverage(tier="t3", total=2)
        cov.record_ok("a")
        cov.record_failure("b", "http_429")
        names = {name for name, _, _ in cov.as_metrics()}
        self.assertEqual(
            names,
            {
                "gcinsight_scan_stacks_total",
                "gcinsight_scan_stacks_scannable",
                "gcinsight_scan_stacks_scanned",
                "gcinsight_scan_coverage_ratio",
                "gcinsight_scan_stacks_failed",
            },
        )
        for _, labels, _ in cov.as_metrics():
            self.assertLessEqual(set(labels), {"tier", "reason"})

    def test_paused_stacks_are_skipped_not_failed(self):
        """The estate's 4 paused stacks answer HTTP 409. Counting them as failures would cap coverage
        at 98.5% forever; counting them as scanned would be the opposite lie."""
        cov = Coverage(tier="t2", total=271)
        for i in range(267):
            cov.record_ok(f"s{i}")
        for slug in ("testsrobot002", "teststack004", "teststack017", "teststack018"):
            cov.record_skipped(slug, "paused")

        self.assertEqual(cov.failed, 0)
        self.assertEqual(cov.scannable, 267)
        self.assertEqual(cov.ratio, 1.0, "a fully-scanned estate must read 100% despite paused stacks")
        self.assertFalse(cov.should_abort)
        meta = cov.as_meta()
        self.assertEqual(meta["stacks_skipped"], 4)
        self.assertEqual(meta["skipped_by_reason"], {"paused": 4})
        self.assertFalse(rollup("x", 1, cov)["partial"])

    def test_skipped_stacks_do_not_mask_real_failures(self):
        cov = Coverage(tier="t2", total=100)
        for i in range(4):
            cov.record_skipped(f"p{i}", "paused")
        for i in range(11):
            cov.record_failure(f"f{i}", "http_500")
        for i in range(85):
            cov.record_ok(f"s{i}")
        self.assertEqual(cov.scannable, 96)
        self.assertTrue(cov.should_abort, "11 of 96 scannable is over the 10% threshold")

    def test_rollup_carries_its_denominator(self):
        """The fix for the flagship silent-wrongness path: a partial scan is visibly partial."""
        cov = Coverage(tier="t1", total=271)
        for i in range(244):
            cov.record_ok(f"s{i}")
        for i in range(27):
            cov.record_failure(f"f{i}", "http_500")

        got = rollup("dashboards_total", 6700, cov)
        self.assertEqual(got["stacks_counted"], 244)
        self.assertEqual(got["stacks_total"], 271)
        self.assertTrue(got["partial"])
        self.assertEqual(got["coverage_ratio"], 0.9004)

    def test_rollup_is_not_partial_at_full_coverage(self):
        cov = Coverage(tier="t1", total=2)
        cov.record_ok("a")
        cov.record_ok("b")
        self.assertFalse(rollup("x", 1, cov)["partial"])

    def test_empty_estate_does_not_divide_by_zero(self):
        cov = Coverage(tier="t1", total=0)
        self.assertEqual(cov.ratio, 0.0)
        self.assertFalse(cov.should_abort)


if __name__ == "__main__":
    unittest.main()
