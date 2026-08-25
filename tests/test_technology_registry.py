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
        fixture = json.loads(FIXTURE_PATH.read_text())
        cls.metric_names = fixture["metric_names"]
        cls.label_matches = fixture.get("technology_label_matches", [])

    def test_registry_is_versioned_data(self):
        self.assertRegex(self.raw["version"], r"^[1-9][0-9]*$")
        self.assertEqual(self.registry.version, self.raw["version"])
        self.assertTrue(self.raw["technologies"])

    def test_every_entry_has_one_matcher_and_name_sentinels_are_unique(self):
        claimed_names = []
        for entry in self.raw["technologies"]:
            self.assertEqual(set(entry), {"key", "name", "match"})
            self.assertEqual(len(entry["match"]), 1)
            matcher, value = next(iter(entry["match"].items()))
            self.assertIn(matcher, {"exact", "pattern", "any_of", "label"})
            self.assertTrue(value)
            if matcher == "exact":
                self.assertIsInstance(value, str)
                claimed_names.append(value)
            elif matcher == "any_of":
                self.assertIsInstance(value, list)
                claimed_names.extend(value)
        self.assertEqual(
            len(claimed_names), len(set(claimed_names)), "two technologies claim one name sentinel"
        )

    def test_no_entry_is_a_bare_first_token_prefix(self):
        for entry in self.raw["technologies"]:
            matcher, value = next(iter(entry["match"].items()))
            if matcher in {"exact", "any_of"}:
                names = [value] if matcher == "exact" else value
                for name in names:
                    self.assertIn("_", name, f"{entry['key']} is a bare first-token prefix")
            elif matcher == "label":
                self.assertEqual(set(value), {"metric", "key", "values"})
                self.assertIn("_", value["metric"])
            else:
                self.assertEqual(entry["key"], "akuity", "pattern matching is an explicit exception")
                self.assertEqual(set(value), {"prefix", "suffix"})
                self.assertEqual(value["prefix"], "akuity_")
                self.assertEqual(value["suffix"], "_cluster_agenthealthstatus_bool")

    def test_fixture_exercises_every_registry_entry(self):
        result = technology_registry.classify(
            self.metric_names, self.registry, label_matches=self.label_matches
        )
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

    def test_the_four_http_semconv_names_are_one_any_of_technology(self):
        entry = next(entry for entry in self.registry.entries if entry.key == "otel_http")
        self.assertEqual(set(entry.any_of), {
            "http_server_request_duration_seconds_count",
            "http_client_request_duration_seconds_count",
            "http_client_duration_milliseconds_count",
            "http_server_duration_milliseconds_count",
        })
        self.assertFalse({"otel_http_client", "otel_http_client_ms", "otel_http_server_ms"} & {
            item.key for item in self.registry.entries
        })

    def test_sdk_matcher_requires_the_reserved_value_not_bare_target_info_presence(self):
        entry = next(entry for entry in self.registry.entries if entry.key == "otel_sdk")
        self.assertEqual(entry.label_metric, "target_info")
        self.assertEqual(entry.label_key, "telemetry_sdk_name")
        self.assertEqual(entry.label_values, frozenset({"opentelemetry"}))

    def test_malformed_json_and_non_object_roots_are_registry_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "registry.json"
            for body in ("{", "[]"):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises(technology_registry.RegistryError):
                    technology_registry.load(path)


class TechnologyClassificationTest(unittest.TestCase):
    def _load(self, technologies: list[dict]) -> technology_registry.Registry:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "registry.json"
            path.write_text(json.dumps({"version": "1", "technologies": technologies}))
            return technology_registry.load(path)

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

    def test_any_of_overlaps_are_rejected_at_load_time(self):
        """One name cannot inflate two technologies merely because one matcher is a name set."""
        technologies = [
            {"key": "a", "name": "A", "match": {"exact": "shared_metric"}},
            {"key": "b", "name": "B", "match": {"any_of": ["other_metric", "shared_metric"]}},
        ]
        with self.assertRaises(technology_registry.RegistryError):
            self._load(technologies)

    def test_label_pairs_cannot_be_claimed_by_two_technologies(self):
        """Aggregated label values lose series identity, so duplicate metric-label claims are unsafe."""
        technologies = [
            {"key": "a", "name": "A", "match": {"label": {
                "metric": "target_info", "key": "telemetry_sdk_name", "values": ["a"],
            }}},
            {"key": "b", "name": "B", "match": {"label": {
                "metric": "target_info", "key": "telemetry_sdk_name", "values": ["b"],
            }}},
        ]
        with self.assertRaises(technology_registry.RegistryError):
            self._load(technologies)

    def test_label_evidence_classifies_only_the_bounded_match_key(self):
        registry = self._load([{"key": "sdk", "name": "SDK", "match": {"label": {
            "metric": "target_info", "key": "telemetry_sdk_name", "values": ["opentelemetry"],
        }}}])
        absent = technology_registry.classify(["target_info"], registry)
        present = technology_registry.classify(
            ["target_info"], registry, label_matches=["sdk"]
        )
        self.assertEqual(absent["technologies"], [])
        self.assertEqual([row["key"] for row in present["technologies"]], ["sdk"])
        self.assertEqual(present["matched_metric_name_count"], 1)

    def test_label_matcher_without_values_means_any_nonempty_value(self):
        registry = self._load([{"key": "sdk", "name": "SDK", "match": {"label": {
            "metric": "target_info", "key": "telemetry_sdk_name",
        }}}])
        self.assertEqual(
            technology_registry.match_label_values(
                "target_info", "telemetry_sdk_name", ["implementation"], registry
            ),
            ("sdk",),
        )
        self.assertEqual(
            technology_registry.match_label_values(
                "target_info", "telemetry_sdk_name", [], registry
            ),
            (),
        )

    def test_label_and_name_match_for_one_metric_is_ambiguous(self):
        """Label evidence must not silently override a technology already claiming the metric name."""
        registry = self._load([
            {"key": "name", "name": "Name", "match": {"exact": "target_info"}},
            {"key": "label", "name": "Label", "match": {"label": {
                "metric": "target_info", "key": "telemetry_sdk_name", "values": ["opentelemetry"],
            }}},
        ])
        with self.assertRaises(technology_registry.AmbiguousMatch):
            technology_registry.classify(
                ["target_info"], registry, label_matches=["label"]
            )

    def test_any_of_and_pattern_match_for_one_metric_is_ambiguous(self):
        registry = self._load([
            {"key": "names", "name": "Names", "match": {"any_of": ["shared_metric"]}},
            {"key": "pattern", "name": "Pattern", "match": {
                "pattern": {"prefix": "shared", "suffix": "metric"},
            }},
        ])
        with self.assertRaises(technology_registry.AmbiguousMatch):
            technology_registry.classify(["shared_metric"], registry)

    def test_unknown_or_inconsistent_label_evidence_is_refused(self):
        registry = self._load([{"key": "sdk", "name": "SDK", "match": {"label": {
            "metric": "target_info", "key": "telemetry_sdk_name", "values": ["opentelemetry"],
        }}}])
        for names, matches in ((["target_info"], ["unknown"]), ([], ["sdk"])):
            with self.subTest(names=names, matches=matches), self.assertRaises(
                technology_registry.RegistryError
            ):
                technology_registry.classify(names, registry, label_matches=matches)


if __name__ == "__main__":
    unittest.main()
