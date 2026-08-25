"""Configurable, identity-free service observability completeness scoring."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

COMPONENTS = ("metrics", "logs", "traces", "profiles", "dashboard", "alert", "slo")
VERSION = "1"


class InvalidWeights(ValueError):
    """The deployment supplied a score configuration that cannot be interpreted safely."""


def parse_weights(raw: str) -> dict[str, float]:
    """Parse a partial JSON override over the equal-weight default."""
    weights = {component: 1.0 for component in COMPONENTS}
    if not raw.strip():
        return weights
    try:
        supplied = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidWeights(f"coverage weights are not valid JSON: {exc.msg}") from exc
    if not isinstance(supplied, Mapping):
        raise InvalidWeights("coverage weights must be a JSON object")
    unknown = sorted(set(supplied) - set(COMPONENTS))
    if unknown:
        raise InvalidWeights(f"coverage weights contain unknown component(s): {', '.join(unknown)}")
    for component, value in supplied.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidWeights(f"coverage weight {component!r} must be a number")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise InvalidWeights(f"coverage weight {component!r} must be finite and non-negative")
        weights[component] = number
    if sum(weights.values()) <= 0:
        raise InvalidWeights("at least one coverage weight must be above zero")
    return weights


def calculate(
    states: Mapping[str, Any], weights: Mapping[str, float],
) -> tuple[float, float, float] | None:
    """Return numerator, maximum and percentage; unknown component state withholds the score."""
    if any(not isinstance(states.get(component), bool) for component in COMPONENTS):
        return None
    maximum = sum(weights[component] for component in COMPONENTS)
    if maximum <= 0:
        raise InvalidWeights("at least one coverage weight must be above zero")
    numerator = sum(weights[component] for component in COMPONENTS if states[component])
    return numerator, maximum, round(numerator / maximum * 100, 1)
