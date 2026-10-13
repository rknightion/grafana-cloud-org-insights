"""Shared verified ECS runtime publication boundary."""
import json
import os
import urllib.parse
import urllib.request


def verified_ecs_runtime() -> bool:
    """Prove this process can read its link-local ECS container metadata.

    An environment variable name alone is trivial to copy into a local shell and therefore cannot be
    the boundary protecting customer-facing publication. Fargate injects a link-local URI whose JSON
    names the running ECS container; require both the authoritative host and that live response.
    """
    uri = (os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
           or os.environ.get("ECS_CONTAINER_METADATA_URI") or "")
    try:
        parsed = urllib.parse.urlsplit(uri)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"169.254.170.2", "fd00:ec2::23"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or not parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return False
        with urllib.request.urlopen(uri, timeout=1.0) as response:  # noqa: S310 - fixed link-local host
            payload = json.load(response)
    except Exception:  # noqa: BLE001 - any metadata ambiguity must fail closed
        return False
    if not isinstance(payload, dict):
        return False
    arn = payload.get("ContainerARN")
    parts = arn.split(":", 5) if isinstance(arn, str) else []
    return len(parts) == 6 and parts[0] == "arn" and parts[2] == "ecs" \
        and parts[5].startswith("container/")

