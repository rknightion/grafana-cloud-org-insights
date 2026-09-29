"""Scrape intervals declared inside Fleet Management pipeline contents (GCI-0046).

A pipeline that scrapes faster than the organisation's default raises data points per minute, and a high
DPM stack bills across the whole organisation. Fleet Management has no interval field on the pipeline
record: the interval lives in the pipeline body, as an Alloy `scrape_interval = "15s"` attribute or an
OTel prometheus receiver `scrape_interval: 15s` key. So this module reads the body and returns numbers.

**The body is parsed in memory and dropped.** Only durations in seconds and counts leave this module. The
contents are the customer's own configuration, and `fleet.pipeline_record` still never retains them.

**A value that is not a literal is UNPARSED, never guessed.** `scrape_interval = argument.x.value` or
`env("INTERVAL")` could be anything, so it is counted and published as unparsed rather than assumed to be
the default. A parser that quietly assumed the default would report exactly the fast pipelines this
exists to find as compliant.

**An omitted interval is the component's documented default**, which is 60s for Alloy's
`prometheus.scrape` and 1m for the OTel prometheus receiver's `global.scrape_interval`. Omission is the
common case, and treating it as "no interval" would make a stack full of default scrapes look unmeasured.

OTel pull receivers other than prometheus (hostmetrics, kubeletstats, database receivers) sample on
`collection_interval` instead, which sets DPM the same way (GCI-0047). Only an EXPLICIT value is read:
the default differs per receiver (1m for most, 10s for some), and guessing it would invent a finding or
hide one. Each pipeline records which attributes its intervals came from.

Deliberately out of scope: `pyroscope.scrape` (profiles do not add DPM) and local configuration outside
Fleet Management, which this platform cannot read.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Alloy's prometheus.scrape and the OTel prometheus receiver both default to one minute.
IMPLICIT_DEFAULT_SECONDS = 60.0

# Distinct intervals kept per pipeline. A pipeline with more distinct intervals than this is unusual,
# and the shortest one, which is what drives DPM, is always kept because the list is sorted ascending.
MAX_INTERVALS = 12

# `manual_scrape_interval` is not a Fleet Management or Alloy field today. It is matched wherever it
# appears so a template that introduces the name is read rather than missed.
_ALLOY_ATTRIBUTES = ("scrape_interval", "default_scrape_interval", "manual_scrape_interval")
_ALLOY_ASSIGN = re.compile(
    r"(?<![\w.])(" + "|".join(_ALLOY_ATTRIBUTES) + r")\s*=(?!=)\s*"
)
_ALLOY_HEADER = re.compile(r"([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*(?:\"[^\"\n]*\")?\s*$")

# Go and Prometheus duration units, longest suffix first so `ms` is not read as `m`.
_UNITS = (("ms", 0.001), ("us", 1e-6), ("µs", 1e-6), ("ns", 1e-9), ("h", 3600.0), ("m", 60.0),
          ("s", 1.0), ("d", 86400.0), ("w", 604800.0), ("y", 31536000.0))
_DURATION = re.compile(r"^(?:\d+(?:\.\d+)?(?:ms|us|µs|ns|h|m|s|d|w|y))+$")
_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|us|µs|ns|h|m|s|d|w|y)")


def parse_duration(text: Any) -> float | None:
    """Seconds for a Go or Prometheus duration string, or None when it is not one.

    Zero is rejected: a zero interval is not a real scrape cadence, and publishing it would divide by
    zero in every DPM factor downstream.
    """
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not _DURATION.fullmatch(value):
        return None
    unit = dict(_UNITS)
    seconds = sum(float(n) * unit[u] for n, u in _PART.findall(value))
    return seconds if seconds > 0 else None


def _mask_alloy(contents: str) -> tuple[str, list[tuple[int, int]]]:
    """Blank comments and string bodies to spaces, keeping every offset, and list the string spans.

    Structure (braces, attribute names) is found on the masked text so a `{` or a `scrape_interval`
    inside a string or a comment can never be mistaken for configuration. Values are read back from the
    original text at the same offset.
    """
    out = list(contents)
    strings: list[tuple[int, int]] = []
    i, n = 0, len(contents)
    while i < n:
        ch = contents[i]
        if ch == "/" and i + 1 < n and contents[i + 1] == "/":
            end = contents.find("\n", i)
            end = n if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
        elif ch == "/" and i + 1 < n and contents[i + 1] == "*":
            end = contents.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out[i:end] = [c if c == "\n" else " " for c in contents[i:end]]
            i = end
        elif ch in "\"`":
            j = i + 1
            while j < n and contents[j] != ch:
                j += 2 if ch == "\"" and contents[j] == "\\" else 1
            end = min(j + 1, n)
            strings.append((i, end))
            out[i + 1:end - 1] = " " * max(0, end - 1 - (i + 1))
            i = end
        else:
            i += 1
    return "".join(out), strings


def _alloy_blocks(masked: str) -> list[tuple[int, int, str]]:
    """Every brace pair as (open, close, header). The header is the text before `{` on its line."""
    blocks: list[tuple[int, int, str]] = []
    stack: list[tuple[int, str]] = []
    for i, ch in enumerate(masked):
        if ch == "{":
            line_start = masked.rfind("\n", 0, i) + 1
            header = masked[line_start:i]
            header = re.split(r"[{}]", header)[-1].strip()
            stack.append((i, header))
        elif ch == "}" and stack:
            start, header = stack.pop()
            blocks.append((start, i, header))
    for start, header in stack:  # unbalanced: close at end rather than drop the block
        blocks.append((start, len(masked), header))
    return blocks


def _component(blocks: list[tuple[int, int, str]], pos: int) -> str | None:
    """The innermost dotted component name (`prometheus.scrape`) whose block encloses `pos`."""
    best: tuple[int, str] | None = None
    for start, end, header in blocks:
        if start < pos < end:
            m = _ALLOY_HEADER.search(header)
            if m and (best is None or start > best[0]):
                best = (start, m.group(1))
    return best[1] if best else None


def alloy_intervals(contents: str) -> tuple[list[float], int]:
    """(interval seconds, unparsed count) for one Alloy configuration."""
    masked, strings = _mask_alloy(contents)
    blocks = _alloy_blocks(masked)
    string_at = {start: end for start, end in strings}
    intervals: list[float] = []
    unparsed = 0
    explicit_blocks: set[int] = set()
    for m in _ALLOY_ASSIGN.finditer(masked):
        name, pos = m.group(1), m.end()
        component = _component(blocks, m.start())
        if name != "manual_scrape_interval" and not (component or "").startswith("prometheus."):
            continue  # pyroscope.scrape and friends do not add DPM
        end = string_at.get(pos)
        seconds = parse_duration(contents[pos + 1:end - 1]) if end else None
        if seconds is None:
            unparsed += 1
        else:
            intervals.append(seconds)
        for start, stop, header in blocks:
            if start < m.start() < stop and header.startswith("prometheus.scrape"):
                explicit_blocks.add(start)
    for start, _stop, header in blocks:
        m = _ALLOY_HEADER.search(header)
        if m and m.group(1) == "prometheus.scrape" and start not in explicit_blocks:
            intervals.append(IMPLICIT_DEFAULT_SECONDS)
    return intervals, unparsed


# --- OTel YAML --------------------------------------------------------------------------------------
#
# The collector is stdlib-only, so this is a small block-style YAML reader, not a YAML implementation.
# It understands what collector configs use: nested mappings, `- ` sequences, scalars and inline
# `[a, b]` lists. Anything else (anchors, multi-line scalars) becomes a string and so cannot produce a
# wrong interval, only an unparsed one.


def _scalar(text: str) -> Any:
    value = text.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [_scalar(v) for v in value[1:-1].split(",") if v.strip()]
    return value


def _yaml_lines(contents: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in contents.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped in {"---", "..."}:
            continue
        lines.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    return lines


def _parse_yaml(lines: list[tuple[int, str]], i: int, indent: int) -> tuple[Any, int]:
    if i < len(lines) and lines[i][1].startswith("- ") or (i < len(lines) and lines[i][1] == "-"):
        seq: list[Any] = []
        item_indent = lines[i][0]
        while i < len(lines) and lines[i][0] == item_indent and (
                lines[i][1].startswith("- ") or lines[i][1] == "-"):
            rest = lines[i][1][1:].lstrip()
            if not rest:
                value, i = _parse_yaml(lines, i + 1, item_indent + 1)
                seq.append(value)
                continue
            # `- key: value` opens a mapping whose further keys sit at the dash's content column.
            content_indent = item_indent + (len(lines[i][1]) - len(rest))
            lines[i] = (content_indent, rest)
            if ":" in rest and not rest.startswith(("\"", "'")):
                value, i = _parse_yaml(lines, i, content_indent)
            else:
                value, i = _scalar(rest), i + 1
            seq.append(value)
        return seq, i
    mapping: dict[str, Any] = {}
    block_indent = lines[i][0] if i < len(lines) else indent
    while i < len(lines) and lines[i][0] == block_indent and not lines[i][1].startswith("- "):
        text = lines[i][1]
        key, sep, rest = text.partition(":")
        if not sep:
            i += 1
            continue
        key = _scalar(key)
        if rest.strip() and not rest.strip().startswith("#"):
            mapping[str(key)] = _scalar(rest)
            i += 1
        elif i + 1 < len(lines) and (lines[i + 1][0] > block_indent or (
                lines[i + 1][0] == block_indent and lines[i + 1][1].startswith("- "))):
            mapping[str(key)], i = _parse_yaml(lines, i + 1, block_indent + 1)
        else:
            mapping[str(key)] = None
            i += 1
    return mapping, i


def parse_yaml(contents: str) -> Any:
    lines = _yaml_lines(contents)
    if not lines:
        return {}
    value, _ = _parse_yaml(lines, 0, 0)
    return value


def _receivers_in_use(doc: dict[str, Any]) -> set[str] | None:
    """Receiver names wired into a service pipeline, or None when the config has no service section.

    An unwired receiver scrapes nothing. A fragment with no `service` section is read in full, because
    leaving its receivers out would hide them rather than prove them idle.
    """
    service = doc.get("service")
    if not isinstance(service, dict) or not isinstance(service.get("pipelines"), dict):
        return None
    used: set[str] = set()
    for pipeline in service["pipelines"].values():
        receivers = pipeline.get("receivers") if isinstance(pipeline, dict) else None
        if isinstance(receivers, list):
            used.update(str(r) for r in receivers)
    return used


def _interval(value: Any) -> float | None | bool:
    """Seconds, None when absent, False when present but not a literal duration."""
    if value is None:
        return None
    seconds = parse_duration(value)
    return False if seconds is None else seconds


def _otel_doc(contents: str) -> dict[str, Any] | None:
    try:
        doc = parse_yaml(contents)
    except (IndexError, ValueError, RecursionError):
        return None
    return doc if isinstance(doc, dict) else None


def _wired_receivers(doc: dict[str, Any]) -> list[tuple[str, Any]]:
    in_use = _receivers_in_use(doc)
    receivers = doc.get("receivers")
    return [(str(name), receiver)
            for name, receiver in (receivers.items() if isinstance(receivers, dict) else ())
            if in_use is None or str(name) in in_use]


def otel_collection_intervals(contents: str) -> tuple[list[float], int]:
    """(explicit `collection_interval` seconds, unparsed count) on wired non-prometheus receivers."""
    doc = _otel_doc(contents)
    if doc is None:
        return [], len(re.findall(r"(?m)^\s*collection_interval\s*:", contents))
    intervals: list[float] = []
    unparsed = 0
    for name, receiver in _wired_receivers(doc):
        if name.split("/", 1)[0] == "prometheus" or not isinstance(receiver, dict):
            continue
        value = _interval(receiver.get("collection_interval"))
        if value is False:
            unparsed += 1
        elif value is not None:
            intervals.append(value)
    return intervals, unparsed


def otel_intervals(contents: str) -> tuple[list[float], int]:
    """(interval seconds, unparsed count) for one OTel collector's prometheus receivers."""
    doc = _otel_doc(contents)
    if doc is None:
        # Unreadable structure: every interval key present is unknown, not absent.
        return [], len(re.findall(r"(?m)^\s*(?:- )?scrape_interval\s*:", contents))
    intervals: list[float] = []
    unparsed = 0
    for name, receiver in _wired_receivers(doc):
        if name.split("/", 1)[0] != "prometheus":
            continue
        config = (receiver or {}).get("config") if isinstance(receiver, dict) else None
        config = config if isinstance(config, dict) else {}
        glob = config.get("global") if isinstance(config.get("global"), dict) else {}
        default = _interval(glob.get("scrape_interval"))
        if default is False:
            unparsed += 1
            default = None
        jobs = config.get("scrape_configs")
        jobs = [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []
        for job in jobs:
            own = _interval(job.get("scrape_interval"))
            if own is False:
                unparsed += 1
            else:
                intervals.append(own if own is not None else (default or IMPLICIT_DEFAULT_SECONDS))
        if not jobs:
            # Scrape configs come from elsewhere (a target allocator, a file). The global interval is
            # still what they inherit.
            intervals.append(default or IMPLICIT_DEFAULT_SECONDS)
    return intervals, unparsed


def summarise(contents: Any, config_type: Any) -> dict[str, Any]:
    """The bounded per-pipeline record: distinct intervals, the shortest, and the unparsed count.

    The `scrape_*` keys predate GCI-0047 and keep their names so hydrated payloads stay comparable; on
    an OTel pipeline they now also carry `collection_interval` values, and `interval_attributes` says
    which attributes contributed (a value or an unparsed expression).
    """
    if not isinstance(contents, str) or not contents.strip():
        return {"scrape_intervals": [], "scrape_interval_min_seconds": None,
                "scrape_intervals_unparsed": 0, "interval_attributes": []}
    if str(config_type or "").upper().endswith("OTEL"):
        parts = {"scrape_interval": otel_intervals(contents),
                 "collection_interval": otel_collection_intervals(contents)}
    else:
        parts = {"scrape_interval": alloy_intervals(contents)}
    found = [v for values, _ in parts.values() for v in values]
    unparsed = sum(n for _, n in parts.values())
    distinct = sorted(set(found))
    return {
        "scrape_intervals": distinct[:MAX_INTERVALS],
        "scrape_interval_min_seconds": distinct[0] if distinct else None,
        "scrape_intervals_unparsed": unparsed,
        "interval_attributes": sorted(name for name, (values, n) in parts.items() if values or n),
    }


def format_seconds(values: Iterable[float]) -> str:
    """`15s, 1m` style, for a table cell."""
    def one(v: float) -> str:
        if v >= 60 and v % 60 == 0:
            return f"{int(v // 60)}m"
        return f"{v:g}s"
    return ", ".join(one(v) for v in values)
