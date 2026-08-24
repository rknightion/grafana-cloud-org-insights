"""Estate-level per-maturity-dimension averages (PLAN 9.1).

`maturity_dimensions` is the widest view in the platform - 271 stacks x 9 dimensions = 2,439 rows - so as
a per-stack metric it would blow the entire 2,500-series ceiling on its own. That left **no trend at all**
for the question leadership actually asks: *which dimension is the estate weakest on?* An estate-level
mean per dimension answers it in 9 series.

Two things here have real room to be wrong, and both fail in the same nasty direction - a trend that
moves with **which tier ran last** rather than with the estate:

1. **The mean must be over the stacks where THAT DIMENSION was scored.** Each scorer returns `None`, not
   0, when it cannot judge, and the T3 dimensions are absent entirely on a T1/T2 run. Averaging `None` as
   0, or dividing by all 271, makes every dimension look worse on the hourly tier than on the weekly one.
2. **The four `UNSCORED_REASONS` must be excluded.** Otherwise the dormant estate drags every dimension
   down and the metric measures stack creation rather than maturity - the same small-N effect that once
   put `stack030` (1 user) top of the leaderboard.

Everything else is the standing contract: declared in the budget, carries the rubric version, and is
**absent rather than 0** on a tier that cannot compute it.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit.budget import CATALOGUE
from collector.pillars import maturity

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

METRIC = "gcinsight_maturity_dimension_mean"


def _load():
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())
    return stacks, dataplane


def _coverage(stacks, tier):
    cov = Coverage(tier=tier, total=len(stacks))
    for s in stacks:
        cov.record_ok(str(s["slug"]))
    return cov


def _means(metrics) -> dict[str, float]:
    return {l["dimension"]: v for n, l, v in metrics if n == METRIC}


class TheMeanIsOverTheRightPopulationTest(unittest.TestCase):
    """Hand-built stacks, so the expected arithmetic is checkable by eye."""

    def test_a_dimension_none_scored_on_is_absent_not_zero(self):
        """The failure this test exists for: `None` averaged as 0 invents a bad score."""
        scored = [
            {"slug": "a", "score": 50.0, "unscored_reason": None,
             "dimensions": [{"dimension": "engagement", "score": None, "applicable": False}]},
        ]
        means = maturity.dimension_means(scored)
        self.assertNotIn("engagement", means,
                         "a dimension nothing could be scored on must be absent, never 0")

    def test_the_denominator_is_the_stacks_that_scored_that_dimension(self):
        """Two stacks scored, one not applicable: the mean is over 2, not 3."""
        scored = [
            {"slug": "a", "score": 1.0, "unscored_reason": None,
             "dimensions": [{"dimension": "engagement", "score": 80.0, "applicable": True}]},
            {"slug": "b", "score": 1.0, "unscored_reason": None,
             "dimensions": [{"dimension": "engagement", "score": 40.0, "applicable": True}]},
            {"slug": "c", "score": 1.0, "unscored_reason": None,
             "dimensions": [{"dimension": "engagement", "score": None, "applicable": False}]},
        ]
        self.assertEqual(maturity.dimension_means(scored)["engagement"], 60.0)

    def test_each_dimension_gets_its_own_denominator(self):
        """A stack can be scored on one dimension and not another; the means must not share an N."""
        scored = [
            {"slug": "a", "score": 1.0, "unscored_reason": None, "dimensions": [
                {"dimension": "engagement", "score": 100.0, "applicable": True},
                {"dimension": "access_hygiene", "score": 50.0, "applicable": True},
            ]},
            {"slug": "b", "score": 1.0, "unscored_reason": None, "dimensions": [
                {"dimension": "engagement", "score": 0.0, "applicable": True},
                {"dimension": "access_hygiene", "score": None, "applicable": False},
            ]},
        ]
        means = maturity.dimension_means(scored)
        self.assertEqual(means["engagement"], 50.0)      # over 2
        self.assertEqual(means["access_hygiene"], 50.0)  # over 1 - not 25.0

    def test_a_zero_score_still_counts(self):
        """0 is a judgement and must pull the mean down; only `None` is 'not judged'."""
        scored = [
            {"slug": "a", "score": 1.0, "unscored_reason": None,
             "dimensions": [{"dimension": "engagement", "score": 0.0, "applicable": True}]},
            {"slug": "b", "score": 1.0, "unscored_reason": None,
             "dimensions": [{"dimension": "engagement", "score": 100.0, "applicable": True}]},
        ]
        self.assertEqual(maturity.dimension_means(scored)["engagement"], 50.0)


class UnscoredStacksAreExcludedTest(unittest.TestCase):
    def test_every_unscored_reason_is_excluded(self):
        """A dormant stack may still have scoreable dimensions - it must not contribute anyway."""
        for reason in maturity.UNSCORED_REASONS:
            scored = [
                {"slug": "good", "score": 90.0, "unscored_reason": None,
                 "dimensions": [{"dimension": "engagement", "score": 90.0, "applicable": True}]},
                {"slug": "out", "score": None, "unscored_reason": reason,
                 "dimensions": [{"dimension": "engagement", "score": 10.0, "applicable": True}]},
            ]
            self.assertEqual(
                maturity.dimension_means(scored)["engagement"], 90.0,
                f"a stack unscored for {reason!r} still dragged the dimension mean down",
            )

    def test_all_stacks_unscored_means_no_metric_at_all(self):
        scored = [
            {"slug": "x", "score": None, "unscored_reason": "paused",
             "dimensions": [{"dimension": "engagement", "score": 10.0, "applicable": True}]},
        ]
        self.assertEqual(maturity.dimension_means(scored), {})

    def test_the_dormant_estate_does_not_move_the_mean(self):
        """Scaled-up version: 1 healthy stack against 40 dormant ones."""
        scored = [{"slug": "good", "score": 80.0, "unscored_reason": None,
                   "dimensions": [{"dimension": "engagement", "score": 80.0, "applicable": True}]}]
        scored += [
            {"slug": f"test{i}", "score": None, "unscored_reason": "too_few_users",
             "dimensions": [{"dimension": "engagement", "score": 0.0, "applicable": True}]}
            for i in range(40)
        ]
        self.assertEqual(maturity.dimension_means(scored)["engagement"], 80.0)


class AgainstTheRealEstateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane = _load()
        cls.t3, cls.t3_views = maturity.build(
            cls.stacks, _coverage(cls.stacks, "t3"), dataplane=cls.dataplane)
        cls.t1, _ = maturity.build(cls.stacks, _coverage(cls.stacks, "t1"))

    def test_the_metric_is_absent_on_a_tier_with_no_dataplane(self):
        """T1 runs hourly. A structural 0 here would overwrite the real weekly value (PLAN 5.3)."""
        self.assertEqual(_means(self.t1), {}, "T1 emitted dimension means without the data plane")

    def test_t3_emits_a_mean_for_the_dimensions_it_scored(self):
        means = _means(self.t3)
        self.assertGreater(len(means), 0)
        self.assertLessEqual(len(means), len(maturity.RUBRIC))
        for key in means:
            self.assertIn(key, {d.key for d in maturity.RUBRIC})

    def test_every_mean_is_a_percentage(self):
        for key, value in _means(self.t3).items():
            self.assertGreaterEqual(value, 0.0, key)
            self.assertLessEqual(value, 100.0, key)

    def test_the_series_count_is_at_most_one_per_dimension(self):
        rows = [(n, tuple(sorted(l.items()))) for n, l, _ in self.t3 if n == METRIC]
        self.assertEqual(len(rows), len(set(rows)), "duplicate dimension-mean series")
        self.assertLessEqual(len(rows), 9, "9 dimensions is the declared fan-out")

    def test_it_carries_the_rubric_version(self):
        """A rubric change must start a new series rather than silently rewriting history."""
        for _, labels, _ in [m for m in self.t3 if m[0] == METRIC]:
            self.assertEqual(labels.get("version"), maturity.RUBRIC_VERSION)
            self.assertEqual(set(labels), {"dimension", "version"})

    def test_it_agrees_with_the_view_it_summarises(self):
        """The view and the metric must not be two definitions that can disagree - recompute the mean
        straight from `maturity_dimensions` and require a match."""
        rows = self.t3_views["maturity_dimensions"]
        scored_slugs = {e["slug"] for e in
                        [maturity.score_stack(s, self.dataplane.get(str(s["slug"]))) for s in self.stacks]
                        if e["unscored_reason"] is None}
        buckets: dict[str, list[float]] = {}
        for r in rows:
            stack = r.get(" Stack") or r.get("Stack")
            score = r.get("Score")
            if stack in scored_slugs and isinstance(score, (int, float)):
                buckets.setdefault(r["Dimension"], []).append(float(score))
        expected = {k: round(sum(v) / len(v), 1) for k, v in buckets.items() if v}
        self.assertEqual(_means(self.t3), expected,
                         "the metric and the view it summarises disagree")

    def test_the_weakest_dimension_is_identifiable(self):
        """The whole point of the metric: leadership asks which dimension is weakest."""
        means = _means(self.t3)
        weakest = min(means, key=means.get)
        self.assertIsInstance(weakest, str)
        self.assertLess(means[weakest], 100.0)


class DeclaredInTheBudgetTest(unittest.TestCase):
    def test_the_metric_is_declared(self):
        spec = next((s for s in CATALOGUE if s.name == METRIC), None)
        self.assertIsNotNone(spec, f"{METRIC} is not declared in budget.py CATALOGUE")

    def test_the_declared_fan_out_covers_nine_dimensions_and_the_version(self):
        spec = next(s for s in CATALOGUE if s.name == METRIC)
        self.assertEqual(spec.labels.get("dimension"), len(maturity.RUBRIC))


if __name__ == "__main__":
    unittest.main()
