"""S3-only daily identity-label risk finding and explicitly partial denominators.

Raw matches are approved for this view and private hydration input only. These views must not enter
Loki findings or business metrics. Compose always iterates live inventory, never the input map.
"""
from __future__ import annotations

import json
from typing import Any

S3_ONLY_VIEWS = frozenset({"risk_label_hygiene", "risk_label_hygiene_coverage"})
VIEW_SCHEMAS = {
    "risk_label_hygiene": {
        " Stack": "string", "Signal": "string", "Scope": "string", "Label name": "string",
        "Class": "string", "Confidence": "string", "Evidence": "string",
        "Sampled values": "number", "Matched values": "number", "Retained values": "number",
        "Raw matched values": "string", "Coverage": "string", "Pattern version": "string",
        "Window start (s)": "number", "Window end (s)": "number",
    },
    "risk_label_hygiene_coverage": {
        " Stack": "string", "Signal": "string", "Coverage": "string", "Reason": "string",
        "Limit flags": "string", "Value failure reasons": "string",
        "Keys returned": "number", "Keys selected": "number", "Keys sampled": "number", "Values sampled": "number",
        "Value reads failed": "number", "Scannable stacks": "number", "Measured stacks (names)": "number",
        "Value-read stacks": "number",
        "Key cap": "number", "Value cap": "number", "Match cap": "number",
        "Response byte cap": "number", "Retained byte cap": "number",
        "Pattern version": "string", "Window start (s)": "number", "Window end (s)": "number",
    },
}
# Dashboard schemas use ordered (column, type) pairs, including for an empty finding set.
VIEW_SCHEMAS = {name: tuple(schema.items()) for name, schema in VIEW_SCHEMAS.items()}


def build(stacks: list[dict[str, Any]], label_risk: dict[str, Any] | None = None):
    if label_risk is None:
        return [], {}
    live = [s for s in stacks if str(s.get("status", "")).lower() != "paused"]
    findings, coverage = [], []
    for signal in ("metrics", "logs", "traces", "profiles"):
        measured = sum((label_risk.get(str(s["slug"])) or {}).get("signals", {}).get(
            signal, {}).get("keys_returned") is not None for s in live)
        value_measured = sum(bool((label_risk.get(str(s["slug"])) or {}).get("signals", {}).get(
            signal, {}).get("keys_sampled")) for s in live)
        for stack in live:
            slug = str(stack["slug"])
            record = label_risk.get(slug) or {}
            summary = (record.get("signals") or {}).get(signal) or {}
            bounds = record.get("bounds") or {}
            coverage.append({
                " Stack": slug, "Signal": signal, "Coverage": summary.get("state", "unavailable"),
                "Reason": summary.get("reason", "not_measured"),
                "Limit flags": ", ".join(k for k in ("server_cap", "local_key_cap", "local_value_cap",
                    "local_match_cap", "unexamined_large_value", "unexamined_large_key") if summary.get(k)),
                "Value failure reasons": json.dumps(summary.get("value_failure_reasons") or {}, sort_keys=True),
                "Keys returned": summary.get("keys_returned"), "Keys selected": summary.get("keys_selected"),
                "Keys sampled": summary.get("keys_sampled"),
                "Values sampled": summary.get("values_sampled"),
                "Value reads failed": summary.get("value_reads_failed"),
                "Scannable stacks": len(live), "Measured stacks (names)": measured,
                "Value-read stacks": value_measured,
                "Key cap": bounds.get("keys"), "Value cap": bounds.get("values"),
                "Match cap": bounds.get("matches"), "Response byte cap": bounds.get("response_bytes"),
                "Retained byte cap": bounds.get("retained_bytes"),
                "Pattern version": record.get("pattern_version"),
                "Window start (s)": record.get("window_start"), "Window end (s)": record.get("window_end"),
            })
            for row in record.get("findings") or []:
                if row.get("signal") != signal:
                    continue
                findings.append({
                    " Stack": slug, "Signal": signal, "Scope": row["scope"], "Label name": row["key"],
                    "Class": row["class"], "Confidence": row["confidence"], "Evidence": row["evidence"],
                    "Sampled values": row["sampled_count"], "Matched values": row["matched_count"],
                    "Retained values": row["retained_count"],
                    "Raw matched values": json.dumps(row["values"], ensure_ascii=False),
                    "Coverage": summary.get("state", "unavailable"),
                    "Pattern version": row["pattern_version"],
                    "Window start (s)": record.get("window_start"), "Window end (s)": record.get("window_end"),
                })
    return [], {"risk_label_hygiene": findings, "risk_label_hygiene_coverage": coverage}


def diagnostic_scan(scan: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic --out is not an approved raw-match store. Keep the S3 envelope untouched."""
    return {**scan, "data": {k: v for k, v in scan.get("data", {}).items() if k != "label_risk"}}
