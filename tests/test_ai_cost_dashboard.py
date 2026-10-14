"""Cost queries must deduct shared allowances before aggregating identities or stacks."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from collector.dashboards import ai_cost, build


class AICostDashboardTest(unittest.TestCase):
    def document(self):
        with tempfile.TemporaryDirectory() as directory:
            for view in ("ai_cost_current", "ai_cost_monthly", "ai_cost_stacks"):
                Path(directory, view + ".json").write_text(json.dumps({"rows": []}))
            with mock.patch.object(build, "BUCKET", "synthetic"), \
                    mock.patch.object(build, "VIEWS_DIR", directory):
                return build.dashboard("AI", "", ai_cost.elements("infinity"),
                                       [ai_cost.tab()], variables=ai_cost.variables())

    def queries(self):
        return {key: panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                for key, panel in self.document()["spec"]["elements"].items()
                if panel["spec"]["data"]["spec"]["queries"]}

    def test_shared_allowance_queries_use_org_identity_population(self):
        queries = self.queries()
        excess = queries["ai_cost_personal_excess"]["expr"]
        count = queries["ai_cost_over_allowance"]["expr"]
        self.assertIn("sum by(email)", excess)
        self.assertIn("clamp_min", excess)
        self.assertIn("${personal_allowance:raw}", excess)
        self.assertIn("> bool (${personal_allowance:raw})", count)
        for key in ("ai_cost_personal_excess", "ai_cost_over_allowance", "ai_cost_seats",
                    "ai_cost_model_total", "ai_cost_system_excess"):
            expr = queries[key]["expr"]
            self.assertNotIn("stack:regex", expr, "shared allowance must not be recalculated on a subset")
            self.assertNotIn("vector(0)", expr, "missing source must remain absent")
            self.assertNotIn("max_over_time", expr, "monthly gauges are not lifetime high-water marks")
            self.assertTrue(queries[key]["instant"], "range reduction can revive a missing source")
            self.assertFalse(queries[key]["range"])

    def test_generated_artifact_guards_variables_and_protects_identity_boundary(self):
        for query in self.queries().values():
            if "expr" in query:
                expr = query["expr"]
                for selector in re.findall(r"grafanacloud_\w+\{([^}]*)\}", expr):
                    self.assertIn('__ignore_usage__=""', selector)
                self.assertEqual(expr.count("("), expr.count(")"))
                if "${" in expr:
                    self.assertIn("< +Inf", expr)
                    self.assertIn(">= 0", expr)
            if "url" in query:
                self.assertNotIn("email", json.dumps(query))
                self.assertNotIn("${personal_allowance", json.dumps(query),
                                 "history cannot reconstruct a different personal allowance")
        queries = self.queries()
        for key in ("ai_cost_captured_current", "ai_cost_history", "ai_cost_stack_history"):
            self.assertEqual(queries[key]["parser"], "backend")
            self.assertTrue(queries[key]["columns"])
            self.assertNotIn("email", json.dumps(queries[key]))
        self.assertIn("stack:regex", queries["ai_cost_stack_history"]["filterExpression"])
        self.assertNotIn("stack:regex", queries["ai_cost_history"].get("filterExpression", ""))
        doc = self.document()
        for panel in doc["spec"]["elements"].values():
            self.assertFalse(panel["spec"].get("links"), "identity panels must not create exports or links")
        defaults = {v["spec"]["name"]: v["spec"]["current"]["value"]
                    for v in doc["spec"]["variables"]}
        self.assertEqual(defaults, {"seat_price_usd": "20", "overage_per_million_usd": "2",
                                   "personal_allowance": "40000000", "system_allowance": "500000000"})
        self.assertEqual(ai_cost.variables(seat_price=14)[0]["spec"]["current"]["value"], "14")
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ai_cost.variables(seat_price=value)
