"""Safe admitted links are resolved from final published targets, never guessed identities."""
import unittest
from tests import test_dashboard_layout as layout_contract


class DrilldownContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layout_contract.DashboardLayoutContractTest.setUpClass.__func__(cls)

    def test_new_risk_findings_and_row_navigation_exist(self):
        for docs in self.documents.values():
            for key in ('_fd_label_high', '_fd_label_possible', '_fd_sa', '_fd_fast'):
                self.assertIn(key, docs['risk']['spec']['elements'])
            board = docs['maturity']['spec']['elements']['board']['spec']
            self.assertTrue(any(p['id'] == 'links' for o in board['vizConfig']['spec']['fieldConfig']['overrides'] for p in o['properties']))

    def test_ai_rankings_link_actual_slug_label_and_hide_legend_fallback(self):
        for docs in self.documents.values():
            for key in ("tbl_stack_users", "tbl_stack_tokens"):
                transforms = docs["ai"]["spec"]["elements"][key]["spec"]["data"]["spec"]["transformations"]
                self.assertEqual([t["spec"]["id"] for t in transforms[:2]], ["labelsToFields", "merge"])
                organize = next(t["spec"]["options"] for t in transforms if t["spec"]["id"] == "organize")
                self.assertEqual(organize["renameByName"]["slug"], "Stack")
                self.assertNotIn("Field", organize["renameByName"])
                self.assertEqual(organize["renameByName"]["stack_id"], "Stack ID")
                self.assertFalse(organize["excludeByName"].get("stack_id", False))

    def test_all_row_links_are_internal_slug_only_and_keep_time(self):
        count = 0
        for prefix, docs in self.documents.items():
            for doc in docs.values():
                for element in doc['spec']['elements'].values():
                    for override in element['spec']['vizConfig']['spec'].get('fieldConfig', {}).get('overrides', []):
                        for prop in override['properties']:
                            if prop['id'] != 'links':
                                continue
                            for link in prop['value']:
                                count += 1
                                self.assertTrue(link['url'].startswith('/d/' + prefix + '-'))
                                self.assertIn('${__url_time_range}', link['url'])
                                self.assertEqual(link['url'].count('var-stack='), 1)
                                self.assertIn('${__value.raw:percentencode}', link['url'])
                                self.assertNotIn('${stack:', link['url'])
        self.assertGreater(count, 30)


class ExactFindingLineageTest(unittest.TestCase):
    def test_only_frozen_finding_filters_preserve_lineage(self):
        from tests.test_dashboard_coverage import FINDING_PRESENTATION_ROOTS, presentation_root
        self.assertEqual(len(FINDING_PRESENTATION_ROOTS), 5)
        for root in FINDING_PRESENTATION_ROOTS:
            self.assertEqual(presentation_root(root), "rows")
            for mutation in (root + '.{"Stack": ` Stack`}', root + '.` Stack`',
                             root + '[enabled = true]', root.replace('rows[', 'meta['),
                             root.replace('$lookup($,', '$lookup({"fabricated": true},')):
                self.assertNotEqual(presentation_root(mutation), "rows")


    def test_stack_type_projection_cannot_credit_replacement_or_filter(self):
        from tests.test_dashboard_coverage import STACK_PRESENTATION_PROJECTIONS, presentation_root
        for suffix in STACK_PRESENTATION_PROJECTIONS:
            self.assertEqual(presentation_root("rows" + suffix), "rows")
            for mutation in (suffix.replace(': $type', ', "forged": true, "x": $type'),
                             suffix.replace(': null', ': "invented"'),
                             suffix + '[enabled = true]', suffix + '.Stack'):
                self.assertNotEqual(presentation_root("rows" + mutation), "rows")
            self.assertNotEqual(presentation_root('rows.{"Stack": Stack}' + suffix), "rows")


class OptionalDrilldownBuildTest(unittest.TestCase):
    def test_public_build_omits_only_unpublished_optional_endpoints(self):
        import json
        import os
        from pathlib import Path
        import shutil
        import subprocess
        import sys
        import tempfile
        from urllib.parse import parse_qs, urlsplit

        root = Path(__file__).resolve().parents[1]
        optional = {
            "risk_label_cardinality": ("label_cardinality", ("_fd_label_high", "_fd_label_possible")),
            "risk_fleet_scrape_intervals": ("fleet_scrape_intervals", ("_fd_fast",)),
            "risk_public_dashboards": ("public_dashboards", ()),
            "risk_retention_policy_status": ("retention_policy_status", ()),
        }
        for missing in [set(), *({name} for name in optional), set(optional)]:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                views, output = Path(directory) / "views", Path(directory) / "dashboards"
                views.mkdir()
                for fixture in (root / "testdata/views").glob("*.json"):
                    if fixture.stem not in missing:
                        shutil.copyfile(fixture, views / fixture.name)
                result = subprocess.run(
                    [sys.executable, str(root / "bin/dashboards.py"), "--out", str(output),
                     "--ds-uid", "infinity-uid"], cwd=root, capture_output=True, text=True, timeout=60,
                    env={**os.environ, "GCINSIGHT_VIEWS_DIR": str(views), "GCINSIGHT_S3_BUCKET": "synthetic",
                         "GCINSIGHT_DASHBOARD_UID_PREFIX": "gcinsight"})
                self.assertEqual(result.returncode, 0, result.stderr)
                documents = {f.stem: json.loads(f.read_text()) for f in output.glob("*.json")}
                risk = documents["gcinsight-risk"]["spec"]["elements"]
                for view, (owner, details) in optional.items():
                    for key in (owner, *details):
                        self.assertEqual(key in risk, view not in missing)
                for document in documents.values():
                    for element in document["spec"]["elements"].values():
                        panel = element["spec"]
                        links = list(panel.get("links", []))
                        for override in panel["vizConfig"]["spec"].get("fieldConfig", {}).get("overrides", []):
                            for prop in override["properties"]:
                                if prop["id"] == "links":
                                    links.extend(prop["value"])
                        for link in links:
                            url = urlsplit(link["url"])
                            panel_id = parse_qs(url.query).get("viewPanel", [])
                            if url.path.startswith("/d/gcinsight-") and panel_id:
                                target = documents[url.path.removeprefix("/d/")]
                                self.assertIn(panel_id[0], {str(e["spec"]["id"])
                                                          for e in target["spec"]["elements"].values()})
                if "risk_retention_policy_status" in missing:
                    panel = documents["gcinsight-operations"]["spec"]["elements"]["_ret_candidate_table"]["spec"]
                    self.assertFalse(any(p["id"] == "links" for o in panel["vizConfig"]["spec"]["fieldConfig"]["overrides"]
                                         for p in o["properties"]))

    def test_required_owner_and_target_typos_still_fail(self):
        from pathlib import Path
        from unittest.mock import patch
        from bin import dashboards
        from collector.dashboards import build, layout
        views = str(Path(__file__).resolve().parents[1] / "testdata/views")
        with patch.object(build, "VIEWS_DIR", views), patch.object(build, "BUCKET", "synthetic"):
            owners = {**layout.REGISTER_OWNERS["risk"], "_fd_sa": "required_owner_typo"}
            with patch.dict(layout.REGISTER_OWNERS, {"risk": owners}):
                with self.assertRaises(KeyError):
                    dashboards.assemble("risk", "infinity-uid")
            targets = {"_ret_candidate_table": ("Stack", [("risk", "required_target_typo", "broken")])}
            with patch.dict(layout.ROW_LINKS, {"operations": targets}):
                with self.assertRaises(KeyError):
                    dashboards.assemble("operations", "infinity-uid")
