"""OnCall acknowledgement shares require matched cohorts and producer windows."""

from pathlib import Path
import unittest
from unittest import mock

from bin import dashboards
from collector.dashboards import build


class OnCallEngagementContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        views = Path(__file__).resolve().parent.parent / "testdata" / "views"
        with (mock.patch.object(build, "VIEWS_DIR", str(views)),
              mock.patch.object(build, "BUCKET", "synthetic")):
            cls.artifacts = {name: dashboards.assemble(name, "infinity-uid")[1]
                             for name in ("operations", "coverage")}

    def panel(self, name, key):
        # D-LAY23 consolidates exact copies; inspect the reachable canonical panel, not a vanished copy.
        canonical = {"n_value_engagement": "n_engagement", "n_value_acknowledged": "n_engaged"}
        if name == "coverage" and key in canonical:
            self.assertNotIn(key, self.artifacts[name]["spec"]["elements"])
            target = self.artifacts["operations"]["spec"]["elements"][canonical[key]]["spec"]
            links = self.artifacts[name]["spec"]["elements"]["_canonical_operations_outcome"]["spec"]["links"]
            self.assertTrue(any(f"viewPanel={target['id']}" in link["url"] for link in links))
            return target
        return self.artifacts[name]["spec"]["elements"][key]["spec"]

    def expressions(self, name, key):
        return [q["spec"]["query"]["spec"]["expr"]
                for q in self.panel(name, key)["data"]["spec"]["queries"]]

    def test_unsupported_acknowledgement_shares_are_withheld_not_diagnostic_numbers(self):
        # A disclaimer beside a still-executed numeric ratio does not withhold it.
        for name, keys in {"operations": ("n_engagement", "b_teamengage", "t_engagement"),
                           "coverage": ("n_value_engagement",)}.items():
            for key in keys:
                with self.subTest(dashboard=name, panel=key):
                    panel = self.panel(name, key)
                    self.assertEqual(panel["data"]["spec"]["queries"], [])
                    self.assertEqual(panel["vizConfig"]["group"], "text")
                    self.assertIn("withheld", panel["title"].lower())
                    content = panel["vizConfig"]["spec"]["options"]["content"].lower()
                    for reason in ("seven days", "unspecified horizon", "group cohorts",
                                   "windows", "not zero", "matching stacks"):
                        self.assertIn(reason, content)
                    self.assertNotRegex(content, r"0%|0\.0%|nobody looked")

    def test_group_gauge_and_seven_day_observations_remain_separate_counts(self):
        for name, group, response in (("operations", "n_engaged_denom", "n_engaged"),
                                      ("coverage", "n_value_groups", "n_value_acknowledged")):
            with self.subTest(dashboard=name):
                gauge = self.panel(name, group)
                observation = self.panel(name, response)
                self.assertIn("timing", gauge["title"].lower())
                self.assertIn("unspecified horizon", gauge["description"].lower())
                self.assertIn("cohort", gauge["description"].lower())
                self.assertIn("7d", observation["title"])
                self.assertIn("seven days", observation["description"])
                self.assertEqual(self.expressions(name, response),
                                 ["sum(grafanacloud_oncall_instance_alert_groups_response_time_seconds_count)"])
                self.assertNotIn(dashboards.GROUPS, self.expressions(name, response)[0])
                for panel in (gauge, observation):
                    self.assertEqual(panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"], "short")
                self.assertNotIn(" / ", self.expressions(name, group)[0])

    def test_built_response_bands_are_seven_day_counts_not_group_shares(self):
        panel = self.panel("operations", "b_ackdist")
        self.assertIn("7d", panel["title"])
        self.assertIn("seven days", panel["description"])
        self.assertIn("producer", panel["description"])
        self.assertIn("dashboard range", panel["description"])
        self.assertIn("recorded response observations", panel["description"])
        self.assertEqual(panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"], "short")
        bucket = "grafanacloud_oncall_instance_alert_groups_response_time_seconds_bucket"
        limits = ("60.0", "300.0", "600.0", "3600.0", "+Inf")
        expected = [f'sum({bucket}{{le="{limits[0]}"}})']
        expected += [f'sum({bucket}{{le="{upper}"}}) - sum({bucket}{{le="{lower}"}})'
                     for lower, upper in zip(limits, limits[1:])]
        self.assertEqual(self.expressions("operations", "b_ackdist"), expected)
        legends = [q["spec"]["query"]["spec"]["legendFormat"]
                   for q in panel["data"]["spec"]["queries"]]
        self.assertEqual(legends, ["within 1 min", "1 to 5 min", "5 to 10 min",
                                   "10 min to 1 hour", "over 1 hour"])
