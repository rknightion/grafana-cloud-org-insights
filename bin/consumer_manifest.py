#!/usr/bin/env python3
"""Validate and upgrade an immutable Grafana Cloud Org Insights consumer manifest."""

from __future__ import annotations

import argparse
import ast
import contextlib
import functools
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from decimal import Decimal
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collector import identity, provision  # noqa: E402

SCHEMA_PATH = ROOT / "consumer" / "manifest.schema.json"
MODULE_ROOT = ROOT / "terraform"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_VALUE_MARKERS = (
    "Bearer ",
    "glsa_",
    "glc_",
    "grafana_service_account_token",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)
TOP_LEVEL_KEYS = {
    "schema_version", "generic_source", "overlay_digest", "runtime_projection_digests",
    "runtime", "aws", "policy",
}
DEFAULT_CORE_PATHS = ("collector", "scan.py", "bin/dashboards.py", "bin/alerts.py")
OVERLAY_KEYS = ("schema_version", "runtime", "aws", "policy")
# aws keys added after manifests already existed. Absent means this default, which never enters the
# overlay digest, so a manifest written before the key existed keeps its digest; prune removes it.
ADDITIVE_AWS_DEFAULTS = {"manage_adopted_bucket_config": False}
MODULE_SOURCE = re.compile(
    r'(source\s*=\s*"git::https://github\.com/'
    r'rknightion/grafana-cloud-org-insights\.git//terraform\?ref=)'
    r'([0-9a-f]{40})(")'
)


class ManifestError(ValueError):
    """The deployment manifest is incomplete, unsafe, or inconsistent."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{path}: {exc}") from exc


def _required_keys(section: str) -> set[str]:
    """Every key of a section in the EFFECTIVE manifest. The schema's `required` lists what the file must
    carry; the rest may be omitted as module defaults."""
    schema = load_json(SCHEMA_PATH)
    return set(schema["properties"][section]["properties"])


def overlay(manifest: dict[str, Any]) -> dict[str, Any]:
    out = {key: manifest[key] for key in OVERLAY_KEYS}
    if isinstance(out["aws"], dict):
        out["aws"] = {key: value for key, value in out["aws"].items()
                      if not (key in ADDITIVE_AWS_DEFAULTS and value is ADDITIVE_AWS_DEFAULTS[key])}
    return out


def calculated_digests(manifest: dict[str, Any], *, legacy_scan_policy: bool = False,
                       module_root: pathlib.Path | None = None) -> tuple[str, dict[str, str]]:
    # The SAME function the task runs at startup. A second implementation here is how the manifest and
    # the rendered environment came to disagree about a policy they both held (GCI-0045).
    # Digests cover the EFFECTIVE manifest: an omitted key hashes as the module default it renders as,
    # so pruning changes no projection digest and the task's rendered environment still matches.
    manifest = effective(manifest, module_root)
    projections = {
        kind: identity.projection_digest(kind, manifest["runtime"][kind])
        for kind in sorted(identity.PROJECTION_ENVS)
    }
    if legacy_scan_policy:
        # Verify the old contract before upgrading it; the old scan digest did not contain this key.
        scan = identity.canonical_projection("scan", manifest["runtime"]["scan"])
        scan.pop("GCINSIGHT_READER_PRODUCT_READS")
        projections["scan"] = digest(scan)
    return digest(overlay(manifest)), projections


def github_repo(value: str) -> str:
    patterns = (
        r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$",
        r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return match.group(1).lower()
    raise ManifestError(f"unsupported GitHub repository URL: {value}")


def validate_json_runtime_types(runtime: dict[str, Any]) -> None:
    """Reject JSON that the module's typed inputs would change before env rendering.

    Keep the manifest immutable: dropping object attributes or coercing a scalar here would also
    require rewriting its overlay digest. The offline variables.tf contract test guards these shapes.
    Decimal parsing detects precision lost by identity's float-to-integer canonicalisation.
    """
    scan = runtime["scan"]
    retention_env = "GCINSIGHT_EXPECTED_RETENTION_POLICY"
    weights_env = "GCINSIGHT_COVERAGE_SCORE_WEIGHTS"
    for env in (retention_env, weights_env):
        try:
            value = json.loads(scan[env], parse_float=Decimal, parse_constant=Decimal)
        except (ValueError, TypeError):
            raise ManifestError(f"runtime.scan.{env} must contain valid JSON") from None
        if env == retention_env:
            if not isinstance(value, list) or any(
                not isinstance(item, dict)
                or set(item) != {"selector", "minimum_period"}
                or any(not isinstance(field, str) for field in item.values())
                for item in value
            ):
                raise ManifestError(
                    f"runtime.scan.{env} must be a list of objects containing exactly "
                    "selector and minimum_period strings"
                )
        else:
            keys = {"metrics", "logs", "traces", "profiles", "dashboard", "alert", "slo"}
            if not isinstance(value, dict) or set(value) != keys or any(
                type(weight) not in (int, Decimal)
                or (isinstance(weight, Decimal) and not weight.is_finite())
                for weight in value.values()
            ):
                raise ManifestError(f"runtime.scan.{env} must contain exactly the seven numeric weights")
            canonical_value = json.loads(
                identity.canonical_json_text(scan[env]), parse_float=Decimal, parse_constant=Decimal
            )
            if value != canonical_value:
                raise ManifestError(f"runtime.scan.{env} loses numeric precision during digest rendering")


def validate(manifest: dict[str, Any], *, allow_legacy_scan_policy: bool = False,
             module_root: pathlib.Path | None = None) -> None:
    if not isinstance(manifest, dict) or set(manifest) != TOP_LEVEL_KEYS:
        raise ManifestError(f"manifest top-level keys differ: expected {sorted(TOP_LEVEL_KEYS)}")
    # Every rule below applies to the effective manifest: an omitted key is only ever the module default.
    raw_aws = manifest.get("aws")
    manifest = effective(manifest, module_root)
    if isinstance(raw_aws, dict) and isinstance(manifest.get("aws"), dict):
        for name, switch in (("bucket_name", "create_bucket"), ("secret_name", "create_secret")):
            if name not in raw_aws and manifest["aws"].get(switch) is False:
                # An adopted resource is named, never derived from name_prefix.
                raise ManifestError(f"aws.{name} must be explicit when aws.{switch} is false")
    if manifest.get("schema_version") != 1:
        raise ManifestError("unsupported manifest schema_version")

    source = manifest.get("generic_source")
    if not isinstance(source, dict) or set(source) != {"repository", "revision"}:
        raise ManifestError("generic_source must contain only repository and revision")
    if github_repo(str(source["repository"])) != "rknightion/grafana-cloud-org-insights":
        raise ManifestError("generic_source.repository does not identify this product repository")
    if not FULL_SHA.fullmatch(str(source["revision"])):
        raise ManifestError("generic_source.revision must be a full lowercase commit SHA")

    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != set(identity.PROJECTION_ENVS):
        raise ManifestError("runtime projections differ from collector.identity.PROJECTION_ENVS")
    product_env = "GCINSIGHT_READER_PRODUCT_READS"
    legacy_scan_policy = (allow_legacy_scan_policy and isinstance(runtime.get("scan"), dict)
                          and product_env not in runtime["scan"])
    for kind, expected_names in identity.PROJECTION_ENVS.items():
        if kind == "scan" and isinstance(runtime.get("scan"), dict):
            expected_names = tuple(name for name in expected_names
                                   if name not in identity.PRODUCER_RULE_DEFAULTS or name in runtime["scan"])
        if kind == "scan" and isinstance(runtime.get("scan"), dict) and not any(
                name in runtime["scan"] for name in identity.LABEL_INVENTORY_DEFAULTS):
            expected_names = tuple(name for name in expected_names
                                   if name not in identity.LABEL_INVENTORY_DEFAULTS)
        if kind == "scan" and legacy_scan_policy:
            expected_names = tuple(name for name in expected_names if name != product_env)
        values = runtime.get(kind)
        if not isinstance(values, dict) or set(values) != set(expected_names):
            present = set(values) if isinstance(values, dict) else set()
            raise ManifestError(
                f"runtime.{kind} keys differ: missing={sorted(set(expected_names) - present)}, "
                f"extra={sorted(present - set(expected_names))}"
            )
        for name, value in values.items():
            if not isinstance(value, str):
                raise ManifestError(f"runtime.{kind}.{name} must be a string")
            if not value and name not in identity.OPTIONAL_EMPTY_ENV:
                raise ManifestError(f"runtime.{kind}.{name} must be explicit and non-empty")
            if "\n" in value or "\x00" in value:
                raise ManifestError(f"runtime.{kind}.{name} is not environment-safe")

    for name in identity.PRODUCER_RULE_DEFAULTS:
        if name in runtime["scan"] and runtime["scan"][name] not in {"0", "1"}:
            raise ManifestError(f"runtime.scan.{name} must be 1 or 0")
    validate_json_runtime_types(runtime)
    for kind in ("scan", "provisioner"):
        for name in ("GCINSIGHT_OPT_OUT", "GCINSIGHT_READER_PRODUCT_READS"):
            value = runtime[kind].get(name)
            # The module renders join(",", compact(split(",", value))). A value that would not survive
            # that unchanged hashes one string here and renders another in the task.
            if isinstance(value, str) and ",".join(part for part in value.split(",") if part) != value:
                raise ManifestError(f"runtime.{kind}.{name} must be a canonical comma list: no empty "
                                    "elements and no leading or trailing comma")
    if any(name in runtime["scan"] for name in identity.LABEL_INVENTORY_DEFAULTS):
        from collector import config
        scan_policy = runtime["scan"]
        if scan_policy["GCINSIGHT_LABEL_INVENTORY_ENABLED"] not in {"0", "1"}:
            raise ManifestError("runtime.scan.GCINSIGHT_LABEL_INVENTORY_ENABLED must be 1 or 0")
        try:
            config.label_inventory_tunables(scan_policy["GCINSIGHT_LABEL_INVENTORY_TUNABLES"])
            config.label_inventory_static_names(scan_policy["GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES"])
            budget = config.label_inventory_budget(scan_policy["GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS"])
            if str(int(budget)) != scan_policy["GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS"]:
                raise ValueError("budget must use whole seconds for Terraform rendering")
        except (config.MissingConfig, ValueError) as exc:
            raise ManifestError(str(exc)) from None

    # Values Terraform cannot round-trip. The consumer wiring renders the flag as `== "1"`, so "true"
    # (which the collector accepts) renders "0"; and both tasks render OPT_OUT from ONE module input,
    # so two different lists make one task refuse to start on a digest mismatch (GCI-0045 review).
    if runtime["scan"]["GCINSIGHT_DASHBOARD_DETAIL_ENABLED"] not in {"1", "0"}:
        raise ManifestError("runtime.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED must be 1 or 0")
    if runtime["scan"]["GCINSIGHT_OPT_OUT"] != runtime["provisioner"]["GCINSIGHT_OPT_OUT"]:
        raise ManifestError("runtime.scan and runtime.provisioner GCINSIGHT_OPT_OUT must be identical")

    if (not legacy_scan_policy
            and runtime["scan"][product_env] != runtime["provisioner"][product_env]):
        raise ManifestError(
            "runtime.scan and runtime.provisioner GCINSIGHT_READER_PRODUCT_READS must be identical"
        )

    for section in ("aws", "policy"):
        values = manifest.get(section)
        required = _required_keys(section)
        if section == "aws" and isinstance(values, dict):
            required -= {name for name in ADDITIVE_AWS_DEFAULTS if name not in values}
        if not isinstance(values, dict) or set(values) != required:
            present = set(values) if isinstance(values, dict) else set()
            raise ManifestError(
                f"{section} keys differ: missing={sorted(required - present)}, "
                f"extra={sorted(present - required)}"
            )

    aws = manifest["aws"]
    boolean_fields = {
        "create_bucket", "create_secret", "create_views_reader_user", "create_provisioner",
        "firehose_logs_enabled", "firehose_log_subscription_enabled", "assign_public_ip",
        "schedules_enabled", "provisioner_enabled", *ADDITIVE_AWS_DEFAULTS,
    }
    if any(not isinstance(aws[name], bool) for name in boolean_fields if name in aws):
        raise ManifestError("all AWS feature and adoption switches must be booleans")
    string_fields = set(aws) - boolean_fields
    if any(not isinstance(aws[name], str) or not aws[name] for name in string_fields):
        raise ManifestError("all AWS identities, schedules, and tag values must be non-empty strings")
    if aws["task_architecture"] not in {"ARM64", "X86_64"}:
        raise ManifestError("aws.task_architecture must be ARM64 or X86_64")

    policy = manifest["policy"]
    policy_strings = {
        "reader_policy_id", "writer_policy_id", "reader_policy_name", "writer_policy_name",
        "provisioner_policy_name", "datasource_query_scope", "rate_card_s3_key",
        "rate_card_semantics", "pii_storage",
    }
    if any(not isinstance(policy[name], str) or not policy[name] for name in policy_strings):
        raise ManifestError("all policy identities and semantic choices must be non-empty strings")
    if policy["datasource_query_scope"] != "datasources:uid:grafanacloud-usage-insights":
        raise ManifestError("policy.datasource_query_scope widens the query permission")
    if (
        type(policy["declared_reader_permission_pairs"]) is not int
        or policy["declared_reader_permission_pairs"] != len(provision.DESIRED_PAIRS)
    ):
        raise ManifestError("declared reader permission-pair count differs from the product role")
    if policy["rate_card_semantics"] not in {"base_rate_only", "dpm_aware"}:
        raise ManifestError("unsupported rate-card semantics")
    if not isinstance(policy["rate_card_present"], bool):
        raise ManifestError("policy.rate_card_present must be a boolean")
    if (
        type(policy["public_dashboards_target"]) is not int
        or policy["public_dashboards_target"] < 0
    ):
        raise ManifestError("policy.public_dashboards_target must be a non-negative integer")

    rendered = canonical(overlay(manifest)).decode()
    for marker in FORBIDDEN_VALUE_MARKERS:
        if marker in rendered:
            raise ManifestError(f"manifest contains forbidden credential marker {marker!r}")
    if runtime["scan"]["GCINSIGHT_STACK_TOKEN_PREFIX"] != runtime["provisioner"]["GCINSIGHT_STACK_TOKEN_PREFIX"]:
        raise ManifestError("scan and provisioner credential-store prefixes differ")
    if runtime["scan"]["GCINSIGHT_ORG_ID"] != runtime["provisioner"]["GCINSIGHT_ORG_ID"]:
        raise ManifestError("scan and provisioner organization identities differ")

    expected_overlay, expected_projections = calculated_digests(
        manifest, legacy_scan_policy=legacy_scan_policy, module_root=module_root
    )
    if not DIGEST.fullmatch(str(manifest["overlay_digest"])) or manifest["overlay_digest"] != expected_overlay:
        raise ManifestError("overlay_digest does not match canonical overlay content")
    recorded = manifest.get("runtime_projection_digests")
    if not isinstance(recorded, dict) or set(recorded) != set(expected_projections):
        raise ManifestError("runtime_projection_digests keys differ from runtime projections")
    if recorded != expected_projections:
        raise ManifestError("runtime projection digest drift")


def regenerate(manifest: dict[str, Any], *, module_root: pathlib.Path | None = None,
               prune_defaults: bool = False) -> dict[str, Any]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("runtime"), dict):
        raise ManifestError("manifest must contain a runtime projection object")
    updated = dict(manifest)
    product_env = "GCINSIGHT_READER_PRODUCT_READS"
    scan = updated["runtime"].get("scan")
    provisioner = updated["runtime"].get("provisioner")
    if isinstance(scan, dict) and product_env not in scan and isinstance(provisioner, dict):
        if product_env in provisioner:
            # Copy only the added seam. Regenerate is explicit; check never rewrites legacy input.
            updated["runtime"] = dict(updated["runtime"], scan=dict(
                scan, **{product_env: provisioner[product_env]}
            ))
    scan = updated["runtime"].get("scan")
    if isinstance(scan, dict) and not any(name in scan for name in identity.LABEL_INVENTORY_DEFAULTS):
        # Freeze the additive group's defaults on a pre-label manifest. A partly present group belongs to
        # a pruned manifest, whose omitted members effective() supplies as module defaults.
        updated["runtime"] = dict(updated["runtime"], scan={
            **identity.LABEL_INVENTORY_DEFAULTS, **scan,
        })
    # Validate before digest calculation too: an overflowing JSON number must be a contract error,
    # not an exception in identity's canonicalisation. Leave malformed projection shapes to validate.
    runtime = effective(updated, module_root)["runtime"]
    scan = runtime.get("scan")
    if isinstance(scan, dict) and all(isinstance(scan.get(env), str) for env in (
        "GCINSIGHT_EXPECTED_RETENTION_POLICY", "GCINSIGHT_COVERAGE_SCORE_WEIGHTS"
    )):
        validate_json_runtime_types(runtime)
    if prune_defaults:
        updated = pruned(updated, module_root)
    try:
        updated["overlay_digest"], updated["runtime_projection_digests"] = calculated_digests(
            updated, module_root=module_root)
    except KeyError as exc:
        raise ManifestError(f"manifest is missing required content: {exc}") from exc
    validate(updated, module_root=module_root)
    return updated


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_text(path: pathlib.Path, text: str, *, mode: int | None = None) -> None:
    resolved_mode = mode if mode is not None else (
        path.stat().st_mode & 0o777 if path.exists() else 0o644
    )
    temporary: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = pathlib.Path(handle.name)
        os.chmod(temporary, resolved_mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: pathlib.Path, value: Any) -> None:
    try:
        atomic_write_text(path, json_text(value))
    except OSError as exc:
        raise ManifestError(f"cannot write {path}: {exc}") from exc


def journal_path(manifest: pathlib.Path) -> pathlib.Path:
    return manifest.with_name(f".{manifest.name}.upgrade-journal.json")


def reject_incomplete_upgrade(manifest: pathlib.Path) -> None:
    journal = journal_path(manifest)
    if journal.exists():
        raise ManifestError(
            f"incomplete consumer upgrade journal exists at {journal}; rerun upgrade to recover"
        )


def recover_incomplete_upgrade(manifest: pathlib.Path, terraform: pathlib.Path) -> None:
    journal = journal_path(manifest)
    if not journal.exists():
        return
    body = load_json(journal)
    required = {
        "schema_version", "manifest_path", "terraform_path", "original_manifest",
        "original_terraform", "target_manifest", "target_terraform",
    }
    if not isinstance(body, dict) or set(body) != required or body.get("schema_version") != 1:
        raise ManifestError(f"invalid consumer upgrade journal at {journal}")
    if pathlib.Path(body["manifest_path"]).resolve() != manifest.resolve():
        raise ManifestError(f"upgrade journal {journal} names a different manifest")
    if pathlib.Path(body["terraform_path"]).resolve() != terraform.resolve():
        raise ManifestError(f"upgrade journal {journal} names different Terraform wiring")
    try:
        current_manifest = manifest.read_text()
        current_terraform = terraform.read_text()
    except OSError as exc:
        raise ManifestError(f"cannot inspect interrupted consumer upgrade: {exc}") from exc
    if current_manifest not in {body["original_manifest"], body["target_manifest"]}:
        raise ManifestError(f"manifest changed independently after interrupted upgrade: {manifest}")
    if current_terraform not in {body["original_terraform"], body["target_terraform"]}:
        raise ManifestError(f"Terraform changed independently after interrupted upgrade: {terraform}")
    try:
        atomic_write_text(manifest, body["original_manifest"])
        atomic_write_text(terraform, body["original_terraform"])
        journal.unlink()
        fsync_directory(journal.parent)
    except OSError as exc:
        raise ManifestError(f"cannot recover interrupted consumer upgrade: {exc}") from exc


def run_git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ManifestError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def verify_remote_commit(root: pathlib.Path, repository: str, revision: str) -> None:
    """Prove the declared remote, not only the local object database, serves the commit."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "fetch", "--dry-run", "--no-tags", repository, revision],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise ManifestError(
            f"declared generic remote timed out resolving commit {revision}"
        ) from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ManifestError(
            f"declared generic remote cannot resolve commit {revision}: {detail}"
        )


def verify_identifier_gate(generic_source: pathlib.Path) -> None:
    result = subprocess.run(
        [str(ROOT / "bin" / "check-customer-identifiers"), str(generic_source)],
        check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ManifestError(result.stderr.strip() or "customer-identifier gate failed")


def verify_no_replacement_core(deployment_root: pathlib.Path, extra_paths: list[str]) -> None:
    for value in (*DEFAULT_CORE_PATHS, *extra_paths):
        path = pathlib.PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise ManifestError(f"invalid forbidden core path {value!r}")
        candidate = deployment_root / path
        tracked = run_git(deployment_root, "ls-files", "--", str(path))
        untracked = run_git(
            deployment_root, "ls-files", "--others", "--exclude-standard", "--", str(path)
        )
        if candidate.exists() or tracked or untracked:
            raise ManifestError(f"deployment contains replacement product core at {path}")


def verify_checkout(manifest: dict[str, Any], generic_source: pathlib.Path) -> None:
    source = manifest["generic_source"]
    if run_git(generic_source, "rev-parse", "HEAD") != source["revision"]:
        raise ManifestError("generic checkout HEAD differs from the manifest revision")
    if run_git(generic_source, "status", "--porcelain", "--untracked-files=normal"):
        raise ManifestError("generic checkout is dirty")
    if github_repo(run_git(generic_source, "remote", "get-url", "origin")) != github_repo(source["repository"]):
        raise ManifestError("generic checkout origin differs from the manifest repository")


def terraform_revision(path: pathlib.Path) -> str:
    try:
        text = path.read_text()
    except OSError as exc:
        raise ManifestError(f"{path}: {exc}") from exc
    matches = MODULE_SOURCE.findall(text)
    if len(matches) != 1:
        raise ManifestError("expected exactly one immutable generic Terraform module source")
    return matches[0][1]


def verify_deployment_files(
    manifest: dict[str, Any], deployment_root: pathlib.Path, terraform: pathlib.Path,
    *, require_committed: bool = False,
) -> None:
    if terraform_revision(terraform) != manifest["generic_source"]["revision"]:
        raise ManifestError("Terraform module ref differs from the manifest revision")
    manifest_value = manifest.pop("__path__", None)
    checked = [terraform]
    if manifest_value:
        checked.append(pathlib.Path(manifest_value))
    relative: list[str] = []
    for path in checked:
        try:
            relative.append(str(path.resolve().relative_to(deployment_root.resolve())))
        except ValueError as exc:
            raise ManifestError(f"{path} is outside deployment root {deployment_root}") from exc
    if require_committed and run_git(deployment_root, "status", "--porcelain", "--", *relative):
        raise ManifestError("deployment manifest or Terraform wiring is not committed")


# --- Terraform wiring preflight (GCI-0045) -------------------------------------------------------
#
# The manifest digest is only half of the contract. The task environment is whatever the module RENDERS,
# and a manifest key the consumer never passes into the module renders as the module default instead.
# The task then refuses to start on a digest mismatch after the image has been pushed and applied. This
# reads the module's own env list and the consumer's module block and fails before either happens.

_MODULE_ENV = re.compile(
    r'\{\s*name\s*=\s*"(GCINSIGHT_[A-Z0-9_]+)",\s*value\s*=\s*(.+?)\s*\},?\s*$', re.M)
_MODULE_ENV_FILES = {"scan": "ecs.tf", "provisioner": "provisioner.tf"}
# Wired by the module from the manifest's own digest block, not from a runtime value.
_WIRING_EXEMPT = frozenset({"GCINSIGHT_RUNTIME_CONFIG_DIGEST", "GCINSIGHT_REQUIRE_EXPLICIT_CONFIG"})
# Projected keys the module renders from something other than one variable, so this preflight cannot
# check them. A test pins this set: a module env entry the regex stops reading shows up as drift here
# rather than as silently lost coverage.
UNCHECKED_PROJECTED_ENV = frozenset({
    "GCINSIGHT_S3_BUCKET",   # local.bucket_name: var.bucket_name or a name_prefix default
    "GCINSIGHT_S3_REGION",   # data.aws_region
    "GCINSIGHT_SSM_REGION",  # data.aws_region
})


def module_env_inputs(module_root: pathlib.Path) -> dict[str, dict[str, tuple[str, str]]]:
    """{kind: {env: (module variable, render expression)}} for env values taken from one variable.

    The module renders `local.inputs.<variable>`, which in explicit mode IS `var.<variable>`
    (terraform/consumer_manifest.tf, pinned by a contract test), so the expression is returned in its
    `var.` form for module_default_render and the offline tofu console round-trip.
    """
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for kind, name in _MODULE_ENV_FILES.items():
        text = (module_root / name).read_text()
        entries: dict[str, tuple[str, str]] = {}
        for env, expr in _MODULE_ENV.findall(text):
            expr = re.sub(r"\blocal\.inputs\.", "var.", expr)
            variables = set(re.findall(r"\bvar\.([a-z0-9_]+)", expr))
            if env in _WIRING_EXEMPT or len(variables) != 1:
                continue
            entries[env] = (variables.pop(), expr)
        out[kind] = entries
    return out


def module_default_render(module_root: pathlib.Path, variable: str, expr: str) -> str | None:
    """What the module renders for `expr` when `variable` is left at its default, or None if unknown."""
    text = "\n".join(p.read_text() for p in sorted(module_root.glob("*.tf")))
    block = re.search(rf'variable\s+"{re.escape(variable)}"\s*\{{(.*?)\n\}}', text, re.S)
    if not block:
        return None
    default = re.search(r"^\s*default\s*=\s*(.+?)\s*$", block.group(1), re.M)
    if not default:
        return None
    raw = default.group(1)
    if raw == "{" and expr.startswith("jsonencode("):
        # A multi-line map of scalars, as coverage_score_weights declares.
        body = block.group(1)[default.end():]
        body = body[:body.index("}")] if "}" in body else ""
        mapping: dict[str, Any] = {}
        for key, value in re.findall(r"^\s*([A-Za-z_][\w]*)\s*=\s*(.+?)\s*$", body, re.M):
            try:
                mapping[key] = json.loads(value)
            except ValueError:
                return None
        return identity.canonical_json_text(json.dumps(mapping))
    if expr.strip() in {f"jsonencode(var.{variable})", f"jsonencode(jsondecode(var.{variable}))"}:
        try:
            value = json.loads(raw)
            if expr.strip() == f"jsonencode(jsondecode(var.{variable}))":
                value = json.loads(value)
            return identity.canonical_json_text(json.dumps(value))
        except (ValueError, TypeError):
            return None
    if expr.strip() == f"tostring(var.{variable})" and re.fullmatch(r"[0-9]+", raw):
        return raw
    bare = expr.strip() == f"var.{variable}"
    if bare and re.fullmatch(r'"[^"]*"', raw):
        return raw[1:-1]
    if expr.startswith("join(") and raw == "[]":
        return ""
    if expr.startswith("jsonencode(") and raw in ("[]", "{}"):
        return raw
    if "?" in expr and raw in ("true", "false"):
        picked = re.search(r'\?\s*"([^"]*)"\s*:\s*"([^"]*)"', expr)
        if picked:
            return picked.group(1) if raw == "true" else picked.group(2)
    return None


# --- Manifest mode (terraform/consumer_manifest.tf) ------------------------------------------------------
#
# In manifest mode the module reads the decoded manifest itself. `local.inputs` in that file is the one
# table of which manifest key feeds which module input; it is parsed here rather than restated, so the
# refusal list and the default renders cannot drift from what the module does.

_MANIFEST_TF = "consumer_manifest.tf"
_INPUT_FROM_KEY = re.compile(
    r'^\s*([a-z0-9_]+)\s*=\s*contains\(local\.manifest_keys\.(scan|provisioner|aws),\s*"([A-Za-z0-9_]+)"\)'
    r'\s*\?.*:\s*var\.\1\s*$')
_INPUT_RENDERED = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*local\.manifest_mode\s*\?.*:\s*var\.\1\s*$")
_INPUT_KILL_SWITCH = re.compile(
    r'^\s*([a-z0-9_]+)\s*=\s*var\.\1\s*&&\s*\(contains\(local\.manifest_keys\.(aws),\s*"([a-z0-9_]+)"\)'
    r'\s*\?.*:\s*(true|false)\)\s*$')
TIER_SCHEDULE_KEY = re.compile(r"^(t[0-9]+)_schedule$")


class ManifestInterface:
    """What a module revision's manifest mode reads, parsed from its consumer_manifest.tf."""

    def __init__(self, inputs: dict[tuple[str, str], str], rendered: frozenset[str],
                 kill_switches: dict[str, tuple[tuple[str, str], bool]],
                 required: dict[str, frozenset[str]], shared: frozenset[str],
                 tier_schedules: dict[str, str]):
        self.inputs = inputs                # (section, key) -> module variable
        self.rendered = rendered            # variables the module renders itself in manifest mode
        self.kill_switches = kill_switches  # variable -> ((section, key), value when the key is absent)
        self.required = required            # section -> keys with no module default
        self.shared = shared                # keys both runtime projections carry, read from scan
        self.tier_schedules = tier_schedules  # tier -> module default schedule expression
        self.tag_keys: dict[str, str] = {}    # tag key -> aws key, applied under the caller's tags

    @property
    def refused(self) -> frozenset[str]:
        """Module arguments a manifest-mode consumer must not pass."""
        return frozenset(self.inputs.values()) | self.rendered


def _local_block(text: str, name: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*([{{\[])", text, re.M)
    if not match:
        return None
    opening = match.group(1)
    closing = {"{": "}", "[": "]"}[opening]
    depth = 0
    for index in range(match.start(1), len(text)):
        depth += {opening: 1, closing: -1}.get(text[index], 0)
        if depth == 0:
            return text[match.start(1) + 1:index]
    raise ManifestError(f"unbalanced {name} in {_MANIFEST_TF}")


def module_manifest_interface(module_root: pathlib.Path | None = None) -> ManifestInterface | None:
    """Parse a module revision's manifest mode, or None for a revision without one."""
    path = (module_root or MODULE_ROOT) / _MANIFEST_TF
    if not path.exists():
        return None
    text = path.read_text()
    block = _local_block(text, "inputs")
    if block is None:
        raise ManifestError(f"{_MANIFEST_TF} has no inputs table")
    inputs: dict[tuple[str, str], str] = {}
    rendered: set[str] = set()
    kill_switches: dict[str, tuple[tuple[str, str], bool]] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if match := _INPUT_FROM_KEY.match(line):
            inputs[(match.group(2), match.group(3))] = match.group(1)
        elif match := _INPUT_RENDERED.match(line):
            rendered.add(match.group(1))
        elif match := _INPUT_KILL_SWITCH.match(line):
            kill_switches[match.group(1)] = ((match.group(2), match.group(3)), match.group(4) == "true")
        else:
            # Fail closed: an entry this parser cannot read would silently drop out of the refusal list.
            raise ManifestError(f"{_MANIFEST_TF} inputs entry has an unsupported shape: {stripped[:60]}")

    def string_list(source: str | None) -> frozenset[str]:
        return frozenset(re.findall(r'"([A-Za-z0-9_]+)"', source or ""))

    required_block = _local_block(text, "manifest_required_keys") or ""
    required = {
        section: string_list(_local_block(required_block, section))
        for section in ("scan", "provisioner", "aws")
    }
    tier_block = _local_block(text, "default_tier_schedules") or ""
    tier_schedules = dict(re.findall(r'^\s*(t[0-9]+)\s*=\s*"([^"]*)"', tier_block, re.M))
    tags = re.search(r"^\s*manifest_tags\s*=.*?\n\s*\}", text, re.M | re.S)
    interface = ManifestInterface(
        inputs, frozenset(rendered), kill_switches, required,
        string_list(_local_block(text, "manifest_shared_keys")), tier_schedules,
    )
    # aws keys the module applies as tags in manifest mode: represented, but not a refused argument.
    interface.tag_keys = dict(re.findall(
        r"^\s*([A-Za-z]+)\s*=\s*tostring\(local\.manifest\.aws\.([a-z_]+)\)", tags.group(0) if tags else "",
        re.M))
    return interface


def _variable_default(module_root: pathlib.Path, variable: str) -> tuple[bool, Any]:
    """(True, value) for a variable whose default is a JSON-literal scalar, else (False, None)."""
    text = "\n".join(p.read_text() for p in sorted(module_root.glob("*.tf")))
    block = re.search(rf'variable\s+"{re.escape(variable)}"\s*\{{(.*?)\n\}}', text, re.S)
    default = re.search(r"^\s*default\s*=\s*(.+?)\s*$", block.group(1), re.M) if block else None
    if not default:
        return False, None
    try:
        value = json.loads(default.group(1))
    except ValueError:
        return False, None
    if value is None or not isinstance(value, (str, bool)):
        return False, None
    return True, value


def _derived_name_default(module_root: pathlib.Path, variable: str) -> str | None:
    """main.tf's `<name>-<suffix>` fallback for an empty bucket_name or secret_name, as a template."""
    text = (module_root / "main.tf").read_text()
    match = re.search(
        rf'^\s*{variable}\s*=\s*local\.inputs\.{variable}\s*!=\s*""\s*\?\s*local\.inputs\.{variable}\s*:'
        r'\s*"\$\{local\.inputs\.name_prefix\}([^"$]*)"\s*$', text, re.M)
    return None if match is None else "{name_prefix}" + match.group(1)


def module_default_renders(module_root: pathlib.Path | None = None) -> dict[tuple[str, str], Any]:
    """{(section, key): the value manifest mode renders when the key is absent}, for every key that has one.

    A key absent from this map has no known default render and stays required. Values for runtime keys are
    rendered env strings; aws values are JSON scalars, and `{name_prefix}` in a string is substituted.
    """
    root = (module_root or MODULE_ROOT).resolve()
    return dict(_module_default_renders(root, _module_fingerprint(root)))


def _module_fingerprint(root: pathlib.Path) -> tuple[tuple[str, int, int], ...]:
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(root.glob("*.tf")))


@functools.lru_cache(maxsize=8)
def _module_default_renders(root: pathlib.Path, _fingerprint: tuple) -> dict[tuple[str, str], Any]:
    interface = module_manifest_interface(root)
    if interface is None:
        return {}
    out: dict[tuple[str, str], Any] = {}
    for kind, entries in module_env_inputs(root).items():
        for env, (variable, expr) in entries.items():
            if env not in identity.PROJECTION_ENVS[kind]:
                continue
            reads = interface.inputs.get((kind, env)) or (
                interface.inputs.get(("scan", env)) if env in interface.shared else None)
            if reads != variable:
                continue
            render = module_default_render(root, variable, expr)
            if render is not None:
                out[(kind, env)] = render
    for (section, key), variable in interface.inputs.items():
        if section != "aws":
            continue
        known, value = _variable_default(root, variable)
        if known and value == "":
            template = _derived_name_default(root, variable)
            known, value = template is not None, template
        if known:
            out[(section, key)] = value
    for (section, key), absent in interface.kill_switches.values():
        out[(section, key)] = absent
    for tier, expression in interface.tier_schedules.items():
        out[("aws", f"{tier}_schedule")] = expression
    for section, keys in interface.required.items():
        for key in keys:
            out.pop((section, key), None)
    return out


def _resolved(value: Any, aws: dict[str, Any]) -> Any:
    if isinstance(value, str) and "{name_prefix}" in value:
        prefix = aws.get("name_prefix")
        return value.replace("{name_prefix}", prefix) if isinstance(prefix, str) and prefix else None
    return value


def effective(manifest: Any, module_root: pathlib.Path | None = None) -> Any:
    """The manifest with every omitted key that has a module default filled with that default render.

    A complete manifest is returned unchanged, so its digests are byte-identical. Malformed shapes are
    returned as they are for validate to report. Three omissions are deliberately NOT filled:
      * the whole label-inventory group, which is the pre-label legacy form identity still accepts;
      * one side of a key both projections carry, which is either the pre-product-reads legacy form or
        a contradiction that validation must report;
      * an ADDITIVE_AWS_DEFAULTS key, whose absence is its default and never enters the overlay digest.
    """
    if not isinstance(manifest, dict):
        return manifest
    runtime, aws = manifest.get("runtime"), manifest.get("aws")
    if not isinstance(runtime, dict) or not isinstance(aws, dict) or not all(
            isinstance(runtime.get(kind), dict) for kind in ("scan", "provisioner")):
        return manifest
    defaults = module_default_renders(module_root)
    if not defaults:
        return manifest
    filled_runtime = {kind: dict(values) if isinstance(values, dict) else values
                      for kind, values in runtime.items()}
    filled_aws = dict(aws)
    label_present = any(name in runtime["scan"] for name in identity.LABEL_INVENTORY_DEFAULTS)
    interface = module_manifest_interface(module_root)
    for (section, key), value in defaults.items():
        if section == "aws":
            if key not in aws and key not in ADDITIVE_AWS_DEFAULTS:
                resolved = _resolved(value, aws)
                if resolved is not None:
                    filled_aws[key] = resolved
            continue
        values = runtime[section]
        if key in values:
            continue
        if section == "scan" and key in identity.PRODUCER_RULE_DEFAULTS:
            # Absent additive flags keep old overlay/runtime digests byte-identical.
            continue
        if section == "scan" and key in identity.LABEL_INVENTORY_DEFAULTS and not label_present:
            continue
        other = "provisioner" if section == "scan" else "scan"
        if interface and key in interface.shared and key in runtime[other]:
            continue
        filled_runtime[section][key] = value
    if filled_runtime == runtime and filled_aws == aws:
        return manifest
    return dict(manifest, runtime=filled_runtime, aws=filled_aws)


def omits_defaultable_keys(manifest: Any) -> bool:
    """Whether the file leaves out a key it would otherwise carry, apart from the legacy forms."""
    if not isinstance(manifest, dict):
        return False
    runtime, aws = manifest.get("runtime"), manifest.get("aws")
    if not isinstance(runtime, dict) or not isinstance(aws, dict):
        return False
    for kind, other in (("scan", "provisioner"), ("provisioner", "scan")):
        values, peer = runtime.get(kind), runtime.get(other)
        if not isinstance(values, dict) or not isinstance(peer, dict):
            return False
        missing = set(identity.PROJECTION_ENVS[kind]) - set(values)
        if kind == "scan":
            missing -= set(identity.PRODUCER_RULE_DEFAULTS)
        if kind == "scan" and not any(name in values for name in identity.LABEL_INVENTORY_DEFAULTS):
            missing -= set(identity.LABEL_INVENTORY_DEFAULTS)
        missing -= {name for name in missing if name in peer}  # pre-product-reads legacy form
        if missing:
            return True
    return bool(_required_keys("aws") - set(ADDITIVE_AWS_DEFAULTS) - set(aws))


def default_changes(manifest: dict[str, Any], before: pathlib.Path, after: pathlib.Path) -> list[str]:
    """Names of omitted keys whose effective value differs between two module revisions."""
    old, new = effective(manifest, before), effective(manifest, after)
    changed = []
    for kind in ("scan", "provisioner"):
        a, b = old["runtime"][kind], new["runtime"][kind]
        changed += [f"runtime.{kind}.{name}" for name in sorted(set(a) | set(b)) if a.get(name) != b.get(name)]
    changed += [f"aws.{name}" for name in sorted(set(old["aws"]) | set(new["aws"]))
                if old["aws"].get(name) != new["aws"].get(name)]
    return changed


def pruned(manifest: dict[str, Any], module_root: pathlib.Path | None = None) -> dict[str, Any]:
    """Remove every key whose value is exactly the module default render.

    Exact, not canonical, equality: effective() fills an omitted key with that same text, so the effective
    overlay is byte-identical and the overlay digest an image is bound to survives pruning. A JSON value
    that is default only after canonicalisation stays. Also kept on purpose:
      * GCINSIGHT_LABEL_INVENTORY_ENABLED when the whole label group is default, because an all-absent
        group is the pre-label legacy form and would hash differently;
      * bucket_name and secret_name of an ADOPTED bucket or secret, whose name identifies an existing
        resource and must not start following name_prefix.
    """
    full = effective(manifest, module_root)
    defaults = module_default_renders(module_root)
    runtime = {kind: dict(values) for kind, values in full["runtime"].items()}
    aws = dict(full["aws"])
    for (section, key), default in defaults.items():
        if section == "aws":
            resolved = _resolved(default, full["aws"])
            if key in aws and type(aws[key]) is type(resolved) and aws[key] == resolved:
                adopted = {"bucket_name": "create_bucket", "secret_name": "create_secret"}.get(key)
                if adopted is None or full["aws"].get(adopted) is True:
                    del aws[key]
            continue
        if section == "scan" and key in identity.PRODUCER_RULE_DEFAULTS:
            # A present flag is a digest-bound marker; absence is the legacy interface.
            continue
        if runtime[section].get(key) == default:
            del runtime[section][key]
    if not any(name in runtime["scan"] for name in identity.LABEL_INVENTORY_DEFAULTS) and any(
            name in full["runtime"]["scan"] for name in identity.LABEL_INVENTORY_DEFAULTS):
        marker = "GCINSIGHT_LABEL_INVENTORY_ENABLED"
        runtime["scan"][marker] = full["runtime"]["scan"][marker]
    return dict(manifest, runtime=runtime, aws=aws)


def manifest_mode_problems(manifest_path: pathlib.Path, terraform_path: pathlib.Path,
                           terraform_text: str, module_root: pathlib.Path) -> list[str] | None:
    """None for an explicit-wiring consumer; else what is wrong with its manifest-mode module block.

    Names only, never values.
    """
    block = _module_block(terraform_text)
    assigned = _assignment(block, "consumer_manifest")
    if assigned is None:
        return None
    interface = module_manifest_interface(module_root)
    if interface is None:
        return ["the pinned module revision has no consumer_manifest input; manifest mode needs v0.10.0 or later"]
    problems: list[str] = []
    code = re.sub(r"(#|//).*", "", assigned).strip()
    source = re.fullmatch(r'jsondecode\(\s*file\(\s*"\$\{path\.module\}/([^"]+)"\s*\)\s*\)', code)
    if source is None or (terraform_path.parent / source.group(1)).resolve() != manifest_path.resolve():
        problems.append('consumer_manifest must be jsondecode(file("${path.module}/<manifest>")) naming '
                        "the manifest being checked")
    for variable in sorted(interface.refused):
        if _assignment(block, variable) is not None:
            problems.append(f"module input {variable} comes from the manifest in manifest mode; "
                            "remove the explicit argument")
    tiers = _assignment(block, "tiers")
    if tiers is not None and re.search(r"\bschedule_expression\b", re.sub(r"(#|//).*", "", tiers)):
        problems.append("tiers schedule_expression comes from the manifest's aws.<tier>_schedule keys in "
                        "manifest mode; remove it")
    return problems


def _module_block(text: str) -> str:
    match = MODULE_SOURCE.search(text)
    if not match:
        raise ManifestError("expected exactly one immutable generic Terraform module source")
    headers = [m for m in re.finditer(r'^\s*module\s+"[^"]+"\s*\{', text, re.M)
               if m.end() <= match.start()]
    if not headers:
        raise ManifestError("generic Terraform module source is not inside a module block")
    depth, i = 0, headers[-1].end() - 1
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i:j + 1]
    raise ManifestError("unbalanced generic Terraform module block")


def _assignment(block: str, variable: str) -> str | None:
    """The right-hand side of `variable = ...` in the module block, across continuation lines."""
    lines = block.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"^(\s*){re.escape(variable)}\s*=(.*)$", line)
        if not match:
            continue
        indent, span = len(match.group(1)), [match.group(2)]
        for follow in lines[index + 1:]:
            if re.match(r"^\s*[a-z_][a-z0-9_]*\s*=", follow) and (
                    len(follow) - len(follow.lstrip())) <= indent:
                break
            span.append(follow)
        return "\n".join(span)
    return None


def terraform_wiring_gaps(manifest: dict[str, Any], terraform_text: str,
                          module_root: pathlib.Path) -> list[str]:
    """Manifest runtime keys the consumer's Terraform would NOT render as the manifest says.

    Names only, never values: a retention selector or an opt-out list is customer data.
    """
    block = _module_block(terraform_text)
    gaps: list[str] = []
    for kind, entries in module_env_inputs(module_root).items():
        runtime = manifest["runtime"].get(kind) or {}
        for env, (variable, expr) in sorted(entries.items()):
            if env not in runtime:
                continue
            assigned = _assignment(block, variable)
            if assigned is not None:
                # An exact token outside comments, so GCINSIGHT_OPT_OUT_X or `# GCINSIGHT_OPT_OUT`
                # cannot satisfy GCINSIGHT_OPT_OUT.
                code = re.sub(r"(#|//).*", "", assigned)
                if not re.search(rf"(?<![A-Z0-9_]){re.escape(env)}(?![A-Z0-9_])", code):
                    gaps.append(f"{kind}: module input {variable} does not read {env} from the manifest")
                continue
            rendered = module_default_render(module_root, variable, expr)
            wanted = str(runtime[env]).strip()
            if env in identity.JSON_VALUED_ENV and wanted:
                wanted = identity.canonical_json_text(wanted)
            if rendered is None or rendered != wanted:
                gaps.append(f"{kind}: {env} is not wired to module input {variable}, so Terraform "
                            "renders the module default rather than the manifest value")
    return gaps


def replaced_terraform_revision(text: str, revision: str) -> str:
    updated, count = MODULE_SOURCE.subn(rf"\g<1>{revision}\g<3>", text)
    if count != 1:
        raise ManifestError("expected exactly one immutable generic Terraform module source")
    return updated


def command_check(args: argparse.Namespace) -> int:
    reject_incomplete_upgrade(args.manifest)
    manifest = load_json(args.manifest)
    module_root = args.generic_source.resolve() / "terraform"
    try:
        validate(manifest, module_root=module_root)
    except ManifestError:
        # Defaults come from the checkout: a checkout at another revision would otherwise surface as a
        # misleading digest drift. Report that first; contract errors keep their own message.
        source = manifest.get("generic_source") if isinstance(manifest, dict) else None
        revision = source.get("revision") if isinstance(source, dict) else None
        try:
            head = run_git(args.generic_source.resolve(), "rev-parse", "HEAD")
        except ManifestError:
            head = None
        if isinstance(revision, str) and head is not None and head != revision:
            raise ManifestError("generic checkout HEAD differs from the manifest revision") from None
        raise
    verify_checkout(manifest, args.generic_source.resolve())
    verify_identifier_gate(args.generic_source.resolve())
    if args.deployment_root or args.terraform:
        if not args.deployment_root or not args.terraform:
            raise ManifestError("--deployment-root and --terraform must be supplied together")
        tagged = dict(manifest)
        tagged["__path__"] = str(args.manifest.resolve())
        verify_deployment_files(
            tagged, args.deployment_root.resolve(), args.terraform.resolve(),
            require_committed=args.require_committed_deployment,
        )
        terraform_text = args.terraform.resolve().read_text()
        problems = manifest_mode_problems(
            args.manifest, args.terraform.resolve(), terraform_text, module_root)
        if problems is None:
            # Explicit wiring: every manifest key must reach the module input that renders it.
            problems = terraform_wiring_gaps(manifest, terraform_text, module_root)
        if problems:
            raise ManifestError("Terraform wiring differs from the manifest:\n  " + "\n  ".join(problems))
        verify_no_replacement_core(
            args.deployment_root.resolve(), args.forbidden_core_path,
        )
    print(
        f"consumer manifest: clean generic={manifest['generic_source']['revision']} "
        f"overlay={manifest['overlay_digest']}"
    )
    return 0


def command_regenerate(args: argparse.Namespace) -> int:
    reject_incomplete_upgrade(args.manifest)
    original = load_json(args.manifest)
    manifest = regenerate(original, prune_defaults=getattr(args, "prune_defaults", False))
    write_json(args.manifest, manifest)
    if getattr(args, "prune_defaults", False):
        before, after = _key_count(original), _key_count(manifest)
        print(f"consumer manifest: pruned {before - after} default-equal keys ({before} -> {after})")
    print(f"consumer manifest: regenerated overlay={manifest['overlay_digest']}")
    return 0


def _key_count(manifest: Any) -> int:
    if not isinstance(manifest, dict):
        return 0
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    return sum(len(values) for values in (*runtime.values(), manifest.get("aws"))
               if isinstance(values, dict))


def static_projection_schema(source: str) -> dict[str, frozenset[str]]:
    """Read only literal projection names from an identity Git artifact, never execute it.

    Unsupported syntax fails closed: this is a compatibility guard, not a cross-version evaluator.
    """
    try:
        if len(source) > 262_144:
            raise ValueError("identity artifact is too large")
        tree = ast.parse(source)
        assignments: dict[str, ast.expr] = {}
        declaration_targets: dict[str, ast.Name] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    if target.id in assignments:
                        raise ValueError("repeated assignment")
                    assignments[target.id] = node.value
                    declaration_targets[target.id] = target
        projections = assignments.get("PROJECTION_ENVS")
        if not isinstance(projections, ast.Dict):
            raise ValueError("projection mapping must be a static dictionary")
        result: dict[str, frozenset[str]] = {}
        for key, value in zip(projections.keys, projections.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                raise ValueError("projection kind must be a literal string")
            if key.value in result or not isinstance(value, ast.Name):
                raise ValueError("projection must refer to one literal environment tuple")
            names_node = assignments.get(value.id)
            if not isinstance(names_node, (ast.Tuple, ast.List)):
                raise ValueError("environment names must be literal")
            names = ast.literal_eval(names_node)
            if (not names or any(not isinstance(name, str) for name in names)
                    or len(names) != len(set(names))):
                raise ValueError("environment names must be unique strings")
            result[key.value] = frozenset(names)
        if not result:
            raise ValueError("projection mapping is empty")
        protected = {"PROJECTION_ENVS"} | {
            value.id for value in projections.values if isinstance(value, ast.Name)
        }
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
                    and node.id in protected and node is not declaration_targets[node.id]):
                raise ValueError("projection collection has an unsupported write")
            if (isinstance(node, (ast.Subscript, ast.Attribute))
                    and isinstance(node.ctx, ast.Store)
                    and any(isinstance(part, ast.Name) and part.id in protected
                            for part in ast.walk(node))):
                raise ValueError("projection collection has an unsupported mutation")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and any(isinstance(part, ast.Name) and part.id in protected
                            for part in ast.walk(node.func))):
                raise ValueError("projection collection has an unsupported method call")
        return result
    except (SyntaxError, ValueError, TypeError, RecursionError) as exc:
        raise ManifestError("unsupported target projection schema: static literals required") from exc


def verify_target_projection_schema(generic: pathlib.Path, revision: str) -> None:
    try:
        source = run_git(generic, "show", f"{revision}:collector/identity.py")
        target = static_projection_schema(source)
        current = {kind: frozenset(names) for kind, names in identity.PROJECTION_ENVS.items()}
        if target != current:
            raise ManifestError("unsupported target projection schema: differs from this tool")
    except ManifestError as exc:
        raise ManifestError(
            "Cannot upgrade with this tool: unsupported target projection schema. "
            "Use target-matched tooling or restore the saved rollback triplet "
            "(manifest, Terraform module ref, immutable image digest); do not blindly regenerate."
        ) from exc


@contextlib.contextmanager
def module_at_revision(generic: pathlib.Path, revision: str):
    """The Terraform module files of one generic commit, materialized read-only in a temporary directory."""
    if not FULL_SHA.fullmatch(revision):
        raise ManifestError("generic_source.revision must be a full lowercase commit SHA")
    with tempfile.TemporaryDirectory(prefix="gcinsight-module-") as name:
        root = pathlib.Path(name)
        # A path-limited listing is empty, not an error, for a revision with no module: it has no defaults.
        for entry in run_git(generic, "ls-tree", "--name-only", revision, "--", "terraform/").splitlines():
            file_name = entry.removeprefix("terraform/")
            if re.fullmatch(r"[A-Za-z0-9_.-]+\.tf", file_name):
                (root / file_name).write_text(run_git(generic, "show", f"{revision}:{entry}") + "\n")
        yield root


def command_upgrade(args: argparse.Namespace) -> int:
    if not FULL_SHA.fullmatch(args.revision):
        raise ManifestError("revision must be a full lowercase commit SHA")
    generic = args.generic_source.resolve()
    run_git(generic, "cat-file", "-e", f"{args.revision}^{{commit}}")
    # Inspect the exact existing commit artifact before even journal recovery can write either file.
    verify_target_projection_schema(generic, args.revision)
    recover_incomplete_upgrade(args.manifest, args.terraform)
    manifest = load_json(args.manifest)
    with contextlib.ExitStack() as stack:
        # A pruned manifest means "the module defaults of ITS revision": validate it against those, and
        # regenerate against the target's, so a default that changed between them changes the digest.
        target_root = stack.enter_context(module_at_revision(generic, args.revision))
        current_root = target_root
        if omits_defaultable_keys(manifest) and isinstance(manifest.get("generic_source"), dict):
            current_root = stack.enter_context(
                module_at_revision(generic, str(manifest["generic_source"].get("revision"))))
        validate(manifest, allow_legacy_scan_policy=True, module_root=current_root)
        if current_root is not target_root:
            changed = default_changes(manifest, current_root, target_root)
            if changed:
                # Names only: a default can be an identity or policy value.
                print("consumer upgrade: the target module changes the default of omitted keys: "
                      + ", ".join(changed))
                if not getattr(args, "accept_default_changes", False):
                    raise ManifestError(
                        "the target revision changes module defaults this pruned manifest relies on; "
                        "review them and rerun with --accept-default-changes, or restore the keys first")
        repository = manifest["generic_source"]["repository"]
        if github_repo(run_git(generic, "remote", "get-url", "origin")) != github_repo(repository):
            raise ManifestError("generic checkout origin differs from the manifest repository")
        verify_remote_commit(generic, repository, args.revision)
        manifest["generic_source"]["revision"] = args.revision
        manifest = regenerate(manifest, module_root=target_root)
    try:
        original_manifest = args.manifest.read_text()
        original_terraform = args.terraform.read_text()
    except OSError as exc:
        raise ManifestError(f"cannot prepare consumer upgrade: {exc}") from exc
    updated_terraform = replaced_terraform_revision(original_terraform, args.revision)
    updated_manifest = json_text(manifest)
    journal = journal_path(args.manifest)
    journal_body = {
        "schema_version": 1,
        "manifest_path": str(args.manifest.resolve()),
        "terraform_path": str(args.terraform.resolve()),
        "original_manifest": original_manifest,
        "original_terraform": original_terraform,
        "target_manifest": updated_manifest,
        "target_terraform": updated_terraform,
    }
    try:
        atomic_write_text(journal, json_text(journal_body), mode=0o600)
        atomic_write_text(args.terraform, updated_terraform)
        atomic_write_text(args.manifest, updated_manifest)
        journal.unlink()
        fsync_directory(journal.parent)
    except OSError as exc:
        restore_errors: list[str] = []
        for path, content in (
            (args.terraform, original_terraform), (args.manifest, original_manifest),
        ):
            try:
                atomic_write_text(path, content)
            except OSError as restore_exc:
                restore_errors.append(f"{path}: {restore_exc}")
        detail = f"; rollback errors: {', '.join(restore_errors)}" if restore_errors else ""
        if not restore_errors:
            try:
                journal.unlink(missing_ok=True)
                fsync_directory(journal.parent)
            except OSError as cleanup_exc:
                detail += f"; journal cleanup error: {cleanup_exc}"
        raise ManifestError(f"consumer upgrade write failed and was rolled back: {exc}{detail}") from exc
    print(f"consumer upgrade: pinned generic source and Terraform module to {args.revision}")
    return 0


def command_env(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    validate(manifest)
    try:
        # The environment the module renders, omitted keys included as their defaults.
        values = effective(manifest)["runtime"][args.kind]
    except KeyError as exc:
        raise ManifestError(f"unknown runtime projection {args.kind!r}") from exc
    for name, value in values.items():
        if "\n" in value or "\x00" in value:
            raise ManifestError(f"runtime value {name} is not shell-environment safe")
        print(f"{name}={value}")
    print("GCINSIGHT_REQUIRE_EXPLICIT_CONFIG=1")
    print(f"GCINSIGHT_RUNTIME_CONFIG_DIGEST={manifest['runtime_projection_digests'][args.kind]}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate a committed consumer and source checkout")
    check.add_argument("--manifest", required=True, type=pathlib.Path)
    check.add_argument("--generic-source", type=pathlib.Path, default=ROOT)
    check.add_argument("--deployment-root", type=pathlib.Path)
    check.add_argument("--terraform", type=pathlib.Path)
    check.add_argument(
        "--require-committed-deployment", action="store_true",
        help="also require the manifest and Terraform wiring to be clean at deployment HEAD",
    )
    check.add_argument(
        "--forbidden-core-path", action="append", default=[],
        help="deployment-relative retired product path that must remain absent; repeat as needed",
    )
    check.set_defaults(handler=command_check)

    render = commands.add_parser("regenerate", help="recalculate deterministic manifest digests")
    render.add_argument("--manifest", required=True, type=pathlib.Path)
    render.add_argument(
        "--prune-defaults", action="store_true",
        help="also remove every key whose value equals this checkout's module default; digests are "
             "unchanged because they cover the effective manifest",
    )
    render.set_defaults(handler=command_regenerate)

    upgrade = commands.add_parser("upgrade", help="update an exact source pin and Terraform module ref")
    upgrade.add_argument("revision")
    upgrade.add_argument("--manifest", required=True, type=pathlib.Path)
    upgrade.add_argument("--terraform", required=True, type=pathlib.Path)
    upgrade.add_argument("--generic-source", type=pathlib.Path, default=ROOT)
    upgrade.add_argument(
        "--accept-default-changes", action="store_true",
        help="proceed when the target module changes the default of a key this manifest omits",
    )
    upgrade.set_defaults(handler=command_upgrade)

    environment = commands.add_parser("env", help="print one validated runtime environment projection")
    environment.add_argument("kind", choices=tuple(identity.PROJECTION_ENVS))
    environment.add_argument("--manifest", required=True, type=pathlib.Path)
    environment.set_defaults(handler=command_env)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.handler(args)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
