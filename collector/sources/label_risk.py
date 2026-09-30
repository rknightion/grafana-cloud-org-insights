"""Bounded daily four-signal label risk reads, not an exhaustive privacy audit.

The normal HTTP client stays GET-only. Only the two fixed native Pyroscope label reads use POST.
Responses and ordinary values are transient. Persist only bounded classified matches and numeric
coverage, with safe enum errors. No error body, URL, decoded claim or unmatched value is returned.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from collector import pii
from collector.httpclient import DeadlineExceeded, ReadOnlyClient, Response, _basic_auth
from collector.netbound import bounded_call

PROFILE_PATHS = frozenset({
    "/querier.v1.QuerierService/LabelNames", "/querier.v1.QuerierService/LabelValues",
})
SIGNALS = {
    "metrics": ("hmInstancePromUrl", "hmInstancePromId", "/api/prom/api/v1"),
    "logs": ("hlInstanceUrl", "hlInstanceId", "/loki/api/v1"),
    "traces": ("htInstanceUrl", "htInstanceId", "/tempo/api/v2/search"),
    "profiles": ("hpInstanceUrl", "hpInstanceId", ""),
}


@dataclass(frozen=True)
class Bounds:
    keys: int = 64
    values: int = 256
    matches: int = 64
    response_bytes: int = 2 * 1024 * 1024
    # Additional aggregate retained-match bound: whole values are omitted, never shortened.
    retained_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if any(v < 1 for v in (self.keys, self.values, self.matches, self.response_bytes,
                               self.retained_bytes)):
            raise ValueError("label bounds must be positive")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def bounded_transport(cap: int) -> Callable[[urllib.request.Request, float], Response]:
    opener = urllib.request.build_opener(_NoRedirect())

    def send(req: urllib.request.Request, timeout: float) -> Response:
        stop = time.monotonic() + timeout
        try:
            fh = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            # Never read an error body: it may echo raw values or credentials.
            exc.close()
            return Response(exc.code, b"", "", {})
        with fh:
            body = bytearray()
            while len(body) <= cap:
                if time.monotonic() >= stop:
                    raise TimeoutError("deadline")
                chunk = fh.read1(min(65536, cap + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            if len(body) > cap:
                raise ValueError("response_byte_cap")
            return Response(fh.status, bytes(body), "", dict(fh.headers))
    return send


def profile_read(
    stack: Mapping[str, Any], cap: str, path: str, body: Mapping[str, Any], *,
    method: str = "POST", timeout: float = 10.0,
    transport: Callable[[urllib.request.Request, float], Response],
) -> Response:
    """Exact inventory-host two-path native JSON exception; no generic RPC helper."""
    if method != "POST" or path not in PROFILE_PATHS:
        raise ValueError("unlisted_label_read")
    base = stack.get("hpInstanceUrl")
    parts = urllib.parse.urlsplit(base if isinstance(base, str) else "")
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment
            or not stack.get("hpInstanceId")):
        raise ValueError("missing_endpoint")
    required = {"start", "end"} | ({"name"} if path.endswith("LabelValues") else set())
    if set(body) != required or any(type(body.get(k)) is not int for k in ("start", "end")):
        raise ValueError("invalid_request")
    if body["start"] >= body["end"] or ("name" in body and not isinstance(body["name"], str)):
        raise ValueError("invalid_request")
    req = urllib.request.Request(base.rstrip("/") + path, json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json; allow-utf8-labelnames=true")
    req.add_header("Authorization", _basic_auth(str(stack["hpInstanceId"]), cap))
    return bounded_call(lambda: transport(req, timeout), timeout)


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, DeadlineExceeded)):
        return "deadline"
    if isinstance(exc, ValueError) and len(exc.args) == 1 and exc.args[0] in (
        "auth", "http_error", "invalid_response", "response_byte_cap", "missing_endpoint", "deadline",
    ):
        return exc.args[0]
    return "read_failed"


def _strings(raw: Any, *, null_empty: bool = False) -> list[str]:
    if raw is None and null_empty:
        return []
    if not isinstance(raw, list) or any(not isinstance(v, str) for v in raw):
        raise ValueError("invalid_response")
    return sorted(set(raw))


def _read(
    client: ReadOnlyClient, stack: Mapping[str, Any], cap: str, signal: str,
    start: int, end: int, bounds: Bounds, key: tuple[str, str] | None,
    rpc_transport: Callable[[urllib.request.Request, float], Response],
) -> tuple[list[tuple[str, str]] | list[str], bool]:
    if client.remaining() <= 0:
        raise TimeoutError("deadline")
    host_field, tenant_field, prefix = SIGNALS[signal]
    base = stack.get(host_field)
    parts = urllib.parse.urlsplit(base if isinstance(base, str) else "")
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment
            or not stack.get(tenant_field)):
        raise ValueError("missing_endpoint")
    if signal == "profiles":
        body: dict[str, Any] = {"start": start * 1000, "end": end * 1000}
        if key is not None:
            body["name"] = key[1]
        response = profile_read(stack, cap, "/querier.v1.QuerierService/" +
                                ("LabelNames" if key is None else "LabelValues"), body,
                                timeout=min(10.0, client.remaining()), transport=rpc_transport)
    else:
        params: dict[str, object] = {"start": start, "end": end}
        if signal == "logs":
            params = {"start": start * 1_000_000_000, "end": end * 1_000_000_000}
        if signal == "metrics":
            params["limit"] = bounds.keys + 1 if key is None else bounds.values + 1
        if signal == "traces":
            route = "/tags" if key is None else "/tag/" + urllib.parse.quote(
                ".".join(key), safe="") + "/values"
        else:
            route = "/labels" if key is None else "/label/" + urllib.parse.quote(key[1], safe="") + "/values"
        response = client.get(base.rstrip("/") + prefix + route, params=params,
                              basic=(str(stack[tenant_field]), cap))
    if not response.ok:
        raise ValueError("auth" if response.status in (401, 403) else "http_error")
    if len(response.body) > bounds.response_bytes:
        raise ValueError("response_byte_cap")
    try:
        doc = response.json()
    except (ValueError, UnicodeError):
        raise ValueError("invalid_response") from None
    if not isinstance(doc, dict):
        raise ValueError("invalid_response")
    partial = bool(doc.get("warnings"))
    if signal == "profiles":
        if doc and "names" not in doc:
            raise ValueError("invalid_response")
        values = _strings(doc.get("names", []))
    elif signal == "traces":
        if key is None:
            scopes = doc.get("scopes")
            if not isinstance(scopes, list):
                raise ValueError("invalid_response")
            names = []
            for scope in scopes:
                if not isinstance(scope, dict) or not isinstance(scope.get("name"), str):
                    raise ValueError("invalid_response")
                tags = _strings(scope.get("tags"))
                if scope["name"] == "intrinsic":
                    continue  # virtual vocabulary, not application attributes
                if scope["name"] not in {"resource", "span"}:
                    partial = True
                    continue
                names.extend((scope["name"], tag) for tag in tags)
            return sorted(set(names)), partial
        raw = doc.get("tagValues")
        if not isinstance(raw, list) or any(not isinstance(v, dict) or
                                           not isinstance(v.get("value"), str) for v in raw):
            raise ValueError("invalid_response")
        values = sorted({v["value"] for v in raw})
    else:
        if doc.get("status") != "success" or "data" not in doc:
            raise ValueError("invalid_response")
        values = _strings(doc["data"], null_empty=signal == "logs")
    return ([("", name) for name in values] if key is None else values), partial


def probe_stack(
    client: ReadOnlyClient, stack: Mapping[str, Any], cap: str, *,
    now: dt.datetime | None = None, bounds: Bounds = Bounds(),
    rpc_transport: Callable[[urllib.request.Request, float], Response] | None = None,
) -> dict[str, Any]:
    end = int((now or dt.datetime.now(dt.timezone.utc)).timestamp())
    start = end - 86400
    rpc_transport = rpc_transport or bounded_transport(bounds.response_bytes)
    records: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    retained = 0
    for signal in SIGNALS:
        summary: dict[str, Any] = {"state": "unavailable", "reason": "read_failed",
                                   "keys_returned": None, "keys_selected": 0, "keys_sampled": 0,
                                   "values_sampled": 0, "value_reads_failed": 0,
                                   "value_failure_reasons": {}}
        records[signal] = summary
        try:
            names, server_partial = _read(client, stack, cap, signal, start, end, bounds, None, rpc_transport)
        except Exception as exc:
            # Only fixed enums survive; suppress echoed source values, URLs and arbitrary error text.
            summary["reason"] = _failure_reason(exc)
            continue
        summary.update(state="partial", reason="unknown_server_completeness",
                       keys_returned=len(names), server_cap=server_partial,
                       local_key_cap=len(names) > bounds.keys)
        # Generic identity contexts first, then deterministic scope/key order. __name__ is not privileged.
        selected = sorted(names, key=lambda k: (not bool(pii.key_classes(k[1])), k))[:bounds.keys]
        for scope, name in selected:
            if len(name) > 512:
                summary["unexamined_large_key"] = True
                continue
            if client.remaining() <= 0:
                summary["reason"] = "deadline"
                break
            summary["keys_selected"] += 1
            for kind, confidence in pii.key_classes(name):
                findings.append(pii.finding(kind, confidence, signal=signal, scope=scope,
                                           key=name, evidence="key_context", sampled_count=None,
                                           matched_count=None, values=[], retained_count=0))
            try:
                values, server_partial = _read(client, stack, cap, signal, start, end, bounds,
                                               (scope, name), rpc_transport)
            except Exception as exc:
                summary["value_reads_failed"] += 1
                reason = _failure_reason(exc)
                counts = summary["value_failure_reasons"]
                counts[reason] = counts.get(reason, 0) + 1
                continue
            summary["keys_sampled"] += 1
            sampled = values[:bounds.values]
            summary["values_sampled"] += len(sampled)
            summary["server_cap"] |= server_partial
            summary["local_value_cap"] = summary.get("local_value_cap", False) or len(values) > bounds.values
            classes: dict[tuple[str, str], dict[str, Any]] = {}
            for value in sampled:
                if len(value) > 8192:
                    summary["unexamined_large_value"] = True
                    continue
                for kind, confidence in pii.value_classes(name, value):
                    row = classes.setdefault((kind, confidence), pii.finding(
                        kind, confidence, signal=signal, scope=scope, key=name, evidence="value_format",
                        sampled_count=len(sampled), matched_count=0, values=[], retained_count=0))
                    row["matched_count"] += 1
                    size = len(json.dumps(value, ensure_ascii=True).encode())
                    if len(row["values"]) < bounds.matches and retained + size <= bounds.retained_bytes:
                        row["values"].append(value)
                        retained += size
                        row["retained_count"] += 1
                    else:
                        summary["local_match_cap"] = True
            findings.extend(classes.values())
    # Even successful empty reads are not proof of unrestricted backend enumeration. Never say clean.
    return {"available": any(s["keys_returned"] is not None for s in records.values()),
            "window_start": start, "window_end": end, "pattern_version": pii.VERSION,
            "bounds": dict(bounds.__dict__), "signals": records, "findings": findings}


def probe_all(client: ReadOnlyClient, stacks: list[dict[str, Any]], cap: str, *,
              concurrency: int = 4, bounds: Bounds = Bounds(),
              max_seconds: float = 900.0) -> dict[str, Any]:
    """Left-join lookup for the freshly discovered inventory supplied by the T2 runner."""
    if not 0 < max_seconds <= 900:
        raise ValueError("label deadline must be in (0, 900]")
    budget = min(max_seconds, client.remaining() / 4)
    transport = bounded_transport(bounds.response_bytes)
    counter_lock = threading.Lock()
    requests = 0
    statuses: dict[int, int] = {}

    def send(req: urllib.request.Request, timeout: float) -> Response:
        nonlocal requests
        if bounded.remaining() <= 0:
            raise TimeoutError("deadline")
        with counter_lock:
            requests += 1
        response = transport(req, min(timeout, bounded.remaining()))
        with counter_lock:
            statuses[response.status] = statuses.get(response.status, 0) + 1
        return response

    bounded = ReadOnlyClient(max_attempts=1, timeout=10.0, deadline=budget, transport=send)
    selected = [s for s in stacks if str(s.get("status", "")).lower() != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, 8))) as pool:
        rows = pool.map(lambda s: probe_stack(bounded, s, cap, bounds=bounds,
                                              rpc_transport=send), selected)
        result = {str(s["slug"]): row for s, row in zip(selected, rows)}
    # The isolated bounded transport still participates in the runner's request accounting, including
    # the native POSTs. No value, key or source body enters these numeric counters.
    client.attempts.requests += requests
    for status, count in statuses.items():
        client.attempts.by_status[status] = client.attempts.by_status.get(status, 0) + count
    return result
