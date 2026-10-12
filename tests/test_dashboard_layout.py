"""D-LAY23: public CLI artifacts, not a second assembly or source-text census."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from collector.dashboards import build
from collector.pillars import findings
from tests.test_dashboard_coverage import declared_schemas, placed

ROOT = Path(__file__).resolve().parents[1]
ORDERS = {
    "estate": "Overview|Findings|Leakage|Change|Scan health|Data freshness|Composition|All stacks|How to read this",
    "cost": "Overview|Findings|Savings available|Levers|Adaptive Logs|Biggest stacks|Signals|DPM reconciliation|Vendor attribution|Included allowance context|Seat context|How to read this",
    "usage": "Overview|Findings|Engagement|Unread telemetry|Adoption|Protocol adoption|Workload|Configured inventory|Bounded producers and configured alerting|How to read this",
    "maturity": "Overview|Leaderboard|Explain a score|Not scored|By dimension|Who owns what|How it is scored|How to read this",
    "risk": "Overview|Findings|Data loss|Alerting health|Alert routing|Delete protection|Access|Credentials|Collectors|Public dashboards|Logs retention|Label cardinality|Label privacy risk|Per stack|How to read this",
    "value": "Overview|Savings|Capability gaps|Adoption|Test and probe adoption|Capability flags|Benchmarks|How to read this",
    "operations": "Alert flow|Logs retention|Backend health|Response time|Ownership|Engagement|How to read this",
    "commercial": "Commitment|Run rate|Consumption vs term|How to read this",
    "ai": "Overview|Findings|Enablement and configuration|Assistant use per stack|Adoption by stack|Token consumption|Commercial|Human vs machine|People and identities|Collection coverage|Feature activity|How to read this",
    "dashboards": "Adoption|What people open|Query behaviour|Public dashboards|Grafana surfaces|Coverage|How to read this",
    "coverage": "Observed estate|Adoption opportunities|Coverage depth|Named service register|Technology and cluster registers|Adjacent datasource estate|Adaptive Traces|Synthetic inventory|SLO inventory|Outcome value|Unit economics|Summary|Classification evidence|How to read this",
    "labelling": "Estate overview|Per-signal rules|Stack scorecard|Cross-signal consistency|Label register|Not evaluated and coverage|How to read this",
}
# view, intended owner element, owner tab, finding evidence element (if any).
REGISTERS = {
    "estate": [("estate_leftovers_idle", "idle", "Leakage", "_fd_idle"),
               ("estate_leftovers_billing", "billing", "Leakage", "_fd_billing"),
               ("estate_drift", "drift", "Composition", "_fd_drift")],
    "cost": [("cost_adaptive_headroom", "headroom", "Levers", "_fd_headroom"),
             ("cost_cardinality_outliers", "cardinality", "Levers", "_fd_cardinality")],
    "usage": [("usage_dormant_stacks", "dormant", "Engagement", "_fd_dormant")],
    "risk": [("risk_admin_sprawl", "admins", "Access", "_fd_admins"),
             ("risk_delete_protection", "noprot", "Delete protection", "_fd_noprot"),
             ("risk_fleet_dead", "fleet", "Collectors", "_fd_fleet"),
             ("risk_plugin_drift", "plugindrift", "Access", "_fd_plugins")],
    "ai": [("ai_enablement_gap", "tbl_ai_gap", "Enablement and configuration", "_fd_ai_gap"),
           ("ai_token_outliers", "tbl_ai_outliers", "Enablement and configuration", "_fd_ai_tokens"),
           ("ai_mcp_auth_failed", "tbl_ai_mcp_failed", "Enablement and configuration", "_fd_ai_mcp"),
           ("ai_config_disabled", "tbl_ai_disabled", "Enablement and configuration", "_fd_ai_off")],
    "maturity": [("maturity", "board", "Leaderboard", None)],
    "labelling": [("labelling_stack_summary", "scorecard", "Stack scorecard", None)],
}
OPTIONAL = ("library_panels_inventory", "playlists_inventory", "reports_inventory", "pdc_networks",
            "cloud_accounts", "ml_jobs", "faro_apps", "irm_integrations", "irm_alert_groups")


def tabs(document):
    return {t["spec"]["title"]: t for t in document["spec"]["layout"]["spec"]["tabs"]}


def visible(panel):
    data = panel["spec"]["data"]["spec"]
    hidden, aliases = {}, {}
    for transform in data["transformations"]:
        if transform["spec"]["id"] == "organize":
            hidden.update(transform["spec"]["options"]["excludeByName"])
            aliases.update(transform["spec"]["options"]["renameByName"])
    return {(column["selector"], aliases.get(column["text"], column["text"]))
            for query in data["queries"]
            for column in query["spec"]["query"]["spec"].get("columns", [])
            if not hidden.get(column["text"])}


class DashboardLayoutContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.documents = {}
        for prefix in ("gcinsight", "consumer"):
            output = Path(cls.directory.name) / prefix
            result = subprocess.run(
                [sys.executable, str(ROOT / "bin/dashboards.py"), "--out", str(output),
                 "--ds-uid", "infinity-uid"], cwd=ROOT, capture_output=True, text=True, timeout=60,
                env={**os.environ, "GCINSIGHT_VIEWS_DIR": str(ROOT / "testdata/views"),
                     "GCINSIGHT_S3_BUCKET": "synthetic-layout", "GCINSIGHT_DASHBOARD_UID_PREFIX": prefix})
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.documents[prefix] = {name: json.loads((output / f"{prefix}-{name}.json").read_text())
                                     for name in ORDERS}

    def test_all_twelve_actual_cli_layouts_follow_the_approved_order(self):
        for name, expected in ORDERS.items():
            with self.subTest(dashboard=name):
                self.assertEqual(list(tabs(self.documents["gcinsight"][name])), expected.split("|"))

    def test_register_source_and_qualified_display_fields_survive_on_the_owner(self):
        schemas = declared_schemas()
        for name, entries in REGISTERS.items():
            document = self.documents["gcinsight"][name]
            for view, owner, tab, _evidence in entries:
                with self.subTest(dashboard=name, owner=owner):
                    payload = json.loads((ROOT / "testdata/views" / f"{view}.json").read_text())
                    fields = {key for row in payload["rows"] for key in row} | {key for key, _ in schemas.get(view, ())}
                    aliases = ({"Machine share of categorised":
                                "Non-web share of categorised (actor identity unproven)"}
                               if view in ("ai_enablement_gap", "ai_token_outliers") else {})
                    expected = {(key, aliases.get(key.strip(), key.strip())) for key in fields}
                    self.assertEqual(visible(document["spec"]["elements"][owner]), expected)
                    self.assertIn(owner, list(placed(tabs(document)[tab])))

    def test_findings_are_evidence_only_with_static_canonical_panel_links(self):
        for prefix, documents in self.documents.items():
            for name, entries in REGISTERS.items():
                document = documents[name]
                for view, owner, _tab, evidence in entries:
                    if not evidence:
                        continue
                    with self.subTest(prefix=prefix, owner=owner):
                        panel = document["spec"]["elements"][evidence]["spec"]
                        spec = next(spec for spec in findings.SPECS if spec.view == view)
                        columns = {selector.strip() for selector, _display in visible({"spec": panel})}
                        expected = {"Stack", *spec.fields} if spec.fields else {selector.strip() for selector, _ in
                                   visible(document["spec"]["elements"][owner])}
                        self.assertEqual(columns, expected)
                        link = panel["links"][0]
                        parsed = urlsplit(link["url"])
                        self.assertEqual(parsed.path, f"/d/{prefix}-{name}")
                        self.assertEqual(parse_qs(parsed.query)["viewPanel"],
                                         [str(document["spec"]["elements"][owner]["spec"]["id"])])
                        self.assertIn("${__url_time_range}", link["url"])
                        self.assertIn("${stack:queryparam}", link["url"])
                        self.assertNotIn("__data", link["url"])

    def test_duplicate_workload_and_outcome_copies_become_owner_link_rows(self):
        for prefix, documents in self.documents.items():
            usage = documents["usage"]
            coverage = documents["coverage"]
            for key in ("n_pods", "n_hosts", "n_assistant", "n_aitokens"):
                self.assertNotIn(key, usage["spec"]["elements"])
            for key in ("n_value_acknowledged", "n_value_engagement", "n_value_tail",
                        "n_value_unowned_team", "n_value_unowned_service", "b_oncall"):
                self.assertNotIn(key, coverage["spec"]["elements"])
            outcome = list(placed(tabs(coverage)["Outcome value"]))
            self.assertEqual(set(outcome), {"outcome_scope", "n_value_groups", "n_value_mtta",
                                           "n_value_mttr", "_canonical_operations_outcome"})
            for name, key, target_name, target_key in (
                ("usage", "_canonical_workload", "coverage", "n_pods"),
                ("usage", "_canonical_ai", "ai", "n_tokens"),
                ("coverage", "_canonical_operations_outcome", "operations", "n_engaged"),
                ("coverage", "_canonical_operations_ownership", "operations", "b_service_owner")):
                panel = documents[name]["spec"]["elements"][key]["spec"]
                self.assertEqual(panel["data"]["spec"]["queries"], [])
                self.assertTrue(any(urlsplit(link["url"]).path == f"/d/{prefix}-{target_name}" and
                                    parse_qs(urlsplit(link["url"]).query)["viewPanel"] ==
                                    [str(documents[target_name]["spec"]["elements"][target_key]["spec"]["id"])]
                                    for link in panel["links"]))
            for key in ("tbl_datasource_provisioned", "tbl_datasource_queried"):
                self.assertIn("comparison copy", coverage["spec"]["elements"][key]["spec"]["title"])
                self.assertIn("canonical:", coverage["spec"]["elements"][key]["spec"]["links"][0]["title"])

    def test_configured_inventory_retains_every_current_reader_with_its_age(self):
        document = self.documents["gcinsight"]["usage"]
        merged = tabs(document)["Configured inventory"]["spec"]["layout"]
        self.assertEqual(merged["kind"], "RowsLayout")
        rows = merged["spec"]["rows"]
        self.assertEqual(rows[0]["spec"]["title"], "Configured footprint summary")
        for view in OPTIONAL:
            row = next(row for row in rows if view in list(placed(row)))
            self.assertIn(f"_age_{view}", list(placed(row)))
        self.assertIn("_optional_view_state", list(placed(tabs(document)["How to read this"])))
        for view in OPTIONAL:
            self.assertIn(f"_meta_{view}", list(placed(tabs(document)["How to read this"])))

    def test_declared_predicates_are_applied_without_changing_source_queries(self):
        documents = self.documents["gcinsight"]
        cardinality = documents["cost"]["spec"]["elements"]["_fd_cardinality"]["spec"]
        data = cardinality["data"]["spec"]
        self.assertEqual(data["queries"][0]["spec"]["query"]["spec"]["filterExpression"], build.STACK_FILTER)
        self.assertEqual(data["transformations"][0]["spec"]["options"], {
            "type": "include", "match": "all", "filters": [{"fieldName": "Worst label values",
            "config": {"id": "greaterOrEqual", "options": {"value": 5000.0}}}]})
        maturity = documents["maturity"]["spec"]["elements"]["unscored_detail"]["spec"]
        self.assertEqual(maturity["data"]["spec"]["transformations"][0]["spec"]["options"]["filters"], [
            {"fieldName": "Unscored reason", "config": {"id": "isNotNull", "options": {}}},
            {"fieldName": "Unscored reason", "config": {"id": "notEqual", "options": {"value": ""}}}])

    def test_conditional_dpm_tab_uses_the_same_final_assembly_order(self):
        from unittest import mock
        from bin import dashboards
        from collector import ratecard
        card = ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm\n"
                              "metrics_series,7,1000,series,0,GBP,month,dpm_aware,4\n")
        with mock.patch.object(build, "VIEWS_DIR", str(ROOT / "testdata/views")), mock.patch.object(build, "BUCKET", "synthetic"):
            document = dashboards.assemble("cost", "infinity-uid", rate_card=card)[1]
        expected = ORDERS["cost"].split("|")
        expected.insert(expected.index("DPM reconciliation"), "DPM-aware savings")
        self.assertEqual(list(tabs(document)), expected)

    def test_sort_only_roots_keep_source_lineage_but_projections_do_not(self):
        from tests.test_dashboard_coverage import presentation_root
        document = self.documents["gcinsight"]["labelling"]
        for key in ("overview", "rules_metrics", "rules_logs", "rules_traces", "rules_profiles"):
            query = document["spec"]["elements"][key]["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
            self.assertEqual(presentation_root(query["root_selector"]), "rows")
        for root in ('rows[Result="fail"]', 'rows^(>Score).{"Stack": ` Stack`}',
                     'meta^(>Score)', 'rows^(>Score).Score'):
            self.assertNotEqual(presentation_root(root), "rows")

    def test_worst_first_and_approved_dense_row_groups(self):
        documents = self.documents["gcinsight"]
        for name, tab, first in (("estate", "Leakage", "billing"), ("estate", "Scan health", "b_failed"),
                                 ("maturity", "Leaderboard", "b_bottom"),
                                 ("operations", "Alert flow", "n_state_history_failures")):
            self.assertEqual(next(placed(tabs(documents[name])[tab])), first)
        commitment = tabs(documents["commercial"])["Commitment"]["spec"]["layout"]["spec"]["rows"]
        self.assertEqual(list(placed(commitment[0])), ["n_consumed_share", "n_term_elapsed"])
        benchmarks = tabs(documents["value"])["Benchmarks"]["spec"]["layout"]["spec"]["rows"]
        trends = [row for row in benchmarks if any(key.startswith("t_bench_") for key in placed(row))]
        self.assertEqual(len(trends), 1)
        self.assertEqual(len(list(placed(trends[0]))), 7)
        self.assertEqual(trends[0]["spec"]["layout"]["spec"]["maxColumnCount"], 2)


if __name__ == "__main__":
    unittest.main()
