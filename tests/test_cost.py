"""Pillar B - cost maths, tested first because a wrong money figure is the worst defect here."""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit import guard
from collector.emit.budget import CATALOGUE
from collector.pillars import cost, estate

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


def _load():
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())
    coverage = Coverage(tier="t3", total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            coverage.record_skipped(str(s["slug"]), "paused")
        else:
            coverage.record_ok(str(s["slug"]))
    return stacks, dataplane, coverage


class CostMathsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane, cls.coverage = _load()
        cls.metrics, cls.views = cost.build(cls.stacks, cls.coverage, cls.dataplane)
        cls.by = {}
        for name, labels, value in cls.metrics:
            cls.by[(name, tuple(sorted(labels.items())))] = value

    def test_series_per_billed_user_uses_billing_not_current_users(self):
        """811 vs 973 is a 17% error. Pin the divisor, not just the shape."""
        series = sum(s.get("hmInstancePromCurrentActiveSeries") or 0 for s in self.stacks)
        billed = sum(s.get("billingActiveUsers") or 0 for s in self.stacks)
        current = sum(s.get("currentActiveUsers") or 0 for s in self.stacks)
        self.assertEqual(billed, 811)
        self.assertEqual(current, 973)
        got = self.by[("gcinsight_cost_series_per_billed_user", ())]
        self.assertEqual(got, round(series / billed, 1))
        self.assertNotEqual(got, round(series / current, 1))

    def test_adaptive_headline_matches_the_findings_register(self):
        self.assertEqual(
            self.by[("gcinsight_cost_adaptive_rules_applied_total", ())], 3635.0
        )
        self.assertEqual(self.by[("gcinsight_cost_stacks_without_adaptive", ())], 106.0)
        pending = sum(v for (n, l), v in self.by.items()
                      if n == "gcinsight_adaptive_recommendations" and ("status", "pending") in l)
        self.assertEqual(pending, 35064.0)

    def test_unadopted_stacks_hold_the_reported_share_of_org_series(self):
        """FINDINGS.md claims 5,685,608 series = 51% of the org. If that drifts, the finding is stale."""
        rows = self.views["cost_adaptive_headroom"]
        self.assertEqual(len(rows), 106)
        self.assertEqual(sum(r["Active series"] for r in rows), 5_685_608)
        share = self.views["cost_summary"][5]
        self.assertEqual(share[" Metric"], "Their share of org series %")
        self.assertEqual(share["Value"], 51.4)

    def test_headroom_is_sorted_by_remediable_volume_not_by_spend(self):
        rows = self.views["cost_adaptive_headroom"]
        self.assertEqual(rows[0][" Stack"], "stack084")
        self.assertEqual([r["Active series"] for r in rows],
                         sorted((r["Active series"] for r in rows), reverse=True))
        for r in rows:
            self.assertEqual(r["Rules applied"], 0, "an unadopted stack has applied nothing")
            self.assertGreater(r["Recs pending"], 0, "and has something to apply")

    def test_adaptive_recommendation_queue_is_bounded_named_and_sorted(self):
        rows = self.views["cost_adaptive_metric_recommendations"]
        self.assertLessEqual(len(rows), 10 * len(self.stacks))
        if rows:
            self.assertEqual(
                list(rows[0]),
                [" Stack", "Metric", "Current series", "Recommended series", "Removable series",
                 "Dependencies"],
            )
            self.assertEqual(
                [row["Removable series"] for row in rows],
                sorted((row["Removable series"] for row in rows), reverse=True),
            )

    def test_cardinality_outlier_is_synthetic_leader_by_an_order_of_magnitude(self):
        rows = self.views["cost_cardinality_outliers"]
        self.assertEqual(rows[0][" Stack"], "stack084")
        self.assertEqual(rows[0]["Label values"], 398_773)
        self.assertGreater(rows[0]["Label values"], 7 * rows[1]["Label values"])

    def test_current_and_billing_usage_are_reported_separately_never_merged(self):
        rows = {r[" Signal"]: r for r in self.views["cost_signal_usage"]}
        # Measured disagreement: the whole reason both columns exist.
        self.assertNotEqual(rows["logs"]["Stacks above floor (current)"],
                            rows["logs"]["Stacks above floor (billing)"])
        for r in rows.values():
            self.assertIn("Current usage", r)
            self.assertIn("Billing usage", r)

    def test_signal_usage_thresholds_at_the_synthetic_floor_not_at_zero(self):
        """~178 stacks report exactly 2 series. '>0' would claim near-universal adoption."""
        self.assertEqual(cost.USAGE_FLOOR, 1000)
        above_zero = len([s for s in self.stacks
                          if (s.get("hmInstancePromCurrentUsage") or 0) > 0])
        rows = {r[" Signal"]: r for r in self.views["cost_signal_usage"]}
        self.assertLess(rows["metrics"]["Stacks above floor (current)"], above_zero)

    def test_savings_in_currency_says_it_is_unavailable_rather_than_rendering_blank(self):
        row = [r for r in self.views["cost_summary"] if r[" Metric"] == "Savings in currency"][0]
        self.assertIn("not available", str(row["Value"]))

    def test_summary_leads_with_the_denominator(self):
        first = self.views["cost_summary"][0]
        self.assertEqual(first[" Metric"], "Stacks measured for Adaptive")
        self.assertIn("267 scannable", str(first["Value"]))

    def test_every_metric_passes_the_label_guard(self):
        self.assertEqual(guard.check_all(self.metrics), len(self.metrics))

    def test_offender_names_never_become_labels(self):
        """Cardinality data is full of unbounded strings. None may reach a metric label value."""
        slugs = {str(s["slug"]) for s in self.stacks}
        allowed_values = slugs | {"pending", "applied"} | set(cost.SIGNAL_USAGE)
        for name, labels, _ in self.metrics:
            for key, value in labels.items():
                self.assertIn(value, allowed_values,
                              f"{name} label {key}={value!r} is not a slug or a declared enum")
        # The worst-label NAME is unbounded, so it exists only as a view column.
        self.assertIn("Worst label", self.views["cost_cardinality_outliers"][0])
        self.assertNotIn("label", {k for _, labels, _ in self.metrics for k in labels})


class CostBudgetConformanceTest(unittest.TestCase):
    """Pillar B is the first pillar big enough to break the budget. Prove it does not."""

    @classmethod
    def setUpClass(cls) -> None:
        stacks, dataplane, coverage = _load()
        cls.metrics, _ = cost.build(stacks, coverage, dataplane)
        cls.declared = {(s.name, tuple(sorted(s.labels))): s for s in CATALOGUE if s.store == "mimir"}

    def test_every_emitted_metric_is_declared(self):
        for name, labels, _ in self.metrics:
            self.assertIn((name, tuple(sorted(labels))), self.declared, f"{name} undeclared")

    def test_actual_series_are_within_the_declared_cardinality(self):
        actual: dict[tuple, int] = {}
        for name, labels, _ in self.metrics:
            key = (name, tuple(sorted(labels)))
            actual[key] = actual.get(key, 0) + 1
        for key, count in actual.items():
            self.assertLessEqual(count, self.declared[key].series,
                                 f"{key[0]} emitted {count}, declared {self.declared[key].series}")


class PillarInteractionTest(unittest.TestCase):
    """Two pillars emitting the same series would publish whichever sample encoded last."""

    def test_pillar_a_and_b_together_emit_no_duplicate_series(self):
        stacks, dataplane, coverage = _load()
        a, _ = estate.build(stacks, coverage)
        b, _ = cost.build(stacks, coverage, dataplane)
        combined = a + b
        self.assertEqual(guard.check_no_duplicates(combined), len(combined))

    def test_the_duplicate_guard_actually_catches_a_collision(self):
        with self.assertRaises(guard.DuplicateSeries):
            guard.check_no_duplicates([("m", {"stack": "a"}, 1.0), ("m", {"stack": "a"}, 2.0)])

    def test_cost_pillar_does_not_recompute_pillar_as_billed_user_total(self):
        """`gcinsight_cost_billed_users` is Pillar A's. B owns the ratio, not the total."""
        stacks, dataplane, coverage = _load()
        b, _ = cost.build(stacks, coverage, dataplane)
        self.assertNotIn("gcinsight_cost_billed_users", {n for n, _, _ in b})


class CostWithoutDataplaneTest(unittest.TestCase):
    """T1/T2 run without T3 data. Missing Adaptive data must read as unknown, never as zero."""

    def test_adaptive_views_are_ABSENT_not_empty_when_the_dataplane_is_absent(self):
        """An empty view is worse than a missing one: every tier writes every view it returns, so a T1
        run would overwrite T3's 106-row headroom table with an empty one and the panel would read
        'nothing to fix'. Measured - T3 blanked risk_access_policies from 754 rows to 0."""
        stacks, _, coverage = _load()
        metrics, views = cost.build(stacks, coverage, dataplane=None)
        self.assertNotIn("cost_adaptive_headroom", views)
        self.assertNotIn("cost_cardinality_outliers", views)
        # The inventory-derived views are still published.
        self.assertIn("cost", views)
        self.assertIn("cost_summary", views)
        for row in views["cost"]:
            self.assertIsNone(row["Adaptive recs pending"])
            self.assertIsNone(row["Adaptive adopted"])
        self.assertNotIn("gcinsight_adaptive_recommendations", {n for n, _, _ in metrics})
        # But the inventory-derived half still works.
        self.assertTrue(any(n == "gcinsight_stack_active_series" for n, _, _ in metrics))

    def test_zero_billed_users_yields_none_not_a_division_error(self):
        stacks, _, coverage = _load()
        _, views = cost.build(stacks, coverage, dataplane=None)
        nobilled = [r for r in views["cost"] if r["Users (billed)"] == 0]
        self.assertTrue(nobilled)
        for r in nobilled:
            self.assertIsNone(r["Series per billed user"])


if __name__ == "__main__":
    unittest.main()
