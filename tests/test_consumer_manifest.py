"""Reusable deployment-manifest, upgrade, and local-build contracts."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from collector import identity, provision

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "consumer_manifest", ROOT / "bin" / "consumer_manifest.py"
)
assert SPEC and SPEC.loader
consumer_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer_manifest)


def fixture(revision: str | None = None) -> dict:
    if revision is None:
        revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout.strip()
    runtime = {
        kind: {name: f"value-{kind}-{index}" for index, name in enumerate(names)}
        for kind, names in identity.PROJECTION_ENVS.items()
    }
    runtime["scan"]["GCINSIGHT_ORG_ID"] = "123456"
    runtime["provisioner"]["GCINSIGHT_ORG_ID"] = "123456"
    runtime["scan"]["GCINSIGHT_STACK_TOKEN_PREFIX"] = "/example/token"
    runtime["provisioner"]["GCINSIGHT_STACK_TOKEN_PREFIX"] = "/example/token"
    runtime["scan"]["GCINSIGHT_OPT_OUT"] = ""
    runtime["provisioner"]["GCINSIGHT_OPT_OUT"] = ""
    runtime["provisioner"]["GCINSIGHT_READER_PRODUCT_READS"] = ""
    runtime["scan"]["GCINSIGHT_READER_PRODUCT_READS"] = ""
    runtime["scan"].update(identity.LABEL_INVENTORY_DEFAULTS)
    runtime["scan"]["GCINSIGHT_DASHBOARD_DETAIL_ENABLED"] = "0"
    runtime["scan"]["GCINSIGHT_EXPECTED_RETENTION_POLICY"] = "[]"
    runtime["scan"]["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"] = json.dumps({
        key: 1 for key in ("metrics", "logs", "traces", "profiles", "dashboard", "alert", "slo")
    })
    body = {
        "schema_version": 1,
        "generic_source": {
            "repository": "https://github.com/rknightion/grafana-cloud-org-insights.git",
            "revision": revision,
        },
        "overlay_digest": "0" * 64,
        "runtime_projection_digests": {kind: "0" * 64 for kind in runtime},
        "runtime": runtime,
        "aws": {
            "name_prefix": "example-insights",
            "bucket_name": "example-insights",
            "secret_name": "example/insights",
            "reader_secret_key": "ORG_READ_TOKEN",
            "writer_secret_key": "WRITE_TOKEN",
            "provisioner_secret_key": "PROVISION_TOKEN",
            "create_bucket": False,
            "create_secret": False,
            "create_views_reader_user": False,
            "create_provisioner": True,
            "firehose_logs_enabled": False,
            "firehose_log_subscription_enabled": False,
            "assign_public_ip": False,
            "schedules_enabled": True,
            "provisioner_enabled": True,
            "schedule_timezone": "UTC",
            "t1_schedule": "cron(5 * * * ? *)",
            "t2_schedule": "cron(20 3 * * ? *)",
            "t3_schedule": "cron(40 2,8,14,20 * * ? *)",
            "t4_schedule": "cron(0 9 * * ? *)",
            "provisioner_schedule": "cron(35 3 * * ? *)",
            "task_architecture": "ARM64",
            "cost_namespace": "example-insights",
            "purpose_tag": "estate-insights",
        },
        "policy": {
            "reader_policy_id": "reader-id",
            "writer_policy_id": "writer-id",
            "reader_policy_name": "insights-reader",
            "writer_policy_name": "insights-writer",
            "provisioner_policy_name": "insights-provisioner",
            "declared_reader_permission_pairs": len(provision.DESIRED_PAIRS),
            "datasource_query_scope": "datasources:uid:grafanacloud-usage-insights",
            "rate_card_present": False,
            "rate_card_s3_key": "config/ratecard.csv",
            "rate_card_semantics": "base_rate_only",
            "public_dashboards_target": 0,
            "pii_storage": "cleartext-internal",
        },
    }
    return consumer_manifest.regenerate(body)


class ManifestValidationTest(unittest.TestCase):
    def test_complete_manifest_validates_and_all_digests_are_deterministic(self):
        body = fixture()
        consumer_manifest.validate(body)
        overlay_digest, projections = consumer_manifest.calculated_digests(body)
        self.assertEqual(body["overlay_digest"], overlay_digest)
        self.assertEqual(body["runtime_projection_digests"], projections)

    def test_additive_label_policy_preserves_old_digest_and_regenerates_explicit_defaults(self):
        body = fixture()
        for name in identity.LABEL_INVENTORY_DEFAULTS:
            body["runtime"]["scan"].pop(name)
        body["overlay_digest"], body["runtime_projection_digests"] = consumer_manifest.calculated_digests(body)
        consumer_manifest.validate(body)
        old = body["runtime_projection_digests"]["scan"]
        upgraded = consumer_manifest.regenerate(body)
        self.assertNotEqual(old, upgraded["runtime_projection_digests"]["scan"])
        for name, default in identity.LABEL_INVENTORY_DEFAULTS.items():
            self.assertNotIn(name, body["runtime"]["scan"])
            self.assertEqual(upgraded["runtime"]["scan"][name], default)
        body["runtime"]["scan"]["GCINSIGHT_LABEL_INVENTORY_ENABLED"] = "0"
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "keys differ"):
            consumer_manifest.validate(body)

    def test_label_policy_canonicalization_and_invalid_limits(self):
        body = fixture()
        body["runtime"]["scan"]["GCINSIGHT_LABEL_INVENTORY_TUNABLES"] = '{"coverage_floor": 1.0}'
        one = consumer_manifest.regenerate(body)
        body["runtime"]["scan"]["GCINSIGHT_LABEL_INVENTORY_TUNABLES"] = '{ "coverage_floor":1 }'
        two = consumer_manifest.regenerate(body)
        self.assertEqual(one["runtime_projection_digests"], two["runtime_projection_digests"])
        for name, value in (("TUNABLES", '{"coverage_floor":0.7}'),
                            ("STATIC_NAMES", '["invalid value"]'),
                            ("BUDGET_SECONDS", "900.0"), ("ENABLED", "true")):
            bad = fixture()
            bad["runtime"]["scan"]["GCINSIGHT_LABEL_INVENTORY_" + name] = value
            with self.assertRaises(consumer_manifest.ManifestError):
                consumer_manifest.regenerate(bad)

    def test_regenerate_reports_a_malformed_manifest_as_a_contract_error(self):
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "runtime projection object"):
            consumer_manifest.regenerate({})

    def test_runtime_contract_is_exact(self):
        body = fixture()
        body["runtime"]["scan"].pop("GCINSIGHT_ORG_ID")
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "runtime.scan keys differ"):
            consumer_manifest.validate(body)

    def test_values_terraform_cannot_round_trip_are_rejected(self):
        body = fixture()
        body["runtime"]["scan"]["GCINSIGHT_DASHBOARD_DETAIL_ENABLED"] = "true"
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "must be 1 or 0"):
            consumer_manifest.validate(consumer_manifest.regenerate(body))
        body = fixture()
        body["runtime"]["provisioner"]["GCINSIGHT_OPT_OUT"] = "stack-a"
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "OPT_OUT must be identical"):
            consumer_manifest.validate(consumer_manifest.regenerate(body))

    def test_digest_drift_is_rejected(self):
        body = fixture()
        body["runtime"]["scan"]["GCINSIGHT_USER_AGENT"] = "changed-user-agent"
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "overlay_digest"):
            consumer_manifest.validate(body)

    def test_credential_markers_are_rejected(self):
        body = fixture()
        body["runtime"]["scan"]["GCINSIGHT_USER_AGENT"] = "Bearer example"
        body["overlay_digest"], body["runtime_projection_digests"] = (
            consumer_manifest.calculated_digests(body)
        )
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "credential marker"):
            consumer_manifest.validate(body)

    def test_permission_count_must_match_the_product_role(self):
        body = fixture()
        body["policy"]["declared_reader_permission_pairs"] += 1
        body["overlay_digest"], body["runtime_projection_digests"] = (
            consumer_manifest.calculated_digests(body)
        )
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "permission-pair count"):
            consumer_manifest.validate(body)

    def test_boolean_is_not_accepted_as_an_integer_policy_count(self):
        body = fixture()
        body["policy"]["public_dashboards_target"] = False
        body["overlay_digest"], body["runtime_projection_digests"] = (
            consumer_manifest.calculated_digests(body)
        )
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "non-negative integer"):
            consumer_manifest.validate(body)

    def test_environment_projection_includes_fail_closed_controls(self):
        body = fixture()
        with tempfile.TemporaryDirectory() as name:
            path = pathlib.Path(name) / "manifest.json"
            consumer_manifest.write_json(path, body)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                consumer_manifest.command_env(argparse.Namespace(manifest=path, kind="alerts"))
        lines = output.getvalue().splitlines()
        self.assertIn("GCINSIGHT_REQUIRE_EXPLICIT_CONFIG=1", lines)
        self.assertIn(
            "GCINSIGHT_RUNTIME_CONFIG_DIGEST=" + body["runtime_projection_digests"]["alerts"],
            lines,
        )

    def test_product_reader_setting_is_part_of_the_provisioner_projection_and_defaults_empty(self):
        body = fixture()
        self.assertEqual(body["runtime"]["provisioner"]["GCINSIGHT_READER_PRODUCT_READS"], "")
        consumer_manifest.validate(body)


class RenderedEnvironmentParityTest(unittest.TestCase):
    """GCI-0045. The manifest digest must equal the digest of the env Terraform actually renders.

    Terraform passes JSON values through `jsonencode(jsondecode(...))`, which sorts keys and writes an
    integral float as an integer. A wave 2 dev rollout hashed the raw manifest string instead, and T2
    refused to start on a policy both sides held identically.
    """

    def test_a_retention_policy_in_either_key_order_matches_the_rendered_environment(self):
        body = fixture()
        body["runtime"]["scan"]["GCINSIGHT_EXPECTED_RETENTION_POLICY"] = (
            '[{"selector": "{kind=\\"auditing\\"}", "minimum_period": "120d"}]')
        weights = json.loads(body["runtime"]["scan"]["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"])
        weights.update(metrics=1.0, logs=2)
        body["runtime"]["scan"]["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"] = json.dumps(weights)
        body = consumer_manifest.regenerate(body)
        rendered = dict(body["runtime"]["scan"])
        # Exactly what `jsonencode(jsondecode(value))` emits for these two values.
        rendered["GCINSIGHT_EXPECTED_RETENTION_POLICY"] = (
            '[{"minimum_period":"120d","selector":"{kind=\\"auditing\\"}"}]')
        rendered["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"] = (
            '{"alert":1,"dashboard":1,"logs":2,"metrics":1,"profiles":1,"slo":1,"traces":1}'
        )
        self.assertEqual(body["runtime_projection_digests"]["scan"],
                         identity.projection_digest("scan", rendered))


class TerraformVariableTypeParityTest(unittest.TestCase):
    def test_coerced_or_lossy_json_is_rejected_before_digesting(self):
        weights = json.loads(fixture()["runtime"]["scan"]["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"])
        cases = [
            ("GCINSIGHT_EXPECTED_RETENTION_POLICY", '[{"selector":"{}","minimum_period":"24h","extra":1}]'),
            ("GCINSIGHT_EXPECTED_RETENTION_POLICY", '[{"selector":2,"minimum_period":"24h"}]'),
            ("GCINSIGHT_EXPECTED_RETENTION_POLICY", '[{"selector":"{}"}]'),
            ("GCINSIGHT_EXPECTED_RETENTION_POLICY", '{}'),
            ("GCINSIGHT_EXPECTED_RETENTION_POLICY", 'not-json'),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", json.dumps(dict(weights, metrics="2"))),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", json.dumps(dict(weights, metrics=True))),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", json.dumps(dict(weights, extra=1))),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", '{}'),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", json.dumps(weights).replace('"metrics": 1', '"metrics": 1e100')),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", json.dumps(weights).replace('"metrics": 1', '"metrics": 1e-1000')),
            ("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", json.dumps(dict(weights, metrics=float("nan")))),
        ]
        for env, raw in cases:
            with self.subTest(env=env, raw=raw):
                body = fixture()
                body["runtime"]["scan"][env] = raw
                body["overlay_digest"], body["runtime_projection_digests"] = (
                    consumer_manifest.calculated_digests(body)
                )
                for operation in (consumer_manifest.validate, consumer_manifest.regenerate):
                    with self.assertRaisesRegex(consumer_manifest.ManifestError, env):
                        operation(body)

    def test_cli_commands_reject_bad_types_without_writing_or_checking_checkout(self):
        with tempfile.TemporaryDirectory() as name:
            path = pathlib.Path(name) / "manifest.json"
            body = fixture()
            body["runtime"]["scan"]["GCINSIGHT_EXPECTED_RETENTION_POLICY"] = (
                '[{"selector":"{}","minimum_period":"24h","extra":1}]'
            )
            path.write_text(consumer_manifest.json_text(body))
            original = path.read_bytes()
            for command in ("regenerate", "check"):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(consumer_manifest.main([
                        command, "--manifest", str(path)
                    ]), 2)
                self.assertEqual(path.read_bytes(), original)

    def test_real_module_types_and_env_expressions_round_trip_offline(self):
        # No provider, backend, network, or apply: console evaluates the actual variable declarations
        # and the same jsonencode expressions used by the ECS task definition.
        weights = json.loads(fixture()["runtime"]["scan"]["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"])
        retention = [{"selector": '{kind="auditing"}', "minimum_period": "24h"}]
        cases = [
            ([], dict(weights, metrics=1.0, logs=2), [], dict(weights, metrics=1.0, logs=2)),
            (retention, dict(weights, metrics=0.125, logs=2),
             retention, dict(weights, metrics=0.125, logs=2)),
            ([], dict(weights, metrics=9007199254740993),
             [], dict(weights, metrics=9007199254740993)),
            # Coercible input is rejected, but its explicitly corrected manifest hashes exactly as
            # the module renders the original input (extra attributes removed, strings converted).
            (retention, weights, [dict(retention[0], extra="discarded")], weights),
            ([], dict(weights, metrics=2), [], dict(weights, metrics="2")),
        ]
        inputs = consumer_manifest.module_env_inputs(ROOT / "terraform")["scan"]
        with tempfile.TemporaryDirectory() as name:
            temp = pathlib.Path(name)
            shutil.copyfile(ROOT / "terraform" / "variables.tf", temp / "variables.tf")
            for retention, scores, tofu_retention, tofu_scores in cases:
                body = fixture()
                scan = body["runtime"]["scan"]
                scan["GCINSIGHT_EXPECTED_RETENTION_POLICY"] = json.dumps(retention)
                scan["GCINSIGHT_COVERAGE_SCORE_WEIGHTS"] = json.dumps(scores)
                body = consumer_manifest.regenerate(body)
                if (retention, scores) != (tofu_retention, tofu_scores):
                    rejected = fixture()
                    rejected["runtime"]["scan"].update({
                        "GCINSIGHT_EXPECTED_RETENTION_POLICY": json.dumps(tofu_retention),
                        "GCINSIGHT_COVERAGE_SCORE_WEIGHTS": json.dumps(tofu_scores),
                    })
                    with self.assertRaises(consumer_manifest.ManifestError):
                        consumer_manifest.regenerate(rejected)
                (temp / "contract.auto.tfvars.json").write_text(json.dumps({
                    "name_prefix": "example-insights", "grafana_org_id": "123456",
                    "write_stack_slug": "example", "mimir_write_url": "https://example.invalid",
                    "mimir_tenant": "1", "loki_write_url": "https://example.invalid",
                    "loki_tenant": "1", "subnet_ids": ["subnet-example"],
                    "expected_retention_policy": tofu_retention, "coverage_score_weights": tofu_scores,
                }))
                expressions = {env: inputs[env][1] for env in (
                    "GCINSIGHT_EXPECTED_RETENTION_POLICY", "GCINSIGHT_COVERAGE_SCORE_WEIGHTS"
                )}
                expression = "jsonencode({" + ",".join(
                    f'{env} = {expr}' for env, expr in expressions.items()
                ) + "})"
                result = subprocess.run(
                    ["tofu", "console", "-no-color"], cwd=temp, input=expression + "\n",
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered = dict(scan, **json.loads(json.loads(result.stdout)))
                self.assertEqual(body["runtime_projection_digests"]["scan"],
                                 identity.projection_digest("scan", rendered))


CONSUMER_TF = """
module "insights" {
  source = "git::https://github.com/rknightion/grafana-cloud-org-insights.git//terraform?ref=%s"

  grafana_org_id            = local.scan.GCINSIGHT_ORG_ID
  fleet_default_scrape_interval = local.scan.GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL
  coverage_score_weights = jsondecode(
    local.scan.GCINSIGHT_COVERAGE_SCORE_WEIGHTS
  )
  %s
}
""" % ("a" * 40, "%s")


class TerraformWiringPreflightTest(unittest.TestCase):
    """GCI-0045 AC2. A manifest key the module block never passes renders as the module default."""

    MODULE = ROOT / "terraform"

    def _manifest(self, **scan):
        body = fixture()
        body["runtime"]["scan"].update(scan)
        return body

    def _gaps(self, body, extra=""):
        return [gap for gap in consumer_manifest.terraform_wiring_gaps(
            body, CONSUMER_TF % extra, self.MODULE)
            if "FLEET_DEFAULT" in gap or "COVERAGE" in gap or "DASHBOARD_DETAIL" in gap]

    def test_an_unwired_non_default_value_is_caught(self):
        body = self._manifest(GCINSIGHT_DASHBOARD_DETAIL_ENABLED="1")
        self.assertEqual(len(self._gaps(body)), 1)
        self.assertIn("GCINSIGHT_DASHBOARD_DETAIL_ENABLED", self._gaps(body)[0])

    def test_an_unwired_value_equal_to_the_module_default_is_accepted(self):
        body = self._manifest(GCINSIGHT_DASHBOARD_DETAIL_ENABLED="0")
        self.assertEqual(self._gaps(body), [])

    def test_a_wired_value_is_accepted_and_a_wrongly_sourced_one_is_not(self):
        body = self._manifest(GCINSIGHT_DASHBOARD_DETAIL_ENABLED="1")
        wired = 'dashboard_detail_enabled = local.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED == "1"'
        self.assertEqual(self._gaps(body, wired), [])
        self.assertEqual(len(self._gaps(body, "dashboard_detail_enabled = true")), 1)

    def test_every_projected_key_is_checked_or_explicitly_unchecked(self):
        """A module env entry the preflight stops parsing must show up here, not vanish silently."""
        inputs = consumer_manifest.module_env_inputs(self.MODULE)
        for kind, names in (("scan", identity.SCAN_ENV), ("provisioner", identity.PROVISIONER_ENV)):
            with self.subTest(kind=kind):
                unchecked = set(names) - set(inputs[kind])
                self.assertEqual(unchecked, set(consumer_manifest.UNCHECKED_PROJECTED_ENV) & set(names))

    def test_a_comment_or_identifier_mentioning_module_does_not_move_the_block(self):
        body = self._manifest(GCINSIGHT_DASHBOARD_DETAIL_ENABLED="1")
        wired = 'dashboard_detail_enabled = local.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED == "1"'
        text = (CONSUMER_TF % wired).replace(
            "  source =", "  count = var.robknight_module_enabled ? 1 : 0\n  # this module is pinned\n  source =")
        gaps = [g for g in consumer_manifest.terraform_wiring_gaps(body, text, self.MODULE)
                if "DASHBOARD_DETAIL" in g or "COVERAGE" in g]
        self.assertEqual(gaps, [])

    def test_gaps_name_keys_and_never_values(self):
        body = self._manifest(GCINSIGHT_DASHBOARD_DETAIL_ENABLED="1",
                              GCINSIGHT_OPT_OUT="customer-stack-secret")
        gaps = consumer_manifest.terraform_wiring_gaps(body, CONSUMER_TF % "", self.MODULE)
        self.assertTrue(any("GCINSIGHT_OPT_OUT" in gap for gap in gaps))
        self.assertNotIn("customer-stack-secret", " ".join(gaps))


class UpgradeTest(unittest.TestCase):
    def test_remote_resolution_timeout_is_a_manifest_error(self):
        with mock.patch.object(
            consumer_manifest.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(["git", "fetch"], 120),
        ):
            with self.assertRaisesRegex(consumer_manifest.ManifestError, "timed out"):
                consumer_manifest.verify_remote_commit(ROOT, "https://github.com/example/repo", "a" * 40)

    def test_upgrade_updates_exactly_the_manifest_pin_and_module_ref(self):
        previous = "a" * 40
        target = "b" * 40
        body = fixture(previous)
        with tempfile.TemporaryDirectory() as name:
            temp = pathlib.Path(name)
            manifest = temp / "consumer.json"
            terraform = temp / "consumer.tf"
            consumer_manifest.write_json(manifest, body)
            terraform.write_text(
                'module "insights" {\n'
                '  source = "git::https://github.com/rknightion/grafana-cloud-org-insights.git//terraform'
                f'?ref={previous}"\n'
                '}\n'
            )
            args = argparse.Namespace(
                revision=target, manifest=manifest, terraform=terraform, generic_source=ROOT,
            )
            with (
                mock.patch.object(consumer_manifest, "run_git") as git,
                mock.patch.object(consumer_manifest, "verify_remote_commit") as remote,
            ):
                git.side_effect = lambda _root, *parts: (
                    body["generic_source"]["repository"] if parts[:3] == (
                        "remote", "get-url", "origin"
                    ) else (ROOT / "collector/identity.py").read_text() if parts[0] == "show" else ""
                )
                consumer_manifest.command_upgrade(args)
            remote.assert_called_once_with(
                ROOT, body["generic_source"]["repository"], target,
            )
            upgraded = json.loads(manifest.read_text())
            self.assertEqual(upgraded["generic_source"]["revision"], target)
            self.assertEqual(consumer_manifest.terraform_revision(terraform), target)
            consumer_manifest.validate(upgraded)

    def test_upgrade_rolls_back_both_files_when_the_second_write_fails(self):
        previous = "a" * 40
        target = "b" * 40
        body = fixture(previous)
        with tempfile.TemporaryDirectory() as name:
            temp = pathlib.Path(name)
            manifest = temp / "consumer.json"
            terraform = temp / "consumer.tf"
            consumer_manifest.write_json(manifest, body)
            terraform.write_text(
                'module "insights" {\n'
                '  source = "git::https://github.com/rknightion/grafana-cloud-org-insights.git//terraform'
                f'?ref={previous}"\n'
                '}\n'
            )
            original_manifest = manifest.read_text()
            original_terraform = terraform.read_text()
            args = argparse.Namespace(
                revision=target, manifest=manifest, terraform=terraform, generic_source=ROOT,
            )
            real_write = consumer_manifest.atomic_write_text
            write_count = 0

            def fail_second_write(path, text, **kwargs):
                nonlocal write_count
                write_count += 1
                if write_count == 3:
                    raise OSError("simulated manifest write failure")
                real_write(path, text, **kwargs)

            with (
                mock.patch.object(consumer_manifest, "run_git") as git,
                mock.patch.object(consumer_manifest, "verify_remote_commit"),
                mock.patch.object(
                    consumer_manifest, "atomic_write_text", side_effect=fail_second_write,
                ),
            ):
                git.side_effect = lambda _root, *parts: (
                    body["generic_source"]["repository"] if parts[:3] == (
                        "remote", "get-url", "origin"
                    ) else (ROOT / "collector/identity.py").read_text() if parts[0] == "show" else ""
                )
                with self.assertRaisesRegex(consumer_manifest.ManifestError, "rolled back"):
                    consumer_manifest.command_upgrade(args)
            self.assertEqual(manifest.read_text(), original_manifest)
            self.assertEqual(terraform.read_text(), original_terraform)
            self.assertFalse(consumer_manifest.journal_path(manifest).exists())

    def test_interrupted_upgrade_is_detected_and_recovered_before_retry(self):
        previous = "a" * 40
        target = "b" * 40
        body = fixture(previous)
        with tempfile.TemporaryDirectory() as name:
            temp = pathlib.Path(name)
            manifest = temp / "consumer.json"
            terraform = temp / "consumer.tf"
            original_manifest = consumer_manifest.json_text(body)
            original_terraform = (
                'module "insights" {\n'
                '  source = "git::https://github.com/rknightion/grafana-cloud-org-insights.git//terraform'
                f'?ref={previous}"\n'
                '}\n'
            )
            upgraded = dict(body)
            upgraded["generic_source"] = dict(body["generic_source"], revision=target)
            upgraded = consumer_manifest.regenerate(upgraded)
            target_manifest = consumer_manifest.json_text(upgraded)
            target_terraform = consumer_manifest.replaced_terraform_revision(
                original_terraform, target,
            )
            manifest.write_text(target_manifest)
            terraform.write_text(original_terraform)
            journal = consumer_manifest.journal_path(manifest)
            journal.write_text(consumer_manifest.json_text({
                "schema_version": 1,
                "manifest_path": str(manifest.resolve()),
                "terraform_path": str(terraform.resolve()),
                "original_manifest": original_manifest,
                "original_terraform": original_terraform,
                "target_manifest": target_manifest,
                "target_terraform": target_terraform,
            }))
            with self.assertRaisesRegex(consumer_manifest.ManifestError, "incomplete consumer upgrade"):
                consumer_manifest.reject_incomplete_upgrade(manifest)
            before = manifest.read_text()
            with self.assertRaisesRegex(consumer_manifest.ManifestError, "incomplete consumer upgrade"):
                consumer_manifest.command_regenerate(argparse.Namespace(manifest=manifest))
            self.assertEqual(manifest.read_text(), before)
            consumer_manifest.recover_incomplete_upgrade(manifest, terraform)
            self.assertEqual(manifest.read_text(), original_manifest)
            self.assertEqual(terraform.read_text(), original_terraform)
            self.assertFalse(journal.exists())

    def test_moving_or_short_revision_is_rejected(self):
        args = argparse.Namespace(
            revision="main", manifest=pathlib.Path("unused"),
            terraform=pathlib.Path("unused"), generic_source=ROOT,
        )
        with self.assertRaisesRegex(consumer_manifest.ManifestError, "full lowercase"):
            consumer_manifest.command_upgrade(args)


class ConsumerShellTest(unittest.TestCase):
    def run_command(self, *command: str, cwd: pathlib.Path, env=None) -> subprocess.CompletedProcess:
        merged_env = os.environ.copy()
        if env is not None:
            merged_env.update(env)
        env = merged_env
        env.setdefault(
            "GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN", "synthetic-private-identifier-[0-9]{20}"
        )
        return subprocess.run(
            list(command), cwd=cwd, env=env, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def git_repository(self, root: pathlib.Path) -> str:
        self.run_command("git", "init", "-q", "-b", "main", cwd=root)
        self.run_command("git", "config", "user.name", "Consumer Test", cwd=root)
        self.run_command("git", "config", "user.email", "consumer@example.invalid", cwd=root)
        self.run_command("git", "config", "commit.gpgsign", "false", cwd=root)
        self.run_command("git", "add", ".", cwd=root)
        self.run_command("git", "commit", "-q", "-m", "test fixture", cwd=root)
        return self.run_command("git", "rev-parse", "HEAD", cwd=root).stdout.strip()

    def clean_product_copy(self, parent: pathlib.Path) -> tuple[pathlib.Path, str]:
        product = parent / "product"
        shutil.copytree(
            ROOT, product,
            ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".terraform", "codex"),
        )
        revision = self.git_repository(product)
        self.run_command(
            "git", "remote", "add", "origin",
            "https://github.com/rknightion/grafana-cloud-org-insights.git", cwd=product,
        )
        return product, revision

    def deployment(
        self, parent: pathlib.Path, revision: str,
    ) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, dict]:
        root = parent / "deployment"
        root.mkdir()
        manifest = root / "consumer.json"
        terraform = root / "consumer.tf"
        body = fixture(revision)
        manifest.write_text(consumer_manifest.json_text(body))
        # A correctly wired consumer: every module input that renders a runtime value reads it from
        # the manifest, which is what the GCI-0045 wiring preflight now requires before a build.
        wiring = "".join(
            f"  {variable} = local.{kind}.{env}\n"
            for kind, entries in consumer_manifest.module_env_inputs(ROOT / "terraform").items()
            for env, (variable, _expr) in sorted(entries.items())
        )
        terraform.write_text(
            'module "insights" {\n'
            '  source = "git::https://github.com/rknightion/grafana-cloud-org-insights.git//terraform'
            f'?ref={revision}"\n'
            f"{wiring}"
            '}\n'
        )
        self.git_repository(root)
        return root, manifest, terraform, body

    def fake_docker(self, parent: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
        fake_bin = parent / "fake-bin"
        fake_bin.mkdir()
        log = parent / "docker.log"
        docker = fake_bin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n"
            "if [ \"$1 $2\" = 'image inspect' ]; then\n"
            "  case \"$*\" in\n"
            "    *Config.Labels*) printf '{\"org.opencontainers.image.source\":\"%s\",\"org.opencontainers.image.revision\":\"%s\",\"io.grafana.gcinsight.overlay.digest\":\"sha256:%s\",\"io.grafana.gcinsight.consumer.revision\":\"%s\"}\\n' \"$EXPECTED_SOURCE\" \"$EXPECTED_REVISION\" \"$EXPECTED_OVERLAY\" \"$EXPECTED_CONSUMER\" ;;\n"
            "    *) echo 'image=sha256:test os=linux arch=arm64 user=collector entrypoint=[python3]' ;;\n"
            "  esac\n"
            "elif [ \"$1\" = run ]; then echo verified; fi\n"
        )
        docker.chmod(0o755)
        return fake_bin, log

    def test_local_build_records_both_revisions_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as name:
            temp = pathlib.Path(name)
            product, revision = self.clean_product_copy(temp)
            deployment, manifest, terraform, body = self.deployment(temp, revision)
            fake_bin, log = self.fake_docker(temp)
            consumer_revision = self.run_command(
                "git", "rev-parse", "HEAD", cwd=deployment,
            ).stdout.strip()
            env = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DOCKER_LOG": str(log),
                "EXPECTED_SOURCE": body["generic_source"]["repository"].removesuffix(".git"),
                "EXPECTED_REVISION": revision,
                "EXPECTED_OVERLAY": body["overlay_digest"],
                "EXPECTED_CONSUMER": consumer_revision,
            }
            result = self.run_command(
                str(product / "bin" / "consumer-build"),
                "--manifest", str(manifest),
                "--deployment-root", str(deployment),
                "--terraform", str(terraform),
                "--tag", "local/test:validation",
                cwd=product, env=env,
            )
            calls = log.read_text()
            self.assertIn(f"GCINSIGHT_SOURCE_REVISION={revision}", calls)
            self.assertIn(f"GCINSIGHT_OVERLAY_DIGEST=sha256:{body['overlay_digest']}", calls)
            self.assertIn(f"GCINSIGHT_CONSUMER_REVISION={consumer_revision}", calls)
            invocations = [line.split() for line in calls.splitlines()]
            self.assertFalse(
                [parts for parts in invocations if "push" in parts or "login" in parts],
                f"docker publish invocation recorded: {calls}",
            )
            self.assertIn("local only; no registry login, push, or tag movement", result.stdout)

    def test_consumer_exec_runs_only_after_full_manifest_check(self):
        with tempfile.TemporaryDirectory() as name:
            temp = pathlib.Path(name)
            product, revision = self.clean_product_copy(temp)
            deployment, manifest, terraform, body = self.deployment(temp, revision)
            code = (
                "import os; print(os.environ['GCINSIGHT_REQUIRE_EXPLICIT_CONFIG']); "
                "print(os.environ['GCINSIGHT_RUNTIME_CONFIG_DIGEST'])"
            )
            result = self.run_command(
                str(product / "bin" / "consumer-exec"),
                "--manifest", str(manifest),
                "--deployment-root", str(deployment),
                "--terraform", str(terraform),
                "--kind", "scan", "--", "python3", "-c", code,
                cwd=product,
            )
            self.assertEqual(
                result.stdout.splitlines(),
                ["1", body["runtime_projection_digests"]["scan"]],
            )
            (deployment / "collector").mkdir()
            rejected = subprocess.run(
                [
                    str(product / "bin" / "consumer-exec"),
                    "--manifest", str(manifest),
                    "--deployment-root", str(deployment),
                    "--terraform", str(terraform),
                    "--kind", "scan", "--", "true",
                ],
                cwd=product, check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN":
                        "synthetic-private-identifier-[0-9]{20}",
                },
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("replacement product core at collector", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
