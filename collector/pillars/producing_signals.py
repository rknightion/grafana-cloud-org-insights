"""Point-in-time producing signals from documented Grafana Cloud usage metrics.

These are backend observations, never evidence that a person opened a Grafana UI.
The source's 24-hour maximum catches intermittent production. It is not a daily total or
an average rate. A missing series is unknown; a returned zero is a measured zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from collector.sources import capability_adoption

VIEW = "coverage_producing_signals"
WINDOW = capability_adoption.WINDOW


@dataclass(frozen=True)
class Signal:
    title: str
    unit: str
    window: str
    meaning: str
    source_url: str


SIGNALS = {
    "metrics": Signal(
        "Metrics", "active series", WINDOW,
        "A positive active-series count was observed in the Metrics backend during the window.",
        "https://grafana.com/docs/grafana-cloud/platform/cost-management-and-billing/"
        "manage-invoices/understand-your-invoice/reconcile-invoices/",
    ),
    "traces": Signal(
        "Traces", "bytes/second", WINDOW,
        "A positive rate of bytes received by Cloud Traces was observed during the window.",
        "https://grafana.com/docs/grafana-cloud/platform/pricing-and-usage/usage-limits/",
    ),
}

SCHEMA = (
    ("Stack", "string"), ("Signal", "string"), ("State", "string"),
    ("Value", "number"), ("Unit", "string"), ("Window", "string"),
    ("Window start", "string"), ("Window end", "string"),
    ("Nonzero means", "string"),
)


def build(stacks: Sequence[Mapping[str, Any]], usage: Mapping[str, Any] | None):
    if not usage or not usage.get("available"):
        return [], {}
    values = usage.get("values") or {}
    rows = []
    for stack in stacks:
        if stack.get("status") == "paused":
            continue
        slug = str(stack.get("slug") or "")
        stack_id = str(stack.get("id") or "")
        if not slug or not stack_id:
            continue
        for key, signal in SIGNALS.items():
            value_map = values.get(key) or {}
            value = value_map.get(stack_id) if isinstance(value_map, Mapping) else None
            state = "missing" if value is None else ("producing" if value > 0 else "measured zero")
            rows.append({
                "Stack": slug, "Signal": signal.title, "State": state,
                "Value": value, "Unit": signal.unit, "Window": signal.window,
                "Window start": usage.get("window_start"),
                "Window end": usage.get("window_end"),
                "Nonzero means": signal.meaning,
            })
    return [], {VIEW: rows} if rows else {}
