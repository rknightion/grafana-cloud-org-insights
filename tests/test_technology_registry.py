"""The technology registry is data, and this test reads the real artifact back."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from collector import technology_registry


ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "collector" / "technology-registry.json"
FIXTURE_PATH = ROOT / "testdata" / "technology-metric-names.json"


class TechnologyRegistryArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(REGISTRY_PATH.read_text())
        cls.registry = technology_registry.load(REGISTRY_PATH)
        cls.metric_names = json.loads(FIXTURE_PATH.read_text())["metric_names"]

    def test_registry_is_versioned_data(self):
        self.assertRegex(self.raw["version"], r"^[1-9][0-9]*$")
        self.assertEqual(self.registry.version, self.raw["version"])
        self.assertTrue(self.raw["technologies"])

    def test_every_entry_has_one_matcher_and_exact_sentinels_are_unique(self):
        exact = []
        for entry in self.raw["technologies"]:
            self.assertEqual(set(entry), {"key", "name", "match"})
            self.assertEqual(len(entry["match"]), 1)
            matcher, value = next(iter(entry["match"].items()))
            self.assertIn(matcher, {"exact", "pattern"})
            self.assertTrue(value)
            if matcher == "exact":
                self.assertIsInstance(value, str)
                exact.append(value)
        self.assertEqual(len(exact), len(set(exact)), "two technologies claim one sentinel")

    def test_no_entry_is_a_bare_first_token_prefix(self):
        for entry in self.raw["technologies"]:
            matcher, value = next(iter(entry["match"].items()))
            if matcher == "exact":
                self.assertIn("_", value, f"{entry['key']} is a bare first-token prefix")
            else:
                self.assertEqual(entry["key"], "akuity", "pattern matching is an explicit exception")
                self.assertEqual(set(value), {"prefix", "suffix"})
                self.assertEqual(value["prefix"], "akuity_")
                self.assertEqual(value["suffix"], "_cluster_agenthealthstatus_bool")

    def test_fixture_exercises_every_registry_entry(self):
        result = technology_registry.classify(self.metric_names, self.registry)
        self.assertEqual(
            {entry.key for entry in self.registry.entries},
            {row["key"] for row in result["technologies"]},
        )

    def test_hpc_and_gpu_estate_is_not_lost_behind_generic_cloud_native_entries(self):
        keys = {entry.key for entry in self.registry.entries}
        self.assertLessEqual({"slurm", "weka", "nvidia_dcgm", "open_ondemand"}, keys)

    def test_akuity_pattern_is_narrow_and_contains_no_fixture_identity(self):
        entry = next(entry for entry in self.registry.entries if entry.key == "akuity")
        self.assertTrue(entry.matches("akuity_managed_platform_cluster_agenthealthstatus_bool"))
        for false_positive in (
            "akuity_up",
            "akuity_cluster_agenthealthstatus_bool_extra",
            "not_akuity_managed_platform_cluster_agenthealthstatus_bool",
            "argocd_cluster_agenthealthstatus_bool",
        ):
            self.assertFalse(entry.matches(false_positive), false_positive)

    def test_registry_version_change_is_observable(self):
        changed = dict(self.raw)
        changed["version"] = str(int(self.raw["version"]) + 1)
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "registry.json"
            path.write_text(json.dumps(changed))
            self.assertNotEqual(technology_registry.load(path).version, self.registry.version)

    def test_raw_regex_patterns_are_rejected(self):
        unsafe = {
            "version": "1",
            "technologies": [
                {"key": "unsafe", "name": "Unsafe", "match": {"pattern": "^(a+)+$"}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "registry.json"
            path.write_text(json.dumps(unsafe))
            with self.assertRaises(technology_registry.RegistryError):
                technology_registry.load(path)

    def test_malformed_json_and_non_object_roots_are_registry_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "registry.json"
            for body in ("{", "[]"):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises(technology_registry.RegistryError):
                    technology_registry.load(path)


class TechnologyClassificationTest(unittest.TestCase):
    def test_matched_and_unmatched_metric_name_counts_are_both_published(self):
        result = technology_registry.classify(
            ["kube_pod_info", "kube_pod_info", "node_cpu_seconds_total", "go_build_info"]
        )
        self.assertEqual(result["total_metric_name_count"], 3)
        self.assertEqual(result["matched_metric_name_count"], 1)
        self.assertEqual(result["unmatched_metric_name_count"], 2)
        self.assertAlmostEqual(result["unmatched_share"], 2 / 3)
        self.assertEqual(result["unmatched_metric_names"], ["go_build_info", "node_cpu_seconds_total"])
        self.assertEqual(result["registry_version"], technology_registry.REGISTRY.version)

    def test_empty_measured_inventory_is_zero_not_a_failure(self):
        result = technology_registry.classify([])
        self.assertEqual(result["total_metric_name_count"], 0)
        self.assertEqual(result["matched_metric_name_count"], 0)
        self.assertEqual(result["unmatched_metric_name_count"], 0)
        self.assertIsNone(result["unmatched_share"], "an empty denominator has no share")
        self.assertEqual(result["technologies"], [])

    def test_ambiguous_match_is_refused_instead_of_double_classified(self):
        raw = {
            "version": "1",
            "technologies": [
                {"key": "a", "name": "A", "match": {
                    "pattern": {"prefix": "shared", "suffix": "metric"}
                }},
                {"key": "b", "name": "B", "match": {
                    "pattern": {"prefix": "shared", "suffix": "metric"}
                }},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "registry.json"
            path.write_text(json.dumps(raw))
            registry = technology_registry.load(path)
            with self.assertRaises(technology_registry.AmbiguousMatch):
                technology_registry.classify(["shared_metric"], registry)


if __name__ == "__main__":
    unittest.main()
