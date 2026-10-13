"""Attribution counterexamples through the public, offline dashboard build surface.

The same observations can come from different actors/apps or have different cumulative
volumes and baselines. Test the display contract, not a ban on legitimate counts or units.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class AttributionPresentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        directory = Path(cls.directory.name)
        views = directory / "views"
        shutil.copytree(ROOT / "testdata" / "views", views)
        # A human can use CLI and automation can use web. These booleans and ratios
        # are the old surface proxy, not independently correlated actor identity.
        cls.seeded = {}
        for name, rows in {
            "ai_category_surface": [
                {" Stack": "synthetic-attribution", "Category": "Investigate", "Surface": "cli",
                 "Messages": 37, "Human driven": False},
                {" Stack": "synthetic-attribution", "Category": "Dashboard", "Surface": "web",
                 "Messages": 11, "Human driven": True}],
            "insights_surface_usage": [
                {" Stack": "synthetic-attribution", "Surface": "app_scenes", "Requests": 43,
                 "Share of stack requests %": 100, "Distinct identified users": 1,
                 "User identity": "observed"}],
            "ai_agent_observability": [
                {" Stack": "synthetic-attribution", "Region": "synthetic-region", "Measured": True,
                 "Positive rate reported (30d)": True, "Maximum generation items/s (30d)": 0.5,
                 "Window": "30d", "Window end": "2026-08-25T00:00:00+00:00",
                 "Detail": "Measured maximum rate within 30d, not cumulative volume."}],
        }.items():
            path = views / f"{name}.json"
            payload = json.loads(path.read_text())
            payload["rows"] = rows
            path.write_text(json.dumps(payload))
            cls.seeded[name] = payload
        env = {**os.environ, "GCINSIGHT_VIEWS_DIR": str(views),
               "GCINSIGHT_S3_BUCKET": "synthetic-attribution"}
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "dashboards.py"), "--out", str(directory / "built"),
             "--ds-uid", "infinity-uid"], cwd=ROOT, env=env, capture_output=True,
            text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        prefix = env.get("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight")
        cls.artifacts = {p.stem.removeprefix(prefix + "-"): json.loads(p.read_text())
                         for p in (directory / "built").glob("*.json")}
        evidence = os.environ.get("GCINSIGHT_ATTRIBUTION_TEST_EVIDENCE")
        if evidence:
            shutil.copytree(directory, evidence)
            (Path(evidence) / "cli.log").write_text(result.stdout + result.stderr)

    def panel(self, dashboard, key):
        return self.artifacts[dashboard]["spec"]["elements"][key]["spec"]

    def query(self, dashboard, key):
        return self.panel(dashboard, key)["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]

    def renames(self, dashboard, key):
        transformations = self.panel(dashboard, key)["data"]["spec"]["transformations"]
        return next(t["spec"]["options"]["renameByName"] for t in transformations
                    if t["kind"] == "organize")

    def content(self, dashboard, key):
        return self.panel(dashboard, key)["vizConfig"]["spec"]["options"]["content"]

    def test_non_web_and_web_proxies_never_display_as_verified_actors(self):
        # Apply only the actual artifact's display-name mapping. The values are not
        # transformed: 37 CLI messages and False remain exactly those observations.
        query = self.query("ai", "tbl_ai_combo_stack")
        self.assertEqual({c["selector"].strip(): c["text"] for c in query["columns"]}["Human driven"],
                         "Human driven")  # Source field contract remains unchanged.
        rename = self.renames("ai", "tbl_ai_combo_stack")
        self.assertEqual(rename["Human driven"], "Web surface proxy (human identity unproven)")
        rows = [{rename.get(k.strip(), k.strip()): v for k, v in row.items()}
                for row in self.seeded["ai_category_surface"]["rows"]]
        self.assertEqual(rows[0]["Messages"], 37)
        self.assertIs(rows[0][rename["Human driven"]], False)
        self.assertIs(rows[1][rename["Human driven"]], True)
        self.assertEqual(self.query("ai", "tbl_ai_combo_stack")["root_selector"], "rows")
        # D-LAY23 leaves the gap's non-evidence attribution field on its widened canonical owner.
        gap = self.panel("ai", "_fd_ai_gap")
        organize = next(t["spec"]["options"] for t in gap["data"]["spec"]["transformations"]
                        if t["kind"] == "organize")
        self.assertTrue(organize["excludeByName"]["Machine share of categorised"])
        self.assertIn(str(self.panel("ai", "tbl_ai_gap")["id"]), gap["links"][0]["url"])
        for key in ("tbl_ai_per_stack", "tbl_ai_gap", "tbl_ai_outliers", "_fd_ai_tokens"):
            display = "Non-web share of categorised (actor identity unproven)"
            self.assertEqual(self.renames("ai", key)["Machine share of categorised"], display)
            overrides = self.panel("ai", key)["vizConfig"]["spec"]["fieldConfig"]["overrides"]
            # Partition restores display aliases after matching the original field name.
            # Resolve the artifact's override target back through its displayName property;
            # the percentunit requirement and qualified actor label remain unchanged.
            displayed_as = {o["matcher"]["options"]: prop["value"]
                            for o in overrides if o["matcher"]["id"] == "byName"
                            for prop in o["properties"] if prop["id"] == "displayName"}
            unit_targets = {displayed_as.get(o["matcher"]["options"], o["matcher"]["options"])
                            for o in overrides if o["matcher"]["id"] == "byName"
                            for prop in o["properties"]
                            if prop == {"id": "unit", "value": "percentunit"}}
            self.assertIn(display, unit_targets)
            # Neither renaming nor formatting changes the 0-1 source ratio to an invented zero.
            transforms = self.panel("ai", key)["data"]["spec"]["transformations"]
            kinds = [t["kind"] for t in transforms]
            if "partitionByValues" in kinds:
                self.assertEqual(kinds, ["organize", "calculateField", "convertFieldType", "partitionByValues"])
                self.assertEqual(transforms[1]["spec"]["options"]["reduce"],
                                 {"reducer": "first", "include": ["Stack"]})
                self.assertEqual(transforms[2]["spec"]["options"]["conversions"],
                                 [{"targetField": "Stack links available", "destinationType": "boolean"}])
                self.assertEqual(transforms[3]["spec"]["options"]["fields"], ["Stack links available"])
            else:
                self.assertEqual(kinds, ["organize"])
        self.assertIn("unproven", self.content("ai", "actor_scope").lower())
        human_tab = next(t["spec"] for t in self.artifacts["ai"]["spec"]["layout"]["spec"]["tabs"]
                         if t["spec"]["title"] == "Human vs machine")
        self.assertIn("actor_scope", json.dumps(human_tab))
        self.assertIn("n_ai_uncategorised", json.dumps(human_tab))
        self.assertNotIn("usually a pipeline", self.panel("ai", "tbl_ai_stack_tpu")["description"])
        self.assertIn("unproven", self.panel("ai", "n_token_users")["title"].lower())
        self.assertIn("user-token series", self.panel("ai", "tbl_people")["title"].lower())
        self.assertIn("lifetime", self.panel("ai", "tbl_people")["title"].lower())

    def test_app_scenes_and_user_ids_do_not_establish_per_app_value_or_people(self):
        # A known Logs frontend and other apps can all emit generic app/scenes.
        # 43 requests and one ID do not establish 43 visits or one human.
        scope = self.content("dashboards", "surface_scope").lower()
        self.assertNotIn("scenes-based app plugins (drilldown and others)", scope)
        self.assertIn("per-app", scope)
        self.assertIn("unproven", scope)
        self.assertEqual(self.renames("dashboards", "tbl_surface_usage")["Distinct identified users"],
                         "Distinct userIds (human identity unproven)")
        query = self.query("dashboards", "tbl_surface_usage")
        self.assertEqual(query["root_selector"], "rows")
        self.assertEqual(query["filterExpression"], 'Stack =~ "^(${stack:regex})$"')
        self.assertEqual(self.seeded["insights_surface_usage"]["rows"][0]["Requests"], 43)
        self.assertIn("not page visits", self.panel("dashboards", "b_surface_share")["description"])
        self.assertIn("human identity unproven", self.panel("dashboards", "n_viewers")["title"].lower())
        self.assertIn("legacy navigation", self.content("dashboards", "opening_scope").lower())
        self.assertIn("24h", self.content("dashboards", "opening_scope"))
        self.assertIn("31d", self.content("dashboards", "opening_scope"))

    def test_positive_max_rate_is_not_cumulative_generations_or_automatic_remediation(self):
        # A brief spike and sustained 0.5/s can share this maximum but have very
        # different cumulative totals. Do not fabricate a volume from either case.
        panel = self.panel("ai", "tbl_ai_agent")
        self.assertIn("cumulative generations unproven", panel["title"].lower())
        self.assertIn("automatic remediation", panel["description"].lower())
        self.assertIn("unproven", panel["description"].lower())
        query = self.query("ai", "tbl_ai_agent")
        self.assertEqual(query["root_selector"], "rows")
        self.assertIn("Maximum generation items/s (30d)", [c["text"] for c in query["columns"]])
        self.assertEqual(self.seeded["ai_agent_observability"]["rows"][0]
                         ["Maximum generation items/s (30d)"], 0.5)
        self.assertNotIn("increase(", json.dumps(panel))
        self.assertNotIn("sum_over_time(", json.dumps(panel))

    def test_medians_remain_seven_day_delays_not_saved_operator_time(self):
        # Identical medians can accompany different workloads and no saved-time
        # baseline at all. Preserve the p50 and seconds, not an ROI conversion.
        self.assertIn("saved operator time unproven", self.content("coverage", "outcome_scope").lower())
        for dashboard, keys in {"coverage": ("n_value_mtta", "n_value_mttr"),
                                "operations": ("n_mtta", "n_mttr")}.items():
            for key in keys:
                with self.subTest(dashboard=dashboard, panel=key):
                    panel = self.panel(dashboard, key)
                    self.assertIn("Median recorded", panel["title"])
                    self.assertIn("(7d)", panel["title"])
                    self.assertIn("histogram_quantile(0.5", self.query(dashboard, key)["expr"])
                    self.assertEqual(panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"], "s")
        self.assertIn("Outcome value", [t["spec"]["title"] for t in
                                        self.artifacts["coverage"]["spec"]["layout"]["spec"]["tabs"]])
        self.assertEqual(len(self.artifacts), 12)
        # Headers and How-to-read content must not contradict the on-tab qualifiers.
        for dashboard in ("ai", "coverage", "dashboards"):
            self.assertIn("unproven", self.artifacts[dashboard]["spec"]["description"].lower())
        self.assertIn("unproven", self.content("ai", "_banner").lower())
        self.assertIn("unproven", self.content("coverage", "_banner").lower())
