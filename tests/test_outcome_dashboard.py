"""The opt-in Operations slice reads only reserved observer projections."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from collector.dashboards import build

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("outcome_dashboards", ROOT / "bin/dashboards.py")
dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dash)


class OutcomeDashboardTest(unittest.TestCase):
    def setUp(self):
        self.views = mock.patch.object(build, "read_view", side_effect=lambda name: json.loads(
            (ROOT / "testdata/views" / f"{name}.json").read_text()))
        self.views.start()
        self.addCleanup(self.views.stop)

    def test_default_off_preserves_assembled_operations(self):
        self.assertEqual(dash.assemble("operations", "synthetic"),
                         dash.assemble("operations", "synthetic", outcome_observer=False))

    def test_opt_in_reads_four_tier_objects_without_stack_filter(self):
        _, artifact = dash.assemble("operations", "synthetic", outcome_observer=True)
        panels = artifact["spec"]["elements"]
        found = [panels[f"_outcome_{tier}"] for tier in ("t1", "t2", "t3", "t4")]
        for tier, panel in zip(("t1", "t2", "t3", "t4"), found, strict=True):
            query = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
            self.assertTrue(query["url"].endswith(f"/views/outcomes/{tier}.json"))
            self.assertEqual(query["parser"], "backend")
            self.assertNotIn("filterExpression", query)
            rendered = [column["selector"] for column in query["columns"]]
            self.assertNotIn("attempt_id", rendered)
            self.assertNotIn("sha256", rendered)
            self.assertNotIn("_state", rendered)
        build.assert_layout_complete(artifact["spec"]["elements"],
                                    _placed(artifact["spec"]["layout"]))

    def test_public_offline_build_forwards_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "GCINSIGHT_VIEWS_DIR": str(ROOT / "testdata/views"),
                   "GCINSIGHT_S3_BUCKET": "synthetic-outcomes"}
            result = subprocess.run(
                [sys.executable, str(ROOT / "bin/dashboards.py"), "--out", directory,
                 "--ds-uid", "synthetic", "--outcome-observer"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            prefix = env.get("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight")
            artifact = json.loads((Path(directory) / f"{prefix}-operations.json").read_text())
            self.assertIn("_outcome_t4", artifact["spec"]["elements"])

    def test_other_dashboards_are_unchanged_with_opt_in(self):
        self.assertEqual(dash.assemble("ai", "synthetic"),
                         dash.assemble("ai", "synthetic", outcome_observer=True))


def _placed(layout):
    spec = layout["spec"]
    names = [item["spec"]["element"]["name"] for item in spec.get("items", [])]
    for child in spec.get("rows", []) + spec.get("tabs", []):
        names += _placed(child["spec"]["layout"])
    return names
