"""Endpoint queues and historical score candidates on public assembled dashboards.

The offline contract checks complement the retained local Prometheus + @grafana/data
runtime witness. They do not claim a browser, fresh inventory or vendor completeness.
"""
from pathlib import Path
import unittest
from unittest import mock

from bin import dashboards
from collector.dashboards import build
from collector.pillars.maturity import TIERS


RISK_QUEUES = ("b_discard", "b_spans_late", "b_trace", "b_trace_discard",
               "b_metadata_discard", "b_notif_by_stack_integration", "b_deadrules", "b_notif")


def assembled_fixture():
    """Return the actual public publication artifacts, including assembly qualifiers."""
    views = Path(__file__).resolve().parent.parent / "testdata" / "views"
    with (mock.patch.object(build, "VIEWS_DIR", str(views)),
          mock.patch.object(build, "BUCKET", "synthetic")):
        return {name: dashboards.assemble(name, "infinity-uid")[1]
                for name in ("cost", "risk", "maturity", "ai")}


def changing_membership_samples():
    """OpenMetrics fixture used by the local Prometheus + Grafana transform witness.

    Twenty old entrants (including the old worst) disappear before the endpoint's
    24h window; a hundred reporting members arrive. Names deliberately put the
    current worst LAST alphabetically, and both top-N unions exceed their bound.
    Maturity samples remain history: they do not assert an authoritative roster.
    """
    start, end = 1700000000, 1700604800
    metrics = (
        "grafanacloud_instance_recommendations_estimated_savings_series",
        "grafanacloud_traces_instance_percentage_complete_traces_flushed",
        "grafanacloud_assistant_active_users", "grafanacloud_grafana_instance_info",
        "gcinsight_maturity_score",
    )
    lines = [f"# TYPE {name} gauge" for name in metrics]
    for index in range(120):
        historical = index < 20
        name = ("departed" if index == 0 else f"old-{index}" if historical
                else "z-worst" if index == 20 else f"current-{index-20:03}")
        times = (range(start, start + 7200, 3600) if historical
                 else range(end - 7200, end + 1, 3600))
        completeness = 0.01 if historical else 0.05 if index == 20 else 0.5 + (index-21)/1000
        for stamp in times:
            labels = f'stack_id="{index}",id="{index}"'
            lines.extend([
                f'{metrics[0]}{{{labels}}} {1000-index} {stamp}',
                f'{metrics[1]}{{{labels}}} {completeness} {stamp}',
                f'{metrics[2]}{{{labels}}} {1000-index} {stamp}',
                f'{metrics[3]}{{stack_id="{index}",slug="{name}"}} 1 {stamp}',
                f'{metrics[4]}{{stack="{name}",version="2"}} {10 if historical else (index-20)%100} {stamp}',
            ])
    # No score series is manufactured for an unscored stack.
    lines.append("# EOF")
    return start, end, "\n".join(lines) + "\n"


class RankingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = assembled_fixture()

    def panel(self, dashboard, key):
        return self.documents[dashboard]["spec"]["elements"][key]["spec"]

    def test_windowed_fault_queues_evaluate_at_endpoint_not_range_union(self):
        for key in RISK_QUEUES:
            with self.subTest(panel=key):
                panel = self.panel("risk", key)
                query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                self.assertTrue(query["instant"])
                self.assertFalse(query["range"])
                self.assertIn("[24h]", query["expr"])
                self.assertIn("range endpoint", panel["title"])
                self.assertIn("not current inventory", panel["description"])
                transforms = panel["data"]["spec"]["transformations"]
                self.assertEqual(transforms[-1]["spec"]["options"], {"limitField": 15})
                self.assertEqual(transforms[1]["spec"]["options"]["sort"],
                    [{"field": "Last *", "desc": key != "b_trace"}])

    def test_live_long_rankings_have_endpoint_values_and_bounded_display(self):
        for key in ("tbl_stack_users", "tbl_stack_tokens", "tbl_people", "tbl_services"):
            with self.subTest(panel=key):
                panel = self.panel("ai", key)
                query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                self.assertTrue(query["instant"])
                self.assertFalse(query["range"])
                self.assertIn("range endpoint", panel["title"])
                self.assertEqual(panel["data"]["spec"]["transformations"][-1]["spec"]["options"],
                                 {"limitField": 100})

    def test_cost_retains_history_but_endpoint_does_not_reduce_old_values(self):
        history = self.panel("cost", "b_savings")
        endpoint = self.panel("cost", "b_savings_endpoint")
        self.assertTrue(history["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["range"])
        self.assertIn("UNION", history["description"])
        self.assertTrue(endpoint["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["instant"])

    def test_historical_rankings_and_trends_explain_changing_membership(self):
        for dashboard, key in (("risk", "t_coll_top"), ("cost", "t_top")):
            panel = self.panel(dashboard, key)
            self.assertIn("changing top-N membership", panel["title"])
            self.assertIn("not a current work queue", panel["description"])
            self.assertTrue(panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["range"])
        panel = self.panel("cost", "b_al_top")
        self.assertIn("historical top-N entrants", panel["title"])
        self.assertIn("not current membership", panel["description"])

    def test_maturity_uses_absolute_existing_tier_boundaries_and_missing_mapping(self):
        self.assertEqual(TIERS, (("leading", 75.0), ("solid", 50.0),
                                ("lagging", 25.0), ("dormant", 0.0)))
        for key in ("b_top", "b_bottom", "b_dims"):
            with self.subTest(panel=key):
                panel = self.panel("maturity", key)
                defaults = panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]
                self.assertEqual(defaults["color"], {"mode": "thresholds"})
                self.assertEqual(defaults["thresholds"], {"mode": "absolute", "steps": [
                    {"value": None, "color": "red"}, {"value": 25, "color": "orange"},
                    {"value": 50, "color": "yellow"}, {"value": 75, "color": "green"}]})
                self.assertEqual(defaults["mappings"], [{"type": "special", "options": {
                    "match": "null+nan", "result": {"text": "Not scored", "color": "gray"}}}])
        for key in ("b_top", "b_bottom"):
            panel = self.panel("maturity", key)
            self.assertIn("historical candidates", panel["title"])
            self.assertIn("not current membership", panel["description"])
            query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
            self.assertIn("last_over_time", query["expr"])
            self.assertIn("[$__range] @ end()", query["expr"])
            self.assertTrue(query["range"], "periodic samples must remain range-safe")
            self.assertEqual(panel["data"]["spec"]["transformations"][-1]["spec"]["options"],
                             {"limitField": 15})


if __name__ == "__main__":
    unittest.main()
