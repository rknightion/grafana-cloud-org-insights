"""Public offline builds must not promote metric spelling to a billable-unit contract."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class RawProductUnitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        env = {**os.environ, "GCINSIGHT_VIEWS_DIR": str(ROOT / "testdata" / "views"),
               "GCINSIGHT_S3_BUCKET": "synthetic-raw-units"}
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "dashboards.py"),
             "--out", cls.directory.name, "--ds-uid", "infinity-uid"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.artifacts = {p.stem.removeprefix(env.get("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight") + "-"):
                         json.loads(p.read_text()) for p in Path(cls.directory.name).glob("*.json")}

    def panel(self, dashboard, key):
        return self.artifacts[dashboard]["spec"]["elements"][key]["spec"]

    def queries(self, dashboard, key):
        return [q["spec"]["query"]["spec"]
                for q in self.panel(dashboard, key)["data"]["spec"]["queries"]]

    def assert_raw(self, dashboard, key):
        panel = self.panel(dashboard, key)
        self.assertIn("raw", panel["title"].lower())
        self.assertIn("not normalised", panel["title"].lower())
        for uncertainty in ("unit", "period", "population", "overlap", "unknown", "not zero"):
            self.assertIn(uncertainty, panel["description"].lower())
        self.assertEqual(panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"], "short")

    def test_host_hour_spelling_does_not_assign_hours_or_a_billing_period(self):
        # Counterexample: the exact same name can report a windowless/overlapping vendor quantity.
        # An h formatter or a current-accounting-period assertion would still misrepresent it.
        for key, metric in {
            "n_infra_host_hours": "grafanacloud_org_infra_o11y_billable_host_hours",
            "n_infra_container_hours": "grafanacloud_org_infra_o11y_billable_container_hours",
            "n_db_host_hours": "grafanacloud_org_db_o11y_billable_host_hours",
            "n_fe_sessions": "grafanacloud_org_fe_o11y_billable_sessions",
        }.items():
            with self.subTest(panel=key):
                self.assertEqual(self.panel("usage", key)["vizConfig"]["spec"]
                                 ["fieldConfig"]["defaults"]["unit"], "short")
                self.assert_raw("usage", key)
                self.assertEqual([q["expr"] for q in self.queries("usage", key)], [f"sum({metric})"])
                self.assertNotIn("current accounting period", self.panel("usage", key)["description"])

    def test_overlapping_service_and_host_generations_remain_separate_raw_observations(self):
        # Identical pod/host headlines now live on Coverage; Usage retains static canonical links.
        for key in ("n_hosts", "n_pods"):
            self.assertNotIn(key, self.artifacts["usage"]["spec"]["elements"])
            self.assertTrue(any(f"viewPanel={self.panel('coverage', key)['id']}" in link["url"]
                                for link in self.panel("usage", "_canonical_workload")["links"]))
        for name, keys in {"usage": ("b_app_hosts", "b_asset_counts",
                                     "b_observed_objects", "b_integration_hosts"),
                           "coverage": ("n_hosts", "n_pods", "n_containers", "t_live_assets")}.items():
            for key in keys:
                with self.subTest(dashboard=name, panel=key):
                    self.assert_raw(name, key)
                    self.assertNotIn("one series per host", self.panel(name, key)["description"])
        self.assertEqual([q["expr"] for q in self.queries("usage", "b_app_hosts")], [
            "sum(grafanacloud_instance_app_o11y_host_count)",
            "sum(grafanacloud_instance_app_o11y_host_v2_count)",
            "sum(grafanacloud_instance_app_o11y_host_v3_count)"])

    def test_product_money_divided_by_unqualified_quantity_is_not_a_unit_price(self):
        # Even equal numbers do not prove matched units, periods or populations. Require raw inputs,
        # not a disclaimer attached to an executed USD/service or USD/host-hour division.
        pairs = {
            "n_spend_app_service": ("grafanacloud_org_app_o11y_overage",
                                     "grafanacloud_app_observability_service_entity_count"),
            "n_spend_infra_host_hour": ("grafanacloud_org_infra_o11y_host_overage",
                                         "grafanacloud_org_infra_o11y_billable_host_hours"),
            "n_spend_infra_container_hour": ("grafanacloud_org_infra_o11y_container_overage",
                                              "grafanacloud_org_infra_o11y_billable_container_hours"),
        }
        for key, metrics in pairs.items():
            with self.subTest(panel=key):
                self.assertEqual([q["expr"] for q in self.queries("coverage", key)],
                                 [f"sum({metric})" for metric in metrics])
                self.assert_raw("coverage", key)
                for query in self.queries("coverage", key):
                    self.assertIn("raw", query["legendFormat"].lower())
                self.assertIn("unit price withheld", self.panel("coverage", key)["description"].lower())

    def test_existing_raw_allowance_pairs_are_not_normalised_or_converted(self):
        pairs = {
            "app": ("app_o11y_billable_host_hours", "app_o11y_included_host_hours"),
            "db": ("db_o11y_billable_host_hours", "db_o11y_included_host_hours"),
            "infra_hosts": ("infra_o11y_billable_host_hours", "infra_o11y_included_host_hours"),
            "infra_containers": ("infra_o11y_billable_container_hours", "infra_o11y_included_container_hours"),
            "frontend": ("fe_o11y_billable_sessions", "fe_o11y_included_sessions"),
        }
        for family, suffixes in pairs.items():
            key = f"context_allow_{family}"
            with self.subTest(panel=key):
                self.assert_raw("cost", key)
                queries = self.queries("cost", key)
                self.assertEqual([query["expr"] for query in queries],
                                 [f"grafanacloud_org_{suffix}" for suffix in suffixes])
                self.assertEqual([query["legendFormat"] for query in queries], ["Raw usage", "Raw included"])
                self.assertIn("no subtraction or utilisation ratio", self.panel("cost", key)["description"])
                transforms = self.panel("cost", key)["data"]["spec"]["transformations"]
                self.assertEqual(transforms[0]["spec"]["options"],
                                 {"mode": "reduceFields", "reducers": ["lastNotNull"]})
                self.assertEqual(transforms[1]["spec"]["id"], "labelsToFields")

    def test_unknown_currency_is_not_rendered_as_money_or_a_known_period(self):
        observed = []
        for dashboard in ("commercial", "ai", "coverage"):
            for key, element in self.artifacts[dashboard]["spec"]["elements"].items():
                panel = element["spec"]
                if "Currency, exact billing period" not in panel.get("description", ""):
                    continue
                observed.append((dashboard, key))
                # Includes table field overrides, column renames and display names, not queries.
                presentation = json.dumps({
                    **{k: panel[k] for k in ("title", "description", "vizConfig")},
                    "transformations": panel["data"]["spec"].get("transformations", []),
                })
                with self.subTest(dashboard=dashboard, panel=key):
                    self.assertNotRegex(presentation, r"(?i)currency[A-Z]{3}|USD|\$/|monthly|/month")
                    self.assertNotRegex(panel["title"], r"(?i)run rate|price")
        self.assertEqual(len(observed), 15)

    def test_surrounding_banners_do_not_assign_billing_units_to_raw_observations(self):
        # These are the actual dashboard header and rendered How-to-read markdown, not panel
        # defaults. A neutral formatter cannot undo a header calling an unknown period monthly.
        for dashboard in ("commercial", "ai", "coverage"):
            spec = self.artifacts[dashboard]["spec"]
            banner = self.panel(dashboard, "_banner")["vizConfig"]["spec"]["options"]["content"]
            for surface, text in (("header", spec["description"]), ("banner", banner)):
                with self.subTest(dashboard=dashboard, surface=surface):
                    for word in ("raw", "not normalised", "currency", "period", "population",
                                 "overlap", "unknown"):
                        self.assertIn(word, text.lower())
                    self.assertNotIn("currency and period are derived", text.lower())
                    self.assertNotIn("safer to quote", text.lower())
        ai_banner = self.panel("ai", "_banner")["vizConfig"]["spec"]["options"]["content"]
        self.assertNotIn("Commercial tabs are live", ai_banner)
        # Known token windows remain qualified independently; this is not a blanket ban on periods.
        self.assertIn("monthly", self.panel("ai", "n_tokens")["description"].lower())
        self.assertIn("month-to-date", self.panel("ai", "tbl_people")["title"].lower())

    def test_reported_billing_navigation_preserves_raw_source_qualification(self):
        spec = self.artifacts["commercial"]["spec"]
        self.assertEqual([tab["spec"]["title"] for tab in spec["layout"]["spec"]["tabs"]],
                         ["Commitment", "Reported billing", "Consumption observations", "How to read this"])
        # Qualification must be visible on the tab's headline panel as well as in the header.
        for text in (spec["description"], self.panel("commercial", "n_runrate")["description"]):
            for phrase in ("Reported billing", "raw source observations", "not a measured normalised rate"):
                self.assertIn(phrase, text)
        ai_commercial = next(tab["spec"] for tab in self.artifacts["ai"]["spec"]["layout"]["spec"]["tabs"]
                             if tab["spec"]["title"] == "Commercial")
        row_title = ai_commercial["layout"]["spec"]["rows"][0]["spec"]["title"].lower()
        self.assertIn("raw", row_title)
        self.assertIn("not normalised", row_title)
        self.assertNotIn("run rate", row_title)

    def test_diagnostic_copy_does_not_reintroduce_an_unqualified_rate(self):
        # Only panels using the unqualified overage/credit model; separately qualified rate-card
        # pricing, contract timestamps, token windows and OnCall's seven days are not this scope.
        scope = {"coverage": ("n_spend_ack", "n_spend_service", "n_spend_billed_user", "n_spend_viewer"),
                 "commercial": ("n_consumed_share", "t_metrics_share", "t_burn", "n_months_metric")}
        for dashboard, keys in scope.items():
            for key in keys:
                with self.subTest(dashboard=dashboard, panel=key):
                    panel = self.panel(dashboard, key)
                    text = (panel["title"] + " " + panel["description"]).lower()
                    self.assertNotIn("run-rate illustration", text)
                    self.assertNotIn("safest figure", text)
                    self.assertNotIn("needs no unit", text)
                    self.assertNotIn("present rate of spend", text)
                    self.assertIn("raw", text)
                    self.assertIn("not normalised", text)
                    for word in ("currency", "period", "population", "overlap", "unknown"):
                        self.assertIn(word, panel["description"].lower())
        forecast = self.panel("commercial", "n_months_metric")
        self.assertNotRegex(forecast["title"], r"(?i)months|run rate")
        self.assertIn("unit", forecast["description"].lower())
        # Timestamp-derived contract timing is still a separate known-unit model, not overage.
        contract = self.panel("commercial", "n_months_contract")
        self.assertIn("Months remaining on the contract", contract["title"])
        self.assertNotIn("present rate of spend", contract["description"])

    def test_ai_money_keeps_its_existing_derived_model_not_a_vendor_currency_contract(self):
        for key in ("n_assistant_overage", "n_token_overage", "tbl_stack_assistant_cost"):
            with self.subTest(panel=key):
                panel = self.panel("ai", key)
                for wording in ("raw", "derived", "not normalised"):
                    self.assertIn(wording, panel["title"].lower())
                for uncertainty in ("currency", "period", "population", "overlap", "unknown"):
                    self.assertIn(uncertainty, panel["description"].lower())

    def test_existing_commercial_model_is_preserved_but_not_a_declared_contract(self):
        for key in ("n_runrate", "n_reconcile", "b_runrate", "t_runrate"):
            panel = self.panel("commercial", key)
            self.assertIn("derived", panel["title"].lower())
            self.assertIn("not normalised", panel["title"].lower())
            for uncertainty in ("raw", "currency", "period", "unknown", "overlap"):
                self.assertIn(uncertainty, panel["description"].lower())
            self.assertEqual(panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"],
                             "short")
        self.assertEqual([q["expr"] for q in self.queries("commercial", "n_runrate")],
                         ["sum(grafanacloud_org_total_overage)"])
        # Independent collector identities and existing diagnostics are not product host units.
        service = self.panel("coverage", "n_services")
        self.assertIn("canonical service identities", service["description"])
        self.assertNotIn("raw", service["title"].lower())
        for key in ("n_spend_billed_user", "n_spend_service", "n_spend_viewer", "n_spend_ack"):
            self.assertIn("derived", self.panel("coverage", key)["title"].lower())
            self.assertIn("not normalised", self.panel("coverage", key)["title"].lower())
            self.assertIn("unknown", self.panel("coverage", key)["description"].lower())
