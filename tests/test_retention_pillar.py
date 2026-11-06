"""Pillar E retention rendering and metric-cardinality contracts."""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import retention


STACKS = [{"slug": "alpha", "status": "active"}, {"slug": "beta", "status": "active"}]


def build(payload, *, policy=(), presence=1):
    """Each record observes `presence` streams for every policy selector unless it says otherwise.

    The default keeps a below-minimum stack a real gap; `presence=None` omits the probe entirely.
    """
    coverage = Coverage(tier="t2", total=len(STACKS))
    for stack in STACKS:
        coverage.record_ok(stack["slug"])
    if presence is not None:
        payload = {
            slug: record if not isinstance(record, dict) or "stream_presence" in record else {
                **record,
                "stream_presence": {item["selector"]: {"available": True, "streams": presence}
                                    for item in policy},
            }
            for slug, record in payload.items()
        }
    return retention.build(STACKS, coverage, payload, expected_policy=policy)


class RetentionPillarTest(unittest.TestCase):
    def test_empty_inventory_with_configured_policy_withholds_status_and_count(self):
        metrics, views = retention.build(
            [], Coverage(tier="t2", total=0), {},
            expected_policy=[{"selector": "{service=\"one\"}", "minimum_period": "14d"}],
        )
        self.assertNotIn("risk_retention_policy_status", views)
        self.assertNotIn(
            "gcinsight_risk_retention_policy_unreadable_stacks",
            {name for name, _labels, _value in metrics},
        )

    def test_empty_inventory_without_expectations_keeps_empty_status_view(self):
        _metrics, views = retention.build([], Coverage(tier="t2", total=0), {})
        self.assertEqual(views["risk_retention_policy_status"], [])

    def test_malformed_limits_stream_withholds_all_rows_and_measured_count(self):
        for invalid in (
            {"selector": '{service="two"}', "period": "invalid", "priority": 2},
            {"selector": '{service="two"}', "period": "7d", "priority": "invalid"},
            {"selector": '{service="two"}', "period": float("inf"), "priority": 2},
        ):
            with self.subTest(invalid=invalid):
                metrics, views = build({
                    "alpha": {
                        "limits": {"available": True, "retention_stream": [
                            {"selector": '{service="one"}', "period": "31d", "priority": 1},
                            invalid,
                        ]},
                        "change_requests": {"available": True, "items": []},
                    },
                    "beta": {"limits": {"available": True, "retention_stream": []}},
                }, policy=[{"selector": '{service="one"}', "minimum_period": "14d"}])
                # A healthy neighbour makes the stream view publishable. Alpha must not leak the
                # valid prefix of its malformed list into that view or the measured denominator.
                self.assertEqual(views["risk_retention_stream"], [])
                self.assertEqual(views["risk_retention_policy_status"][0]["Status"], "unreadable")
                self.assertIsNone(views["risk_retention_policy_status"][0]["Effective days"])
                self.assertEqual(
                    {name: value for name, _, value in metrics}[
                        "gcinsight_risk_retention_stacks_measured"], 1.0,
                )

    def test_plugin_route_failure_does_not_hide_readable_loki_policy(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"selector": "{service=\"one\"}", "period": "31d", "priority": 1},
                ]},
                "change_requests": {"available": False},
            },
        }, policy=[{"selector": "{service=\"one\"}", "minimum_period": "14d"}])
        self.assertEqual(len(views["risk_retention_stream"]), 1)
        self.assertEqual(views["risk_retention_policy_status"][0]["Status"], "compliant")
        values = {name: value for name, _, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_stacks_measured"], 1.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_compliant_stacks"], 1.0)
        self.assertNotIn("gcinsight_risk_retention_change_request_stacks", values)

    def test_policy_status_lists_compliant_below_and_unreadable_per_expectation(self):
        policy = [
            {"selector": "{service=\"one\"}", "minimum_period": "14d"},
            {"selector": "{service=\"two\"}", "minimum_period": "14d"},
        ]
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"selector": "{service=\"one\"}", "period": "31d", "priority": 1},
                    {"selector": "{service=\"two\"}", "period": "7d", "priority": 1},
                ]},
                "change_requests": {"available": True, "items": []},
            },
            "beta": {
                "limits": {"available": False},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=policy)

        rows = views["risk_retention_policy_status"]
        self.assertEqual(len(rows), len(STACKS) * len(policy))
        self.assertEqual(
            [(row[" Stack"], row["Selector"], row["Status"]) for row in rows],
            [
                ("alpha", "{service=\"one\"}", "compliant"),
                ("alpha", "{service=\"two\"}", "below policy"),
                ("beta", "{service=\"one\"}", "unreadable"),
                ("beta", "{service=\"two\"}", "unreadable"),
            ],
        )
        self.assertEqual(rows[2]["Effective days"], None)
        self.assertEqual(rows[3]["Effective days"], None)
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_compliant_stacks"], 0.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_unreadable_stacks"], 1.0)

    def test_failed_plugin_route_keeps_confirmed_loki_policy_breach(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_period": "7d", "retention_stream": []},
                "change_requests": {"available": False},
            },
        }, policy=[{"selector": "{service=\"one\"}", "minimum_period": "14d"}])
        self.assertEqual(views["risk_retention_policy_status"][0]["Status"], "below policy")
        self.assertEqual(views["risk_retention_policy_status"][0]["Effective days"], 7)
        self.assertEqual(len(views["risk_retention_policy_gaps"]), 1)
        self.assertEqual(
            {n: v for n, _, v in metrics}["gcinsight_risk_retention_policy_gap_stacks"], 1.0,
        )

    def test_fully_compliant_stack_counts_once_across_multiple_expectations(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": [
                    {"selector": "{service=\"one\"}", "period": "31d", "priority": 1},
                    {"selector": "{service=\"two\"}", "period": "31d", "priority": 1},
                ]},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[
            {"selector": "{service=\"one\"}", "minimum_period": "14d"},
            {"selector": "{service=\"two\"}", "minimum_period": "14d"},
        ])
        self.assertEqual(
            [row["Status"] for row in views["risk_retention_policy_status"][:2]],
            ["compliant", "compliant"],
        )
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_compliant_stacks"], 1.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 0.0)

    def test_empty_expectations_have_no_status_rows_or_compliant_metric(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            },
        })
        self.assertEqual(views["risk_retention_policy_status"], [])
        self.assertNotIn(
            "gcinsight_risk_retention_policy_compliant_stacks", {n for n, _, _ in metrics}
        )
        self.assertNotIn(
            "gcinsight_risk_retention_policy_unreadable_stacks", {n for n, _, _ in metrics}
        )

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
            " Stack": "alpha", "Scope": "stream rule", "Period days": 31, "Priority": 2,
            "Selector": "{team=\"ops\"}",
        }])

    def test_missing_retention_stream_makes_no_row_or_policy_gap(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[{"selector": "{team=\"ops\"}", "minimum_period": "14d"}])

        self.assertNotIn("risk_retention_stream", views)
        self.assertNotIn("risk_retention_policy_gaps", views)
        self.assertEqual(views["risk_retention_policy_status"][0]["Status"], "unreadable")
        self.assertNotIn(
            "gcinsight_risk_retention_policy_gap_stacks",
            {name for name, _labels, _value in metrics},
        )
        self.assertNotIn(
            "gcinsight_risk_retention_stacks_measured",
            {name for name, _labels, _value in metrics},
        )

    def test_non_governing_overlapping_selector_cannot_make_policy_unreadable(self):
        for overlap, priority, period in (
            ('{service="api",team="ops"}', 2, "1d"),
            ('{service=~"api|worker"}', 2, "1d"),
            ('{service="api",team="ops"}', 3, "31d"),
        ):
            with self.subTest(overlap=overlap, priority=priority, period=period):
                metrics, views = build({
                    "alpha": {"limits": {"available": True, "retention_stream": [
                        {"selector": '{service="api"}', "period": "31d", "priority": 3},
                        {"selector": '{service="api"}', "period": "7d", "priority": 1},
                        {"selector": overlap, "period": period, "priority": priority},
                    ]}},
                }, policy=[{"selector": '{service="api"}', "minimum_period": "14d"}])
                self.assertEqual(views["risk_retention_policy_status"][0], {
                    " Stack": "alpha", "Selector": '{service="api"}',
                    "Expected days": 14, "Effective days": 31, "Streams (7d)": 1, "Status": "compliant",
                })
                self.assertEqual(views["risk_retention_policy_gaps"], [])
                values = {name: value for name, _, value in metrics}
                self.assertEqual(values["gcinsight_risk_retention_policy_compliant_stacks"], 1.0)
                # Beta is in the live inventory but has no limits, so it remains unreadable.
                self.assertEqual(values["gcinsight_risk_retention_policy_unreadable_stacks"], 1.0)

    def test_overlapping_selector_with_shorter_rule_is_unreadable(self):
        metrics, views = build({
            "alpha": {"limits": {"available": True, "retention_stream": [
                {"selector": '{service="api"}', "period": "31d", "priority": 1},
                {"selector": '{service="api",team="ops"}', "period": "7d", "priority": 2},
            ]}, "change_requests": {"available": True, "items": []}},
        }, policy=[{"selector": '{service="api"}', "minimum_period": "14d"}])
        self.assertEqual(views["risk_retention_policy_status"][0]["Status"], "unreadable")
        self.assertIsNone(views["risk_retention_policy_status"][0]["Effective days"])
        self.assertEqual(views["risk_retention_policy_gaps"], [])
        self.assertNotIn("gcinsight_risk_retention_policy_compliant_stacks", {n for n, _, _ in metrics})

    def test_regex_selector_cannot_be_proven_disjoint(self):
        _metrics, views = build({
            "alpha": {"limits": {"available": True, "retention_stream": [
                {"selector": '{service="api"}', "period": "31d", "priority": 1},
                {"selector": '{service=~"api|worker"}', "period": "7d", "priority": 2},
            ]}, "change_requests": {"available": True, "items": []}},
        }, policy=[{"selector": '{service="api"}', "minimum_period": "14d"}])
        self.assertEqual(views["risk_retention_policy_status"][0]["Status"], "unreadable")

    def test_one_ambiguous_expectation_prevents_whole_stack_compliance(self):
        metrics, views = build({
            "alpha": {"limits": {"available": True, "retention_stream": [
                {"selector": '{service="api"}', "period": "31d", "priority": 1},
                {"selector": '{service="api",team="ops"}', "period": "7d", "priority": 2},
                {"selector": '{service="worker"}', "period": "31d", "priority": 1},
            ]}},
        }, policy=[
            {"selector": '{service="api"}', "minimum_period": "14d"},
            {"selector": '{service="worker"}', "minimum_period": "14d"},
        ])
        self.assertEqual(
            [row["Status"] for row in views["risk_retention_policy_status"][:2]],
            ["unreadable", "compliant"],
        )
        values = {name: value for name, _, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_compliant_stacks"], 0.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_unreadable_stacks"], 2.0)

    def test_policy_count_keeps_confirmed_breach_when_another_stack_is_unreadable(self):
        metrics, views = build({
            "alpha": {
                "limits": {"available": True, "retention_period": "1w", "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            },
            "beta": {
                "limits": {"available": True},
                "change_requests": {"available": True, "items": []},
            },
        }, policy=[{"selector": "{team=\"ops\"}", "minimum_period": "14d"}])

        self.assertEqual(views["risk_retention_policy_gaps"], [{
            " Stack": "alpha", "Selector": "{team=\"ops\"}",
            "Expected days": 14, "Effective days": 7, "Streams (7d)": 1,
        }])
        self.assertEqual(
            [(row[" Stack"], row["Status"]) for row in views["risk_retention_policy_status"]],
            [("alpha", "below policy"), ("beta", "unreadable")],
        )
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 1.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_unreadable_stacks"], 1.0)

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
            "Expected days": 14, "Effective days": 7, "Streams (7d)": 1,
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
            "Expected days": 14, "Effective days": 7, "Streams (7d)": 1,
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


    def test_prometheus_duration_notation_parses_folded_weeks_and_years(self):
        for raw, days in (("2w", 14), ("1y", 365), ("17w1d", 120), ("744h", 31), ("0s", 0),
                          ("31d", 31), ("1d12h", 1.5), ("90m", 0.0625)):
            with self.subTest(raw=raw):
                self.assertEqual(retention.period_days(raw), days)
        for raw in ("", "d", "2x", "1d2w", "-1d", "1.5w"):
            with self.subTest(raw=raw):
                self.assertIsNone(retention.period_days(raw))

    def test_unruled_stack_with_tenant_default_is_measured_and_policy_uses_default(self):
        # Witnessed: Loki omits an empty retention_stream but always renders retention_period.
        metrics, views = build({
            "alpha": {"limits": {"available": True, "retention_period": "25w5d"}},
            "beta": {"limits": {"available": True, "retention_period": "31d"}},
        }, policy=[{"selector": '{service="audit"}', "minimum_period": "120d"}])
        self.assertEqual(
            [(row[" Stack"], row["Effective days"], row["Status"])
             for row in views["risk_retention_policy_status"]],
            [("alpha", 180, "compliant"), ("beta", 31, "below policy")],
        )
        values = {name: value for name, _, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_stacks_measured"], 2.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_unreadable_stacks"], 0.0)

    def test_unruled_streams_without_a_readable_default_stay_unreadable(self):
        for limits in ({"available": True, "retention_stream": []},
                       {"available": True, "retention_period": "forever", "retention_stream": []}):
            with self.subTest(limits=limits):
                _metrics, views = build({"alpha": {"limits": limits}},
                                        policy=[{"selector": '{team="ops"}', "minimum_period": "14d"}])
                row = views["risk_retention_policy_status"][0]
                self.assertEqual((row["Status"], row["Effective days"]), ("unreadable", None))
                self.assertEqual(views["risk_retention_policy_gaps"], [])

    def test_stream_view_lists_only_tenant_defaults_departing_from_the_estate_mode(self):
        stacks = [{"slug": slug, "status": "active"} for slug in ("a", "b", "c", "d")]
        coverage = Coverage(tier="t2", total=len(stacks))
        _metrics, views = retention.build(stacks, coverage, {
            "a": {"limits": {"available": True, "retention_period": "31d"}},
            "b": {"limits": {"available": True, "retention_period": "31d", "retention_stream": [
                {"selector": '{service="audit"}', "period": "17w1d"}]}},
            "c": {"limits": {"available": True, "retention_period": "180d"}},
            "d": {"limits": {"available": False}},
        })
        self.assertEqual(views["risk_retention_stream"], [
            {" Stack": "b", "Scope": "stream rule", "Period days": 120, "Priority": 0,
             "Selector": '{service="audit"}'},
            {" Stack": "c", "Scope": "tenant default", "Period days": 180, "Priority": None,
             "Selector": None},
        ])

    def test_tied_tenant_defaults_have_no_mode_and_are_all_listed(self):
        _metrics, views = build({
            "alpha": {"limits": {"available": True, "retention_period": "31d"}},
            "beta": {"limits": {"available": True, "retention_period": "90d"}},
        })
        self.assertEqual(
            sorted((row[" Stack"], row["Period days"]) for row in views["risk_retention_stream"]),
            [("alpha", 31), ("beta", 90)],
        )

class RetentionPolicyStreamPresenceTest(unittest.TestCase):
    """Below the minimum, observed streams separate a real gap from a selector with nothing to keep."""

    POLICY = [{"selector": '{kind="auditing"}', "minimum_period": "120d"}]

    @staticmethod
    def record(presence):
        record = {"limits": {"available": True, "retention_period": "31d", "retention_stream": []}}
        if presence is not None:
            record["stream_presence"] = {'{kind="auditing"}': presence}
        return record

    def test_absent_streams_are_reported_apart_from_gaps(self):
        metrics, views = build({
            "alpha": self.record({"available": True, "streams": 0}),
            "beta": self.record({"available": True, "streams": 2}),
        }, policy=self.POLICY, presence=None)
        status = {row[" Stack"]: (row["Status"], row["Streams (7d)"])
                  for row in views["risk_retention_policy_status"]}
        self.assertEqual(status, {"alpha": ("no matching streams", 0), "beta": ("below policy", 2)})
        self.assertEqual([row[" Stack"] for row in views["risk_retention_policy_gaps"]], ["beta"])
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 1.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_no_stream_stacks"], 1.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_compliant_stacks"], 0.0)

    def test_unknown_presence_stays_a_gap_rather_than_hiding_one(self):
        for presence in (None, {"available": False, "state": "http_error"},
                         {"available": True, "streams": -1}, {"available": True, "streams": True}):
            with self.subTest(presence=presence):
                metrics, views = build({"alpha": self.record(presence)}, policy=self.POLICY,
                                       presence=None)
                row = views["risk_retention_policy_status"][0]
                self.assertEqual((row["Status"], row["Streams (7d)"]),
                                 ("below policy, streams unknown", None))
                self.assertEqual(views["risk_retention_policy_gaps"][0]["Streams (7d)"], None)
                values = {name: value for name, _labels, value in metrics}
                self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 1.0)
                self.assertEqual(values["gcinsight_risk_retention_policy_no_stream_stacks"], 0.0)

    def test_presence_never_changes_a_compliant_or_unreadable_result(self):
        record = self.record({"available": True, "streams": 0})
        record["limits"]["retention_period"] = "180d"
        _metrics, views = build({
            "alpha": record,
            "beta": {"limits": {"available": False},
                     "stream_presence": {'{kind="auditing"}': {"available": True, "streams": 0}}},
        }, policy=self.POLICY, presence=None)
        status = {row[" Stack"]: row["Status"] for row in views["risk_retention_policy_status"]}
        self.assertEqual(status, {"alpha": "compliant", "beta": "unreadable"})

    def test_a_real_gap_on_another_selector_is_not_also_counted_as_no_streams(self):
        policy = self.POLICY + [{"selector": '{service="api"}', "minimum_period": "60d"}]
        record = self.record(None)
        record["stream_presence"] = {'{kind="auditing"}': {"available": True, "streams": 0},
                                     '{service="api"}': {"available": True, "streams": 3}}
        metrics, _views = build({"alpha": record}, policy=policy, presence=None)
        values = {name: value for name, _labels, value in metrics}
        self.assertEqual(values["gcinsight_risk_retention_policy_gap_stacks"], 1.0)
        self.assertEqual(values["gcinsight_risk_retention_policy_no_stream_stacks"], 0.0)


if __name__ == "__main__":
    unittest.main()
