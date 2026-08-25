"""Versioned, bounded technology vocabulary for metric-sentinel classification."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from collections.abc import Iterable
from typing import Any


REGISTRY_PATH = pathlib.Path(__file__).with_name("technology-registry.json")
PROM_METRIC_RE = re.compile(r"^[A-Za-z_:][A-Za-z0-9_:]*$")
PROM_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RegistryError(ValueError):
    """The registry artifact is malformed or unsafe to classify with."""


class AmbiguousMatch(RegistryError):
    """One metric name matched more than one technology."""


@dataclasses.dataclass(frozen=True)
class Technology:
    key: str
    name: str
    exact: str | None = None
    any_of: tuple[str, ...] = ()
    pattern_prefix: str | None = None
    pattern_suffix: str | None = None
    label_metric: str | None = None
    label_key: str | None = None
    label_values: frozenset[str] | None = None

    def matches(self, metric_name: str) -> bool:
        if self.exact is not None:
            return metric_name == self.exact
        if self.any_of:
            return metric_name in self.any_of
        if self.label_metric is not None:
            return False
        assert self.pattern_prefix is not None and self.pattern_suffix is not None
        return (
            metric_name.startswith(self.pattern_prefix)
            and metric_name.endswith(self.pattern_suffix)
            and len(metric_name) > len(self.pattern_prefix) + len(self.pattern_suffix)
        )


@dataclasses.dataclass(frozen=True)
class Registry:
    version: str
    entries: tuple[Technology, ...]


@dataclasses.dataclass(frozen=True)
class LabelQuery:
    metric_name: str
    label_key: str
    accepted_values: frozenset[str] | None


def load(path: pathlib.Path = REGISTRY_PATH) -> Registry:
    """Read and validate the registry data file.

    Loading is strict so a bad registry edit fails the collector at build/test time instead of quietly
    reclassifying history or allowing two technologies to claim the same exact sentinel.
    """
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RegistryError("registry must contain valid JSON") from exc
    if not isinstance(raw, dict):
        raise RegistryError("registry root must be an object")
    version = raw.get("version")
    if not isinstance(version, str) or not version.isdigit() or int(version) < 1:
        raise RegistryError("registry version must be a positive integer string")
    technologies = raw.get("technologies")
    if not isinstance(technologies, list) or not technologies:
        raise RegistryError("registry technologies must be a non-empty list")

    entries: list[Technology] = []
    keys: set[str] = set()
    claimed_name_sentinels: set[str] = set()
    claimed_label_pairs: set[tuple[str, str]] = set()
    for position, raw_entry in enumerate(technologies):
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"key", "name", "match"}:
            raise RegistryError(f"technology {position} must contain only key, name and match")
        key, name, matcher = raw_entry["key"], raw_entry["name"], raw_entry["match"]
        if not isinstance(key, str) or not key or key in keys:
            raise RegistryError(f"technology {position} has a blank or duplicate key")
        if not isinstance(name, str) or not name.strip():
            raise RegistryError(f"technology {key} has no display name")
        if not isinstance(matcher, dict) or len(matcher) != 1:
            raise RegistryError(f"technology {key} must declare exactly one matcher")
        kind, value = next(iter(matcher.items()))
        if kind not in {"exact", "pattern", "any_of", "label"}:
            raise RegistryError(f"technology {key} has an invalid matcher")
        if kind == "exact":
            if not isinstance(value, str) or not PROM_METRIC_RE.fullmatch(value):
                raise RegistryError(f"technology {key} exact sentinel must be a non-empty string")
            if value in claimed_name_sentinels:
                raise RegistryError(f"name sentinel {value!r} is claimed twice")
            claimed_name_sentinels.add(value)
            entry = Technology(key=key, name=name, exact=value)
        elif kind == "any_of":
            if (
                not isinstance(value, list) or not value
                or any(not isinstance(item, str) or not PROM_METRIC_RE.fullmatch(item)
                       for item in value)
                or len(value) != len(set(value))
            ):
                raise RegistryError(
                    f"technology {key} any_of must be a non-empty list of unique metric names"
                )
            overlap = claimed_name_sentinels.intersection(value)
            if overlap:
                raise RegistryError(f"name sentinels {sorted(overlap)!r} are claimed twice")
            claimed_name_sentinels.update(value)
            entry = Technology(key=key, name=name, any_of=tuple(value))
        elif kind == "pattern":
            if not isinstance(value, dict) or set(value) != {"prefix", "suffix"}:
                raise RegistryError(
                    f"technology {key} pattern must contain only prefix and suffix"
                )
            prefix, suffix = value["prefix"], value["suffix"]
            if not isinstance(prefix, str) or not prefix or not isinstance(suffix, str) or not suffix:
                raise RegistryError(f"technology {key} pattern bounds must be non-empty strings")
            entry = Technology(
                key=key, name=name, pattern_prefix=prefix, pattern_suffix=suffix
            )
        else:
            if not isinstance(value, dict) or not {"metric", "key"} <= set(value) or not set(
                value
            ) <= {"metric", "key", "values"}:
                raise RegistryError(
                    f"technology {key} label matcher must contain metric, key and optional values"
                )
            metric_name, label_key = value["metric"], value["key"]
            if not isinstance(metric_name, str) or not PROM_METRIC_RE.fullmatch(metric_name):
                raise RegistryError(f"technology {key} label metric must be a Prometheus metric name")
            if not isinstance(label_key, str) or not PROM_LABEL_RE.fullmatch(label_key):
                raise RegistryError(f"technology {key} label key must be a Prometheus label name")
            pair = (metric_name, label_key)
            if pair in claimed_label_pairs:
                raise RegistryError(f"label matcher {metric_name}.{label_key} is claimed twice")
            raw_values = value.get("values")
            accepted_values: frozenset[str] | None = None
            if raw_values is not None:
                if (
                    not isinstance(raw_values, list) or not raw_values
                    or any(not isinstance(item, str) or not item for item in raw_values)
                    or len(raw_values) != len(set(raw_values))
                ):
                    raise RegistryError(
                        f"technology {key} label values must be a non-empty unique string list"
                    )
                accepted_values = frozenset(raw_values)
            claimed_label_pairs.add(pair)
            entry = Technology(
                key=key, name=name, label_metric=metric_name, label_key=label_key,
                label_values=accepted_values,
            )
        keys.add(key)
        entries.append(entry)
    return Registry(version=version, entries=tuple(entries))


REGISTRY = load()


def label_queries(registry: Registry = REGISTRY) -> tuple[LabelQuery, ...]:
    """Return the bounded named-metric reads required by the registry."""
    return tuple(
        LabelQuery(entry.label_metric, entry.label_key, entry.label_values)
        for entry in registry.entries if entry.label_metric is not None and entry.label_key is not None
    )


def match_label_values(
    metric_name: str,
    label_key: str,
    values: Iterable[str],
    registry: Registry = REGISTRY,
) -> tuple[str, ...]:
    """Minimise raw label values immediately to bounded registry keys."""
    observed = {value for value in values if isinstance(value, str) and value}
    matches = []
    for entry in registry.entries:
        if entry.label_metric != metric_name or entry.label_key != label_key:
            continue
        if observed and (entry.label_values is None or observed.intersection(entry.label_values)):
            matches.append(entry.key)
    if len(matches) > 1:
        raise AmbiguousMatch(f"label {metric_name}.{label_key} matches technologies {matches}")
    return tuple(matches)


def classify(
    metric_names: Iterable[str],
    registry: Registry = REGISTRY,
    *,
    label_matches: Iterable[str] = (),
) -> dict[str, Any]:
    """Classify a measured metric-name inventory and publish its unmatched remainder.

    Callers pass this only after a successful label read. An empty iterable is therefore a measured
    absence and honestly returns zero counts; a failed read never calls this function and produces no
    row in the coverage pillar.
    """
    names = sorted({name for name in metric_names if isinstance(name, str) and name})
    matched_label_keys = {
        key for key in label_matches if isinstance(key, str) and key
    }
    entries_by_key = {entry.key: entry for entry in registry.entries}
    invalid_label_keys = {
        key for key in matched_label_keys
        if key not in entries_by_key or entries_by_key[key].label_metric is None
    }
    if invalid_label_keys:
        raise RegistryError(f"unknown label evidence keys {sorted(invalid_label_keys)!r}")
    missing_metrics = {
        entries_by_key[key].label_metric for key in matched_label_keys
        if entries_by_key[key].label_metric not in names
    }
    if missing_metrics:
        raise RegistryError(f"label evidence has no matching metric names {sorted(missing_metrics)!r}")
    matched_by_key: dict[str, list[str]] = {entry.key: [] for entry in registry.entries}
    unmatched: list[str] = []
    for metric_name in names:
        matches = [entry for entry in registry.entries if entry.matches(metric_name)]
        matches.extend(
            entry for entry in registry.entries
            if entry.key in matched_label_keys and entry.label_metric == metric_name
        )
        if len(matches) > 1:
            raise AmbiguousMatch(
                f"metric {metric_name!r} matches technologies {[entry.key for entry in matches]}"
            )
        if not matches:
            unmatched.append(metric_name)
            continue
        matched_by_key[matches[0].key].append(metric_name)

    technologies = [
        {
            "key": entry.key,
            "name": entry.name,
            "matched_metric_name_count": len(matched_by_key[entry.key]),
            "matched_metric_names": matched_by_key[entry.key],
        }
        for entry in registry.entries
        if matched_by_key[entry.key]
    ]
    matched_count = len(names) - len(unmatched)
    return {
        "registry_version": registry.version,
        "total_metric_name_count": len(names),
        "matched_metric_name_count": matched_count,
        "unmatched_metric_name_count": len(unmatched),
        "unmatched_share": len(unmatched) / len(names) if names else None,
        "technologies": technologies,
        "unmatched_metric_names": unmatched,
    }
