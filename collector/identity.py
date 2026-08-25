"""Validated consumer identity and runtime-projection helpers.

Core code uses the canonical ``gcinsight`` identity. A customer consumer may select a stable external
identity at the output/generation seams without forking the collector. Secrets are deliberately absent
from every projection: the digest proves non-secret configuration, while ECS secret selectors are
validated separately by Terraform.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Iterable, Mapping

CANONICAL_METRIC_PREFIX = "gcinsight"
_SAFE_ID = re.compile(r"^[a-z][a-z0-9_.-]*$")

SCAN_ENV = (
    "GCINSIGHT_ORG_ID", "GCINSIGHT_WRITE_STACK", "GCINSIGHT_MIMIR_URL",
    "GCINSIGHT_MIMIR_TENANT", "GCINSIGHT_LOKI_URL", "GCINSIGHT_LOKI_TENANT",
    "GCINSIGHT_S3_BUCKET", "GCINSIGHT_S3_REGION", "GCINSIGHT_SSM_REGION",
    "GCINSIGHT_STACK_TOKEN_PREFIX", "GCINSIGHT_METRIC_PREFIX", "GCINSIGHT_LOKI_JOB",
    "GCINSIGHT_USER_AGENT", "GCINSIGHT_OPT_OUT", "GCINSIGHT_COVERAGE_SCORE_WEIGHTS",
)
PROVISIONER_ENV = (
    "GCINSIGHT_ORG_ID", "GCINSIGHT_SSM_REGION", "GCINSIGHT_STACK_TOKEN_PREFIX",
    "GCINSIGHT_ROLE_NAME", "GCINSIGHT_ROLE_DISPLAY", "GCINSIGHT_ROLE_GROUP",
    "GCINSIGHT_READER_SA_NAME", "GCINSIGHT_ADMIN_SA_NAME",
    "GCINSIGHT_TOKEN_NAME_PREFIX", "GCINSIGHT_OPT_OUT",
)
DASHBOARD_ENV = (
    "GCINSIGHT_WRITE_STACK_ID", "GCINSIGHT_WRITE_STACK_URL", "GCINSIGHT_S3_BUCKET",
    "GCINSIGHT_S3_REGION", "GCINSIGHT_METRIC_PREFIX", "GCINSIGHT_DASHBOARD_UID_PREFIX",
    "GCINSIGHT_DASHBOARD_TITLE_PREFIX", "GCINSIGHT_DASHBOARD_DS_NAME",
    "GCINSIGHT_DASHBOARD_FOLDER_TITLE", "GCINSIGHT_DASHBOARD_TAG",
    "GCINSIGHT_INSIGHTS_FOLDER_UID",
)
ALERT_ENV = (
    "GCINSIGHT_WRITE_STACK_URL", "GCINSIGHT_INSIGHTS_FOLDER_UID", "GCINSIGHT_PROM_DS_UID",
    "GCINSIGHT_METRIC_PREFIX", "GCINSIGHT_ALERT_RULE_GROUP", "GCINSIGHT_ALERT_RULE_UIDS_JSON",
    "GCINSIGHT_ALERT_TITLE_PREFIX", "GCINSIGHT_ALERT_TITLE_SEPARATOR",
    "GCINSIGHT_ALERT_SERVICE_LABEL",
)
PROJECTION_ENVS = {
    "scan": SCAN_ENV,
    "provisioner": PROVISIONER_ENV,
    "dashboards": DASHBOARD_ENV,
    "alerts": ALERT_ENV,
}
OPTIONAL_EMPTY_ENV = frozenset({"GCINSIGHT_OPT_OUT"})


class InvalidIdentity(ValueError):
    """A consumer identity or runtime projection is incomplete or contradictory."""


def env(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise InvalidIdentity(f"{name} must not be empty")
    return value


def metric_prefix() -> str:
    value = env("GCINSIGHT_METRIC_PREFIX", CANONICAL_METRIC_PREFIX)
    if not _SAFE_ID.fullmatch(value):
        raise InvalidIdentity(f"GCINSIGHT_METRIC_PREFIX is not a safe metric prefix: {value!r}")
    return value.rstrip("_")


def external_metric_name(name: str) -> str:
    canonical = f"{CANONICAL_METRIC_PREFIX}_"
    if not name.startswith(canonical):
        if metric_prefix() == CANONICAL_METRIC_PREFIX:
            return name
        raise InvalidIdentity(f"metric {name!r} is outside the canonical {canonical!r} namespace")
    return f"{metric_prefix()}_{name[len(canonical):]}"


def canonical_metric_name(name: str) -> str:
    external = f"{metric_prefix()}_"
    if name.startswith(external):
        return f"{CANONICAL_METRIC_PREFIX}_{name[len(external):]}"
    return name


def replace_metric_text(value: str) -> str:
    return value.replace(f"{CANONICAL_METRIC_PREFIX}_", f"{metric_prefix()}_")


def map_tree(value: Any) -> Any:
    """Apply metric identity to every string in a generated dashboard/alert document."""
    if isinstance(value, str):
        return replace_metric_text(value)
    if isinstance(value, list):
        return [map_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(map_tree(item) for item in value)
    if isinstance(value, dict):
        return {key: map_tree(item) for key, item in value.items()}
    return value


def canonical_projection(kind: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    try:
        names = PROJECTION_ENVS[kind]
    except KeyError as exc:
        raise InvalidIdentity(f"unknown runtime projection {kind!r}") from exc
    source = os.environ if environ is None else environ
    return {name: str(source.get(name, "")).strip() for name in names}


def projection_digest(kind: str, environ: Mapping[str, str] | None = None) -> str:
    payload = json.dumps(canonical_projection(kind, environ), sort_keys=True,
                         separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def verify_runtime_projection(kind: str, *, environ: Mapping[str, str] | None = None) -> str | None:
    """Verify a customer task's non-secret config, or allow generic defaults when no digest is set."""
    source = os.environ if environ is None else environ
    expected = str(source.get("GCINSIGHT_RUNTIME_CONFIG_DIGEST", "")).strip()
    required = str(source.get("GCINSIGHT_REQUIRE_EXPLICIT_CONFIG", "")).strip() == "1"
    if not expected:
        if required:
            raise InvalidIdentity("GCINSIGHT_RUNTIME_CONFIG_DIGEST is required for this consumer")
        return None
    actual = projection_digest(kind, source)
    if actual != expected:
        raise InvalidIdentity(
            f"{kind} runtime projection digest mismatch: expected {expected}, resolved {actual}"
        )
    missing = [
        name for name, value in canonical_projection(kind, source).items()
        if not value and name not in OPTIONAL_EMPTY_ENV
    ]
    if required and missing:
        raise InvalidIdentity(f"{kind} runtime projection has empty required fields: {', '.join(missing)}")
    return actual


def json_mapping(name: str, default: Mapping[str, str]) -> dict[str, str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return dict(default)
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidIdentity(f"{name} is not valid JSON: {exc}") from exc
    if not isinstance(body, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                             for k, v in body.items()):
        raise InvalidIdentity(f"{name} must be a JSON object of string values")
    if set(body) != set(default):
        raise InvalidIdentity(
            f"{name} keys differ: missing={sorted(set(default) - set(body))}, "
            f"extra={sorted(set(body) - set(default))}"
        )
    return dict(body)


def externalize_metrics(
    metrics: Iterable[tuple[str, Mapping[str, str], float]],
) -> list[tuple[str, Mapping[str, str], float]]:
    return [(external_metric_name(name), labels, value) for name, labels, value in metrics]
