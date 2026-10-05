"""Public CLI compatibility and real module-rendered source eligibility."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector import identity
from tests.test_consumer_manifest import ROOT, consumer_manifest, fixture
from tests.test_slo_inventory import STACK, client_for

KEY = "GCINSIGHT_READER_PRODUCT_READS"


def legacy_manifest(policy):
    body = fixture()
    body["runtime"]["provisioner"][KEY] = policy
    body["runtime"]["scan"].pop(KEY, None)
    body["overlay_digest"] = consumer_manifest.digest(consumer_manifest.overlay(body))
    body["runtime_projection_digests"] = {
        kind: hashlib.sha256(json.dumps(
            identity.canonical_projection(kind, values) if kind != "scan" else {
                k: v for k, v in identity.canonical_projection(kind, values).items() if k != KEY
            }, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        for kind, values in body["runtime"].items()
    }
    return body


def cli(*args, env=None):
    return subprocess.run(["python3", str(ROOT / "bin/consumer_manifest.py"), *args],
                          text=True, capture_output=True, env=env, timeout=30)


@pytest.mark.parametrize("policy", ["", "slo", "slo,synthetic-monitoring",
                                     "slo,synthetic-monitoring,synthetic-monitoring-query", "library-panels"])
def test_legacy_cli_regenerate_upgrade_and_real_scan_eligibility(policy):
    with tempfile.TemporaryDirectory() as name:
        temp = pathlib.Path(name)
        manifest = temp / "consumer.json"
        original = legacy_manifest(policy)
        manifest.write_text(json.dumps(original))
        result = cli("regenerate", "--manifest", str(manifest))
        assert result.returncode == 0, result.stderr
        updated = json.loads(manifest.read_text())
        assert updated["runtime"]["scan"][KEY] == policy
        consumer_manifest.validate(updated)
        # Upgrade runs the actual CLI; only its network/process edge is replaced.
        manifest.write_text(json.dumps(original))
        terraform = temp / "consumer.tf"
        terraform.write_text('module "insights" {\n  source = "git::https://github.com/'
                             'rknightion/grafana-cloud-org-insights.git//terraform?ref='
                             + original["generic_source"]["revision"] + '"\n}\n')
        git = temp / "git"
        git.write_text('#!/bin/sh\ncase "$*" in\n*"remote get-url origin"*) echo '
                       'https://github.com/rknightion/grafana-cloud-org-insights.git;;\n'
                       '*"show "*) exec "' + shutil.which("git") + '" -C "' + str(ROOT)
                       + '" show HEAD:collector/identity.py;;\nesac\n')
        git.chmod(0o755)
        result = cli("upgrade", "b" * 40, "--manifest", str(manifest), "--terraform",
                     str(terraform), env=dict(os.environ, PATH=str(temp) + ":" + os.environ["PATH"]))
        assert result.returncode == 0, result.stderr
        upgraded = json.loads(manifest.read_text())
        assert upgraded["runtime"]["scan"][KEY] == policy
        assert upgraded["generic_source"]["revision"] == "b" * 40
        assert consumer_manifest.terraform_revision(terraform) == "b" * 40
        consumer_manifest.validate(upgraded)
        wired = terraform.read_text().replace("\n}",
            '\n  provisioner_product_reads = split(",", local.provisioner.' + KEY + ')\n}')
        gaps = consumer_manifest.terraform_wiring_gaps(upgraded, wired, ROOT / "terraform")
        assert not [gap for gap in gaps if KEY in gap]
        result = cli("env", "scan", "--manifest", str(manifest))
        assert result.returncode == 0, result.stderr
        emitted = dict(line.split("=", 1) for line in result.stdout.splitlines())
        expression = consumer_manifest.module_env_inputs(ROOT / "terraform")["scan"][KEY][1]
        render_root = temp / "render"
        render_root.mkdir()
        shutil.copyfile(ROOT / "terraform/variables.tf", render_root / "variables.tf")
        variables = {"name_prefix": "example-insights", "grafana_org_id": "123456",
                     "write_stack_slug": "example", "mimir_write_url": "https://example.invalid",
                     "mimir_tenant": "1", "loki_write_url": "https://example.invalid",
                     "loki_tenant": "1", "subnet_ids": ["subnet-example"]}
        if policy:
            variables["provisioner_product_reads"] = policy.split(",")
        (render_root / "contract.auto.tfvars.json").write_text(json.dumps(variables))
        rendered = subprocess.run(["tofu", "console", "-no-color"], cwd=render_root,
                                  input=expression + "\n", text=True, capture_output=True, timeout=30)
        assert rendered.returncode == 0, rendered.stderr
        emitted[KEY] = json.loads(rendered.stdout)
        assert emitted[KEY] == policy
        identity.verify_runtime_projection("scan", environ=emitted)
        tampered = dict(emitted, **{KEY: "" if policy else "slo"})
        with pytest.raises(identity.InvalidIdentity, match="digest mismatch"):
            identity.verify_runtime_projection("scan", environ=tampered)
        with mock.patch.dict(os.environ, emitted), mock.patch.object(
            scan.credentials, "load_all", return_value={"obs-hub": {"token": "synthetic-token"},
                                                      "current": {"token": "synthetic"}}
        ) as credentials:
            data, errors = scan.gather_slo_inventory(client_for({"slos": []}),
                                                    SimpleNamespace(concurrency=1), [STACK])
            assert not errors
            assert bool(data) == ("slo" in policy.split(","))
            assert credentials.called == ("slo" in policy.split(","))
            # The same real module-rendered policy must gate the new source, not the old SM token.
            from tests.test_synthetic import fixture_client
            client, calls = fixture_client()
            data, errors = scan.gather_synthetic_inventory(client, SimpleNamespace(concurrency=1), [STACK])
            assert not errors
            selected = "synthetic-monitoring-query" in policy.split(",")
            assert bool(data) == selected
            assert len(calls) == (3 if selected else 0)
            from tests.test_library_panels import STACK as LIBRARY_STACK, client_for as library_client, page
            library_calls = []
            data, errors = scan.gather_library_panels_inventory(
                library_client([(page([1, 2]), 200)], library_calls),
                SimpleNamespace(concurrency=1), [LIBRARY_STACK])
            # This closed token must pass through the actual module/manifest policy to the scan.
            selected_library = "library-panels" in policy.split(",")
            assert not errors
            assert len(library_calls) == (2 if selected_library else 0)
            assert bool(data) == selected_library
            if selected_library:
                assert data == {"current": {"available": True, "library_panel_count": 2}}


def test_cli_rejects_mismatch_without_rewriting_manifest():
    body = legacy_manifest("slo")
    body["runtime"]["scan"][KEY] = ""
    with tempfile.TemporaryDirectory() as name:
        path = pathlib.Path(name) / "consumer.json"
        text = json.dumps(body)
        path.write_text(text)
        for command in ("regenerate", "check"):
            result = cli(command, "--manifest", str(path))
            assert result.returncode == 2
            assert "must be identical" in result.stderr
            assert path.read_text() == text


def test_upgrade_rejects_corrupt_legacy_digest_before_migration():
    body = legacy_manifest("slo")
    body["runtime"]["provisioner"][KEY] = ""
    with pytest.raises(consumer_manifest.ManifestError, match="overlay_digest"):
        consumer_manifest.validate(body, allow_legacy_scan_policy=True)
