#!/usr/bin/env python3
"""Validate and upgrade an immutable Grafana Cloud Org Insights consumer manifest."""

from __future__ import annotations

import argparse
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
    schema = load_json(SCHEMA_PATH)
    return set(schema["properties"][section]["required"])


def overlay(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: manifest[key] for key in OVERLAY_KEYS}


def calculated_digests(manifest: dict[str, Any]) -> tuple[str, dict[str, str]]:
    # The SAME function the task runs at startup. A second implementation here is how the manifest and
    # the rendered environment came to disagree about a policy they both held (GCI-0045).
    projections = {
        kind: identity.projection_digest(kind, manifest["runtime"][kind])
        for kind in sorted(identity.PROJECTION_ENVS)
    }
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


def validate(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or set(manifest) != TOP_LEVEL_KEYS:
        raise ManifestError(f"manifest top-level keys differ: expected {sorted(TOP_LEVEL_KEYS)}")
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
    for kind, expected_names in identity.PROJECTION_ENVS.items():
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

    validate_json_runtime_types(runtime)

    # Values Terraform cannot round-trip. The consumer wiring renders the flag as `== "1"`, so "true"
    # (which the collector accepts) renders "0"; and both tasks render OPT_OUT from ONE module input,
    # so two different lists make one task refuse to start on a digest mismatch (GCI-0045 review).
    if runtime["scan"]["GCINSIGHT_DASHBOARD_DETAIL_ENABLED"] not in {"1", "0"}:
        raise ManifestError("runtime.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED must be 1 or 0")
    if runtime["scan"]["GCINSIGHT_OPT_OUT"] != runtime["provisioner"]["GCINSIGHT_OPT_OUT"]:
        raise ManifestError("runtime.scan and runtime.provisioner GCINSIGHT_OPT_OUT must be identical")

    for section in ("aws", "policy"):
        values = manifest.get(section)
        required = _required_keys(section)
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
        "schedules_enabled", "provisioner_enabled",
    }
    if any(not isinstance(aws[name], bool) for name in boolean_fields):
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

    expected_overlay, expected_projections = calculated_digests(manifest)
    if not DIGEST.fullmatch(str(manifest["overlay_digest"])) or manifest["overlay_digest"] != expected_overlay:
        raise ManifestError("overlay_digest does not match canonical overlay content")
    recorded = manifest.get("runtime_projection_digests")
    if not isinstance(recorded, dict) or set(recorded) != set(expected_projections):
        raise ManifestError("runtime_projection_digests keys differ from runtime projections")
    if recorded != expected_projections:
        raise ManifestError("runtime projection digest drift")


def regenerate(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("runtime"), dict):
        raise ManifestError("manifest must contain a runtime projection object")
    updated = dict(manifest)
    # Validate before digest calculation too: an overflowing JSON number must be a contract error,
    # not an exception in identity's canonicalisation. Leave malformed projection shapes to validate.
    scan = updated["runtime"].get("scan")
    if isinstance(scan, dict) and all(isinstance(scan.get(env), str) for env in (
        "GCINSIGHT_EXPECTED_RETENTION_POLICY", "GCINSIGHT_COVERAGE_SCORE_WEIGHTS"
    )):
        validate_json_runtime_types(updated["runtime"])
    try:
        updated["overlay_digest"], updated["runtime_projection_digests"] = calculated_digests(updated)
    except KeyError as exc:
        raise ManifestError(f"manifest is missing required content: {exc}") from exc
    validate(updated)
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
    """{kind: {env: (module variable, render expression)}} for env values taken from one variable."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for kind, name in _MODULE_ENV_FILES.items():
        text = (module_root / name).read_text()
        entries: dict[str, tuple[str, str]] = {}
        for env, expr in _MODULE_ENV.findall(text):
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
    validate(manifest)
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
        gaps = terraform_wiring_gaps(
            manifest, args.terraform.resolve().read_text(),
            args.generic_source.resolve() / "terraform",
        )
        if gaps:
            raise ManifestError("Terraform wiring differs from the manifest:\n  " + "\n  ".join(gaps))
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
    manifest = regenerate(load_json(args.manifest))
    write_json(args.manifest, manifest)
    print(f"consumer manifest: regenerated overlay={manifest['overlay_digest']}")
    return 0


def command_upgrade(args: argparse.Namespace) -> int:
    if not FULL_SHA.fullmatch(args.revision):
        raise ManifestError("revision must be a full lowercase commit SHA")
    recover_incomplete_upgrade(args.manifest, args.terraform)
    generic = args.generic_source.resolve()
    run_git(generic, "cat-file", "-e", f"{args.revision}^{{commit}}")
    manifest = load_json(args.manifest)
    validate(manifest)
    repository = manifest["generic_source"]["repository"]
    if github_repo(run_git(generic, "remote", "get-url", "origin")) != github_repo(repository):
        raise ManifestError("generic checkout origin differs from the manifest repository")
    verify_remote_commit(generic, repository, args.revision)
    manifest["generic_source"]["revision"] = args.revision
    manifest = regenerate(manifest)
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
        values = manifest["runtime"][args.kind]
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
    render.set_defaults(handler=command_regenerate)

    upgrade = commands.add_parser("upgrade", help="update an exact source pin and Terraform module ref")
    upgrade.add_argument("revision")
    upgrade.add_argument("--manifest", required=True, type=pathlib.Path)
    upgrade.add_argument("--terraform", required=True, type=pathlib.Path)
    upgrade.add_argument("--generic-source", type=pathlib.Path, default=ROOT)
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
