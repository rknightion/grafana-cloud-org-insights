"""Behavioral contracts for the shipped Terraform IAM policies."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
IAM = (ROOT / "terraform" / "iam.tf").read_text()
VARIABLES = (ROOT / "terraform" / "variables.tf").read_text()
MAIN = (ROOT / "terraform" / "main.tf").read_text()
OUTPUTS = (ROOT / "terraform" / "outputs.tf").read_text()
FIREHOSE = (ROOT / "terraform" / "firehose.tf").read_text()
CHECK_TAGS = (ROOT / "bin" / "check-tags.sh").read_text()


def _block(source: str, header: str) -> str:
    """Return one balanced HCL block, including its outer braces."""
    start = source.index(header)
    opening = source.index("{", start + len(header))
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening : index + 1]
    raise AssertionError(f"unterminated HCL block: {header}")


def _statements(policy: str) -> list[str]:
    statements = []
    offset = 0
    while True:
        match = re.search(r"\bstatement\s*\{", policy[offset:])
        if match is None:
            return statements
        start = offset + match.start()
        statement = _block(policy[start:], "statement")
        statements.append(statement)
        offset = start + len("statement") + len(statement)


def _list_items(block: str, attribute: str) -> set[str]:
    match = re.search(rf"\b{re.escape(attribute)}\s*=\s*\[", block)
    if match is None:
        raise AssertionError(f"missing {attribute} list")
    opening = block.index("[", match.start())
    closing = block.index("]", opening)
    return {
        item.strip().rstrip(",")
        for item in block[opening + 1 : closing].splitlines()
        if item.strip() and not item.lstrip().startswith("#")
    }


class ProvisionerProductReadsValidationTest(unittest.TestCase):
    def test_irm_alert_groups_is_an_explicit_optional_product_read_token(self):
        block = _block(VARIABLES, 'variable "provisioner_product_reads"')
        self.assertIn('default     = []', block)
        self.assertIn('"irm-alert-groups"', block)


class StackTokenPathPolicyTest(unittest.TestCase):
    EXPECTED_RESOURCES = {
        "local.stack_token_arn_prefix",
        '"${local.stack_token_arn_prefix}/*"',
    }

    def test_collector_can_list_the_stack_token_path_and_read_its_children(self):
        policy = _block(
            IAM, 'data "aws_iam_policy_document" "stack_tokens_read"'
        )
        attachment = _block(
            IAM, 'resource "aws_iam_role_policy" "task_stack_tokens"'
        )

        self._assert_get_parameters_by_path_resources(policy)
        self.assertIn("role   = aws_iam_role.task.id", attachment)
        self.assertIn(
            "policy = data.aws_iam_policy_document.stack_tokens_read.json",
            attachment,
        )

    def test_provisioner_can_list_the_stack_token_path_and_manage_its_children(self):
        policy = _block(IAM, 'data "aws_iam_policy_document" "provisioner"')
        attachment = _block(IAM, 'resource "aws_iam_role_policy" "provisioner"')

        self._assert_get_parameters_by_path_resources(policy)
        self.assertIn("role   = aws_iam_role.provisioner[0].id", attachment)
        self.assertIn(
            "policy = data.aws_iam_policy_document.provisioner[0].json",
            attachment,
        )

    def test_provisioner_can_never_write_the_bare_stack_token_path(self):
        policy = _block(IAM, 'data "aws_iam_policy_document" "provisioner"')
        write_statements = [
            statement
            for statement in _statements(policy)
            if '"ssm:PutParameter"' in statement or '"ssm:DeleteParameter"' in statement
        ]
        self.assertEqual(1, len(write_statements))
        self.assertEqual(
            {'"${local.stack_token_arn_prefix}/*"'},
            _list_items(write_statements[0], "resources"),
            "the bare prefix exists only so GetParametersByPath can list it; writes are child-only",
        )

    def _assert_get_parameters_by_path_resources(self, policy: str) -> None:
        matching = [
            statement
            for statement in _statements(policy)
            if '"ssm:GetParametersByPath"' in statement
        ]
        self.assertEqual(1, len(matching))
        self.assertEqual(
            self.EXPECTED_RESOURCES,
            _list_items(matching[0], "resources"),
            "GetParametersByPath must authorize the path ARN itself as well as its children",
        )


class RateCardPolicyTest(unittest.TestCase):
    RATE_CARD_ARN = '"${local.bucket_arn}/config/ratecard.csv"'

    def test_collector_can_read_only_the_rate_card_config_object(self):
        policy = _block(IAM, 'data "aws_iam_policy_document" "task"')
        matching = [
            statement
            for statement in _statements(policy)
            if self.RATE_CARD_ARN in _list_items(statement, "resources")
        ]

        self.assertEqual(1, len(matching))
        self.assertEqual({'"s3:GetObject"'}, _list_items(matching[0], "actions"))


class SchedulerProvisionerPolicyTest(unittest.TestCase):
    def test_scheduler_can_run_the_provisioner_and_pass_its_task_role(self):
        policy = _block(IAM, 'data "aws_iam_policy_document" "scheduler"')
        statements = _statements(policy)
        run_tasks = next(s for s in statements if 'sid    = "RunScanTasks"' in s)
        pass_roles = next(s for s in statements if 'sid    = "PassTaskRoles"' in s)

        self.assertIn("aws_ecs_task_definition.provisioner", run_tasks)
        self.assertIn("aws_iam_role.provisioner", pass_roles)


class FirehoseLogPathTest(unittest.TestCase):
    COMMON_ATTRIBUTES = {
        "lbl_job",
        "lbl_service_name",
        "lbl_tier",
        "lbl_env",
        "lbl_aws_account",
    }

    def test_firehose_and_subscription_are_separate_default_off_switches(self):
        for variable in ("firehose_logs_enabled", "firehose_log_subscription_enabled"):
            block = _block(VARIABLES, f'variable "{variable}"')
            self.assertIn("type        = bool", block)
            self.assertIn("default     = false", block)

        stream = _block(
            FIREHOSE, 'resource "aws_kinesis_firehose_delivery_stream" "ecs_logs"'
        )
        subscription = _block(
            FIREHOSE, 'resource "aws_cloudwatch_log_subscription_filter" "ecs_logs"'
        )
        self.assertIn("count = local.inputs.firehose_logs_enabled ? 1 : 0", stream)
        self.assertIn(
            "count = local.inputs.firehose_log_subscription_enabled ? 1 : 0",
            subscription,
        )
        self.assertIn("local.inputs.firehose_logs_enabled", subscription)

    def test_destination_is_derived_from_the_configured_loki_hostname(self):
        self.assertNotIn('variable "firehose_endpoint', VARIABLES)
        self.assertIn("loki_hostname", MAIN)
        self.assertIn(
            'https://aws-${local.loki_hostname}/aws-logs/api/v1/push',
            MAIN,
        )

        destination = _block(
            FIREHOSE, 'resource "aws_kinesis_firehose_delivery_stream" "ecs_logs"'
        )
        self.assertRegex(destination, r"\burl\s*=\s*local\.firehose_loki_endpoint")

    def test_firehose_uses_only_an_adopted_http_endpoint_secret(self):
        secret = _block(VARIABLES, 'variable "firehose_access_key_secret_arn"')
        self.assertIn('default     = ""', secret)
        self.assertIn("api_key", secret)
        self.assertNotRegex(FIREHOSE, r'(resource|data)\s+"aws_secretsmanager_secret"')

        stream = _block(
            FIREHOSE, 'resource "aws_kinesis_firehose_delivery_stream" "ecs_logs"'
        )
        self.assertNotRegex(stream, r"\baccess_key\s*=")
        secrets = _block(stream, "secrets_manager_configuration")
        self.assertIn("enabled    = true", secrets)
        self.assertIn("secret_arn = var.firehose_access_key_secret_arn", secrets)
        self.assertIn("role_arn   = aws_iam_role.firehose[0].arn", secrets)

    def test_delivery_contract_is_gzip_one_megabyte_sixty_seconds_failed_only(self):
        stream = _block(
            FIREHOSE, 'resource "aws_kinesis_firehose_delivery_stream" "ecs_logs"'
        )
        self.assertIn('destination = "http_endpoint"', stream)
        self.assertIn("buffering_size     = 1", stream)
        self.assertIn("buffering_interval = 60", stream)
        self.assertIn('s3_backup_mode     = "FailedDataOnly"', stream)

        request = _block(stream, "request_configuration")
        self.assertIn('content_encoding = "GZIP"', request)
        backup = _block(stream, "s3_configuration")
        self.assertIn('compression_format = "GZIP"', backup)

    def test_common_attributes_are_the_only_bounded_stream_labels(self):
        stream = _block(
            FIREHOSE, 'resource "aws_kinesis_firehose_delivery_stream" "ecs_logs"'
        )
        names = set(re.findall(r'name\s*=\s*"(lbl_[A-Za-z0-9_]+)"', stream))
        self.assertEqual(self.COMMON_ATTRIBUTES, names)
        for unbounded in ("task_arn", "task_id", "container_id", "image_digest"):
            self.assertNotIn(f"lbl_{unbounded}", stream)

    def test_roles_are_scoped_to_delivery_and_the_adopted_secret(self):
        kms_key = _block(VARIABLES, 'variable "firehose_access_key_secret_kms_key_arn"')
        self.assertIn('default     = ""', kms_key)

        firehose_policy = _block(
            FIREHOSE, 'data "aws_iam_policy_document" "firehose"'
        )
        self.assertIn('"secretsmanager:GetSecretValue"', firehose_policy)
        self.assertIn("var.firehose_access_key_secret_arn", firehose_policy)
        self.assertIn('"kms:Decrypt"', firehose_policy)
        self.assertIn("var.firehose_access_key_secret_kms_key_arn", firehose_policy)
        self.assertIn('"s3:PutObject"', firehose_policy)

        subscription_policy = _block(
            FIREHOSE, 'data "aws_iam_policy_document" "firehose_subscription"'
        )
        self.assertIn('"firehose:PutRecord"', subscription_policy)
        self.assertIn('"firehose:PutRecordBatch"', subscription_policy)
        self.assertIn("aws_kinesis_firehose_delivery_stream.ecs_logs[0].arn", subscription_policy)

    def test_subscription_trust_matches_the_creation_time_log_group_source_arn(self):
        assume = _block(
            FIREHOSE, 'data "aws_iam_policy_document" "firehose_subscription_assume"'
        )
        self.assertIn('test     = "ArnLike"', assume)
        self.assertIn('values = ["${aws_cloudwatch_log_group.tasks.arn}"]', assume)
        self.assertNotIn('"${aws_cloudwatch_log_group.tasks.arn}:*"', assume)
        self.assertIn('variable = "aws:SourceAccount"', assume)
        self.assertIn('values   = [data.aws_caller_identity.current.account_id]', assume)

    def test_every_new_named_resource_is_in_the_live_tag_gate(self):
        for label in (
            "Firehose delivery stream",
            "Firehose failed-record bucket",
            "Firehose access-key secret",
            "Firehose subscription role",
        ):
            self.assertIn(label, CHECK_TAGS)

    def test_tag_gate_derives_the_adopted_secret_from_the_live_stream(self):
        self.assertIn("FIREHOSE_ACCESS_KEY_SECRET_ARN", CHECK_TAGS)
        self.assertIn("SecretsManagerConfiguration.SecretARN", CHECK_TAGS)

    def test_generated_manual_task_command_propagates_cost_tags(self):
        command = _block(OUTPUTS, 'output "run_task_command"')
        self.assertIn("--propagate-tags TASK_DEFINITION", command)


class LabelRiskRetentionTest(unittest.TestCase):
    """Render the shipped lifecycle rule expressions without a provider or backend."""

    def render(self, days=90):
        storage = (ROOT / "terraform" / "storage.tf").read_text()
        lifecycle = _block(storage, 'resource "aws_s3_bucket_lifecycle_configuration" "data"')
        # Keep the real HCL attribute expressions. Only translate repeated nested blocks
        # into console object/list syntax; no policy values are supplied by this harness.
        rules = []
        offset = 0
        while match := re.search(r"\brule\s*\{", lifecycle[offset:]):
            start = offset + match.start()
            rule = _block(lifecycle[start:], "rule")
            rules.append(re.sub(
                r"\b(filter|expiration|noncurrent_version_expiration|abort_incomplete_multipart_upload)\s*\{",
                r"\1 = {", rule,
            ))
            offset = start + len("rule") + len(rule)
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "variables.tf").write_text(VARIABLES)
            Path(temp, "terraform.tfvars.json").write_text(json.dumps({
                "name_prefix": "synthetic-retention", "grafana_org_id": "synthetic",
                "write_stack_slug": "synthetic", "mimir_write_url": "https://example.invalid",
                "mimir_tenant": "synthetic", "loki_write_url": "https://example.invalid",
                "loki_tenant": "synthetic", "subnet_ids": ["subnet-synthetic"],
                "scan_retention_days": days,
            }))
            env = {k: v for k, v in os.environ.items() if not k.startswith("TF_VAR_")}
            rendered = subprocess.run(
                ["tofu", "console", "-no-color"], cwd=temp, env=env,
                input="jsonencode([" + ",\n".join(rules) + "])\n",
                text=True, capture_output=True, timeout=30,
            )
        return rendered

    def test_raw_match_current_view_expires_without_expiring_other_last_good_views(self):
        for days in (90, 12):
            with self.subTest(days=days):
                rendered = self.render(days)
                self.assertEqual(0, rendered.returncode, rendered.stderr)
                rules = json.loads(json.loads(rendered.stdout))
                expirations = {
                    rule["filter"].get("prefix", ""): rule["expiration"]["days"]
                    for rule in rules if "expiration" in rule and rule["status"] == "Enabled"
                }
                self.assertEqual(
                    {"scans/": days, "views/risk_label_hygiene.json": days}, expirations,
                    "raw matches must not survive indefinitely in the current view; other views stay last-good",
                )
                noncurrent = [r for r in rules if "noncurrent_version_expiration" in r]
                self.assertEqual(1, len(noncurrent))
                self.assertEqual({}, noncurrent[0]["filter"])
                self.assertEqual(7, noncurrent[0]["noncurrent_version_expiration"]["noncurrent_days"])

    def test_retention_rejects_nonpositive_and_fractional_days(self):
        for days in (0, -1, 1.5):
            with self.subTest(days=days):
                rendered = self.render(days)
                self.assertIn("scan_retention_days must be a positive whole number of days", rendered.stderr)


if __name__ == "__main__":
    unittest.main()
