"""Versioned, bounded technology vocabulary for metric-sentinel classification."""

from __future__ import annotations

import dataclasses
import json
import pathlib
from collections.abc import Iterable
from typing import Any


REGISTRY_PATH = pathlib.Path(__file__).with_name("technology-registry.json")


class RegistryError(ValueError):
    """The registry artifact is malformed or unsafe to classify with."""


class AmbiguousMatch(RegistryError):
    """One metric name matched more than one technology."""


@dataclasses.dataclass(frozen=True)
class Technology:
    key: str
    name: str
    exact: str | None = None
    pattern_prefix: str | None = None
    pattern_suffix: str | None = None

    def matches(self, metric_name: str) -> bool:
        if self.exact is not None:
            return metric_name == self.exact
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
    exact_sentinels: set[str] = set()
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
        if kind not in {"exact", "pattern"}:
            raise RegistryError(f"technology {key} has an invalid matcher")
        if kind == "exact":
            if not isinstance(value, str) or not value:
                raise RegistryError(f"technology {key} exact sentinel must be a non-empty string")
            if value in exact_sentinels:
                raise RegistryError(f"exact sentinel {value!r} is claimed twice")
            exact_sentinels.add(value)
            entry = Technology(key=key, name=name, exact=value)
        else:
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
        keys.add(key)
        entries.append(entry)
    return Registry(version=version, entries=tuple(entries))


REGISTRY = load()


def classify(metric_names: Iterable[str], registry: Registry = REGISTRY) -> dict[str, Any]:
    """Classify a measured metric-name inventory and publish its unmatched remainder.

    Callers pass this only after a successful label read. An empty iterable is therefore a measured
    absence and honestly returns zero counts; a failed read never calls this function and produces no
    row in the coverage pillar.
    """
    names = sorted({name for name in metric_names if isinstance(name, str) and name})
    matched_by_key: dict[str, list[str]] = {entry.key: [] for entry in registry.entries}
    unmatched: list[str] = []
    for metric_name in names:
        matches = [entry for entry in registry.entries if entry.matches(metric_name)]
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
