"""Deterministic labelling catalogue and bounded serialized input seam (schema v1).

Sources persist this envelope only in private label_inventory hydration and S3 views.
Each stack envelope has schema_version and signals; each signal has data (present,
empty, unknown), state, reason, window (head/24h), register, register_truncated and
inputs. A measured-empty exact-200 read alone permits data=empty. Unavailable data
is unknown, never empty. Signal completeness describes ALL required input reads.

Input keys are registered in the catalogue. Each carries state/reason,
names_truncated and values_overflow (0/1), and <=256 numeric samples. A sample has
value, semantics (exact/at_least), population (series/streams or null),
population_semantics, label_kind (dynamic/static). Each registered input declares
unit and aggregation; kind alone does not specify sample units. All comparisons
are per sample in that input's unit; observed evidence is the maximum eligible
sample. Cardinality inputs use distinct_values per label/span-name set. Raw
metric_series/labels_per_series/labels_per_stream inputs use actual per-object
sizes (series_per_metric/labels_per_series/labels_per_stream), NOT precomputed
numbers of violating objects. For aggregation=offending_objects, offending_labels
counts offending objects once each, never the sum of their sizes. Absence inputs
use missing_names and aggregated violation inputs (including shape_count and
service_gap) use violation_count. For aggregation=sum_violations, offending_labels
sums the counts in samples that cross a band. Producers must supply disjoint
violation counts so aggregation does not count the same violation twice.
Cross-signal service_gap samples count each signal's own unmatched identities,
never service values or sets. All counts are source-derived, not raw values.
Sources classify static names against their configured infrastructure allowlist
before minimization; the evaluator never infers static status from population.

The <=256-row register has the exact fields validated below: minimized name or
null, name_class, name_count, scope, distinct_count, count_semantics, shape_counts,
series_count, stream_count. A suppressed name has only class/count; its other
measurements are null/empty. Names >512 UTF-8 bytes or matching pii key/value
classes must be suppressed. Shape keys are only uuid/hex_id/epoch/url_with_id/
long_value. No raw values or PII shapes are admitted. Never send the register to
finding events, metrics, stdout or diagnostic output. Validation errors never
interpolate input. Validating this envelope is not a replacement for source-side
minimization or the source canary.

Each signal is capped at 256 KiB serialized UTF-8 (JSON compact separators,
ensure_ascii=False). Producers drop whole rows, never shorten names or values.
Dropping register or sample rows sets state=partial/reason=truncated, and
register_truncated or names_truncated respectively. Counts from capped reads use
at_least. A values byte-cap sets values_overflow=1 and reason=overflow, not an
empty successful sample. Overflow is a FAIL condition in evidence, not an extra
result-reason enum. Input deadline/missing/partial zero cannot pass. Register
truncation conservatively prevents a pass on every dependent rule, even if an
aggregate appears complete. If the offending-label aggregate exceeds MAX_COUNT,
it saturates at MAX_COUNT and evidence at_least=1 explicitly marks the lower
bound, even for individually exact samples. An exact aggregate equal to MAX_COUNT
remains exact. This is not a values-read byte-cap and does not set condition to
overflow or alter the already-proven failure band. Extending inputs/routes requires
a catalogue-version bump; changing this row schema requires a schema-version bump.

No I/O in evaluate(). It returns only rule ids, stack ids, closed enums and
numbers; caller must left-join it against fresh live inventory, never publish
this module's serialized source envelope to diagnostic or finding surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from collector import pii

CATALOGUE_PATH = Path(__file__).with_name("label_rules.json")
SIGNALS = ("metrics", "logs", "traces", "profiles")
WEIGHTS = {"low": 1, "medium": 3, "high": 5}
REASONS = {"missing_input", "route_parked", "truncated", "deadline",
           "no_signal_data", "precondition_false"}
COVERAGE_REASONS = {"none", "missing_input", "route_parked", "truncated", "deadline", "overflow"}
SHAPES = {"uuid", "hex_id", "epoch", "url_with_id", "long_value"}
MAX_REGISTER_ROWS = 256
MAX_SAMPLES = 256
MAX_SIGNAL_BYTES = 256 * 1024
MAX_COUNT = 2**53 - 1
# Closed units specify both permitted rule kind and offending-evidence aggregation.
INPUT_UNITS = {
    "distinct_values": ("cardinality", "offending_objects"),
    "missing_names": ("absence", "sum_violations"),
    "violation_count": ("count", "sum_violations"),
    "series_per_metric": ("count", "offending_objects"),
    "labels_per_series": ("count", "offending_objects"),
    "labels_per_stream": ("count", "offending_objects"),
}
EVIDENCE_SCHEMA = {"offending_labels": "number", "observed": "number", "at_least": "flag",
                   "worst_band": ["none", "warn", "high", "critical"],
                   "condition": ["none", "overflow"]}


class RuleError(ValueError):
    """Unsafe catalogue/input; messages are fixed and never include supplied data."""


def _require(condition: bool, message: str = "invalid labelling schema") -> None:
    if not condition:
        raise RuleError(message)


def _fields(value: Any, fields: set[str]) -> None:
    _require(isinstance(value, dict) and set(value) == fields)


def _count(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_COUNT


def _enum(value: Any, choices: Any) -> bool:
    return isinstance(value, str) and value in choices


def validate_evidence(evidence: Any) -> dict:
    """Reject unknown fields, free text, booleans, nonfinite and negative numbers."""
    _require(isinstance(evidence, dict), "invalid finding evidence")
    for key, value in evidence.items():
        spec = EVIDENCE_SCHEMA.get(key)
        if spec == "number":
            valid = type(value) in (int, float) and 0 <= value <= MAX_COUNT and math.isfinite(value)
        elif spec == "flag":
            valid = type(value) is int and value in (0, 1)
        elif isinstance(spec, list):
            valid = _enum(value, spec)
        else:
            valid = False
        _require(valid, "invalid finding evidence")
    return evidence


@dataclass(frozen=True)
class Catalogue:
    version: int
    inputs: dict
    rules: tuple[dict, ...]
    threshold_sources: dict


def _thresholds(value: Any) -> None:
    _require(isinstance(value, dict) and bool(value) and set(value) <= {"warn", "high", "critical"})
    values = [value[band] for band in ("warn", "high", "critical") if band in value]
    _require(all(_count(n) and n > 0 for n in values) and values == sorted(set(values)))


def validate_catalogue(raw: Any) -> Catalogue:
    _fields(raw, {"catalogue_version", "evidence_schema", "inputs", "rules", "threshold_sources"})
    _require(_count(raw["catalogue_version"]) and raw["catalogue_version"] > 0)
    _require(raw["evidence_schema"] == EVIDENCE_SCHEMA, "invalid finding evidence schema")
    _require(isinstance(raw["inputs"], dict) and 0 < len(raw["inputs"]) <= 128)
    for key, entry in raw["inputs"].items():
        _require(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) is not None)
        _fields(entry, {"signals", "route", "kind", "unit", "aggregation"})
        _require(isinstance(entry["signals"], list) and bool(entry["signals"]) and
                 all(_enum(s, SIGNALS) for s in entry["signals"]) and
                 len(set(entry["signals"])) == len(entry["signals"]))
        _require(_enum(entry["route"], {"approved", "parked", "unapproved"}))
        _require(_enum(entry["kind"], {"cardinality", "absence", "count"}))
        _require(_enum(entry["unit"], INPUT_UNITS))
        _require((entry["kind"], entry["aggregation"]) == INPUT_UNITS[entry["unit"]],
                 "input unit and aggregation conflict")
    _require(isinstance(raw["rules"], list) and 0 < len(raw["rules"]) <= 256)
    seen = set()
    for r in raw["rules"]:
        _fields(r, {"id", "signals", "severity", "mode", "input", "thresholds",
                    "provenance", "source_url", "verified_on", "verification", "size_floor"})
        _require(isinstance(r["id"], str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", r["id"]) is not None)
        _require(r["id"] not in seen)
        seen.add(r["id"])
        _require(isinstance(r["input"], str) and r["input"] in raw["inputs"])
        entry = raw["inputs"][r["input"]]
        _require(isinstance(r["signals"], list) and bool(r["signals"]) and
                 all(_enum(s, entry["signals"]) for s in r["signals"]) and
                 len(set(r["signals"])) == len(r["signals"]))
        _require(_enum(r["severity"], WEIGHTS) and _enum(r["mode"], {"deterministic", "judgement"}))
        _require(_enum(r["provenance"], {"published", "ps", "policy"}))
        _require(_enum(r["verification"], {"verified", "unverified"}))
        _require(r["provenance"] != "published" or r["verification"] == "verified")
        _require(type(r["size_floor"]) is bool)
        _require(not r["size_floor"] or entry["kind"] == "cardinality")
        _thresholds(r["thresholds"])
        _require(isinstance(r["source_url"], str))
        url = urlsplit(r["source_url"])
        _require(url.scheme == "https" and bool(url.hostname) and not url.username and not url.password)
        if r["verification"] == "verified":
            _require(isinstance(r["verified_on"], str))
            try:
                date = dt.date.fromisoformat(r["verified_on"])
            except ValueError:
                raise RuleError("invalid verification date") from None
            _require(date.isoformat() == r["verified_on"])
        else:
            _require(r["verified_on"] is None)
    _require(isinstance(raw["threshold_sources"], dict) and set(raw["threshold_sources"]) <= seen)
    for rule_id, bands in raw["threshold_sources"].items():
        r = next(r for r in raw["rules"] if r["id"] == rule_id)
        _require(isinstance(bands, dict) and set(bands) <= set(r["thresholds"]))
        for source in bands.values():
            _fields(source, {"provenance", "source_url"})
            _require(_enum(source["provenance"], {"published", "ps", "policy"}))
            # Different external claims require their own verification, not an
            # inherited date. This seam admits only policy overrides for now.
            _require(source["provenance"] == "policy" and isinstance(source["source_url"], str))
            url = urlsplit(source["source_url"])
            _require(url.scheme == "https" and bool(url.hostname) and not url.username and not url.password)
    # Copy through JSON so mutation of the loader's argument cannot alter the validated catalogue.
    clean = json.loads(json.dumps(raw))
    return Catalogue(clean["catalogue_version"], clean["inputs"], tuple(clean["rules"]), clean["threshold_sources"])


def load(path: Path = CATALOGUE_PATH) -> Catalogue:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        raise RuleError("unreadable labelling catalogue") from None
    return validate_catalogue(raw)


def _state(value: dict) -> None:
    _require(_enum(value["state"], {"complete", "partial", "unavailable"}))
    _require(_enum(value["reason"], COVERAGE_REASONS))
    _require((value["state"] == "complete") == (value["reason"] == "none"))
    if value["state"] == "unavailable":
        _require(value["reason"] in {"missing_input", "route_parked", "deadline"})


def validate_inventory(envelope: Any, catalogue: Catalogue | None = None) -> dict:
    """Validate an already minimized per-stack serialized input. No coercion."""
    catalogue = catalogue or CATALOGUE
    _fields(envelope, {"schema_version", "signals"})
    _require(type(envelope["schema_version"]) is int and envelope["schema_version"] == 1)
    _require(isinstance(envelope["signals"], dict) and set(envelope["signals"]) <= set(SIGNALS))
    for signal, payload in envelope["signals"].items():
        _fields(payload, {"data", "state", "reason", "window", "register", "register_truncated", "inputs"})
        _state(payload)
        _require(_enum(payload["data"], {"present", "empty", "unknown"}))
        _require(_enum(payload["window"], {"head", "24h"}))
        _require(payload["data"] != "empty" or payload["state"] == "complete")
        _require(payload["state"] != "unavailable" or payload["data"] == "unknown")
        _require(type(payload["register_truncated"]) is int and payload["register_truncated"] in (0, 1))
        _require(not payload["register_truncated"] or payload["state"] == "partial")
        rows = payload["register"]
        _require(isinstance(rows, list) and len(rows) <= MAX_REGISTER_ROWS)
        for row in rows:
            _fields(row, {"name", "name_class", "name_count", "scope", "distinct_count",
                          "count_semantics", "shape_counts", "series_count", "stream_count"})
            _require(_enum(row["name_class"], {"ordinary", "oversize", "pii"}))
            _require(_count(row["name_count"]) and row["name_count"] > 0)
            _require(_enum(row["scope"], {"label", "resource", "span", "event", "link", "instrumentation", "intrinsic"}))
            _require(_enum(row["count_semantics"], {"exact", "at_least"}))
            if row["name_class"] == "ordinary":
                name = row["name"]
                _require(isinstance(name, str) and bool(name))
                try:
                    size = len(name.encode("utf-8"))
                except UnicodeError:
                    raise RuleError("invalid minimized name") from None
                _require(size <= 512 and not pii.key_classes(name) and not pii.value_classes("", name),
                         "invalid minimized name")
                _require(row["name_count"] == 1)
            else:
                _require(row["name"] is None and row["distinct_count"] is None and
                         row["series_count"] is None and row["stream_count"] is None and not row["shape_counts"])
            for field in ("distinct_count", "series_count", "stream_count"):
                _require(row[field] is None or _count(row[field]))
            shapes = row["shape_counts"]
            _require(isinstance(shapes, dict) and set(shapes) <= SHAPES and all(_count(n) for n in shapes.values()))
        inputs = payload["inputs"]
        _require(isinstance(inputs, dict) and set(inputs) <= set(catalogue.inputs))
        for key, inp in inputs.items():
            _require(signal in catalogue.inputs[key]["signals"])
            _fields(inp, {"state", "reason", "names_truncated", "values_overflow", "samples"})
            _state(inp)
            for flag in ("names_truncated", "values_overflow"):
                _require(type(inp[flag]) is int and inp[flag] in (0, 1))
                _require(not inp[flag] or inp["state"] == "partial")
            _require(not inp["values_overflow"] or inp["reason"] == "overflow")
            _require(isinstance(inp["samples"], list) and len(inp["samples"]) <= MAX_SAMPLES)
            for sample in inp["samples"]:
                _fields(sample, {"value", "semantics", "population", "population_semantics", "label_kind"})
                _require(_count(sample["value"]))
                _require(sample["population"] is None or _count(sample["population"]))
                _require(_enum(sample["semantics"], {"exact", "at_least"}) and
                         _enum(sample["population_semantics"], {"exact", "at_least"}))
                _require(_enum(sample["label_kind"], {"dynamic", "static"}))
        try:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (ValueError, UnicodeError):
            raise RuleError("invalid serialized input") from None
        _require(len(encoded) <= MAX_SIGNAL_BYTES, "serialized input exceeds bound")
        if payload["data"] == "empty":
            _require(not rows and all(not i["samples"] and i["state"] == "complete" for i in inputs.values()))
    return envelope


def _tunables(tunables: Any, catalogue: Catalogue) -> dict:
    if tunables is None:
        tunables = {}
    _require(isinstance(tunables, dict) and set(tunables) <= {"size_floor", "static_multiplier", "coverage_floor", "thresholds"})
    settings = {"size_floor": 100, "static_multiplier": 10, "coverage_floor": 0.8, "thresholds": {}} | tunables
    _require(_count(settings["size_floor"]) and settings["size_floor"] > 0)
    _require(_count(settings["static_multiplier"]) and settings["static_multiplier"] >= 1)
    floor = settings["coverage_floor"]
    _require(type(floor) in (int, float) and 0.8 <= floor <= 1)
    overrides = settings["thresholds"]
    _require(isinstance(overrides, dict) and set(overrides) <= {r["id"] for r in catalogue.rules})
    for thresholds in overrides.values():
        _thresholds(thresholds)
    return settings


def _result(stack: str, rule: dict, outcome: str, reason: str | None = None,
            evidence: dict | None = None, severity: str | None = None) -> dict:
    _require(outcome in {"pass", "fail", "not_evaluated", "not_applicable"})
    _require(reason is None or reason in REASONS)
    return {"stack": stack, "signal": rule["signals"][0] if len(rule["signals"]) == 1 else "cross_signal",
            "rule": rule["id"], "result": outcome, "reason": reason,
            "severity": severity or rule["severity"], "weight": WEIGHTS[rule["severity"]],
            "evidence": validate_evidence(evidence or {"offending_labels": 0, "observed": 0,
                             "at_least": 0, "worst_band": "none", "condition": "none"})}


def _evaluate_rule(stack: str, signals: dict, rule: dict, catalogue: Catalogue, settings: dict) -> dict:
    entry = catalogue.inputs[rule["input"]]
    def done(outcome, reason=None, evidence=None, severity=None):
        return _result(stack, rule, outcome, reason, evidence, severity)
    if rule["mode"] == "judgement" or rule["verification"] != "verified" or entry["route"] != "approved":
        return done("not_evaluated", "route_parked")
    payloads = [signals.get(s) for s in rule["signals"]]
    # A cross-signal rule is inapplicable if either signal was measured empty, not
    # when an API was missing, deadline-limited or unavailable.
    if any(p and p["data"] == "empty" for p in payloads):
        return done("not_applicable", "no_signal_data")
    if any(p is None or p["data"] == "unknown" for p in payloads):
        reason = "deadline" if any(p and p["reason"] == "deadline" for p in payloads) else "missing_input"
        return done("not_evaluated", reason)
    inputs = [p["inputs"].get(rule["input"]) for p in payloads]
    if any(i is None for i in inputs):
        return done("not_evaluated", "missing_input")
    for p, inp in zip(payloads, inputs):
        if inp["state"] == "unavailable" or inp["reason"] == "deadline" or p["reason"] == "deadline":
            reason = "deadline" if "deadline" in (inp["reason"], p["reason"]) else "missing_input"
            return done("not_evaluated", reason)
    if any(i["values_overflow"] for i in inputs):
        return done("fail", evidence={"offending_labels": 0, "observed": 0, "at_least": 1,
                    "worst_band": "warn", "condition": "overflow"}, severity="medium" if rule["severity"] == "low" else rule["severity"])
    if entry["kind"] == "absence" and any(i["names_truncated"] or p["register_truncated"]
                                              for p, i in zip(payloads, inputs)):
        return done("not_evaluated", "truncated")
    samples = [s for inp in inputs for s in inp["samples"]]
    if not samples:
        return done("not_evaluated", "missing_input")
    uncertain = any(i["state"] == "partial" or p["state"] == "partial" for p, i in zip(payloads, inputs))
    thresholds = settings["thresholds"].get(rule["id"], rule["thresholds"])
    band_rank = {"none": 0, "warn": 1, "high": 2, "critical": 3}
    worst = "none"
    offending = observed = lower = eligible = 0
    for sample in samples:
        if rule["size_floor"]:
            population = sample["population"]
            if population is None:
                return done("not_evaluated", "missing_input")
            if population < settings["size_floor"]:
                if sample["population_semantics"] == "at_least":
                    uncertain = True
                continue
        eligible += 1
        observed = max(observed, sample["value"])
        lower |= sample["semantics"] == "at_least"
        multiplier = settings["static_multiplier"] if sample["label_kind"] == "static" and entry["kind"] == "cardinality" else 1
        band = "none"
        for name in ("warn", "high", "critical"):
            if name in thresholds and sample["value"] >= thresholds[name] * multiplier:
                band = name
        if band != "none":
            increment = sample["value"] if entry["aggregation"] == "sum_violations" else 1
            total = offending + increment
            if total > MAX_COUNT:
                lower = 1
            offending = min(total, MAX_COUNT)
            if band_rank[band] > band_rank[worst]:
                worst = band
        elif sample["semantics"] == "at_least":
            uncertain = True
    evidence = {"offending_labels": offending, "observed": observed, "at_least": int(lower),
                "worst_band": worst, "condition": "none"}
    if worst != "none":
        severity = ("high" if worst in {"high", "critical"} else "medium") if entry["kind"] == "cardinality" else rule["severity"]
        return done("fail", evidence=evidence, severity=severity)
    if uncertain:
        return done("not_evaluated", "truncated", evidence)
    if not eligible:
        return done("not_applicable", "precondition_false")
    return done("pass", evidence=evidence)


def evaluate(stack_inventory: dict, rules: Catalogue | None = None, tunables: dict | None = None) -> dict:
    """Evaluate minimized envelopes; caller supplies only the fresh live stack set.

    Summary weights use the rule's fixed catalogue severity, not the observed
    failure band, so missing critical evidence cannot shrink a denominator.
    Judgement/unverified/unapproved entries use route_parked to preserve the frozen
    reason enum. Cross-signal summaries stay view-only. Scores below 0.8 are absent.
    """
    catalogue = rules or CATALOGUE
    # Revalidate dataclass contents: frozen does not recursively freeze mappings.
    catalogue = validate_catalogue({"catalogue_version": catalogue.version,
        "inputs": catalogue.inputs, "rules": list(catalogue.rules), "evidence_schema": EVIDENCE_SCHEMA,
        "threshold_sources": catalogue.threshold_sources})
    settings = _tunables(tunables, catalogue)
    _require(isinstance(stack_inventory, dict) and all(isinstance(s, str) and s for s in stack_inventory))
    results = []
    summaries = []
    for stack, envelope in sorted(stack_inventory.items()):
        _require(isinstance(stack, str) and bool(stack))
        signals = validate_inventory(envelope, catalogue)["signals"]
        rows = [_evaluate_rule(stack, signals, r, catalogue, settings) for r in catalogue.rules]
        results.extend(rows)
        for signal in (*SIGNALS, "cross_signal"):
            subset = [r for r in rows if r["signal"] == signal]
            applicable = [r for r in subset if r["result"] != "not_applicable" and r["reason"] != "route_parked"]
            evaluated = [r for r in applicable if r["result"] in {"pass", "fail"}]
            passed = [r for r in evaluated if r["result"] == "pass"]
            aw = sum(r["weight"] for r in applicable)
            ew = sum(r["weight"] for r in evaluated)
            pw = sum(r["weight"] for r in passed)
            coverage = ew / aw if aw else None
            summary = {"stack": stack, "signal": signal, "applicable_weight": aw,
                       "evaluated_weight": ew, "passed_weight": pw, "rules_evaluated": len(evaluated),
                       "rules_passed": len(passed), "coverage": coverage}
            if ew and coverage >= settings["coverage_floor"]:
                summary["score"] = 100 * pw / ew
            summaries.append(summary)
    return {"catalogue_version": catalogue.version, "results": results, "summaries": summaries}


def threshold_provenance(rule_id: str, catalogue: Catalogue | None = None,
                         tunables: dict | None = None) -> dict:
    """Per-band provenance. Tuned numbers are policy, never a published limit.

    Unverified catalogue entries use a policy placeholder, not published
    provenance, and are excluded until a passage is verified. Source URL on a
    tuned threshold identifies the original rationale, not a
    claim that its new numeric value was published there. Static multipliers
    and size/coverage floors are likewise policy (D-LBL3/D-LBL8).
    """
    catalogue = catalogue or CATALOGUE
    settings = _tunables(tunables, catalogue)
    r = next((r for r in catalogue.rules if r["id"] == rule_id), None)
    _require(r is not None)
    thresholds = settings["thresholds"].get(rule_id, r["thresholds"])
    return {band: {"value": value,
                   "provenance": "policy" if rule_id in settings["thresholds"] else
                       catalogue.threshold_sources.get(rule_id, {}).get(band, {}).get("provenance", r["provenance"]),
                   "source_url": catalogue.threshold_sources.get(rule_id, {}).get(band, {}).get("source_url", r["source_url"]),
                   "verified_on": r["verified_on"], "verification": r["verification"]}
            for band, value in thresholds.items()}


CATALOGUE = load()
