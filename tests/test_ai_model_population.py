"""Execute assembled model queries against synthetic monthly gauges, not string copies."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from collector.dashboards import ai_cost, build


@unittest.skipUnless(shutil.which("promtool"), "requires local Prometheus expression evaluator")
class AIModelPopulationTest(unittest.TestCase):
    def test_identity_cost_and_headline_share_token_active_seats(self):
        with tempfile.TemporaryDirectory() as directory:
            for view in ("ai_cost_current", "ai_cost_monthly", "ai_cost_stacks"):
                Path(directory, view + ".json").write_text('{"rows": []}')
            with mock.patch.object(build, "BUCKET", "synthetic"), \
                    mock.patch.object(build, "VIEWS_DIR", directory):
                elements = ai_cost.elements("infinity")

            def expr(key, price=14):
                query = elements[key]["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
                for name, value in (("seat_price_usd", price), ("personal_allowance", 40000000),
                                    ("system_allowance", 500000000), ("overage_per_million_usd", 2)):
                    query = query.replace("${" + name + ":raw}", str(value))
                return query

            def series(identity, stack, tokens, category="user"):
                return {"series": 'grafanacloud_ai_tokens_user_total_tokens{email="%s",stack_id="%s",user_type="%s"}'
                        % (identity, stack, category), "values": str(tokens)}

            def check(query, samples):
                return {"expr": query, "eval_time": "0m", "exp_samples": samples}

            detail = expr("ai_cost_live_user_model")
            fixture = {"evaluation_interval": "1m", "tests": [
                {"input_series": [series("zero", "a", 0), series("active", "a", 30000000),
                                  series("active", "b", 20000000), series("system", "a", 1, "service")],
                 "promql_expr_test": [
                     check(detail, [{"labels": '{email="zero"}', "value": 0},
                                    {"labels": '{email="active"}', "value": 34}]),
                     check(expr("ai_cost_model_total"), [{"labels": "{}", "value": 34}]),
                     check(expr("ai_cost_live_user_model", 20), [
                         {"labels": '{email="zero"}', "value": 0},
                         {"labels": '{email="active"}', "value": 40}]),
                     check(expr("ai_cost_live_user_model", -1), []),
                 ]},
                {"input_series": [series("zero", "a", 0)], "promql_expr_test": [
                    check(detail, [{"labels": '{email="zero"}', "value": 0}]),
                    check(expr("ai_cost_model_seats"), [{"labels": "{}", "value": 0}]),
                ]},
                {"input_series": [], "promql_expr_test": [check(detail, []),
                    check(expr("ai_cost_model_seats"), [])]},
            ]}
            fixture_path = Path(directory, "population.json")
            fixture_path.write_text(json.dumps(fixture))
            result = subprocess.run([shutil.which("promtool"), "test", "rules", str(fixture_path)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
