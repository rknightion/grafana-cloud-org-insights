"""Key-only classification for unbounded Mimir label-name findings.

The data-plane cardinality endpoint returns label names and their cardinality counts. This module
classifies only the name (the label key). It never accepts, reads or retains a label value. The count in
the endpoint response is a numeric measurement of the name's cardinality, not a label value.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from collections.abc import Iterable, Mapping
from typing import Any


PATTERN_PATH = pathlib.Path(__file__).with_name("label_patterns.json")
# Alias names make the artifact boundary explicit to callers that use the registry vocabulary.
PATTERNS_PATH = PATTERN_PATH
LABEL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CLASS_UNBOUNDED = "unbounded"
CONFIDENCE_HIGH = "high"
CONFIDENCE_POSSIBLE = "possible"
CONFIDENCE_TIERS = (CONFIDENCE_HIGH, CONFIDENCE_POSSIBLE)
# Metric labels use a distinct, closed vocabulary so the metric says exactly which confidence bucket
# it represents without carrying a label name.
METRIC_KIND = {
    CONFIDENCE_HIGH: "high_confidence",
    CONFIDENCE_POSSIBLE: "possible",
}
SIGNAL = "metrics"

# `dataplane.cardinality()` calls Mimir with this default. The source does not need to retain a second
# copy of the request parameter: every row is explicitly disclosed as being from this top-N window by
# the risk pillar using the same constant.
TOP_N = 20


class PatternError(ValueError):
    """The versioned generic pattern artifact or a cardinality row is unsafe to classify."""


@dataclasses.dataclass(frozen=True)
class PatternSet:
    """Validated exact label-name patterns and their confidence tiers."""

    version: int
    high: frozenset[str]
    possible: frozenset[str]

    @property
    def confidence_by_name(self) -> dict[str, str]:
        return {
            **{name: CONFIDENCE_HIGH for name in self.high},
            **{name: CONFIDENCE_POSSIBLE for name in self.possible},
        }

    @property
    def patterns(self) -> frozenset[str]:
        return self.high | self.possible


def _version(value: Any) -> int:
    if isinstance(value, bool):
        raise PatternError("pattern version must be a positive integer")
    if isinstance(value, int) and value >= 1:
        return value
    # Accepting the registry's string representation keeps the loader compatible with the existing
    # versioned-artifact convention while the shipped pattern file remains a simple integer version.
    if isinstance(value, str) and value.isdigit() and int(value) >= 1:
        return int(value)
    raise PatternError("pattern version must be a positive integer")


def _tier(raw: Any, name: str) -> frozenset[str]:
    if not isinstance(raw, list) or not raw:
        raise PatternError(f"unbounded.{name} must be a non-empty list")
    if any(
        not isinstance(pattern, str)
        or not pattern
        or not LABEL_NAME_RE.fullmatch(pattern)
        or len(pattern) == 1
        for pattern in raw
    ):
        raise PatternError(f"unbounded.{name} must contain non-singleton label names")
    if len(raw) != len(set(raw)):
        raise PatternError(f"unbounded.{name} must contain unique label names")
    return frozenset(raw)


def load(path: pathlib.Path = PATTERN_PATH) -> PatternSet:
    """Read and validate the generic, versioned label-name pattern artifact."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise PatternError("label pattern data must contain valid readable JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"version", "unbounded"}:
        raise PatternError("label pattern data must contain only version and unbounded")
    version = _version(raw["version"])
    unbounded = raw["unbounded"]
    if not isinstance(unbounded, dict) or set(unbounded) != set(CONFIDENCE_TIERS):
        raise PatternError("unbounded must contain exactly high and possible tiers")
    high = _tier(unbounded[CONFIDENCE_HIGH], CONFIDENCE_HIGH)
    possible = _tier(unbounded[CONFIDENCE_POSSIBLE], CONFIDENCE_POSSIBLE)
    overlap = high & possible
    if overlap:
        raise PatternError(f"label names appear in more than one confidence tier: {sorted(overlap)!r}")
    return PatternSet(version=version, high=high, possible=possible)


PATTERNS = load()
PATTERN_SET = PATTERNS
REGISTRY = PATTERNS
PATTERN_VERSION = PATTERNS.version


def classify(label_name: Any, patterns: PatternSet = PATTERNS) -> tuple[str, str] | None:
    """Return ``(class, confidence)`` for one exact label key, or ``None``.

    Matching is intentionally case-sensitive and does not strip, lowercase, split or otherwise
    transform the key. That makes ``trace_id_extra`` and ``Trace_id`` safe non-matches.
    """
    if not isinstance(label_name, str) or not label_name:
        return None
    confidence = patterns.confidence_by_name.get(label_name)
    return (CLASS_UNBOUNDED, confidence) if confidence is not None else None


classify_label = classify


def _cardinality_count(value: Any) -> int:
    """Validate the numeric cardinality count without accepting a raw label value."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PatternError("a matched label name must carry a non-negative integer value count")
    return value


def classify_rows(
    top_labels: Iterable[Mapping[str, Any]], patterns: PatternSet = PATTERNS
) -> list[dict[str, Any]]:
    """Classify matching rows from Mimir's ``top_labels`` payload.

    The only fields read from each row are ``label`` (the key) and ``values`` (the numeric cardinality
    count already produced by the source). A malformed row makes the enclosing read unsafe to report;
    callers should mark that stack unreadable rather than turning it into a clean zero.
    """
    if isinstance(top_labels, (str, bytes)):
        raise PatternError("top_labels must be an iterable of row objects")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        rows = iter(top_labels)
    except TypeError as exc:
        raise PatternError("top_labels must be an iterable of row objects") from exc
    for row in rows:
        if not isinstance(row, Mapping):
            raise PatternError("each top_labels entry must be an object")
        label_name = row.get("label")
        if not isinstance(label_name, str) or not label_name:
            raise PatternError("each top_labels entry must carry a non-empty label name")
        classification = classify(label_name, patterns)
        if classification is None:
            continue
        if label_name in seen:
            raise PatternError(f"duplicate label name in top_labels: {label_name!r}")
        seen.add(label_name)
        class_name, confidence = classification
        result.append({
            "label": label_name,
            "values": _cardinality_count(row.get("values")),
            "class": class_name,
            "confidence": confidence,
        })
    return result


classify_top_labels = classify_rows
