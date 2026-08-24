"""Fleet Management pipeline matchers, evaluated against collector attributes.

FM exposes no API for "which collectors does this pipeline target" - probed 2026-08-20, every candidate
RPC method 404s - so the count is computed here from the pipeline's `matchers` against each collector's
`attributes`. That makes it the one number in the Fleet Management set that is DERIVED rather than
reported, and it must be labelled as such wherever it renders.

The syntax is Prometheus label matchers, and two of its rules decide thousands of collectors either way:

- **Regexes are FULLY ANCHORED.** `collector.os=~"win"` does NOT match `windows`. Unanchored evaluation
  would silently inflate every count built on a regex matcher.
- **A missing label is the empty string, not a non-match.** A collector with no `platform` attribute
  therefore MATCHES `platform!="kubernetes"`. Treating absence as a non-match gives the opposite answer
  on exactly the collectors a negated matcher exists to select.

Matchers within one pipeline are ANDed. Observed in the wild on one estate: `=`, `!=` and `=~`, with
pipelines carrying pairs like `platform!="kubernetes"` AND `collector.os="darwin"`.

**Nothing here ever guesses.** A matcher that will not parse, or a regex that will not compile, raises
rather than evaluating to False - because False is indistinguishable from "genuinely matched nothing"
and would publish an undercount as a fact. `targets()` turns that into `None` for the affected pipeline
and refuses to compute the unmatched total at all.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

# Longest operator first: `!=` and `!~` both contain a character the shorter forms use, so trying `=`
# before `!=` parses `a!="b"` as label `a!`.
_OPERATORS = ("!=", "=~", "!~", "=")

# **Fleet Management accepts UNQUOTED values, and refusing them cost 17 real matchers.** Measured across
# the estate's 1,180 matchers: 17 on 4 stacks were shapes like `workloadType=daemonset` and
# `service-discovery=true`, all inside pipelines GRAFANA generated for k8s-monitoring onboarding. So the
# unquoted form is not user error, it is what the product writes, and rejecting it made the "collectors
# targeted" figure unknown on every one of those pipelines.
#
# The unquoted branch is still narrow on purpose: a value may not contain a quote (that is a half-quoted
# string, which is malformed) and may not begin with `=` or `~` (that is a mistyped operator such as
# `a==b`, where guessing equality-with-`=b` would be worse than refusing).
_LABEL = r"[A-Za-z_][A-Za-z0-9_.\-/]*"
_OP = r"!=|=~|!~|="
_MATCHER = re.compile(
    rf'^(?P<label>{_LABEL})(?P<op>{_OP})'
    rf'(?:"(?P<quoted>.*)"|(?P<bare>[^"=~][^"]*|))$'
)

# Fleet matcher values are customer-controlled. A bounded pattern prevents an unexpectedly large regex
# from consuming disproportionate compile/evaluation time during an estate-wide sweep. Normal product
# matchers are short label selectors; anything beyond this is unknown rather than guessed.
MAX_REGEX_LENGTH = 1_024


class UnparsedMatcher(ValueError):
    """A matcher this module does not understand. Never downgraded to a non-match."""


def parse(matcher: str) -> tuple[str, str, str] | None:
    """`(label, operator, value)`, or None when the string is not a matcher we understand."""
    hit = _MATCHER.match((matcher or "").strip())
    if not hit:
        return None
    quoted, bare = hit.group("quoted"), hit.group("bare")
    return hit.group("label"), hit.group("op"), quoted if quoted is not None else (bare or "")


def _regex(pattern: str) -> re.Pattern[str]:
    if len(pattern) > MAX_REGEX_LENGTH:
        raise UnparsedMatcher(
            f"regex is {len(pattern)} characters; maximum is {MAX_REGEX_LENGTH}"
        )
    try:
        # `fullmatch` at the call site rather than wrapping in ^...$ - wrapping breaks on a pattern
        # containing a top-level alternation, where `^a|b$` anchors only the first branch.
        return re.compile(pattern)
    except re.error as exc:
        raise UnparsedMatcher(f"invalid regex {pattern!r}: {exc}") from exc


def _prepare(matchers: Sequence[str]) -> tuple[tuple[str, str, str | re.Pattern[str]], ...]:
    prepared: list[tuple[str, str, str | re.Pattern[str]]] = []
    for raw in matchers or ():
        parsed = parse(raw)
        if parsed is None:
            raise UnparsedMatcher(f"cannot parse matcher {raw!r}")
        label, op, want = parsed
        prepared.append((label, op, _regex(want) if op in {"=~", "!~"} else want))
    return tuple(prepared)


def _matches_prepared(
    attributes: Mapping[str, Any],
    matchers: Sequence[tuple[str, str, str | re.Pattern[str]]],
) -> bool:
    for label, op, want in matchers:
        # Absent label == empty string. See the module docstring; this single line is the difference
        # between selecting and excluding every collector a negated matcher targets.
        have = str(attributes.get(label, "") or "")
        if op == "=":
            ok = have == want
        elif op == "!=":
            ok = have != want
        elif op == "=~":
            ok = isinstance(want, re.Pattern) and want.fullmatch(have) is not None
        else:  # "!~"
            ok = isinstance(want, re.Pattern) and want.fullmatch(have) is None
        if not ok:
            return False
    return True


def matches(attributes: Mapping[str, Any], matchers: Sequence[str]) -> bool:
    """Does one collector satisfy EVERY matcher? An empty matcher list is unconstrained.

    An empty list returning True is deliberate: a pipeline with no matchers targets the whole fleet, and
    returning False would hide a fleet-wide configuration entirely.
    """
    return _matches_prepared(attributes, _prepare(matchers))


def targets(
    pipelines: Iterable[Mapping[str, Any]],
    collectors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """How many collectors each pipeline targets, plus the self-checks.

    Returns `counts` (per pipeline, `None` where its matchers would not parse), `enabled_counts` (the
    same but zero for a disabled pipeline), `unparsed`, and `unmatched`.

    **`unmatched` is the self-check, and it is `None` unless every pipeline parsed.** A collector no
    pipeline targets receives no configuration, which is a finding on its own - but with one pipeline's
    reach unknown, "targeted by nothing" is unknowable, and reporting a number there would accuse
    collectors of being unconfigured when the unparsed pipeline may well cover them.

    A DISABLED pipeline still gets a count: its matchers describe a target set regardless of whether it
    is acting on them. `enabled_counts` is the "actually being configured" view. Collapsing the two would
    report a switched-off pipeline as covering collectors it never reaches.
    """
    attrs = [c.get("attributes") or {} for c in collectors]
    counts: list[int | None] = []
    enabled_counts: list[int] = []
    covered: set[int] = set()
    unparsed = 0
    all_parsed = True

    for pipeline in pipelines:
        selector = list(pipeline.get("matchers") or [])
        try:
            prepared = _prepare(selector)
            hits = [i for i, a in enumerate(attrs) if _matches_prepared(a, prepared)]
        except UnparsedMatcher:
            unparsed += 1
            all_parsed = False
            counts.append(None)
            enabled_counts.append(0)
            continue
        counts.append(len(hits))
        if pipeline.get("enabled"):
            enabled_counts.append(len(hits))
            covered.update(hits)
        else:
            enabled_counts.append(0)

    return {
        "counts": counts,
        "enabled_counts": enabled_counts,
        "unparsed": unparsed,
        "unmatched": (len(attrs) - len(covered)) if all_parsed else None,
    }
