"""Default-off, unwired Loki volume input for a private S3 view only.

D-VOL20 permits service names in that view, not diagnostics, events or labels.
The single witnessed route measures the returned producers, not a separate total.
Query-work stats are deliberately ignored. Remainder and total stay unknown even
below the limit: the values-free witness supplies no completeness/total marker.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any
from urllib.parse import urlsplit

from collector.httpclient import DeadlineExceeded, ReadOnlyClient

PATH = "/loki/api/v1/index/volume"
WINDOW_SECONDS = 86400
LIMIT = 100
REASONS = frozenset({"none", "disabled", "missing_endpoint", "no_credential",
                     "http_error", "invalid_response", "deadline", "transport_error"})
_INTEGER = re.compile(r"[0-9]+", re.ASCII)


def _unavailable(reason: str) -> dict[str, Any]:
    return {"state": "unavailable", "reason": reason, "window_seconds": WINDOW_SECONDS,
            "rows": [], "other_bytes": None, "total_bytes": None, "truncated": False}


def _rows(body: Any) -> list[dict[str, Any]]:
    if (not isinstance(body, dict) or body.get("status") != "success"
            or body.get("warnings") or body.get("errors")):
        raise ValueError("invalid_response")
    data = body.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        raise ValueError("invalid_response")
    result = data.get("result")
    if not isinstance(result, list) or len(result) > LIMIT:
        raise ValueError("invalid_response")
    rows = []
    seen = set()
    for item in result:
        if not isinstance(item, dict):
            raise ValueError("invalid_response")
        metric, value = item.get("metric"), item.get("value")
        if not isinstance(metric, dict) or set(metric) != {"service_name"}:
            raise ValueError("invalid_response")
        name = metric["service_name"]
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("invalid_response")
        name.encode("utf-8")
        if (not isinstance(value, list) or len(value) != 2
                or type(value[0]) not in (int, float) or not math.isfinite(value[0])
                or not isinstance(value[1], str) or not _INTEGER.fullmatch(value[1])):
            raise ValueError("invalid_response")
        rows.append({"service_name": name, "bytes": int(value[1])})
        seen.add(name)
    return sorted(rows, key=lambda row: (-row["bytes"], row["service_name"]))


def _probe(client: ReadOnlyClient, stack: dict[str, Any], cap: str) -> dict[str, Any]:
    if not cap:
        return _unavailable("no_credential")
    try:
        base = stack.get("hlInstanceUrl")
        parts = urlsplit(base if isinstance(base, str) else "")
        tenant = stack.get("hlInstanceId")
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment
                or not tenant or isinstance(tenant, bool)):
            return _unavailable("missing_endpoint")
    except ValueError:
        return _unavailable("missing_endpoint")
    end = time.time_ns()
    try:
        response = client.get(base.rstrip("/") + PATH, basic=(str(tenant), cap), guarded=True,
                              params={"query": '{service_name=~".+"}',
                                      "targetLabels": "service_name", "limit": LIMIT,
                                      "start": end - WINDOW_SECONDS * 1_000_000_000, "end": end})
        if response.status != 200:
            return _unavailable("http_error")
        try:
            rows = _rows(response.json())
        except (ValueError, TypeError, OverflowError):
            return _unavailable("invalid_response")
        return {"state": "complete", "reason": "none", "window_seconds": WINDOW_SECONDS,
                "rows": rows, "other_bytes": None, "total_bytes": None,
                "truncated": len(rows) == LIMIT}
    except (DeadlineExceeded, TimeoutError):
        return _unavailable("deadline")
    except Exception:  # noqa: BLE001 - never expose response content or exception text
        return _unavailable("transport_error")


def probe_all(client: ReadOnlyClient, stacks: list[dict[str, Any]], cap: str, *,
              enabled: bool = False) -> dict:
    """Left-join fresh inventory only. Disabled means zero HTTP calls.

    Complete describes a valid bounded response, not a whole-tenant inventory.
    Callers must fence this private input before any diagnostic/publication wiring.
    """
    return {"stacks": {str(stack["slug"]): _probe(client, stack, cap) if enabled
                       else _unavailable("disabled") for stack in stacks if stack.get("slug")}}


def composition_inputs(inputs: dict) -> dict:
    """Mirror label_inventory's private composition seam; no diagnostic serialization."""
    return dict(inputs)
