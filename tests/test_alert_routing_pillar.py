"""Pillar E rendering contract for the stack-local alert-routing inventory."""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import compose, risk
from collector.sources import alert_routing
from tests.test_alert_routing import FakeClient, STACK, contact, rule


class AlertRoutingPillarTest(unittest.TestCase):
    def setUp(self):
        self.stacks = [{"slug": "alpha", "status": "active"}]
        self.coverage = Coverage(tier="t2", total=1)
        self.coverage.record_ok("alpha")
        self.payload = {
            "alpha": {
                "available": True,
                "state": "ok",
                "completeness": "api_has_no_total",
                "rules_total": 12,
                "rules_active": 10,
                "rules_direct_receiver": 4,
                "rules_active_inherited": 6,
                "rules_active_missing_receiver": 1,
                "rules_unverified_builtin": 1,
                "contact_point_integrations": 3,
                "findings_total": 8,
                "findings_retained": 2,
                "findings_truncated": False,
                "findings": [
                    {
                        "rule_uid": "missing",
                        "title": "Missing receiver",
                        "folder_uid": "f1",
                        "rule_group": "g1",
                        "paused": False,
                        "routing": "direct",
                        "receiver": "gone",
                        "receiver_state": "missing",
                    },
                    {
                        "rule_uid": "inherited",
                        "title": "Inherited routing",
                        "folder_uid": "f1",
                        "rule_group": "g1",
                        "paused": False,
                        "routing": "inherited",
                        "receiver": None,
                        "receiver_state": "not_applicable",
                    },
                ],
            }
        }

    def test_counts_have_a_named_drill_down(self):
        metrics, views = risk.build(
            self.stacks, self.coverage, alert_routing=self.payload,
        )
        by_name = {name: value for name, _labels, value in metrics}
        self.assertEqual(by_name["gcinsight_risk_alert_rules_total"], 12)
        self.assertEqual(by_name["gcinsight_risk_alert_rules_active_inherited"], 6)
        self.assertEqual(by_name["gcinsight_risk_alert_rules_active_missing_receiver"], 1)
        self.assertEqual(by_name["gcinsight_risk_alert_routing_stacks_measured"], 1)
        self.assertEqual(len(views["risk_alert_routing"]), 1)
        self.assertEqual(len(views["risk_alert_routing_findings"]), 2)
        self.assertEqual(views["risk_alert_routing_findings"][0]["Rule uid"], "missing")

    def test_contact_type_mix_reaches_public_composition_without_new_metrics(self):
        contacts = [contact("platform"), dict(contact("chat"), type="slack")]
        out = alert_routing.probe_stack(
            FakeClient([(200, [rule("inherited")]), (200, contacts)]), STACK, "tok",
        )
        metrics, views, _ = compose.build_all(
            self.stacks, self.coverage, alert_routing={"alpha": out},
        )
        self.assertEqual(
            views["risk_alert_routing"][0]["Contact point type mix"],
            '{"email": 1, "slack": 1}',
        )
        legacy = {key: value for key, value in out.items() if key != "contact_point_type_counts"}
        old_metrics, old_views, _ = compose.build_all(
            self.stacks, self.coverage, alert_routing={"alpha": legacy},
        )
        self.assertEqual(metrics, old_metrics)
        self.assertIsNone(old_views["risk_alert_routing"][0]["Contact point type mix"])
        for counts, expected in (({}, "{}"), (None, None)):
            _, views, _ = compose.build_all(
                self.stacks, self.coverage,
                alert_routing={"alpha": dict(out, contact_point_type_counts=counts)},
            )
            self.assertEqual(views["risk_alert_routing"][0]["Contact point type mix"], expected)

    def test_missing_input_is_absent_not_zero(self):
        metrics, views = risk.build(self.stacks, self.coverage)
        self.assertFalse({name for name, _labels, _value in metrics} & {
            "gcinsight_risk_alert_rules_total",
            "gcinsight_risk_alert_rules_active_inherited",
            "gcinsight_risk_alert_rules_active_missing_receiver",
            "gcinsight_risk_alert_routing_stacks_measured",
        })
        self.assertNotIn("risk_alert_routing", views)
        self.assertNotIn("risk_alert_routing_findings", views)


if __name__ == "__main__":
    unittest.main()
