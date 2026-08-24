"""Pillar E rendering contract for the stack-local alert-routing inventory."""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import risk


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
