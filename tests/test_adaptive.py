"""Adaptive Metrics recommendations: turning the verbose payload into a remediable-series figure.

The default `/aggregations/recommendations` response carries only `metric`, `drop_labels` and
`aggregations` - no series counts at all, so no saving can be derived from it. The counts appear only
with `?verbose=true`, which is what makes a currency figure possible. Verified live 2026-08-20.

The records themselves are NOT stored: one stack returned 25,779 of them at 11 MB. Only aggregates and
a small top-N sample survive into the scan envelope.
"""

from __future__ import annotations

import unittest

from collector.sources import dataplane


def rec(metric, current, recommended, *, rules=0, queries=0, dashboards=0, action="add"):
    return {
        "metric": metric,
        "drop_labels": ["instance"],
        "aggregations": ["sum:counter"],
        "recommended_action": action,
        "current_series_count": current,
        "recommended_series_count": recommended,
        "raw_series_count": current,
        "total_series_before_aggregation": current,
        "total_series_after_aggregation": recommended,
        "usages_in_rules": rules,
        "usages_in_queries": queries,
        "usages_in_dashboards": dashboards,
        "kept_labels": ["__name__", "job"],
    }


class SummariseTest(unittest.TestCase):
    def test_remediable_is_the_sum_of_the_per_metric_reduction(self):
        out = dataplane.summarise_recommendations([
            rec("a", 2600, 13),
            rec("b", 2600, 39),
        ])
        self.assertEqual(out["series_under_recommendation"], 5200)
        self.assertEqual(out["series_after_recommendation"], 52)
        self.assertEqual(out["remediable_series"], 5148)

    def test_an_empty_payload_is_zero_not_missing(self):
        out = dataplane.summarise_recommendations([])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["recommendations_pending"], 0)

    def test_a_recommendation_that_increases_series_is_not_a_saving(self):
        """Arithmetic honesty: only a real reduction counts, whatever the action says."""
        out = dataplane.summarise_recommendations([rec("a", 10, 40)])
        self.assertEqual(out["remediable_series"], 0)

    def test_unused_metrics_are_split_out_as_the_safe_subset(self):
        """A recommendation on a metric nothing queries is safe to apply; one in a live dashboard is
        a review item. Conflating them overstates what can be actioned this week."""
        out = dataplane.summarise_recommendations([
            rec("safe", 1000, 100),
            rec("in_dashboard", 1000, 100, dashboards=3),
            rec("in_rule", 1000, 100, rules=1),
            rec("in_query", 1000, 100, queries=7),
        ])
        self.assertEqual(out["remediable_series"], 3600)
        self.assertEqual(out["remediable_series_unused"], 900)

    def test_the_top_sample_is_bounded_and_ordered_by_reduction(self):
        recs = [rec(f"m{i}", 1000 * i, 0) for i in range(1, 40)]
        out = dataplane.summarise_recommendations(recs)
        top = out["sample_recommendations"]
        self.assertLessEqual(len(top), dataplane.RECOMMENDATION_SAMPLE)
        reductions = [t["remediable_series"] for t in top]
        self.assertEqual(reductions, sorted(reductions, reverse=True))
        self.assertEqual(top[0]["metric"], "m39")

    def test_the_sample_never_carries_the_whole_record(self):
        """25,779 records at 11 MB per stack is why aggregates exist. The sample must stay small."""
        out = dataplane.summarise_recommendations([rec("a", 1000, 10)])
        self.assertEqual(set(out["sample_recommendations"][0]),
                         {"metric", "current_series", "recommended_series",
                          "remediable_series", "used_in"})

    def test_action_counts_are_recorded_so_a_new_action_is_visible(self):
        out = dataplane.summarise_recommendations([
            rec("a", 100, 10), rec("b", 100, 10, action="update"),
        ])
        self.assertEqual(out["actions"], {"add": 1, "update": 1})

    def test_keep_and_remove_are_not_pending_savings(self):
        """`keep` changes nothing and `remove` expands or preserves the raw series set. Neither is
        a remediable-series reduction, and both legitimately omit count fields in the live API."""
        out = dataplane.summarise_recommendations([
            {"metric": "already-applied", "recommended_action": "keep"},
            {"metric": "rule-to-delete", "recommended_action": "remove"},
        ])
        self.assertEqual(out["recommendations_pending"], 1)
        self.assertEqual(out["recommendation_records_savings_bearing"], 0)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 0)
        self.assertTrue(out["series_counts_complete"])
        self.assertEqual(out["remediable_series"], 0)

    def test_keep_does_not_reclaim_an_already_realised_reduction(self):
        out = dataplane.summarise_recommendations([
            rec("already-applied", 100, 10, action="keep"),
        ])
        self.assertEqual(out["recommendations_pending"], 0)
        self.assertEqual(out["remediable_series"], 0)

    def test_documented_before_after_fields_are_valid_for_add_or_update(self):
        out = dataplane.summarise_recommendations([
            {
                "metric": "new-rule",
                "recommended_action": "add",
                "total_series_before_aggregation": 100,
                "total_series_after_aggregation": 20,
            },
            {
                "metric": "changed-rule",
                "recommended_action": "update",
                "total_series_before_aggregation": 30,
                "total_series_after_aggregation": 10,
            },
        ])
        self.assertTrue(out["series_counts_complete"])
        self.assertEqual(out["recommendation_records_savings_bearing"], 2)
        self.assertEqual(out["recommendation_records_with_series_counts"], 2)
        self.assertEqual(out["remediable_series"], 100)

    def test_update_without_a_marginal_before_count_is_incomplete(self):
        """`raw_series_count` is the unaggregated input, not the output of the current rule. Using it
        as the update baseline would count savings already realised by the existing rule."""
        out = dataplane.summarise_recommendations([{
            "metric": "changed-rule",
            "recommended_action": "update",
            "raw_series_count": 1000,
            "recommended_series_count": 10,
            "total_series_after_aggregation": 10,
        }])
        self.assertFalse(out["series_counts_complete"])
        self.assertEqual(out["recommendation_records_missing_series_counts"], 1)
        self.assertEqual(out["remediable_series"], 0)

    def test_missing_counts_are_treated_as_zero_not_an_exception(self):
        """A payload without the verbose fields must degrade, not crash: `verbose=true` is a query
        parameter and a future API could stop honouring it."""
        out = dataplane.summarise_recommendations([
            {"metric": "a", "drop_labels": [], "aggregations": []},
        ])
        self.assertEqual(out["recommendations_pending"], 1)
        self.assertEqual(out["remediable_series"], 0)
        self.assertFalse(out["verbose"])

    def test_verbose_is_true_only_when_the_counts_are_actually_present(self):
        self.assertTrue(dataplane.summarise_recommendations([rec("a", 10, 1)])["verbose"])


class RequestShapeTest(unittest.TestCase):
    def test_the_recommendations_call_asks_for_verbose(self):
        """Without it the response has no series counts at all, so no saving can be computed. The
        default payload looks complete, which is exactly why this is pinned."""
        calls: list[str] = []

        class FakeResp:
            ok = True
            status = 200
            def json(self): return []

        class FakeClient:
            def get(self, url, basic=None):
                calls.append(url)
                return FakeResp()

        stack = {"slug": "s", "hmInstancePromUrl": "https://prom.example",
                 "hmInstancePromId": "1", "id": 1}
        dataplane.adaptive_metrics(FakeClient(), stack, "cap")
        recs = [c for c in calls if "recommendations" in c]
        self.assertTrue(recs)
        self.assertIn("verbose=true", recs[0])


if __name__ == "__main__":
    unittest.main()
