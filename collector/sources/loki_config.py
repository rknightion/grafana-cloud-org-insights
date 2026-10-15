"""Read effective Loki retention and the stack-local retention request queue.

The effective limits endpoint is a Loki dataplane read, so it uses the organisation CAP with the
stack's Loki tenant id as HTTP basic-auth user.  Retention requests live behind the Grafana plugin
resource endpoint and use the existing per-stack reader.  They are deliberately independent reads:
one unavailable route must not turn a readable route into an invented zero.
"""

from __future__ import annotations

import ast
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient
from collector.sources.loki_read import LOKI_READ_HEADERS

LIMITS_PATH = "config/tenant/v1/limits"
RETENTION_REQUESTS_PATH = "api/plugins/grafana-dbcfg-app/resources/v1/lokiconfigretentions"
SETTINGS_PATH = "api/plugins/grafana-dbcfg-app/resources/v1/settings"

OK = "ok"
NO_CREDENTIAL = "no_credential"
NO_LOKI_INSTANCE = "no_loki_instance"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
NOT_FOUND = "endpoint_absent_404"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
INVALID_RESPONSE = "invalid_response"

_YAML_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_YAML_INTEGER = re.compile(r"^-?[0-9]+$")
# Same source response ceiling as label_inventory; no dependency or general YAML loader.
MAX_LIMITS_BYTES = 2 * 1024 * 1024
MAX_CONFIG_LINES = 4096
MAX_CONFIG_ITEMS = 256
LABELLING_FIELDS = frozenset({"otlp_config", "discover_service_name", "discover_log_levels"})


def _balanced_yaml_line(line: str) -> bool:
    quote = ""
    escaped = False
    square = curly = 0
    for char in line:
        if escaped:
            escaped = False
            continue
        if quote:
            if char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
        elif char == "[":
            square += 1
        elif char == "]":
            square -= 1
        elif char == "{":
            curly += 1
        elif char == "}":
            curly -= 1
        if square < 0 or curly < 0:
            return False
    return not quote and square == 0 and curly == 0


def _yaml_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        raise ValueError("empty scalar")
    if value[0] in "'\"":
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, str):
            raise ValueError("quoted scalar is not a string")
        return parsed
    if _YAML_INTEGER.fullmatch(value):
        return int(value)
    return value


def _yaml_limits(body: bytes, *, labelling: bool = False) -> dict[str, Any]:
    """Validate the envelope, then parse only the caller's independent field domain."""
    if len(body) > MAX_LIMITS_BYTES:
        raise ValueError("limits byte cap")
    text = body.decode("utf-8")
    if text.lstrip().startswith(("{", "[")):
        raise ValueError("malformed JSON is not YAML")
    lines = text.splitlines()
    if len(lines) > MAX_CONFIG_LINES:
        raise ValueError("limits line cap")
    top_level = [line for line in lines if line and not line[0].isspace()
                 and not line.startswith(("#", "- "))]
    if (
        not top_level
        or "\t" in text
        or any(":" not in line for line in top_level)
        or any(not _YAML_KEY.fullmatch(line.partition(":")[0]) for line in top_level)
        or any(not _balanced_yaml_line(line) for line in lines)
    ):
        raise ValueError("response is not a YAML mapping")
    if labelling:
        return _labelling_yaml(lines)

    start: int | None = None
    inline = ""
    for index, line in enumerate(lines):
        if line.startswith("retention_stream:"):
            start = index + 1
            inline = line.partition(":")[2].strip()
            break
    if start is None:
        return {}
    if inline == "[]":
        return {"retention_stream": []}
    if inline:
        raise ValueError("retention_stream is not a block list")

    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            # Indentless lists are approved only for the separate labelling domain.
            # Never turn an unparsed nonempty retention list into measured absence.
            if line.startswith("- "):
                raise ValueError("unsupported indentless retention_stream")
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            stripped = stripped[2:].strip()
        if current is None or ":" not in stripped:
            raise ValueError("retention_stream contains a non-mapping item")
        key, _, raw = stripped.partition(":")
        key = key.strip()
        if not _YAML_KEY.fullmatch(key):
            raise ValueError("retention_stream contains an invalid key")
        current[key] = _yaml_scalar(raw)
    if current is not None:
        items.append(current)
    return {"retention_stream": items}


def _config_scalar(raw: str) -> Any:
    """A closed scalar grammar, not YAML constructors, aliases, tags or flow collections."""
    value = raw.strip()
    if value in {"{}", "[]"}:
        return {} if value == "{}" else []
    if value in {"true", "false"}:
        return value == "true"
    if (not value or len(value.encode("utf-8")) > 4096
            or (value[0] not in "'\"" and
                (value[0] in "&*!>|%[{" or any(c in value for c in ":#{}[]")))):
        raise ValueError("unsupported config scalar")
    if value.startswith('"'):
        parsed = json.loads(value)
        if not isinstance(parsed, str):
            raise ValueError("invalid quoted config scalar")
        return parsed
    if value.startswith("'"):
        if not value.endswith("'") or "'" in value[1:-1].replace("''", ""):
            raise ValueError("invalid quoted config scalar")
        return value[1:-1].replace("''", "'")
    return _yaml_scalar(value)


def _config_block(tokens: list[tuple[int, str]], depth: int = 0) -> Any:
    """Only block maps/lists, including Go YAML's indentless sequences.

    Recursion, lines and collection sizes are bounded. Unknown OTLP structures
    are rejected later, never executed or interpreted as effective defaults.
    """
    if not tokens or depth > 6:
        raise ValueError("invalid config block")
    indent = tokens[0][0]
    if tokens[0][1].startswith("- "):
        chunks: list[list[tuple[int, str]]] = []
        for level, text in tokens:
            if level < indent:
                raise ValueError("invalid list indentation")
            if level == indent:
                if not text.startswith("- "):
                    raise ValueError("invalid list item")
                chunks.append([(level + 2, text[2:].strip())])
            else:
                if not chunks:
                    raise ValueError("invalid list continuation")
                chunks[-1].append((level, text))
        if len(chunks) > MAX_CONFIG_ITEMS:
            raise ValueError("config item cap")
        result = []
        for chunk in chunks:
            if ":" in chunk[0][1] and not chunk[0][1].startswith(("'", '"')):
                result.append(_config_block(chunk, depth + 1))
            elif len(chunk) == 1:
                result.append(_config_scalar(chunk[0][1]))
            else:
                raise ValueError("invalid scalar continuation")
        return result
    result = {}
    index = 0
    while index < len(tokens):
        level, text = tokens[index]
        if level != indent or ":" not in text:
            raise ValueError("invalid mapping indentation")
        key, _, raw = text.partition(":")
        if not _YAML_KEY.fullmatch(key) or key in result:
            raise ValueError("invalid or duplicate config key")
        end = index + 1
        while end < len(tokens) and (tokens[end][0] > indent or
              (tokens[end][0] == indent and tokens[end][1].startswith("- "))):
            end += 1
        if raw.strip():
            if end != index + 1:
                raise ValueError("invalid scalar continuation")
            value = _config_scalar(raw)
        else:
            value = _config_block(tokens[index + 1:end], depth + 1)
        result[key] = value
        if len(result) > MAX_CONFIG_ITEMS:
            raise ValueError("config item cap")
        index = end
    return result


def _labelling_yaml(lines: list[str]) -> dict[str, Any]:
    selected = {}
    seen = set()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line[0].isspace() or line.startswith(("#", "- ")):
            index += 1
            continue
        key = line.partition(":")[0]
        if key in seen:
            raise ValueError("duplicate limits key")
        seen.add(key)
        end = index + 1
        while end < len(lines) and (not lines[end] or lines[end][0].isspace()
              or lines[end].startswith(("#", "- "))):
            end += 1
        if key in LABELLING_FIELDS:
            tokens = [(len(s) - len(s.lstrip(" ")), s.strip()) for s in lines[index:end]
                      if s.strip() and not s.lstrip().startswith("#")]
            selected.update(_config_block(tokens))
        index = end
    return selected


def labelling_limits(response: Any) -> dict[str, Any]:
    """Transient three-field projection. Callers must reduce names before persistence.

    Missing fields stay absent. No volume/structured-metadata/default inference.
    JSON and the witnessed block YAML undergo the same closed shape checks.
    """
    if len(response.body) > MAX_LIMITS_BYTES:
        raise ValueError("limits byte cap")
    def unique_mapping(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate limits key")
            result[key] = value
        return result
    try:
        body = json.loads(response.body, object_pairs_hook=unique_mapping)
    except json.JSONDecodeError:
        body = _yaml_limits(response.body, labelling=True)
    if not isinstance(body, dict):
        raise ValueError("limits is not a mapping")
    selected = {key: body[key] for key in LABELLING_FIELDS if key in body}
    def names(value):
        if (not isinstance(value, list) or len(value) > MAX_CONFIG_ITEMS or
                any(not isinstance(v, str) or not v or len(v.encode("utf-8")) > 4096 for v in value)):
            raise ValueError("invalid config names")
    if "discover_service_name" in selected:
        names(selected["discover_service_name"])
    if "discover_log_levels" in selected and type(selected["discover_log_levels"]) is not bool:
        raise ValueError("invalid discovery flag")
    if "otlp_config" in selected:
        otlp = selected["otlp_config"]
        if not isinstance(otlp, dict) or set(otlp) - {"resource_attributes"}:
            raise ValueError("unsupported OTLP structure")
        resource = otlp.get("resource_attributes", {})
        if not isinstance(resource, dict) or set(resource) - {"ignore_defaults", "attributes_config"}:
            raise ValueError("unsupported resource structure")
        if "ignore_defaults" in resource and type(resource["ignore_defaults"]) is not bool:
            raise ValueError("invalid defaults flag")
        configs = resource.get("attributes_config", [])
        if not isinstance(configs, list) or len(configs) > MAX_CONFIG_ITEMS:
            raise ValueError("invalid attribute configs")
        for config in configs:
            if (not isinstance(config, dict) or set(config) - {"action", "attributes", "regex"}
                    or not isinstance(config.get("action"), str)
                    or config["action"] not in {"index_label", "structured_metadata", "drop"}
                    or not ({"attributes", "regex"} & set(config))):
                raise ValueError("invalid attribute config")
            if "attributes" in config:
                names(config["attributes"])
            if "regex" in config and (not isinstance(config["regex"], str) or not config["regex"]
                    or len(config["regex"].encode("utf-8")) > 4096):
                raise ValueError("invalid attribute regex")
    return selected


def _limits_body(response: Any) -> Mapping[str, Any]:
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = _yaml_limits(response.body)
    if not isinstance(body, Mapping):
        raise ValueError(f"expected object, got {type(body).__name__}")
    return body


def unavailable(slug: str, state: str, detail: str = "") -> dict[str, Any]:
    """A domain-specific unavailable record, safe to join by inventory slug."""
    return {"available": False, "slug": slug, "state": state, "detail": detail[:240]}


def _state_for(status: int) -> str:
    return {401: UNAUTHORISED, 403: FORBIDDEN, 404: NOT_FOUND}.get(status, HTTP_ERROR)


def _limits_record(client: ReadOnlyClient, stack: Mapping[str, Any], cap: str) -> dict[str, Any]:
    slug = str(stack.get("slug") or "")
    base = stack.get("hlInstanceUrl")
    tenant = stack.get("hlInstanceId")
    if not isinstance(base, str) or not base.strip() or tenant is None or tenant == "":
        return unavailable(slug, NO_LOKI_INSTANCE, "inventory has no usable Loki endpoint or tenant id")
    if not cap:
        return unavailable(slug, NO_CREDENTIAL, "no organisation CAP")
    try:
        response = client.get(f"{base.rstrip('/')}/{LIMITS_PATH}", basic=(str(tenant), cap),
                              headers=LOKI_READ_HEADERS)
    except Exception as exc:  # noqa: BLE001 - one stack must not fail the estate sweep
        return unavailable(slug, TRANSPORT_ERROR, type(exc).__name__)
    if not response.ok:
        return unavailable(slug, _state_for(response.status), f"HTTP {response.status}")
    try:
        body = _limits_body(response)
    except (UnicodeDecodeError, ValueError, SyntaxError) as exc:
        return unavailable(slug, INVALID_RESPONSE, f"invalid limits body ({type(exc).__name__})")
    streams = body.get("retention_stream")
    if streams is not None and (
        not isinstance(streams, list) or not all(isinstance(item, Mapping) for item in streams)
    ):
        return unavailable(slug, INVALID_RESPONSE, "retention_stream is not a list of objects")
    record: dict[str, Any] = {"available": True, "slug": slug, "state": OK}
    # The key being absent is distinct from a successful empty stream list.  It means this API version
    # did not disclose the state needed for a policy comparison, so the pillar must withhold that check.
    if streams is not None:
        record["retention_stream"] = [dict(item) for item in streams]
    return record


def _request_item(item: Mapping[str, Any]) -> dict[str, Any]:
    spec = item.get("spec")
    status = item.get("status")
    spec = spec if isinstance(spec, Mapping) else {}
    status = status if isinstance(status, Mapping) else {}
    pr_info = status.get("pr_info")
    pr_info = pr_info if isinstance(pr_info, Mapping) else {}
    shared = {"author", "message", "request_timestamp"}
    # An unknown spec field is part of the API's user request and must survive untouched.  `limit` is
    # also surfaced in its own display column, but remains in opaque so no extension is discarded.
    opaque = {key: value for key, value in spec.items() if key not in shared}
    return {
        "author": spec.get("author"),
        "message": spec.get("message"),
        "request_timestamp": spec.get("request_timestamp"),
        "limit": opaque.get("limit"),
        "opaque": opaque,
        "status": status.get("status"),
        "processed_timestamp": status.get("processed_timestamp"),
        "pr_number": pr_info.get("number"),
    }


def _requests_record(client: ReadOnlyClient, stack: Mapping[str, Any], token: str) -> dict[str, Any]:
    slug = str(stack.get("slug") or "")
    base = stack.get("url")
    if not isinstance(base, str) or not base.strip():
        return unavailable(slug, INVALID_RESPONSE, "inventory has no usable stack URL")
    if not token:
        return unavailable(slug, NO_CREDENTIAL, "no stored per-stack reader token")
    try:
        response = client.get(f"{base.rstrip('/')}/{RETENTION_REQUESTS_PATH}", bearer=token)
    except Exception as exc:  # noqa: BLE001 - one stack must not fail the estate sweep
        return unavailable(slug, TRANSPORT_ERROR, type(exc).__name__)
    if not response.ok:
        return unavailable(slug, _state_for(response.status), f"HTTP {response.status}")
    try:
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - malformed JSON is an explicit state
        return unavailable(slug, INVALID_RESPONSE, f"invalid JSON ({type(exc).__name__})")
    items = body.get("items") if isinstance(body, Mapping) else None
    if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
        return unavailable(slug, INVALID_RESPONSE, "expected items list of objects")
    return {"available": True, "slug": slug, "state": OK,
            "items": [_request_item(item) for item in items]}


def probe_stack(
    client: ReadOnlyClient,
    stack: Mapping[str, Any],
    cap: str,
    token: str,
) -> dict[str, Any]:
    """Read one stack's effective Loki limits and independent request queue using only GET."""
    return {
        "slug": str(stack.get("slug") or ""),
        "limits": _limits_record(client, stack, cap),
        "change_requests": _requests_record(client, stack, token),
    }


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    cap: str,
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    concurrency: int = 12,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Probe the live inventory only; credential-only departed stacks never enter the output."""
    results: dict[str, Any] = {}

    def one(stack: Mapping[str, Any]) -> None:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            return
        token = str((credentials.get(slug) or {}).get("token") or "")
        try:
            results[slug] = probe_stack(client, stack, cap, token)
        except Exception as exc:  # noqa: BLE001 - defensive boundary around an individual stack
            results[slug] = {
                "slug": slug,
                "limits": unavailable(slug, TRANSPORT_ERROR, type(exc).__name__),
                "change_requests": unavailable(slug, TRANSPORT_ERROR, type(exc).__name__),
            }
            if on_error:
                on_error(slug, f"loki_config: {type(exc).__name__}")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(one, stacks))
    return results
