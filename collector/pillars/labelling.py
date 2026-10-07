"""Deterministic bounded labelling views and versioned trend metrics.

The minimized source envelope is private. Only the register carries label names;
no view is a FindingSpec or an event. Service/cluster sets are transient and the
cross-signal view exposes set sizes only. Every join starts with fresh inventory.
Score policy belongs to label_rules.evaluate; forwarded tunables also govern the
severity coverage floor. Maturity and existing cardinality findings are unchanged.
"""
from __future__ import annotations

from itertools import combinations
import json
from typing import Any

from collector import label_rules

SIGNALS = label_rules.SIGNALS
SEVERITIES = tuple(label_rules.WEIGHTS)
PILLAR = "L"
VIEW_SCHEMAS = {
    "labelling_findings": (
        (" Stack", "string"), ("Signal", "string"), ("Rule", "string"),
        ("Result", "string"), ("Reason", "string"), ("Severity", "string"),
        ("Weight", "number"), ("Offending objects", "number"), ("Observed", "number"),
        ("At least", "number"), ("Worst band", "string"), ("Condition", "string"),
        ("Threshold provenance", "string"), ("Catalogue version", "number"),
    ),
    "labelling_stack_summary": (
        (" Stack", "string"), ("Signal", "string"), ("Data", "string"),
        ("Input state", "string"), ("Input reason", "string"), ("Window", "string"),
        ("Applicable weight", "number"), ("Evaluated weight", "number"), ("Passed weight", "number"),
        ("Rules evaluated", "number"), ("Rules passed", "number"), ("Rules failed", "number"),
        ("Not evaluated", "number"), ("Not applicable", "number"), ("Excluded rules", "number"),
        ("Low findings", "number"), ("Medium findings", "number"), ("High findings", "number"),
        ("Low coverage", "number"), ("Medium coverage", "number"), ("High coverage", "number"),
        ("Coverage", "number"), ("Score", "number"), ("Worst severity", "string"),
        ("Catalogue version", "number"),
    ),
    "labelling_cross_signal": (
        (" Stack", "string"), ("Signal A", "string"), ("Signal B", "string"),
        ("State", "string"), ("Services A", "number"), ("Services B", "number"),
        ("Shared services", "number"), ("Union services", "number"),
        ("Only A", "number"), ("Only B", "number"), ("Metric clusters", "number"),
        ("Catalogue version", "number"),
    ),
    "labelling_label_register": (
        (" Stack", "string"), ("Signal", "string"), ("Label name", "string"),
        ("Name class", "string"), ("Name count", "number"), ("Scope", "string"),
        ("Distinct count", "number"), ("Count semantics", "string"),
        ("UUID shapes", "number"), ("Hex ID shapes", "number"), ("Epoch shapes", "number"),
        ("URL with ID shapes", "number"), ("Long value shapes", "number"),
        ("Series count", "number"), ("Stream count", "number"), ("Window", "string"),
        ("Input state", "string"), ("Input reason", "string"),
        ("Register truncated", "number"), ("Catalogue version", "number"),
    ),
}
S3_ONLY_VIEWS = frozenset(VIEW_SCHEMAS)
_SERVICE_FIELDS = dict(zip(SIGNALS, ("metric_services", "log_services", "trace_services", "profile_services")))
_SHAPE_FIELDS = {"uuid": "UUID shapes", "hex_id": "Hex ID shapes", "epoch": "Epoch shapes",
                 "url_with_id": "URL with ID shapes", "long_value": "Long value shapes"}


def _potential_severities(rule: dict) -> set[str]:
    """Coverage includes every fixed-weight rule that can contribute to a severity.

    Cardinality failures can escalate from medium to high. Counting high findings
    without those rules in high's denominator would turn an unmeasured cardinality
    input into a confident zero. Overflow can also escalate low rules to medium.
    """
    severities = {rule["severity"]}
    if label_rules.CATALOGUE.inputs[rule["input"]]["kind"] == "cardinality":
        severities.update(("medium", "high"))
    if rule["severity"] == "low":
        severities.add("medium")
    return severities


def _severity_counts(results: list[dict], floor: float) -> dict[str, tuple[int | None, float | None]]:
    rules = {r["id"]: r for r in label_rules.CATALOGUE.rules}
    out = {}
    for severity in SEVERITIES:
        applicable = [r for r in results if r["result"] != "not_applicable" and
                      r["reason"] != "route_parked" and severity in _potential_severities(rules[r["rule"]])]
        aw = sum(r["weight"] for r in applicable)
        ew = sum(r["weight"] for r in applicable if r["result"] in ("pass", "fail"))
        coverage = ew / aw if aw else None
        count = sum(r["result"] == "fail" and r["severity"] == severity for r in results)
        out[severity] = (count if aw and coverage >= floor else None, coverage)
    return out


def build(stacks: list[dict[str, Any]], label_inventory: dict | None = None,
          signal_inventory: dict | None = None, *, tunables: dict | None = None):
    if label_inventory is None or not stacks:
        return [], {}
    live = [s for s in stacks if str(s.get("status", "")).lower() != "paused"]
    envelopes = {str(s["slug"]): label_inventory.get(str(s["slug"]), {"schema_version": 1, "signals": {}})
                 for s in live}
    evaluated = label_rules.evaluate(envelopes, tunables=tunables)
    version = evaluated["catalogue_version"]
    floor = (tunables or {}).get("coverage_floor", 0.8)  # evaluate has validated policy, including its floor.
    metrics = []
    if any(slug in label_inventory for slug in envelopes):
        metrics.append(("gcinsight_labelling_catalogue_version", {}, float(version)))
    views = {name: [] for name in VIEW_SCHEMAS if name != "labelling_cross_signal"}
    provenance = {r["id"]: json.dumps(label_rules.threshold_provenance(r["id"], tunables=tunables),
                                    sort_keys=True, separators=(",", ":")) for r in label_rules.CATALOGUE.rules}
    for result in evaluated["results"]:
        evidence = result["evidence"]
        views["labelling_findings"].append({
            " Stack": result["stack"], "Signal": result["signal"], "Rule": result["rule"],
            "Result": result["result"], "Reason": result["reason"], "Severity": result["severity"],
            "Weight": result["weight"], "Offending objects": evidence["offending_labels"],
            "Observed": evidence["observed"], "At least": evidence["at_least"],
            "Worst band": evidence["worst_band"], "Condition": evidence["condition"],
            "Threshold provenance": provenance[result["rule"]], "Catalogue version": version,
        })
    by_stack_signal: dict[tuple[str, str], list[dict]] = {}
    for result in evaluated["results"]:
        by_stack_signal.setdefault((result["stack"], result["signal"]), []).append(result)
    for summary in evaluated["summaries"]:
        slug, signal = summary["stack"], summary["signal"]
        if signal not in SIGNALS:  # Cross-signal results and counts are view-only, never extra metric enums.
            continue
        payload = envelopes[slug]["signals"].get(signal, {})
        results = by_stack_signal.get((slug, signal), [])
        counts = _severity_counts(results, floor)
        failures = [r for r in results if r["result"] == "fail"]
        row = {" Stack": slug, "Signal": signal, "Data": payload.get("data", "unknown"),
               "Input state": payload.get("state", "unavailable"), "Input reason": payload.get("reason", "missing_input"),
               "Window": payload.get("window"), "Applicable weight": summary["applicable_weight"],
               "Evaluated weight": summary["evaluated_weight"], "Passed weight": summary["passed_weight"],
               "Rules evaluated": summary["rules_evaluated"], "Rules passed": summary["rules_passed"],
               "Rules failed": len(failures), "Not evaluated": sum(r["result"] == "not_evaluated" for r in results),
               "Not applicable": sum(r["result"] == "not_applicable" for r in results),
               "Excluded rules": sum(r["reason"] == "route_parked" for r in results),
               "Coverage": summary["coverage"], "Score": summary.get("score"),
               "Worst severity": max((r["severity"] for r in failures), key=label_rules.WEIGHTS.get, default=None),
               "Catalogue version": version}
        for severity, (count, coverage) in counts.items():
            row[f"{severity.title()} findings"] = count
            row[f"{severity.title()} coverage"] = coverage
        views["labelling_stack_summary"].append(row)
        labels = {"stack": slug, "signal": signal}
        if summary["evaluated_weight"]:
            for key, suffix in (("rules_evaluated", "rules_evaluated"), ("rules_passed", "rules_passed"), ("score", "score")):
                if key in summary:
                    metrics.append((f"gcinsight_labelling_{suffix}", dict(labels), float(summary[key])))
    for slug, envelope in envelopes.items():
        signal_results = [r for signal in SIGNALS for r in by_stack_signal.get((slug, signal), [])]
        for severity, (count, _coverage) in _severity_counts(signal_results, floor).items():
            if count is not None:
                metrics.append(("gcinsight_labelling_findings", {"stack": slug, "severity": severity}, float(count)))
        for signal, payload in envelope["signals"].items():
            for source in payload["register"]:  # The strict seam already caps this at 256 whole rows.
                row = {" Stack": slug, "Signal": signal, "Label name": source["name"],
                       "Name class": source["name_class"], "Name count": source["name_count"], "Scope": source["scope"],
                       "Distinct count": source["distinct_count"], "Count semantics": source["count_semantics"],
                       "Series count": source["series_count"], "Stream count": source["stream_count"],
                       "Window": payload["window"], "Input state": payload["state"], "Input reason": payload["reason"],
                       "Register truncated": payload["register_truncated"], "Catalogue version": version}
                # Suppressed names persist class/count only: do not normalize their absent counts to zero.
                row.update({field: source["shape_counts"].get(shape, 0) if source["name_class"] == "ordinary" else None
                            for shape, field in _SHAPE_FIELDS.items()})
                views["labelling_label_register"].append(row)
    if signal_inventory is not None:
        views["labelling_cross_signal"] = []
        for stack in live:
            slug = str(stack["slug"])
            record = signal_inventory.get(slug) or {}
            available = record.get("available") is True
            sets = {signal: set(record.get(field) or []) for signal, field in _SERVICE_FIELDS.items()} if available else {}
            clusters = len(set(record.get("clusters") or [])) if available else None
            for a, b in combinations(SIGNALS, 2):
                views["labelling_cross_signal"].append({
                    " Stack": slug, "Signal A": a, "Signal B": b, "State": "complete" if available else "unavailable",
                    "Services A": len(sets[a]) if available else None, "Services B": len(sets[b]) if available else None,
                    "Shared services": len(sets[a] & sets[b]) if available else None,
                    "Union services": len(sets[a] | sets[b]) if available else None,
                    "Only A": len(sets[a] - sets[b]) if available else None,
                    "Only B": len(sets[b] - sets[a]) if available else None,
                    "Metric clusters": clusters, "Catalogue version": version,
                })
    return metrics, views
