"""Public offline CLI state fixtures; JSONata reference-runtime evidence is retained separately."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from collector.dashboards import build, view_metadata

ROOT = Path(__file__).resolve().parent.parent
VIEW = "library_panels_inventory"


class OptionalViewStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.states = {}
        for state in ("absent", "measured-empty", "old-last-good", "partial", "unavailable",
                      "missing-metadata", "false-empty", "disabled", "absent-all", "bounded-partial"):
            directory = Path(cls.directory.name) / state
            views = directory / "views"
            shutil.copytree(ROOT / "testdata" / "views", views)
            path = views / f"{VIEW}.json"
            payload = {
                "meta": {"generated_at": "2020-01-02T00:00:00+00:00", "coverage_ratio": 0.95,
                         "inputs": {VIEW: {"available": True, "stale": False, "age_seconds": 21600}}},
                "rows": [{"Stack": "synthetic-retained", "Configured library panels": 0}],
            }
            if state in ("partial", "unavailable", "disabled"):
                payload["meta"]["inputs"][VIEW].update(available=False, state=state)
            if state == "missing-metadata":
                payload.pop("meta")
            if state == "false-empty":
                payload["rows"] = []
            if state == "bounded-partial":
                payload["rows"][0]["Response state"] = "partial"
            if state == "absent-all":
                for view in view_metadata.USAGE_OPTIONAL_VIEWS:
                    (views / f"{view}.json").unlink()
            elif state == "absent":
                path.unlink()
            else:
                path.write_text(json.dumps(payload))
            env = {**os.environ, "GCINSIGHT_VIEWS_DIR": str(views),
                   "GCINSIGHT_S3_BUCKET": "synthetic-optional-state"}
            result = subprocess.run([sys.executable, str(ROOT / "bin" / "dashboards.py"),
                                     "--out", str(directory / "built"), "--ds-uid", "infinity-uid"],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stderr)
            prefix = env.get("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight")
            artifact = json.loads((directory / "built" / f"{prefix}-usage.json").read_text())
            cls.states[state] = artifact
            evidence = os.environ.get("GCINSIGHT_OPTIONAL_TEST_EVIDENCE")
            if evidence:
                shutil.copytree(directory, Path(evidence) / state)
                (Path(evidence) / state / "cli.log").write_text(result.stdout + result.stderr)

    def test_absent_numeric_table_does_not_hide_state(self):
        elements = self.states["absent"]["spec"]["elements"]
        self.assertNotIn(VIEW, elements)
        self.assertNotIn(f"_meta_{VIEW}", elements)
        self.assertNotIn(f"{VIEW}.json", json.dumps(self.states["absent"]))
        guide = elements["_optional_view_state"]["spec"]["vizConfig"]["spec"]["options"]["content"]
        self.assertIn(f"**{VIEW}**: No object at build read", guide)
        self.assertIn("current state unknown", guide)
        self.assertIn("No publication marker or input age", guide)
        self.assertIn("401/403", guide)
        self.assertIn("not evidence of disabled", guide)
        self.assertIn("No such build-read omissions", self.states["measured-empty"]["spec"]
                      ["elements"]["_optional_view_state"]["spec"]["vizConfig"]["spec"]["options"]["content"])

    def test_all_absent_views_have_static_disclosure_without_object_queries(self):
        artifact = self.states["absent-all"]
        guide = artifact["spec"]["elements"]["_optional_view_state"]["spec"]["vizConfig"]\
            ["spec"]["options"]["content"]
        for view in view_metadata.USAGE_OPTIONAL_VIEWS:
            with self.subTest(view=view):
                self.assertIn(f"**{view}**: No object at build read", guide)
                self.assertNotIn(f"_meta_{view}", artifact["spec"]["elements"])
                self.assertNotIn(f"{view}.json", json.dumps(artifact))

    def test_state_is_runtime_and_retained_marker_never_replaced(self):
        for state, artifact in self.states.items():
            if state in ("absent", "absent-all"):
                continue
            with self.subTest(state=state):
                panel = artifact["spec"]["elements"][f"_meta_{VIEW}"]["spec"]
                query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                self.assertEqual(query["parser"], "backend")
                self.assertTrue(query["url"].endswith(f"/views/{VIEW}.json"))
                self.assertNotIn("2020-01-02", json.dumps(panel))
                selectors = {c["selector"] for c in query["columns"]}
                self.assertIn("measurement", selectors)
                self.assertIn("scan_coverage", selectors)
                self.assertIn("Partial at publication", query["root_selector"])
                self.assertIn("Disabled at publication", query["root_selector"])
                self.assertIn("not current source health", panel["description"])
                self.assertNotIn("filterExpression", query)

    def test_real_build_reader_failure_surface_is_not_optional_absence(self):
        # Exercise the actual AWS-CLI read adapter, not a replacement read_view implementation.
        errors = ("An error occurred (401) when calling the HeadObject operation: Unauthorized",
                  "An error occurred (403) when calling the HeadObject operation: Forbidden",
                  "Could not connect to the endpoint URL: synthetic.invalid")
        with mock.patch.object(build, "VIEWS_DIR", ""), mock.patch.object(build, "BUCKET", "synthetic"):
            for error in errors:
                with self.subTest(error=error), mock.patch.object(build.subprocess, "run", return_value=
                        subprocess.CompletedProcess([], 1, "", error)):
                    with self.assertRaisesRegex(RuntimeError, error.split(":")[0].replace("(", r"\(").replace(")", r"\)")):
                        build.read_view(VIEW)
            with mock.patch.object(build.subprocess, "run", return_value=
                    subprocess.CompletedProcess([], 0, "not JSON", "")):
                with self.assertRaises(json.JSONDecodeError):
                    build.read_view(VIEW)
            with mock.patch.object(build.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 1, "", "An error occurred (404) when calling the HeadObject operation: Not Found")):
                with self.assertRaises(FileNotFoundError):
                    build.read_view(VIEW)

    def test_public_cli_invalid_json_is_failure_not_measured_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            views = Path(directory) / "views"
            shutil.copytree(ROOT / "testdata" / "views", views)
            (views / f"{VIEW}.json").write_text("not JSON")
            result = subprocess.run([sys.executable, str(ROOT / "bin" / "dashboards.py"),
                                     "--out", str(Path(directory) / "built"), "--ds-uid", "infinity-uid"],
                                    cwd=ROOT, env={**os.environ, "GCINSIGHT_VIEWS_DIR": str(views)},
                                    capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("JSONDecodeError", result.stderr)
            prefix = os.environ.get("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight")
            self.assertFalse((Path(directory) / "built" / f"{prefix}-usage.json").exists())
