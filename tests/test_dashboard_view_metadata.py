"""Exercise snapshot qualifications through the public offline dashboard CLI."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class ViewMetadataContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.states = {}
        for state in ("failed-inventory", "unknown-departure", "missing-metadata", "old-last-good"):
            directory = Path(cls.directory.name) / state
            views = directory / "views"
            shutil.copytree(ROOT / "testdata" / "views", views)
            path = views / "cost_cardinality_outliers.json"
            payload = json.loads(path.read_text())
            # This row is absent from the separately updated estate snapshot. Its departure is
            # not proven: neither a historical table nor Mimir label values are fresh inventory.
            payload["rows"] = [dict(payload["rows"][0], **{" Stack": "historical-only"})]
            payload["meta"] = {
                "generated_at": "2020-01-02T00:00:00+00:00", "tier": "t1",
                "coverage_ratio": 1.0, "stacks_total": 1,
                "inputs": {"dataplane": {"available": True, "stale": False,
                                         "age_seconds": 21600, "source": "hydrated"}},
            }
            if state == "failed-inventory":
                estate = json.loads((views / "estate.json").read_text())
                estate["meta"] = {"generated_at": "2020-01-01T00:00:00+00:00"}
                (views / "estate.json").write_text(json.dumps(estate))
            elif state == "missing-metadata":
                payload.pop("meta")
            path.write_text(json.dumps(payload))
            env = {**os.environ, "GCINSIGHT_VIEWS_DIR": str(views),
                   "GCINSIGHT_S3_BUCKET": "synthetic-view-metadata"}
            result = subprocess.run(
                [sys.executable, str(ROOT / "bin" / "dashboards.py"),
                 "--out", str(directory / "built"), "--ds-uid", "infinity-uid"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stderr)
            prefix = env.get("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight")
            artifact = json.loads((directory / "built" / f"{prefix}-cost.json").read_text())
            cls.states[state] = (artifact, payload)
            evidence = os.environ.get("GCINSIGHT_METADATA_TEST_EVIDENCE")
            if evidence:
                target = Path(evidence) / state
                shutil.copytree(directory, target)
                (target / "cli.log").write_text(result.stdout + result.stderr)

    def test_every_state_has_runtime_snapshot_metadata_not_build_time_literals(self):
        for state, (artifact, payload) in self.states.items():
            with self.subTest(state=state):
                panel = artifact["spec"]["elements"]["_meta_cost_cardinality_outliers"]["spec"]
                query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                self.assertEqual(query["parser"], "backend")
                self.assertTrue(query["url"].endswith("/views/cost_cardinality_outliers.json"))
                self.assertIn("$millis()", query["root_selector"])
                self.assertIn("meta.generated_at", query["root_selector"])
                self.assertIn("age_seconds", query["root_selector"])
                self.assertNotIn("historical-only", json.dumps(panel))
                self.assertNotIn("2020-01-02", json.dumps(panel))
                self.assertNotIn("filterExpression", query)
                self.assertIn("current membership unknown", query["root_selector"])
                self.assertIn("Unknown", query["root_selector"])
                self.assertIn("not exact observation timestamps", panel["description"])
                self.assertIn("not per-view completeness", panel["description"])
                columns = {c["text"]: c["type"] for c in query["columns"]}
                self.assertEqual(columns["Publication age (s)"], "number")
                self.assertEqual(columns["Input age now (s)"], "number")

    def test_departure_is_not_inferred_and_missing_inventory_is_not_zero(self):
        for state, (artifact, _) in self.states.items():
            with self.subTest(state=state):
                table = artifact["spec"]["elements"]["cardinality"]["spec"]
                query = table["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                self.assertEqual(query["root_selector"], "rows")
                self.assertEqual(query["filterExpression"], 'Stack =~ "^(${stack:regex})$"')
                self.assertIn("historical/unknown", table["description"])
                self.assertIn("empty result", table["description"])
                self.assertNotIn("current inventory", query["filterExpression"])
                variable = artifact["spec"]["variables"][0]["spec"]
                self.assertEqual(variable["query"]["spec"]["query"],
                                 "label_values(gcinsight_stack_active_series,stack)")
                self.assertEqual(variable["options"], [])
                self.assertEqual(variable["allValue"], ".*")

    def test_metadata_is_deduplicated_and_placed_without_new_tabs(self):
        artifact, _ = self.states["old-last-good"]
        spec = artifact["spec"]
        tabs = spec["layout"]["spec"]["tabs"]
        self.assertEqual(tabs[-1]["spec"]["title"], "How to read this")
        row = next(row["spec"] for row in tabs[-1]["spec"]["layout"]["spec"]["rows"]
                   if row["spec"]["title"] == "Published view metadata (historical snapshots)")
        self.assertIn("_meta_cost_cardinality_outliers", json.dumps(row))
        referenced = set()
        for key, element in spec["elements"].items():
            if key.startswith("_meta_"):
                continue
            for wrapped in element["spec"]["data"]["spec"]["queries"]:
                query = wrapped["spec"]["query"]
                url = query["spec"].get("url", "")
                if query["group"] == "yesoreyeram-infinity-datasource" and "/views/" in url:
                    referenced.add(url.rsplit("/", 1)[-1].removesuffix(".json"))
        self.assertEqual({key.removeprefix("_meta_") for key in spec["elements"]
                          if key.startswith("_meta_")}, referenced)
