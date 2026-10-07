"""Configuration is REQUIRED, not defaulted.

Every value here names a specific Grafana Cloud org, stack or tenant. A default would be one
deployment's identifiers baked into everyone else's collector, and the failure mode is silent: the
scan runs, authenticates, and writes a correct-looking set of series to somebody else's tenant.

So `load()` refuses rather than guessing, and the message names the variable and what it is for.
"""

from __future__ import annotations

import os
import unittest

from collector import config

REQUIRED = (
    "GCINSIGHT_READ_TOKEN",
    "GCINSIGHT_ORG_ID",
    "GCINSIGHT_WRITE_STACK",
    "GCINSIGHT_MIMIR_URL",
    "GCINSIGHT_MIMIR_TENANT",
    "GCINSIGHT_LOKI_URL",
    "GCINSIGHT_LOKI_TENANT",
)

COMPLETE = {
    "GCINSIGHT_READ_TOKEN": "read-token",
    "GCINSIGHT_WRITE_TOKEN": "write-token",
    "GCINSIGHT_ORG_ID": "123456",
    "GCINSIGHT_WRITE_STACK": "obs-hub",
    "GCINSIGHT_MIMIR_URL": "https://prometheus-prod-01-eu-west-0.grafana.net",
    "GCINSIGHT_MIMIR_TENANT": "111111",
    "GCINSIGHT_LOKI_URL": "https://logs-prod-001.grafana.net",
    "GCINSIGHT_LOKI_TENANT": "222222",
}


class _Env:
    """Replace the whole GCINSIGHT_* namespace, so a developer's own shell cannot mask a failure."""

    def __init__(self, **values: str):
        self.values = values

    def __enter__(self):
        self.saved = {k: v for k, v in os.environ.items() if k.startswith("GCINSIGHT_")}
        for k in self.saved:
            del os.environ[k]
        os.environ.update(self.values)
        return self

    def __exit__(self, *exc):
        for k in [k for k in os.environ if k.startswith("GCINSIGHT_")]:
            del os.environ[k]
        os.environ.update(self.saved)
        return False


class RequiredConfigTest(unittest.TestCase):
    def test_a_complete_environment_loads(self):
        with _Env(**COMPLETE):
            cfg = config.load(tier="t1")
        self.assertEqual(cfg.org_id, "123456")
        self.assertEqual(cfg.write_stack, "obs-hub")
        self.assertEqual(cfg.mimir_tenant, "111111")
        self.assertEqual(cfg.coverage_score_weights, {
            component: 1.0 for component in config.observability_score.COMPONENTS
        })

    def test_invalid_coverage_weights_fail_configuration_loading(self):
        with _Env(**dict(COMPLETE, GCINSIGHT_COVERAGE_SCORE_WEIGHTS='{"slo": -1}')):
            with self.assertRaisesRegex(
                config.MissingConfig, "GCINSIGHT_COVERAGE_SCORE_WEIGHTS"
            ):
                config.load(tier="t1")

    def test_dashboard_detail_flag_is_explicit_and_strict(self):
        """A misspelt rollout flag must not silently disable the denominator evidence."""
        with _Env(**dict(COMPLETE, GCINSIGHT_DASHBOARD_DETAIL_ENABLED="true")):
            self.assertTrue(config.load(tier="t2").dashboard_detail_enabled)
        with _Env(**dict(COMPLETE, GCINSIGHT_DASHBOARD_DETAIL_ENABLED="sometimes")):
            with self.assertRaisesRegex(config.MissingConfig, "DASHBOARD_DETAIL"):
                config.load(tier="t2")

    def test_expected_retention_policy_is_optional_validated_json(self):
        with _Env(**dict(
            COMPLETE,
            GCINSIGHT_EXPECTED_RETENTION_POLICY=(
                '[{"selector":"{service=\\"api\\"}","minimum_period":"14d"}]'
            ),
        )):
            cfg = config.load(tier="t2")
        self.assertEqual(cfg.expected_retention_policy, ({
            "selector": '{service="api"}', "minimum_period": "14d",
        },))
        self.assertEqual(cfg.redacted["expected_retention_policy_count"], 1)
        self.assertNotIn("service", str(cfg.redacted))

        with _Env(**dict(COMPLETE, GCINSIGHT_EXPECTED_RETENTION_POLICY='{"selector":"x"}')):
            with self.assertRaisesRegex(config.MissingConfig, "JSON list"):
                config.load(tier="t2")
        with _Env(**dict(
            COMPLETE,
            GCINSIGHT_EXPECTED_RETENTION_POLICY=(
                '[{"selector":"{service=\\"api\\"}","minimum_period":"two weeks"}]'
            ),
        )):
            with self.assertRaisesRegex(config.MissingConfig, "hours or days"):
                config.load(tier="t2")

    def test_fleet_default_scrape_interval_defaults_to_60s_and_is_validated(self):
        with _Env(**COMPLETE):
            self.assertEqual(config.load(tier="t1").fleet_default_scrape_interval_seconds, 60.0)
        with _Env(**dict(COMPLETE, GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL="1m30s")):
            self.assertEqual(config.load(tier="t1").fleet_default_scrape_interval_seconds, 90.0)
        for bad in ("30", "0s", "fast"):
            with self.subTest(value=bad), _Env(**dict(
                    COMPLETE, GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL=bad)):
                with self.assertRaisesRegex(config.MissingConfig, "positive duration"):
                    config.load(tier="t1")

    def test_label_inventory_tunables_defaults_and_strict_policy(self):
        import json
        with _Env(**COMPLETE):
            cfg = config.load(tier="t2")
        self.assertFalse(cfg.label_inventory_enabled)
        self.assertEqual(cfg.label_inventory_budget_seconds, 900)
        self.assertEqual(cfg.label_inventory_tunables, {
            "size_floor": 100, "static_multiplier": 10, "coverage_floor": 0.8,
            "thresholds": {},
        })
        self.assertIn("host", cfg.label_inventory_static_names)
        policy = {"size_floor": 200, "coverage_floor": 0.9, "thresholds": {
            "M4": {"warn": 200, "high": 2000, "critical": 20000}}}
        with _Env(**dict(COMPLETE, GCINSIGHT_LABEL_INVENTORY_TUNABLES=json.dumps(policy),
                         GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES='["custom_host"]',
                         GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS="60",
                         GCINSIGHT_OPT_OUT="leave-alone")):
            cfg = config.load(tier="t2")
        self.assertEqual(cfg.label_inventory_tunables["size_floor"], 200)
        self.assertEqual(cfg.label_inventory_static_names, ("custom_host",))
        self.assertEqual(cfg.label_inventory_budget_seconds, 60)
        self.assertEqual(cfg.opt_out, ("leave-alone",))
        self.assertNotIn("custom_host", str(cfg.redacted))
        for env, bad in (
            ("TUNABLES", '{"coverage_floor":0.79}'),
            ("TUNABLES", '{"size_floor":true}'),
            ("TUNABLES", '{"thresholds":{"unknown":{"warn":1}}}'),
            ("TUNABLES", '{"thresholds":{"M6":{"warn":31}}}'),
            ("TUNABLES", '{"thresholds":{"M4":{"warn":200}}}'),
            ("TUNABLES", '{"thresholds":{"M4":{"warn":2000,"high":100,"critical":10000}}}'),
            ("TUNABLES", '{"unknown":1}'),
            ("TUNABLES", '{"coverage_floor":NaN}'),
            ("STATIC_NAMES", '["secret@example.com"]'),
            ("STATIC_NAMES", '["host","host"]'),
            ("BUDGET_SECONDS", "901"), ("BUDGET_SECONDS", "nan"),
            ("BUDGET_SECONDS", "0"),
        ):
            with self.subTest(env=env, bad=bad), _Env(**dict(
                    COMPLETE, **{"GCINSIGHT_LABEL_INVENTORY_" + env: bad})):
                with self.assertRaisesRegex(config.MissingConfig, "LABEL_INVENTORY"):
                    config.load(tier="t2")

    def test_label_policy_reaches_existing_source_parameters(self):
        from unittest import mock
        from collector.httpclient import ReadOnlyClient
        from collector.sources import label_inventory
        with _Env(**dict(COMPLETE, GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS="30",
                         GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES='["custom_host"]')):
            cfg = config.load(tier="t2")
        with mock.patch.object(label_inventory, "probe_stack", return_value={}) as probe:
            result = label_inventory.probe_all(
                ReadOnlyClient(deadline=400), [{"slug": "synthetic", "status": "active"}], "fake-token",
                enabled=True, max_seconds=cfg.label_inventory_budget_seconds,
                static_names=cfg.label_inventory_static_names)
        self.assertEqual(result, {"synthetic": {}})
        self.assertEqual(probe.call_args.kwargs["static_names"], ("custom_host",))
        self.assertLessEqual(probe.call_args.args[0].remaining(), 30)

    def test_real_tier_runners_forward_source_and_evaluator_policy(self):
        from unittest import mock
        import scan
        class ReachedSeam(Exception):
            pass
        with _Env(**dict(COMPLETE, GCINSIGHT_LABEL_INVENTORY_ENABLED="1",
                         GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS="30",
                         GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES='["custom_host"]',
                         GCINSIGHT_LABEL_INVENTORY_TUNABLES='{"size_floor":200}')):
            cfg = config.load(tier="t2")
        stacks = [{"slug": "synthetic", "status": "active"}]
        with mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks), \
                mock.patch.object(scan.label_risk_src, "probe_all", return_value={}), \
                mock.patch.object(scan.label_inventory_src, "probe_all", side_effect=ReachedSeam) as source:
            with self.assertRaises(ReachedSeam):
                scan.run_t2(None, cfg)
        self.assertEqual(source.call_args.kwargs["max_seconds"], cfg.label_inventory_budget_seconds)
        self.assertEqual(source.call_args.kwargs["static_names"], cfg.label_inventory_static_names)
        self.assertTrue(source.call_args.kwargs["enabled"])
        with mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks), \
                mock.patch.object(scan.dataplane, "probe_all", return_value={}), \
                mock.patch.object(scan.hydrate, "hydrate", return_value=({"label_inventory": {}}, {})), \
                mock.patch.object(scan, "load_ratecard", return_value=None), \
                mock.patch.object(scan, "assistant_gaps", return_value={}), \
                mock.patch.object(scan.compose, "build_all", side_effect=ReachedSeam) as producer:
            with self.assertRaises(ReachedSeam):
                scan.run_t3(None, cfg)
        self.assertEqual(producer.call_args.kwargs["label_inventory_tunables"], cfg.label_inventory_tunables)
        self.assertIn("label_inventory", producer.call_args.kwargs)

    def test_every_required_variable_is_refused_when_absent(self):
        for missing in REQUIRED:
            env = {k: v for k, v in COMPLETE.items() if k != missing}
            with self.subTest(missing=missing), _Env(**env):
                with self.assertRaises(config.IncompleteConfig) as caught:
                    config.load(tier="t1")
                self.assertIn(missing, str(caught.exception),
                              "the error must name the variable, or it is a scavenger hunt")

    def test_an_empty_string_counts_as_absent(self):
        """A blank env var is how a broken deployment presents - Terraform passing through an unset
        variable gives "" rather than removing the key."""
        with _Env(**dict(COMPLETE, GCINSIGHT_MIMIR_TENANT="   ")):
            with self.assertRaises(config.MissingConfig):
                config.load(tier="t1")

    def test_both_refusals_share_one_base_so_a_caller_needs_one_except(self):
        """scan.py exits on `IncompleteConfig`. When these were unrelated classes, a missing org id
        escaped as a traceback while a missing token exited cleanly."""
        self.assertTrue(issubclass(config.MissingCredential, config.IncompleteConfig))
        self.assertTrue(issubclass(config.MissingConfig, config.IncompleteConfig))

    def test_the_write_token_still_falls_back_to_the_read_token(self):
        """One credential is enough for an interactive read-only run; deployment sets both."""
        env = {k: v for k, v in COMPLETE.items() if k != "GCINSIGHT_WRITE_TOKEN"}
        with _Env(**env):
            cfg = config.load(tier="t1")
        self.assertEqual(cfg.write_token, cfg.cap)
        self.assertFalse(cfg.redacted["credentials_split"])

    def test_no_module_constant_carries_a_deployment_identifier(self):
        """The regression this file exists for: a default org id or stack slug reintroduced as a
        convenience, so a fresh deployment silently writes to whoever's identifiers were left here."""
        for name in dir(config):
            if not name.isupper():
                continue
            value = getattr(config, name)
            if not isinstance(value, str):
                continue
            self.assertFalse(
                value.isdigit() and len(value) >= 5,
                f"config.{name} = {value!r} looks like an org or tenant id",
            )
            self.assertNotIn("grafana.net", value,
                             f"config.{name} = {value!r} names a specific stack endpoint")

    def test_no_credential_is_ever_in_the_redacted_form(self):
        with _Env(**COMPLETE):
            red = config.load(tier="t1").redacted
        self.assertNotIn("read-token", str(red))
        self.assertNotIn("write-token", str(red))


if __name__ == "__main__":
    unittest.main()


class LabellingStabilityRecipeTest(unittest.TestCase):
    """Exercise the real read-only CLI on explicitly synthetic dated artifacts."""

    def test_recipe_checks_actual_artifacts_and_fails_closed(self):
        import copy
        import datetime as dt
        import hashlib
        import json
        import pathlib
        import subprocess
        import tempfile
        from collector import identity, label_rules
        repo = pathlib.Path(__file__).resolve().parent.parent
        sample = {"value": 0, "semantics": "exact", "population": 100,
                  "population_semantics": "exact", "label_kind": "dynamic"}
        payload = {"schema_version": 1, "signals": {}}
        for signal in label_rules.SIGNALS:
            payload["signals"][signal] = {
                "data": "present", "state": "complete", "reason": "none",
                "window": "head" if signal == "metrics" else "24h",
                "register": [], "register_truncated": 0,
                "inputs": {key: {"state": "complete", "reason": "none", "names_truncated": 0,
                                 "values_overflow": 0, "samples": [sample]}
                           for key, entry in label_rules.CATALOGUE.inputs.items()
                           if signal in entry["signals"] and entry["route"] == "approved"},
            }
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            def write(name, value):
                (root / name).write_text(json.dumps(value))
                # Keep privacy/schema controls bound to their intentionally changed object body.
                if name.startswith("scan-"):
                    witness = root / name.replace("scan-", "publication-")
                    if witness.exists():
                        publication = json.loads(witness.read_text())
                        body = (root / name).read_bytes()
                        publication["body_sha256"] = hashlib.sha256(body).hexdigest()
                        publication["response"]["ETag"] = '"' + hashlib.md5(body).hexdigest() + '"'
                        publication["response"]["ContentLength"] = len(body)
                        witness.write_text(json.dumps(publication))
            environment = {name: "synthetic-" + str(index)
                           for index, name in enumerate(identity.SCAN_ENV)}
            environment.update(identity.LABEL_INVENTORY_DEFAULTS)
            environment["GCINSIGHT_LABEL_INVENTORY_ENABLED"] = "1"
            runtime_digest = identity.projection_digest("scan", environment)
            environment["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] = runtime_digest
            environment["GCINSIGHT_REQUIRE_EXPLICIT_CONFIG"] = "1"
            manifest = {"v": 1, "runtime_projection_digest": runtime_digest, "source_sha": "a" * 40, "image_digest": "sha256:" + "b" * 64,
                        "catalogue_version": label_rules.CATALOGUE.version,
                        "deadline_seconds": 3600, "max_score_delta": 0, "observations": []}
            for day in range(3):
                at = dt.datetime(2026, 1, 1 + day, tzinfo=dt.timezone.utc)
                task = f"arn:aws:ecs:region:123456789012:task/cluster/synthetic-{day}"
                observation = {key: manifest[key] for key in ("source_sha", "image_digest", "catalogue_version", "runtime_projection_digest")}
                observation.update(task_arn=task, container_name="collector",
                                   publication_at=(at + dt.timedelta(seconds=110)).isoformat())
                for key in ("scan", "stopped", "memory", "schedule", "launch", "task_definition", "publication"):
                    observation[key + "_path"] = f"{key}-{day}.json"
                manifest["observations"].append(observation)
                write(observation["scan_path"], {
                    "meta": {"tier": "t2", "generated_at": (at + dt.timedelta(seconds=100)).isoformat(),
                             "duration_seconds": 90, "scan_healthy": True, "sources_healthy": True},
                    "data": {"label_inventory": {"synthetic": copy.deepcopy(payload)}}})
                body = (root / observation["scan_path"]).read_bytes()
                stamp = (at + dt.timedelta(seconds=100)).isoformat().replace(":", "").replace("-", "")
                write(observation["publication_path"], {
                    "request": {"Bucket": environment["GCINSIGHT_S3_BUCKET"], "Key": f"scans/t2/{stamp}.json",
                                "VersionId": f"synthetic-version-{day}"},
                    "response": {"VersionId": f"synthetic-version-{day}",
                                 "LastModified": observation["publication_at"], "ContentLength": len(body),
                                 "ETag": '"' + hashlib.md5(body).hexdigest() + '"', "ServerSideEncryption": "AES256"},
                    "body_sha256": hashlib.sha256(body).hexdigest()})
                write(observation["stopped_path"], {"tasks": [{
                    "taskArn": task, "lastStatus": "STOPPED", "memory": "512",
                    "clusterArn": "arn:aws:ecs:region:123456789012:cluster/synthetic",
                    "taskDefinitionArn": "arn:aws:ecs:region:123456789012:task-definition/synthetic-t2:1",
                    "startedAt": at.isoformat(), "stoppedAt": (at + dt.timedelta(seconds=120)).isoformat(),
                    "containers": [{"name": "collector", "exitCode": 0, "imageDigest": manifest["image_digest"]}]}]})
                write(observation["memory_path"], {
                    "task_arn": task, "method": "cgroup-memory.peak", "peak_bytes": 1024,
                    "limit_bytes": 512 * 1024 * 1024, "window_start": at.isoformat(),
                    "window_end": (at + dt.timedelta(seconds=120)).isoformat()})
                definition = "arn:aws:ecs:region:123456789012:task-definition/synthetic-t2:1"
                cluster = "arn:aws:ecs:region:123456789012:cluster/synthetic"
                role = "arn:aws:iam::123456789012:role/synthetic-scheduler"
                write(observation["schedule_path"], {
                    "Arn": "arn:aws:scheduler:region:123456789012:schedule/default/synthetic",
                    "State": "ENABLED", "Target": {"Arn": cluster, "RoleArn": role,
                    "EcsParameters": {"TaskDefinitionArn": definition}}})
                write(observation["launch_path"], {
                    "eventName": "RunTask", "eventSource": "ecs.amazonaws.com", "eventTime": at.isoformat(),
                    "userAgent": "scheduler.amazonaws.com", "userIdentity": {
                        "sessionContext": {"sessionIssuer": {"arn": role}}},
                    "requestParameters": {"cluster": cluster, "taskDefinition": definition},
                    "responseElements": {"tasks": [{"taskArn": task, "taskDefinitionArn": definition}]}})
                write(observation["task_definition_path"], {"taskDefinition": {
                    "taskDefinitionArn": definition, "containerDefinitions": [{
                        "name": "collector", "image": "example.invalid/synthetic@" + manifest["image_digest"],
                        "command": ["--tier", "t2", "--deadline-seconds", "3600"],
                        "environment": [{"name": name, "value": value} for name, value in environment.items()]}]}})
            write("evidence.json", manifest)
            command = ["just", "verify-labelling-stability", str(root / "evidence.json")]
            def run():
                return subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=30)
            # Fail for missing measured memory before demonstrating the synthetic happy path.
            memory = (root / "memory-0.json").read_bytes()
            (root / "memory-0.json").unlink()
            self.assertNotEqual(run().returncode, 0)
            (root / "memory-0.json").write_bytes(memory)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            success = run()
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(json.loads(success.stdout)["span_hours"], 48)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            scan = json.loads((root / "scan-0.json").read_text())
            scan["data"]["label_inventory"]["synthetic"]["raw_values"] = ["PRIVATE_SENTINEL"]
            write("scan-0.json", scan)
            failed = run()
            self.assertNotEqual(failed.returncode, 0)
            self.assertNotIn("PRIVATE_SENTINEL", failed.stdout + failed.stderr)
            (root / "scan-0.json").write_bytes(before["scan-0.json"])
            (root / "publication-0.json").write_bytes(before["publication-0.json"])
            for path, mutate in (
                ("launch-0.json", lambda value: value.update(userAgent="manual-operator")),
                ("launch-0.json", lambda value: value["responseElements"]["tasks"][0].update(taskArn="wrong-task")),
                ("task_definition-0.json", lambda value: next(
                    entry for entry in value["taskDefinition"]["containerDefinitions"][0]["environment"]
                    if entry["name"] == "GCINSIGHT_LABEL_INVENTORY_TUNABLES").update(value='{"coverage_floor":0.9}')),
            ):
                value = json.loads(before[path])
                mutate(value)
                write(path, value)
                self.assertNotEqual(run().returncode, 0)
                (root / path).write_bytes(before[path])
            for flags in (["--dry-run", "--limit", "1"], ["--dry-run"], ["--dry"],
                          ["--limit", "1"], ["--limit=1"], ["--stack", "synthetic"],
                          ["--stack=synthetic"], ["--out", "diagnostic.json"], ["--ignore-lock"],
                          ["--tier", "t1"]):
                with self.subTest(disqualified_command=flags):
                    definition = json.loads(before["task_definition-0.json"])
                    definition["taskDefinition"]["containerDefinitions"][0]["command"].extend(flags)
                    write("task_definition-0.json", definition)
                    rejected = run()
                    (root / "task_definition-0.json").write_bytes(before["task_definition-0.json"])
                    self.assertNotEqual(rejected.returncode, 0, flags)
            for name, mutate in (
                ("wrong_bucket", lambda p: p["request"].update(Bucket="wrong-bucket")),
                ("wrong_key", lambda p: p["request"].update(Key="scans/t2/latest.json")),
                ("wrong_version", lambda p: p["response"].update(VersionId="wrong-version")),
                ("unversioned", lambda p: p["request"].update(VersionId="null")),
                ("wrong_etag", lambda p: p["response"].update(ETag='"' + "0" * 32 + '"')),
                ("wrong_digest", lambda p: p.update(body_sha256="0" * 64)),
                ("wrong_length", lambda p: p["response"].update(ContentLength=1)),
                ("stale_object", lambda p: p["response"].update(LastModified="2025-01-01T00:00:00Z")),
                ("opaque_kms_etag", lambda p: p["response"].update(ServerSideEncryption="aws:kms")),
                ("multipart_etag", lambda p: p["response"].update(ETag='"' + "0" * 32 + '-2"')),
                ("caller_only_digest", lambda p: p["response"].pop("ETag")),
                ("missing_last_modified", lambda p: p["response"].pop("LastModified")),
            ):
                with self.subTest(unbound_object=name):
                    publication = json.loads(before["publication-0.json"])
                    mutate(publication)
                    write("publication-0.json", publication)
                    rejected = run()
                    (root / "publication-0.json").write_bytes(before["publication-0.json"])
                    self.assertNotEqual(rejected.returncode, 0, name)
            for flags in (["--dry-run"], ["--limit=1"], ["--stack=synthetic"], ["--tier=t1"]):
                with self.subTest(disqualified_actual_override=flags):
                    stopped = json.loads(before["stopped-0.json"])
                    stopped["tasks"][0]["overrides"] = {"containerOverrides": [{"name": "collector",
                        "command": ["--tier", "t2", "--deadline-seconds", "3600", *flags]}]}
                    write("stopped-0.json", stopped)
                    rejected = run()
                    (root / "stopped-0.json").write_bytes(before["stopped-0.json"])
                    self.assertNotEqual(rejected.returncode, 0)
            with self.subTest(forged_caller_timestamp=True):
                forged = copy.deepcopy(manifest)
                forged["observations"][0]["publication_at"] = "2026-01-01T00:01:51Z"
                write("evidence.json", forged)
                rejected = run()
                write("evidence.json", manifest)
                self.assertNotEqual(rejected.returncode, 0)
            # Native full-object checksum binds KMS/opaque ETags without treating ETag as MD5.
            import base64
            publication = json.loads(before["publication-0.json"])
            publication["response"].update(ServerSideEncryption="aws:kms", ETag='"' + "0" * 32 + '"',
                ChecksumType="FULL_OBJECT", ChecksumSHA256=base64.b64encode(
                    hashlib.sha256(before["scan-0.json"]).digest()).decode())
            write("publication-0.json", publication)
            checksum_success = run()
            self.assertEqual(checksum_success.returncode, 0, checksum_success.stderr)
            for checksum_type, checksum in (("COMPOSITE", publication["response"]["ChecksumSHA256"]),
                                           ("FULL_OBJECT", base64.b64encode(b"wrong").decode())):
                with self.subTest(invalid_native_checksum=checksum_type):
                    publication["response"].update(ChecksumType=checksum_type, ChecksumSHA256=checksum)
                    write("publication-0.json", publication)
                    self.assertNotEqual(run().returncode, 0)
            (root / "publication-0.json").write_bytes(before["publication-0.json"])
            with self.subTest(missing_object_witness=True):
                (root / "publication-0.json").unlink()
                rejected = run()
                (root / "publication-0.json").write_bytes(before["publication-0.json"])
                self.assertNotEqual(rejected.returncode, 0)
            short = copy.deepcopy(manifest)
            short["observations"].pop()
            write("evidence.json", short)
            self.assertNotEqual(run().returncode, 0)


class BuildToolTargetsAreNotDefaultedTest(unittest.TestCase):
    """The two BUILD tools name their target in module-level constants, outside `config.load()`.

    They were therefore missed by the sweep that made everything else required, and each one carried a
    real deployment's identifier as its default: `bin/dashboards.py` defaulted the write stack's numeric
    id, and `bin/alerts.py` defaulted the insights folder uid. Neither fails loudly - the v2 resource API
    namespaces dashboards as `stacks-<id>`, so an id is all it needs, and a folder uid that exists on
    the stack it came from takes alert rules straight into somebody else's folder.

    Read as SOURCE, not imported: importing evaluates the constants against this process's environment,
    so a variable set in the shell running the suite would hide the default entirely.
    """

    #: file -> (target variables, the argv that reaches the publish path). `--publish` takes a
    #: dashboard name in one tool and is a bare flag in the other, so the argv cannot be shared.
    TARGETS = {
        "bin/dashboards.py": (("GCINSIGHT_WRITE_STACK_URL", "GCINSIGHT_WRITE_STACK_ID"),
                              ["--publish", "estate"]),
        "bin/alerts.py": (("GCINSIGHT_WRITE_STACK_URL", "GCINSIGHT_INSIGHTS_FOLDER_UID"),
                          ["--publish"]),
    }

    def _source(self, path: str) -> str:
        import pathlib
        return (pathlib.Path(__file__).resolve().parent.parent / path).read_text()

    def test_no_target_variable_has_a_default(self):
        import re
        for path, (variables, _argv) in self.TARGETS.items():
            src = self._source(path)
            for var in variables:
                with self.subTest(file=path, var=var):
                    found = re.findall(rf'os\.environ\.get\(\s*"{var}"\s*,\s*("[^"]*")\s*\)', src)
                    self.assertTrue(found, f"{var} is not read in {path} - has it been renamed?")
                    for default in found:
                        self.assertEqual(default, '""', f"{var} in {path} defaults to {default}")

    def test_each_tool_refuses_when_a_target_is_unset(self):
        """A default is only half of it: unset must exit non-zero rather than build a relative URL."""
        import subprocess
        import sys
        for path, (variables, argv) in self.TARGETS.items():
            for var in variables:
                with self.subTest(file=path, missing=var):
                    env = {k: v for k, v in os.environ.items() if not k.startswith("GCINSIGHT_")}
                    env["GCINSIGHT_GRAFANA_TOKEN"] = "t"
                    for other in variables:
                        if other != var:
                            env[other] = "x"
                    proc = subprocess.run(
                        [sys.executable, path, *argv],
                        capture_output=True, text=True, env=env,
                        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
                    )
                    self.assertNotEqual(proc.returncode, 0,
                                        f"{path} ran with {var} unset:\n{proc.stdout[-400:]}")
                    self.assertIn(var, proc.stderr, proc.stderr[-400:])
