"""Upgrade inspects real Git artifacts without importing target code."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from tests.test_consumer_manifest import ROOT, consumer_manifest, fixture
from tests.test_scan_product_policy import KEY, cli, legacy_manifest

def old_target_repository(temp):
    # CI is shallow. Retain the captured old declarations instead of fetching history in an offline test.
    product = temp / "old-product"
    (product / "collector").mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/fixtures/consumer_identity_v030.txt",
                    product / "collector/identity.py")
    for args in (("init", "-q"), ("add", "collector/identity.py"),
                 ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "-qm", "Captured old projection schema")):
        subprocess.run([shutil.which("git"), "-C", str(product), *args],
                       check=True, capture_output=True, timeout=30)
    target = subprocess.run([shutil.which("git"), "-C", str(product), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    return product, target


def offline_git(temp):
    # Only remote lookup/network fetch are stubbed; cat-file/show read real repository objects.
    git = temp / "git"
    git.write_text('#!/bin/sh\ncase "$*" in\n*"remote get-url origin"*) echo '
                   'https://github.com/rknightion/grafana-cloud-org-insights.git;;\n'
                   '*"fetch --dry-run"*) exit 0;;\n*) exec "' + shutil.which("git") + '" "$@";;\nesac\n')
    git.chmod(0o755)
    return dict(os.environ, PATH=str(temp) + ":" + os.environ["PATH"])


def files(temp, body):
    manifest = temp / "consumer.json"
    manifest.write_text(json.dumps(body))
    terraform = temp / "consumer.tf"
    terraform.write_text('module "insights" {\n  source = "git::https://github.com/'
                         'rknightion/grafana-cloud-org-insights.git//terraform?ref='
                         + body["generic_source"]["revision"] + '"\n}\n')
    return manifest, terraform


def test_real_cli_old_target_rejected_before_either_file_changes():
    with tempfile.TemporaryDirectory() as name:
        temp = pathlib.Path(name)
        manifest, terraform = files(temp, fixture())
        before = (manifest.read_bytes(), terraform.read_bytes())
        # Even an existing recovery journal must not trigger writes for an unsupported target.
        journal = consumer_manifest.journal_path(manifest)
        journal.write_text("saved recovery evidence")
        product, target = old_target_repository(temp)
        result = cli("upgrade", target, "--manifest", str(manifest), "--terraform", str(terraform),
                     "--generic-source", str(product), env=offline_git(temp))
        # Against the original implementation this reports 0 and replaces both inputs.
        after = (manifest.read_bytes(), terraform.read_bytes())
        assert result.returncode == 2, (result.stdout, result.stderr, after != before)
        assert "target projection schema" in result.stderr
        assert "target-matched" in result.stderr and "saved rollback triplet" in result.stderr
        assert after == before
        assert journal.read_text() == "saved recovery evidence"


@pytest.mark.parametrize("corrupt", [False, True])
def test_real_cli_supported_forward_legacy_preserves_policy_and_checks_old_digest(corrupt):
    with tempfile.TemporaryDirectory() as name:
        temp = pathlib.Path(name)
        body = legacy_manifest("slo")
        target = fixture()["generic_source"]["revision"]
        if corrupt:
            body["runtime_projection_digests"]["scan"] = "0" * 64
        manifest, terraform = files(temp, body)
        before = (manifest.read_bytes(), terraform.read_bytes())
        result = cli("upgrade", target, "--manifest", str(manifest), "--terraform", str(terraform),
                     env=offline_git(temp))
        if corrupt:
            assert result.returncode == 2
            assert "digest drift" in result.stderr
            assert (manifest.read_bytes(), terraform.read_bytes()) == before
        else:
            assert result.returncode == 0, result.stderr
            updated = json.loads(manifest.read_text())
            assert updated["runtime"]["scan"][KEY] == "slo"
            consumer_manifest.validate(updated)


@pytest.mark.parametrize("mutation", [
    'SCAN_ENV += ("GCINSIGHT_NEW_TARGET_FIELD",)\n',
    'PROJECTION_ENVS["scan"] = ()\n',
    'SCAN_ENV: tuple = ()\n',
])
def test_schema_extraction_rejects_nonliteral_writes(mutation):
    source = (ROOT / "collector/identity.py").read_text()
    if mutation.startswith("SCAN_ENV +="):
        source = source.replace("PROJECTION_ENVS = {", mutation + "PROJECTION_ENVS = {")
    else:
        source += "\n" + mutation
    with pytest.raises(consumer_manifest.ManifestError, match="target projection schema"):
        consumer_manifest.static_projection_schema(source)


def test_schema_extraction_rejects_dynamic_code_without_executing_it():
    source = (ROOT / "collector/identity.py").read_text()
    malicious = source.replace('"scan": SCAN_ENV,', '"scan": dangerous(),')
    with pytest.raises(consumer_manifest.ManifestError, match="target projection schema"):
        consumer_manifest.static_projection_schema(malicious)
