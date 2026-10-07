"""Default-off bounded T2 labelling input, private S3 hydration only (schema v1).

Mimir uses cardinality/label_names then capped, prioritized label_values reads:
head counts, per-label series populations and numeric per-metric sizes. Values
and metric names are transient; no 24h values are mixed into that head window.
Cross-signal value-set comparisons remain missing, not clean zeros.
The other three signals use existing 24h names/values reads. Their undocumented
server completeness remains partial/truncated even below the local caps or empty.
No series, OTLP config, intrinsic Tempo name or overrides routes are activated.

The isolated source gets <=900s and <=one quarter of the tier's remaining time,
immediately after label_risk and before gcom detail in run_t2. Exhaustion produces
partial/deadline, including stacks not yet visited. Request bodies/values are
transient; errors are fixed enums. label_risk's behavior is not changed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import datetime as dt
import json
import math
import time
import re
import threading
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

from collector import label_rules, pii
from collector.httpclient import DeadlineExceeded, ReadOnlyClient, Response
from collector.sources import label_risk

SIGNALS = label_risk.SIGNALS
MAX_SECONDS = 900.0
STATIC_NAMES = frozenset({"host", "hostname", "cluster", "namespace", "node",
                          "k8s_cluster_name", "k8s_namespace_name", "k8s_node_name",
                          "k8s.cluster.name", "k8s.namespace.name", "k8s.node.name"})
_NAME_PRIORITY = re.compile(r"(?:user|session|request|trace|span|uuid|guid|ip|email|timestamp|url|path|pod|instance)[._-]?(?:id|name)?", re.I)
_SHAPES = {
    "uuid": re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.I),
    "hex_id": re.compile(r"^[0-9a-f]{16,64}$", re.I),
    "epoch": re.compile(r"^(?:1[0-9]{9}|[12][0-9]{12}|[12][0-9]{15}|[12][0-9]{18})$"),
    "url_with_id": re.compile(r"^https?://[^\s]+/(?:[^\s/]+/)*[^\s/]*(?:[0-9]{6,}|[0-9a-f]{8}-[0-9a-f-]{27,})[^\s]*$", re.I),
}


@dataclass(frozen=True)
class Bounds:
    keys: int = 64
    values: int = 256
    names: int = 500
    rows: int = 256
    response_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        limits = {"keys": 256, "values": 256, "names": 500, "rows": 256,
                  "response_bytes": 2 * 1024 * 1024}
        if any(type(getattr(self, k)) is not int or not 1 <= getattr(self, k) <= v
               for k, v in limits.items()):
            raise ValueError("invalid label inventory bounds")


def bounded_transport(cap: int) -> Callable:
    """Keep exact status and a cap+1-byte overflow witness through the GET client.

    Its retry helper wraps transport exceptions, so throwing the cap exception at
    that edge would lose the overflow enum. Return bounded transient bytes instead;
    _read checks exact 200 first, then discards an overflowing body before parsing.
    Error bodies are never read and redirects never forward credentials.
    """
    opener = urllib.request.build_opener(label_risk._NoRedirect())

    def send(req: urllib.request.Request, timeout: float) -> Response:
        stop = time.monotonic() + timeout
        try:
            fh = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            exc.close()
            return Response(exc.code, b"", "", {})
        with fh:
            if fh.status != 200:
                return Response(fh.status, b"", "", {})
            # HTTPMessage.get() returns only the first field. Any duplicate,
            # even an identical value, is ambiguous framing: reject before reads.
            get_all = getattr(fh.headers, "get_all", None)
            if callable(get_all):
                lengths = get_all("Content-Length") or []
                if len(lengths) > 1:
                    raise ValueError("invalid_response_framing")
                declared = lengths[0] if lengths else None
            else:
                # Headerless/mapping process-edge responses remain supported.
                declared = fh.headers.get("Content-Length")
            if declared is not None:
                if (not isinstance(declared, str) or not declared.strip().isascii()
                        or not declared.strip().isdecimal()
                        or fh.headers.get("Transfer-Encoding")):
                    raise ValueError("invalid_response_framing")
                declared = int(declared.strip())
            body = bytearray()
            while len(body) <= cap:
                if time.monotonic() >= stop:
                    raise TimeoutError("deadline")
                chunk = fh.read1(min(65536, cap + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            # read1() with an amount can silently EOF before Content-Length.
            # A cap+1 read is deliberately incomplete and remains an overflow
            # witness; anything admitted for parsing must match its framing.
            if len(body) <= cap and declared is not None and len(body) != declared:
                raise ValueError("incomplete_response_body")
            return Response(fh.status, bytes(body), "", {})
    return send


def _input(state="complete", reason="none", *, truncated=False, overflow=False, samples=None):
    return {"state": state, "reason": reason, "names_truncated": int(truncated),
            "values_overflow": int(overflow), "samples": samples or []}


def _sample(value: int, semantics="exact", *, kind="dynamic", population=None):
    return {"value": value, "semantics": semantics, "population": population,
            "population_semantics": "exact", "label_kind": kind}


def _reason(exc: Exception) -> str:
    if isinstance(exc, (DeadlineExceeded, TimeoutError)):
        return "deadline"
    if isinstance(exc, ValueError) and exc.args == ("response_byte_cap",):
        return "overflow"
    return "missing_input"


def _name_class(name: str) -> str:
    if len(name.encode("utf-8")) > 512:
        return "oversize"
    if pii.key_classes(name) or pii.value_classes("", name):
        return "pii"
    return "ordinary"


def _row(scope: str, name: str, count: int | None = None, semantics="exact") -> dict:
    kind = _name_class(name)
    return {"name": name if kind == "ordinary" else None, "name_class": kind,
            "name_count": 1, "scope": scope, "distinct_count": count if kind == "ordinary" else None,
            "count_semantics": semantics, "shape_counts": {}, "series_count": None, "stream_count": None}


def _strings(raw: Any) -> list[str]:
    if not isinstance(raw, list) or any(not isinstance(v, str) or not v for v in raw):
        raise ValueError("invalid_response")
    # Also reject lone surrogate code points, before names reach minimization or URL encoding.
    for value in raw:
        value.encode("utf-8")
    return sorted(set(raw))


def _read(client: ReadOnlyClient, stack: Mapping[str, Any], cap: str, signal: str,
          start: int, end: int, bounds: Bounds, transport: Callable,
          key: tuple[str, str] | None = None) -> tuple[list, bool]:
    if client.remaining() <= 0:
        raise TimeoutError("deadline")
    host, tenant, prefix = SIGNALS[signal]
    base = stack.get(host)
    parts = urllib.parse.urlsplit(base if isinstance(base, str) else "")
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment or not stack.get(tenant)):
        raise ValueError("missing_endpoint")
    if signal == "profiles":
        body = {"start": start * 1000, "end": end * 1000}
        if key is not None:
            body["name"] = key[1]
        response = label_risk.profile_read(stack, cap, "/querier.v1.QuerierService/" +
            ("LabelNames" if key is None else "LabelValues"), body,
            timeout=min(10.0, client.remaining()), transport=transport)
    else:
        params: dict[str, object] = {"start": start, "end": end}
        if signal == "metrics":
            params = {"limit": bounds.names if key is None else bounds.values, "count_method": "inmemory"}
            route = "/cardinality/label_names" if key is None else "/cardinality/label_values"
            if key is not None:
                params["label_names[]"] = key[1]
        elif signal == "logs":
            params = {"start": start * 1_000_000_000, "end": end * 1_000_000_000}
            route = "/labels" if key is None else "/label/" + urllib.parse.quote(key[1], safe="") + "/values"
        else:
            route = "/tags" if key is None else "/tag/" + urllib.parse.quote(".".join(key), safe="") + "/values"
        response = client.get(base.rstrip("/") + prefix + route, params=params,
            headers={"Accept": "application/json; allow-utf8-labelnames=true"},
            basic=(str(stack[tenant]), cap))
    if response.status != 200:
        raise ValueError("http_error")
    if len(response.body) > bounds.response_bytes:
        raise ValueError("response_byte_cap")
    doc = response.json()
    if not isinstance(doc, dict):
        raise ValueError("invalid_response")
    partial = bool(doc.get("warnings"))
    if signal == "metrics":
        if key is not None:
            return _mimir_values(doc, key[1], bounds.values), partial
        raw = doc.get("cardinality")
        total = doc.get("label_names_count")
        values_total = doc.get("label_values_count_total")
        if (not isinstance(raw, list) or not label_rules._count(total)
                or not label_rules._count(values_total)):
            raise ValueError("invalid_response")
        rows = []
        for item in raw:
            if (not isinstance(item, dict) or not isinstance(item.get("label_name"), str)
                    or not item["label_name"] or not label_rules._count(item.get("label_values_count"))):
                raise ValueError("invalid_response")
            item["label_name"].encode("utf-8")
            rows.append(("label", item["label_name"], item["label_values_count"]))
        if (len({r[1] for r in rows}) != len(rows) or total < len(rows)
                or values_total < sum(r[2] for r in rows)
                or (not total and (rows or values_total))):
            raise ValueError("invalid_response")
        return rows, partial or total != len(rows) or len(rows) >= bounds.names
    if signal == "traces":
        if key is None:
            raw = doc.get("scopes")
            if not isinstance(raw, list):
                raise ValueError("invalid_response")
            names = []
            for scope in raw:
                if not isinstance(scope, dict) or not isinstance(scope.get("name"), str):
                    raise ValueError("invalid_response")
                tags = _strings(scope.get("tags"))
                if scope["name"] == "intrinsic":
                    continue
                if scope["name"] not in {"resource", "span"}:
                    partial = True
                    continue
                names.extend((scope["name"], name, None) for name in tags)
            return sorted(set(names)), True  # No complete enumeration witness.
        raw = doc.get("tagValues")
        if not isinstance(raw, list) or any(not isinstance(v, dict) or
            not isinstance(v.get("value"), str) for v in raw):
            raise ValueError("invalid_response")
        # Empty label VALUES are valid; unlike names they need not be nonempty.
        values = [v["value"] for v in raw]
    elif signal == "profiles":
        if doc and "names" not in doc:
            raise ValueError("invalid_response")
        values = doc.get("names", [])
    else:
        if doc.get("status") != "success" or "data" not in doc:
            raise ValueError("invalid_response")
        values = [] if doc["data"] is None else doc["data"]
    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
        raise ValueError("invalid_response")
    for value in values:
        value.encode("utf-8")
    if key is None:
        return [("label", name, None) for name in _strings(values)], True
    return sorted(set(values)), True  # At least observed values, never a complete inventory.


def _mimir_values(doc: dict, name: str, limit: int) -> dict:
    """C1 head-only shape; reconcile before reducing. Never persist this document."""
    labels, total = doc.get("labels"), doc.get("series_count_total")
    if (not label_rules._count(total) or not isinstance(labels, list) or len(labels) != 1
            or not isinstance(labels[0], dict) or labels[0].get("label_name") != name):
        raise ValueError("invalid_response")
    label = labels[0]
    count, population, values = label.get("label_values_count"), label.get("series_count"), label.get("cardinality")
    if (not label_rules._count(count) or not label_rules._count(population)
            or population > total or not isinstance(values, list) or len(values) > limit
            or count < len(values)):
        raise ValueError("invalid_response")
    seen, series = set(), 0
    for value in values:
        if (not isinstance(value, dict) or not isinstance(value.get("label_value"), str)
                or not label_rules._count(value.get("series_count"))):
            raise ValueError("invalid_response")
        raw = value["label_value"]
        raw.encode("utf-8")
        if raw in seen:
            raise ValueError("invalid_response")
        seen.add(raw)
        series += value["series_count"]
    if (series > population or (count == len(values) and series != population)
            or (not count and population) or (count and not values)):
        raise ValueError("invalid_response")
    return {"count": count, "population": population, "values": values,
            "partial": count != len(values) or len(values) >= limit}


def _shape_counts(name, values):
    shapes, offending = {}, 0
    for value in values:
        if pii.value_classes(name, value):
            continue
        classes = [kind for kind, pattern in _SHAPES.items() if pattern.fullmatch(value)]
        if len(value.encode("utf-8")) > 256:
            classes.append("long_value")
        offending += bool(classes)
        for kind in classes:
            shapes[kind] = shapes.get(kind, 0) + 1
    return shapes, offending


def _metric_inputs(client, stack, cap, start, end, bounds, transport, kept, payload, static_names):
    """Reduce at most keys head reads; no value or metric-name string survives."""
    inputs = payload["inputs"]
    truncated = payload["state"] == "partial"
    inputs["shape_count"] = _input("unavailable", "missing_input")
    inputs["metric_series"] = _input("unavailable", "missing_input")
    distinct, shape_count, successful = [], 0, 0
    shape_partial, overflow, failure = truncated, False, None
    for index, ((scope, name, count), row) in enumerate(zip(kept, payload["register"])):
        population = None
        if index < bounds.keys and row["name_class"] != "oversize":
            try:
                measurement, warned = _read(client, stack, cap, "metrics", start, end,
                                             bounds, transport, (scope, name))
            except Exception as exc:
                failure = "deadline" if client.remaining() <= 0 else _reason(exc)
                overflow |= failure == "overflow"
                shape_partial = True
                payload.update(state="partial", reason="overflow" if overflow else failure)
                if name == "__name__":
                    inputs["metric_series"] = _input("partial" if failure in {"deadline", "overflow"} else "unavailable",
                        failure, truncated=truncated and failure in {"deadline", "overflow"},
                        overflow=failure == "overflow")
            else:
                successful += name != "__name__"
                count, population = measurement["count"], measurement["population"]
                partial = warned or measurement["partial"]
                shape_partial |= partial
                if partial and failure is None:
                    payload.update(state="partial", reason="truncated")
                values = measurement["values"]
                if name == "__name__":
                    inputs["metric_series"] = _input("partial" if partial or truncated else "complete",
                        "truncated" if partial or truncated else "none", truncated=truncated,
                        samples=[_sample(v["series_count"], "at_least" if partial else "exact") for v in values])
                else:
                    shapes, offending = _shape_counts(name, (v["label_value"] for v in values))
                    shape_count += offending
                    if row["name_class"] == "ordinary":
                        row["shape_counts"] = shapes
                if row["name_class"] == "ordinary":
                    row.update(distinct_count=count, series_count=population)
        else:
            shape_partial = True
            if failure is None:
                payload.update(state="partial", reason="truncated")
        distinct.append(_sample(count, population=population,
            kind="static" if name in static_names else "dynamic"))
    inputs["distinct_values"]["samples"] = distinct
    if successful or overflow:
        partial = shape_partial or failure is not None
        inputs["shape_count"] = _input("partial" if partial else "complete",
            "overflow" if overflow else (failure or ("truncated" if partial else "none")),
            truncated=truncated, overflow=overflow,
            samples=[_sample(shape_count, "at_least" if partial else "exact")])
    elif failure:
        inputs["shape_count"] = _input("partial" if failure in {"deadline", "overflow"} else "unavailable",
                                      failure, overflow=overflow)
    if failure or payload["state"] == "partial":
        inputs["distinct_values"].update(state="partial", reason="overflow" if overflow else (failure or "truncated"),
                                         values_overflow=int(overflow))


def _priority(row: tuple) -> tuple:
    scope, name, count = row
    return (name != "__name__", not bool(pii.key_classes(name) or _NAME_PRIORITY.search(name)),
            -(count if count is not None else 0), scope, name)


def _signal(client, stack, cap, signal, start, end, bounds, transport, static_names):
    payload = {"data": "unknown", "state": "unavailable", "reason": "missing_input",
               "window": "head" if signal == "metrics" else "24h", "register": [],
               "register_truncated": 0, "inputs": {}}
    try:
        names, names_partial = _read(client, stack, cap, signal, start, end, bounds, transport)
    except Exception as exc:
        reason = "deadline" if client.remaining() <= 0 else _reason(exc)
        # A names byte-cap is not a values-read finding. No absence can pass it.
        payload.update(state="partial" if reason in {"deadline", "overflow"} else "unavailable",
                       reason="truncated" if reason == "overflow" else reason)
        return payload
    names = sorted(names, key=_priority)
    truncated = names_partial or len(names) > min(bounds.names, bounds.rows)
    kept = names[:min(bounds.names, bounds.rows)]
    payload.update(data="present" if names else ("unknown" if truncated else "empty"),
                   state="partial" if truncated else "complete", reason="truncated" if truncated else "none",
                   register_truncated=int(len(names) > len(kept)))
    if not names:
        return payload
    inputs = payload["inputs"]
    state, reason = ("partial", "truncated") if truncated else ("complete", "none")
    identities = {"metrics": {("label", "service_name"), ("label", "job")},
                  "logs": {("label", "service_name")}, "traces": {("resource", "service.name")},
                  "profiles": {("label", "service_name")}}
    inputs["missing_identity"] = _input(state, reason, truncated=truncated,
        samples=[_sample(int(not any((s, n) in identities[signal] for s, n, _ in kept)))])
    if signal in {"metrics", "logs", "profiles"}:
        inputs["distinct_values"] = _input(state, reason, truncated=truncated)
    if signal != "metrics":
        inputs["shape_count"] = _input("unavailable", "missing_input")
    shape_count = successful_reads = 0
    shape_partial = truncated
    shape_overflow = False
    failure = None
    for index, (scope, name, count) in enumerate(kept):
        row = _row(scope, name, count)
        payload["register"].append(row)
        semantics = "exact"
        if signal != "metrics" and index < bounds.keys and row["name_class"] != "oversize":
            try:
                values, values_partial = _read(client, stack, cap, signal, start, end, bounds,
                                               transport, (scope, name))
            except Exception as exc:
                failure = "deadline" if client.remaining() <= 0 else _reason(exc)
                shape_overflow |= failure == "overflow"
                payload.update(state="partial", reason=failure)
                continue
            successful_reads += 1
            sampled = values[:bounds.values]
            semantics = "at_least" if values_partial or len(values) > bounds.values else "exact"
            count = len(sampled)
            shape_partial |= semantics == "at_least"
            shapes = {}
            for value in sampled:
                # PII never enters shape counts; arbitrarily long values are transient long_value only.
                if pii.value_classes(name, value):
                    continue
                classes = [kind for kind, pattern in _SHAPES.items() if pattern.fullmatch(value)]
                if len(value.encode("utf-8")) > 256:
                    classes.append("long_value")
                shape_count += bool(classes)  # Each offending sampled value counted once, not per class.
                for kind in classes:
                    shapes[kind] = shapes.get(kind, 0) + 1
            if row["name_class"] == "ordinary":
                row.update(distinct_count=count, count_semantics=semantics, shape_counts=shapes)
        elif signal != "metrics":
            shape_partial = True
        if "distinct_values" in inputs and count is not None:
            inputs["distinct_values"]["samples"].append(_sample(count, semantics,
                kind="static" if name in static_names else "dynamic"))
    if signal != "metrics":
        shape = inputs["shape_count"]
        if successful_reads or shape_overflow:
            shape.update(_input("partial" if shape_partial or failure else "complete",
                "overflow" if shape_overflow else (failure or ("truncated" if shape_partial else "none")),
                truncated=truncated, overflow=shape_overflow,
                samples=[_sample(shape_count, "at_least" if shape_partial or failure else "exact")]))
        elif failure:
            shape.update(_input("partial" if failure in {"deadline", "overflow"} else "unavailable",
                                failure, overflow=shape_overflow))
        distinct = inputs.get("distinct_values")
        if distinct is not None and failure:
            distinct.update(state="partial", reason="overflow" if shape_overflow else failure,
                            values_overflow=int(shape_overflow))
    if signal == "metrics":
        _metric_inputs(client, stack, cap, start, end, bounds, transport, kept, payload, static_names)
    # Coalesce suppressed names by class/scope; their measurements remain null/empty.
    rows, suppressed = [], {}
    for row in payload["register"]:
        if row["name_class"] == "ordinary":
            rows.append(row)
        else:
            key = (row["name_class"], row["scope"])
            if key in suppressed:
                suppressed[key]["name_count"] += 1
            else:
                suppressed[key] = row
    payload["register"] = rows + list(suppressed.values())
    # JSON escaping can inflate even <=512-byte names. Drop whole rows, never trim a name;
    # numeric input samples remain actual observations but register truncation blocks every pass.
    while len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > label_rules.MAX_SIGNAL_BYTES:
        payload["register"].pop()
        payload.update(state="partial", register_truncated=1)
        if payload["reason"] not in {"overflow", "deadline", "missing_input"}:
            payload["reason"] = "truncated"
        for inp in inputs.values():
            if inp["state"] != "unavailable":
                inp.update(state="partial", names_truncated=1)
                if inp["reason"] not in {"overflow", "deadline", "missing_input"}:
                    inp["reason"] = "truncated"
    return payload


def probe_stack(client: ReadOnlyClient, stack: Mapping[str, Any], cap: str, *,
                now: dt.datetime | None = None, bounds: Bounds = Bounds(),
                rpc_transport: Callable | None = None, static_names=STATIC_NAMES) -> dict:
    end = int((now or dt.datetime.now(dt.timezone.utc)).timestamp())
    transport = rpc_transport or bounded_transport(bounds.response_bytes)
    envelope = {"schema_version": 1, "signals": {signal: _signal(client, stack, cap, signal,
        end - 86400, end, bounds, transport, static_names) for signal in SIGNALS}}
    return label_rules.validate_inventory(envelope)


def probe_all(client: ReadOnlyClient, stacks: list[dict[str, Any]], cap: str, *, enabled=False,
              concurrency=4, bounds: Bounds = Bounds(), max_seconds=MAX_SECONDS,
              static_names=STATIC_NAMES) -> dict:
    """Iterate only the runner's fresh inventory; disabled means no transport or client construction."""
    if not enabled:
        return {}
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or not 0 < max_seconds <= MAX_SECONDS:
        raise ValueError("invalid label inventory deadline")
    budget = min(max_seconds, client.remaining() / 4)
    transport = bounded_transport(bounds.response_bytes)
    counter_lock = threading.Lock()
    requests = 0
    statuses = {}

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
                                            rpc_transport=send, static_names=static_names), selected)
        result = {str(s["slug"]): row for s, row in zip(selected, rows)}
    client.attempts.requests += requests
    for status, count in statuses.items():
        client.attempts.by_status[status] = client.attempts.by_status.get(status, 0) + count
    return result


def composition_inputs(inputs: dict) -> dict:
    """Pass private inputs to composition; diagnostic and publication fences remain separate."""
    return dict(inputs)


def diagnostic_scan(scan: dict) -> dict:
    """No names/counts from private input or the future register in diagnostic --out.

    Filter known view maps too, without mutating S3 data. Numeric findings need no
    FindingSpec; no generic finding event is generated by this source.
    """
    safe = {**scan, "data": {k: v for k, v in scan.get("data", {}).items() if k != "label_inventory"}}
    for field in ("views", "_emit"):
        value = safe.get(field)
        if not isinstance(value, dict):
            continue
        if field == "views":
            safe[field] = {k: v for k, v in value.items() if k != "labelling_label_register"}
        else:
            safe[field] = {**value, "views": {k: v for k, v in value.get("views", {}).items()
                                             if k != "labelling_label_register"}}
    safe["data"].pop("labelling_label_register", None)
    return safe
