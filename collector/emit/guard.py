"""Label-cardinality guard - a hard gate in the emit path (SPEC §5.3, §10.3, PLAN 5.2).

An unbounded label is an **error**, not a warning.

**Never argue this against the org total - that is the wrong denominator and it always flatters.** Every
series lands on ONE stack, so the honest comparison is to that stack's own series count. On the reference
estate the same footprint reads as +0.012% of the org and as a double-digit percentage increase on the
stack carrying it, a gap of roughly 2,000x. Since many orgs email each stack owner a monthly cost report,
the owner sees the second number. `collector/emit/budget.py` owns the figure and the ceiling; this module
enforces the label discipline the budget assumes.

`stack` is allowed because the estate is a closed set and it is the primary key everything is sliced by.
Metric names, dashboard uids, user logins, rule names and version strings are not - they go to Loki or S3.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

# Label keys any metric may carry. Adding to this list is a deliberate cardinality decision.
ALLOWED_LABELS = frozenset({
    "stack",      # 271 values, the primary key
    "region",     # 8
    "cluster",    # 10
    "tier",       # 4
    "reason",     # closed failure vocabulary
    "role",       # admin/editor/viewer
    "signal",     # metrics/logs/traces/profiles/alerts/grafana
    "status",     # active/paused/total
    "severity",
    "kind",
    "version",    # the maturity-rubric version, NOT a Grafana build string
    "dimension",  # 9, the maturity RUBRIC keys - a closed set defined in code, not from the estate
    "input",      # 4, emit/hydrate.py INPUT_OWNER - a closed set defined in code
    # Assistant's own chat taxonomy, and ONLY on the estate-wide rollup that carries no `stack` label
    # (pillars/ai.py). Observed 2026-08-20: 6 categories x 6 surfaces in 21 real combinations, declared
    # at 8 x 8. Neither value is tenant-authored, so the set is bounded by the product, and
    # `gcinsight_ai_estate_category_combos` makes any expansion visible. The per-stack cross product
    # would be 273 x 21 and is deliberately a view (`ai_category_surface`) instead.
    "category",   # Dashboard / Investigate / Learn / Observe / Other / Errors
    "surface",    # web / automation / a2a / cli / slack / lodestone
})

# Values that betray an unbounded dimension having leaked into a label.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_LOOKS_LIKE_BUILD = re.compile(r"^\d+\.\d+\.\d+-\d{6,}")
MAX_LABEL_VALUE_LEN = 64


class UnboundedLabel(ValueError):
    """A metric tried to carry a label that would blow the series budget."""


def check(name: str, labels: Mapping[str, str]) -> None:
    for key, value in labels.items():
        if key not in ALLOWED_LABELS:
            raise UnboundedLabel(
                f"{name}: label key {key!r} is not in the allow-list. If it is genuinely bounded, add "
                f"it to ALLOWED_LABELS deliberately; otherwise put it in Loki or S3."
            )
        text = str(value)
        if len(text) > MAX_LABEL_VALUE_LEN:
            raise UnboundedLabel(f"{name}: label {key!r} value is {len(text)} chars - unbounded")
        if _EMAIL.search(text):
            raise UnboundedLabel(f"{name}: label {key!r} looks like an email address")
        if _LOOKS_LIKE_BUILD.match(text):
            raise UnboundedLabel(
                f"{name}: label {key!r} looks like a Grafana build string - those churn on every "
                f"upgrade. Emit a drift boolean instead."
            )


def check_all(metrics: Iterable[tuple[str, Mapping[str, str], float]]) -> int:
    """Gate an entire metric batch. Raises on the first offender; returns the count checked."""
    n = 0
    for name, labels, _ in metrics:
        check(name, labels)
        n += 1
    return n


class DuplicateSeries(ValueError):
    """Two pillars emitted the same (name, labels). remote_write would take whichever arrived last."""


def check_no_duplicates(metrics: Iterable[tuple[str, Mapping[str, str], float]]) -> int:
    """Refuse a batch containing the same series twice.

    Becomes possible the moment more than one pillar runs: Pillar A owns the inventory-derived estate
    rollups, and a later pillar recomputing one of them would silently publish whichever sample the
    remote_write encoder emitted last. That is a wrong number on a leadership panel, with no error.
    """
    seen: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    for name, labels, value in metrics:
        key = (name, tuple(sorted(labels.items())))
        if key in seen:
            raise DuplicateSeries(
                f"{name}{dict(key[1])} emitted twice (values {seen[key]} and {value}). One pillar owns "
                f"each series - see collector/emit/budget.py CATALOGUE for which."
            )
        seen[key] = value
    return len(seen)


def series_count(metrics: Iterable[tuple[str, Mapping[str, str], float]]) -> dict[str, int]:
    """Series per metric name - the input to the budget table (PLAN 0.12) and acceptance §10.2."""
    out: dict[str, int] = {}
    for name, _, _ in metrics:
        out[name] = out.get(name, 0) + 1
    return out
