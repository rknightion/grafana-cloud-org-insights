"""Pillar E retention rendering and metric-cardinality contracts."""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import retention


STACKS = [{"slug": "alpha", "status": "active"}, {"slug": "beta", "status": "active"}]


def build(payload, *, policy=()):
    coverage = Coverage(tier="t2", total=len(STACKS))
    for stack in STACKS:
        coverage.record_ok(stack["slug"])
    return retention.build(STACKS, coverage, payload, expected_policy=policy)


class RetentionPillarTest(unittest.TestCase):
    def test_empty_items_is_no_self_serve_request_not_an_unreadable_or_zero_denominator(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            },
        })

        values = {(name, tuple(sorted(labels.items()))): value for name, labels, value in metrics}
        self.assertEqual(values[("gcinsight_risk_retention_stacks_measured", ())], 1.0)
        self.assertEqual(values[("gcinsight_risk_retention_change_request_stacks", ())], 1.0)
        for status in retention.REQUEST_STATUSES:
            self.assertEqual(values[("gcinsight_risk_retention_change_requests", (("status", status),))], 0.0)
        self.assertEqual(views["risk_retention_change_requests"], [])
        self.assertEqual(views["risk_retention_stream"], [])

    def test_applied_pending_and_unknown_spec_values_are_rows_not_metric_labels(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": [
                    {"status": "applied", "request_timestamp": "requested", "processed_timestamp": "done",
                     "author": "operator", "message": "longer", "pr_number": 7,
                     "limit": {"period": "31d"}, "opaque": {"new_key": {"kept": True}}},
                    {"status": "pending", "request_timestamp": "later", "processed_timestamp": None,
                     "author": "operator", "message": "review", "pr_number": None,
                     "limit": {"period": "7d"}, "opaque": {"new_key": ["still", "kept"]}},
                ]},
            },
        })

        values = {(name, tuple(sorted(labels.items()))): value for name, labels, value in metrics}
        self.assertEqual(values[("gcinsight_risk_retention_change_requests", (("status", "applied"),))], 1.0)
        self.assertEqual(values[("gcinsight_risk_retention_change_requests", (("status", "pending"),))], 1.0)
        rows = views["risk_retention_change_requests"]
        self.assertEqual(rows[0]["Opaque keys"], '{"new_key":{"kept":true}}')
        self.assertEqual(rows[1]["Opaque keys"], '{"new_key":["still","kept"]}')
        self.assertEqual(rows[0]["Limit"], '{"period":"31d"}')
        self.assertEqual(rows[0]["PR"], 7)

    def test_stream_rows_keep_period_priority_and_selector(self):
        _metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"period": "31d", "priority": 2, "selector": "{team=\"ops\"}"},
                ]},
                "change_requests": {"available": True, "items": []},
            },
        })

        self.assertEqual(views["risk_retention_stream"], [{
            " Stack": "alpha", "Period days": 31, "Priority": 2, "Selector": "{team=\"ops\"}",
        }])

    def test_missing_retention_stream_makes_no_row_or_policy_gap(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[{"selector": "{team=\"ops\"}", "minimum_period": "14d"}])

        self.assertEqual(views["risk_retention_stream"], [])
        self.assertEqual(views["risk_retention_policy_gaps"], [])
        self.assertNotIn(
            "gcinsight_risk_retention_policy_gap_stacks",
            {name for name, _labels, _value in metrics},
        )

    def test_policy_metric_is_absent_when_any_readable_limit_lacks_selector_evidence(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            },
            "beta": {
                "limits": {"available": True},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[{"selector": "{team=\"ops\"}", "minimum_period": "14d"}])

        self.assertEqual(views["risk_retention_policy_gaps"], [{
            " Stack": "alpha", "Selector": "{team=\"ops\"}",
            "Expected days": 14, "Effective days": None,
        }])
        self.assertNotIn(
            "gcinsight_risk_retention_policy_gap_stacks",
            {name for name, _labels, _value in metrics},
            "a partial policy population must not publish a structural aggregate",
        )

    def test_policy_only_marks_readable_unsatisfied_streams_as_gaps(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"period": "31d", "priority": 1, "selector": "{team=\"ops\"}"},
                    {"period": "7d", "priority": 2, "selector": "{team=\"app\"}"},
                ]},
                "change_requests": {"available": True, "items": []},
            },
            "beta": {
                "limits": {"available": False},
                "change_requests": {"available": False},
            },
        }, policy=[
            {"selector": "{team=\"ops\"}", "minimum_period": "14d"},
            {"selector": "{team=\"app\"}", "minimum_period": "14d"},
        ])

        self.assertEqual(views["risk_retention_policy_gaps"], [{
            " Stack": "alpha", "Selector": "{team=\"app\"}",
            "Expected days": 14, "Effective days": 7,
        }])
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 1.0)

    def test_policy_uses_highest_priority_and_shorter_period_for_a_tie(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"period": "31d", "priority": 1, "selector": "{team=\"ops\"}"},
                    {"period": "10d", "priority": 2, "selector": "{team=\"ops\"}"},
                    {"period": "7d", "priority": 2, "selector": "{team=\"ops\"}"},
                ]},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[{"selector": "{team=\"ops\"}", "minimum_period": "14d"}])

        self.assertEqual(views["risk_retention_policy_gaps"], [{
            " Stack": "alpha", "Selector": "{team=\"ops\"}",
            "Expected days": 14, "Effective days": 7,
        }])
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 1.0)

    def test_no_policy_has_empty_gap_view_and_no_gap_metric(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            },
        })

        self.assertEqual(views["risk_retention_policy_gaps"], [])
        self.assertNotIn("gcinsight_risk_retention_policy_gap_stacks", {name for name, _, _ in metrics})

    def test_retention_metrics_never_carry_customer_detail_labels(self):
        metrics, _views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"period": "7d", "priority": 1, "selector": "{tenant=\"unbounded\"}"},
                ]},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[{"selector": "{tenant=\"unbounded\"}", "minimum_period": "14d"}])

        forbidden = {"stack", "author", "message", "selector", "label", "label_name"}
        self.assertTrue(metrics)
        for _name, labels, _value in metrics:
            self.assertFalse(forbidden & set(labels))
            self.assertLessEqual(set(labels), {"status"})


if __name__ == "__main__":
    unittest.main()
