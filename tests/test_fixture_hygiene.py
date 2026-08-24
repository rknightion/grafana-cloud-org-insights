"""The published fixtures contain synthetic identifiers, not deployment identifiers."""

from __future__ import annotations

import json
import pathlib
import re
import unittest

from bin import make_compose_fixture


ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTDATA = ROOT / "testdata"
COMPOSE = ROOT / "tests" / "fixtures" / "compose_inputs.json"

STACK_RANGE = range(5_000_000, 6_000_000)
METRICS_RANGE = range(6_000_000, 7_000_000)
LOGS_RANGE = range(7_000_000, 8_000_000)
TRACES_RANGE = range(8_000_000, 9_000_000)
ALERTS_RANGE = range(9_000_000, 10_000_000)
K6_RANGE = range(10_000_000, 11_000_000)
DATASOURCE_RANGE = range(20_000, 30_000)
GRAFANA_INSTANCE_RANGE = range(30_000, 40_000)
USER_RANGE = range(40_000, 50_000)
SYNTHETIC_ORG_ID = 900_001

INSTANCE_RANGE_BY_TYPE = {
    "grafana": STACK_RANGE,
    "metrics": METRICS_RANGE,
    "logs": LOGS_RANGE,
    "traces": TRACES_RANGE,
    "alerts": ALERTS_RANGE,
}
SYNTHETIC_SLUG = re.compile(
    r"^(?:stack\d{3}[a-z]?|obs-hub(?:-dev)?|test(?:stack|srobot(?:delete)?|lab)?\d+)$"
)


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def ids_for(stack: dict) -> set[str]:
    fields = (
        "id", "hmInstancePromId", "hmInstanceGraphiteId", "hlInstanceId", "htInstanceId",
        "hpInstanceId", "amInstanceId", "agentManagementInstanceId", "k6OrgId",
    )
    return {str(stack[field]) for field in fields if stack.get(field) is not None}


class SyntheticIdentifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = load(TESTDATA / "gcom-instances-2026-08-17.json")["items"]
        cls.by_slug = {str(s["slug"]): s for s in cls.inventory}
        cls.allowed_ids = set().union(*(ids_for(s) for s in cls.inventory))

    def assert_synthetic_instance_id(self, value: object, instance_type: str) -> None:
        self.assertIn(int(value), INSTANCE_RANGE_BY_TYPE[instance_type])

    def assert_synthetic_slug(self, value: object) -> None:
        self.assertRegex(str(value), SYNTHETIC_SLUG)

    def test_inventory_uses_reserved_synthetic_namespaces(self):
        for stack in self.inventory:
            with self.subTest(stack=stack["slug"]):
                self.assertIn(int(stack["id"]), STACK_RANGE)
                self.assertEqual(stack["hpInstanceId"], stack["id"])
                self.assertEqual(stack["agentManagementInstanceId"], stack["id"])
                self.assertIn(int(stack["hmInstancePromId"]), METRICS_RANGE)
                self.assertIn(int(stack["hmInstanceGraphiteId"]), METRICS_RANGE)
                self.assertIn(int(stack["hlInstanceId"]), LOGS_RANGE)
                self.assertIn(int(stack["htInstanceId"]), TRACES_RANGE)
                self.assertIn(int(stack["amInstanceId"]), ALERTS_RANGE)
                if stack.get("k6OrgId") is not None:
                    self.assertIn(int(stack["k6OrgId"]), K6_RANGE)

    def test_usage_label_values_use_reserved_instance_namespaces(self):
        for value in load(TESTDATA / "ui-instance-ids.json")["data"]:
            with self.subTest(instance_id=value):
                self.assertTrue(any(int(value) in namespace
                                    for namespace in INSTANCE_RANGE_BY_TYPE.values()))
                self.assertIn(str(value), self.allowed_ids)

    def test_usage_series_ids_match_their_reserved_signal_namespace(self):
        for row in load(TESTDATA / "ui-series-pairs.json")["data"]:
            with self.subTest(instance_type=row["instance_type"],
                              instance_id=row["instance_id"]):
                self.assert_synthetic_instance_id(row["instance_id"], row["instance_type"])
                self.assertEqual(int(row["org_id"]), SYNTHETIC_ORG_ID)
                self.assertIn(str(row["instance_id"]), self.allowed_ids)

    def test_region_map_ids_match_their_reserved_signal_namespace(self):
        for region in load(TESTDATA / "region-map.json").values():
            self.assert_synthetic_slug(region["slug"])
            for value, instance_type in region["pairs"]:
                with self.subTest(instance_type=instance_type, instance_id=value):
                    self.assert_synthetic_instance_id(value, instance_type)

    def test_otlp_evidence_uses_synthetic_metrics_ids_and_slugs(self):
        for row in load(TESTDATA / "otlp-floor.json")["stacks"]:
            with self.subTest(stack=row["slug"]):
                self.assert_synthetic_instance_id(row["metrics_instance_id"], "metrics")
                if row["slug"] is not None:
                    self.assert_synthetic_slug(row["slug"])
                    self.assertEqual(
                        int(row["metrics_instance_id"]),
                        int(self.by_slug[row["slug"]]["hmInstancePromId"]),
                    )

    def test_auxiliary_fixtures_use_reserved_local_identifier_namespaces(self):
        users = load(TESTDATA / "gcom-instance-users.json")["items"]
        self.assertTrue(all(int(user["id"]) in USER_RANGE for user in users))

        datasources = load(TESTDATA / "gcom-instance-datasources.json")["items"]
        self.assertTrue(all(int(ds["id"]) in DATASOURCE_RANGE for ds in datasources))
        self.assertTrue(all(int(ds["instanceId"]) in GRAFANA_INSTANCE_RANGE
                            for ds in datasources))
        for datasource in datasources:
            auth_user = str(datasource.get("basicAuthUser") or "")
            if auth_user.isdigit():
                value = int(auth_user)
                self.assertTrue(value == SYNTHETIC_ORG_ID or any(
                    value in namespace for namespace in INSTANCE_RANGE_BY_TYPE.values()
                ))
            json_data = datasource.get("jsonData", {})
            if json_data.get("stackId") is not None:
                self.assertIn(int(json_data["stackId"]), STACK_RANGE)
            if json_data.get("orgId") is not None:
                self.assertEqual(int(json_data["orgId"]), SYNTHETIC_ORG_ID)

    def test_compose_fixture_uses_synthetic_stack_and_realm_ids(self):
        data = load(COMPOSE)
        stack_ids = {str(s["id"]) for s in data["stacks"]}
        self.assertTrue(all(int(value) in STACK_RANGE for value in stack_ids))
        for stack in data["stacks"]:
            with self.subTest(stack=stack["slug"]):
                self.assertEqual(int(stack["orgId"]), SYNTHETIC_ORG_ID)
                self.assertEqual(stack["hpInstanceId"], stack["id"])
                self.assertEqual(stack["agentManagementInstanceId"], stack["id"])
                self.assertIn(int(stack["hmInstancePromId"]), METRICS_RANGE)
                self.assertIn(int(stack["hmInstanceGraphiteId"]), METRICS_RANGE)
                self.assertIn(int(stack["hlInstanceId"]), LOGS_RANGE)
                self.assertIn(int(stack["htInstanceId"]), TRACES_RANGE)
                self.assertIn(int(stack["amInstanceId"]), ALERTS_RANGE)
        for policy in data["access_policies"]:
            self.assertRegex(policy["name"], r"^policy\d{3}$")
            for realm in policy.get("realms", []):
                value = str(realm.get("identifier", ""))
                if realm.get("type") == "stack":
                    self.assertIn(int(value), STACK_RANGE)
                elif realm.get("type") == "org":
                    self.assertEqual(int(value), SYNTHETIC_ORG_ID)

    def test_fixture_stack_slugs_are_synthetic(self):
        compose = load(COMPOSE)
        for stack in [*self.inventory, *compose["stacks"]]:
            self.assert_synthetic_slug(stack["slug"])

    def test_generated_view_stack_columns_use_synthetic_slugs(self):
        for path in sorted((TESTDATA / "views").glob("*.json")):
            for row in load(path).get("rows", []):
                for key, value in row.items():
                    if key.strip().lower() in {"stack", "slug"} and value:
                        with self.subTest(view=path.name, column=key, value=value):
                            self.assert_synthetic_slug(value)

    def test_fixture_human_names_follow_the_synthetic_convention(self):
        compose = load(COMPOSE)
        for record in compose["stack_detail"].values():
            for user in record.get("users", []):
                name = str(user.get("name") or "")
                if name:
                    self.assertRegex(name, r"\d{2}$")

    def test_live_fixture_export_cannot_overwrite_the_committed_fixture(self):
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            make_compose_fixture.output_path(str(COMPOSE))

        export = make_compose_fixture.output_path("/tmp/gcinsight-live-compose.json")
        self.assertNotEqual(export, COMPOSE.resolve())


if __name__ == "__main__":
    unittest.main()
