"""Product identity seams used by immutable customer consumers."""

from __future__ import annotations

import json
import os
import pathlib
import unittest
from unittest import mock

from collector import identity

ROOT = pathlib.Path(__file__).resolve().parent.parent


class MetricIdentityTest(unittest.TestCase):
    def test_alternate_prefix_changes_names_but_never_labels(self):
        labels = {"stack": "stack001", "kind": "measured"}
        with mock.patch.dict(os.environ, {"GCINSIGHT_METRIC_PREFIX": "customer_insight"}):
            got = identity.externalize_metrics([
                ("gcinsight_estate_stacks", labels, 1.0),
            ])
        self.assertEqual(got, [("customer_insight_estate_stacks", labels, 1.0)])

    def test_alternate_prefix_refuses_foreign_core_metric(self):
        with mock.patch.dict(os.environ, {"GCINSIGHT_METRIC_PREFIX": "customer_insight"}):
            with self.assertRaises(identity.InvalidIdentity):
                identity.external_metric_name("some_other_product_total")

    def test_carry_state_name_normalises_to_canonical(self):
        with mock.patch.dict(os.environ, {"GCINSIGHT_METRIC_PREFIX": "customer_insight"}):
            self.assertEqual(
                identity.canonical_metric_name("customer_insight_maturity_score"),
                "gcinsight_maturity_score",
            )


class RuntimeProjectionTest(unittest.TestCase):
    def _complete(self, kind: str) -> dict[str, str]:
        return {name: f"value-{index}" for index, name in enumerate(identity.PROJECTION_ENVS[kind])}

    def test_digest_is_over_exact_consumed_fields_and_excludes_provenance(self):
        env = self._complete("scan")
        first = identity.projection_digest("scan", env)
        env["GCINSIGHT_OVERLAY_DIGEST"] = "not-a-runtime-input"
        env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] = "not-self-referential"
        self.assertEqual(identity.projection_digest("scan", env), first)

    def test_customer_runtime_refuses_a_wrong_projection(self):
        env = self._complete("provisioner")
        env["GCINSIGHT_REQUIRE_EXPLICIT_CONFIG"] = "1"
        env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] = "0" * 64
        with self.assertRaises(identity.InvalidIdentity):
            identity.verify_runtime_projection("provisioner", environ=env)

    def test_customer_runtime_accepts_the_exact_projection(self):
        env = self._complete("scan")
        env["GCINSIGHT_REQUIRE_EXPLICIT_CONFIG"] = "1"
        env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] = identity.projection_digest("scan", env)
        self.assertEqual(
            identity.verify_runtime_projection("scan", environ=env),
            env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"],
        )

    def test_customer_runtime_accepts_an_empty_opt_out_policy(self):
        env = self._complete("scan")
        env["GCINSIGHT_OPT_OUT"] = ""
        env["GCINSIGHT_REQUIRE_EXPLICIT_CONFIG"] = "1"
        env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] = identity.projection_digest("scan", env)
        self.assertEqual(
            identity.verify_runtime_projection("scan", environ=env),
            env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"],
        )

    def test_alert_projection_owns_display_and_routing_identity(self):
        self.assertTrue({
            "GCINSIGHT_ALERT_TITLE_PREFIX",
            "GCINSIGHT_ALERT_TITLE_SEPARATOR",
            "GCINSIGHT_ALERT_SERVICE_LABEL",
        }.issubset(identity.ALERT_ENV))


class CrossLayerIdentityTest(unittest.TestCase):
    def test_ssm_prefix_is_wired_through_both_tasks_and_both_code_paths(self):
        collector = (ROOT / "collector" / "credentials.py").read_text()
        provision = (ROOT / "collector" / "provision.py").read_text()
        scan_tf = (ROOT / "terraform" / "ecs.tf").read_text()
        provision_tf = (ROOT / "terraform" / "provisioner.tf").read_text()
        for source in (collector, provision):
            self.assertIn('identity.env("GCINSIGHT_STACK_TOKEN_PREFIX"', source)
        for source in (scan_tf, provision_tf):
            self.assertIn('name = "GCINSIGHT_STACK_TOKEN_PREFIX", value = var.stack_token_prefix', source)

    def test_provisioner_persistent_identity_fields_have_environment_seams(self):
        source = (ROOT / "collector" / "provision.py").read_text()
        for name in (
            "GCINSIGHT_ROLE_NAME", "GCINSIGHT_ROLE_DISPLAY", "GCINSIGHT_ROLE_GROUP",
            "GCINSIGHT_READER_SA_NAME", "GCINSIGHT_ADMIN_SA_NAME",
            "GCINSIGHT_TOKEN_NAME_PREFIX",
        ):
            self.assertIn(name, source)

    def test_alert_uid_mapping_has_exact_closed_keys(self):
        default = {
            "coverage": "c", "staleness_t1": "1", "staleness_t2": "2",
            "staleness_t3": "3", "staleness_t4": "4", "input": "i",
            "credential_gap": "g",
        }
        with mock.patch.dict(os.environ, {
            "GCINSIGHT_ALERT_RULE_UIDS_JSON": json.dumps({**default, "extra": "x"})
        }):
            with self.assertRaises(identity.InvalidIdentity):
                identity.json_mapping("GCINSIGHT_ALERT_RULE_UIDS_JSON", default)


if __name__ == "__main__":
    unittest.main()
