"""Public-documentation evidence and synthetic matching for GCI-0031."""

from __future__ import annotations

import json
import pathlib
import unittest

from collector import technology_registry


ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "collector" / "technology-registry.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "gci_0031_technology_metric_names.json"


class GCI0031TechnologySentinelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_registry = json.loads(REGISTRY_PATH.read_text())
        cls.registry = technology_registry.load(REGISTRY_PATH)
        cls.fixture = json.loads(FIXTURE_PATH.read_text())

    def test_registered_sentinels_have_primary_documentation_provenance(self):
        evidence = self.raw_registry["research"]
        entries = {entry["key"]: entry for entry in self.raw_registry["technologies"]}
        accepted = {item["key"]: item for item in evidence["accepted"]}

        self.assertEqual(set(accepted), {"clickhouse", "cockroachdb"})
        for key, item in accepted.items():
            with self.subTest(key=key):
                entry = entries[key]
                self.assertEqual(entry["match"], {"exact": item["metric_name"]})
                self.assertTrue(item["description"])
                self.assertTrue(item["emitter"])
                self.assertTrue(item["version_scope"])
                self.assertTrue(item["documentation"])
                self.assertTrue(all(url.startswith("https://") for url in item["documentation"]))

    def test_unsupported_candidates_stay_unregistered_with_reasons(self):
        evidence = self.raw_registry["research"]
        keys = {entry["key"] for entry in self.raw_registry["technologies"]}
        omitted = {item["key"]: item for item in evidence["omitted"]}

        self.assertEqual(set(omitted), {"cilium", "istio"})
        for key, item in omitted.items():
            with self.subTest(key=key):
                self.assertNotIn(key, keys)
                self.assertTrue(item["metric_name"])
                self.assertTrue(item["description"])
                self.assertTrue(item["emitter"])
                self.assertTrue(item["version_scope"])
                self.assertTrue(item["documentation"])
                self.assertTrue(item["reason"])

    def test_synthetic_fixture_matches_only_the_accepted_sentinels(self):
        result = technology_registry.classify(
            self.fixture["metric_names"], self.registry
        )

        self.assertEqual(
            {row["key"] for row in result["technologies"]},
            set(self.fixture["expected_technology_keys"]),
        )
        self.assertEqual(
            result["unmatched_metric_names"],
            self.fixture["expected_unmatched_metric_names"],
        )


if __name__ == "__main__":
    unittest.main()
