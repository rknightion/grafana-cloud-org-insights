"""Coverage accounting - the fix for the collector's worst silent-wrongness path.

Without this, a scan that fails 27 of 271 stacks renders as a *smaller estate*: "7,416 dashboards"
quietly becomes 6,700, and an adoption curve grows a dip that is a scan failure. Every rollup
carries its denominator so a partial scan is visibly partial (SPEC §5.2, §10.4).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Above this share of failed stacks the tier exits non-zero rather than publishing a thin scan.
FAILURE_ABORT_RATIO = 0.10


@dataclass
class Coverage:
    tier: str
    total: int
    scanned: int = 0
    failures: Counter = field(default_factory=Counter)
    skipped: Counter = field(default_factory=Counter)
    _failed_stacks: dict[str, str] = field(default_factory=dict)
    _skipped_stacks: dict[str, str] = field(default_factory=dict)

    def record_ok(self, stack: str) -> None:
        self.scanned += 1
        # A stack that failed earlier in the tier and then succeeded is no longer a failure.
        reason = self._failed_stacks.pop(stack, None)
        if reason is not None:
            self.failures[reason] -= 1
            if self.failures[reason] <= 0:
                del self.failures[reason]

    def record_failure(self, stack: str, reason: str) -> None:
        self.failures[reason] += 1
        self._failed_stacks[stack] = reason

    def record_skipped(self, stack: str, reason: str) -> None:
        """Not scannable by design - e.g. a paused stack, whose Grafana is not running.

        Distinct from a failure: counting the estate's 4 paused stacks as failures caps coverage at
        98.5% forever and trains everyone to ignore the warning. Counting them as *scanned* would be
        the opposite lie.
        """
        self.skipped[reason] += 1
        self._skipped_stacks[stack] = reason

    @property
    def failed(self) -> int:
        return sum(self.failures.values())

    @property
    def scannable(self) -> int:
        """Stacks a healthy scan is expected to cover - the estate less the ones skipped by design."""
        return max(0, self.total - sum(self.skipped.values()))

    @property
    def ratio(self) -> float:
        """Share of the SCANNABLE estate covered. 1.0 when nothing failed."""
        return (self.scanned / self.scannable) if self.scannable else 0.0

    @property
    def should_abort(self) -> bool:
        return bool(self.scannable) and (self.failed / self.scannable) > FAILURE_ABORT_RATIO

    def as_meta(self) -> dict[str, object]:
        return {
            "stacks_total": self.total,
            "stacks_scannable": self.scannable,
            "stacks_scanned": self.scanned,
            "stacks_failed": self.failed,
            "stacks_skipped": sum(self.skipped.values()),
            "coverage_ratio": round(self.ratio, 4),
            "failures_by_reason": dict(self.failures),
            "skipped_by_reason": dict(self.skipped),
            "failed_stacks": dict(self._failed_stacks),
            "skipped_stacks": dict(self._skipped_stacks),
        }

    def as_metrics(self) -> list[tuple[str, dict[str, str], float]]:
        """(name, labels, value) triples. Labels stay bounded - reasons are a closed vocabulary."""
        out: list[tuple[str, dict[str, str], float]] = [
            ("gcinsight_scan_stacks_total", {"tier": self.tier}, float(self.total)),
            ("gcinsight_scan_stacks_scannable", {"tier": self.tier}, float(self.scannable)),
            ("gcinsight_scan_stacks_scanned", {"tier": self.tier}, float(self.scanned)),
            ("gcinsight_scan_coverage_ratio", {"tier": self.tier}, self.ratio),
        ]
        for reason, count in sorted(self.failures.items()):
            out.append(
                ("gcinsight_scan_stacks_failed", {"tier": self.tier, "reason": reason}, float(count))
            )
        for reason, count in sorted(self.skipped.items()):
            out.append(
                ("gcinsight_scan_stacks_skipped", {"tier": self.tier, "reason": reason}, float(count))
            )
        return out


def rollup(name: str, value: float, coverage: Coverage) -> dict[str, object]:
    """Wrap an estate-wide aggregate with the denominator it was computed over.

    Any figure shown to a customer goes through this, so "7,416 dashboards" can never be presented
    without the fact that it was summed over N of 271 stacks.
    """
    return {
        "name": name,
        "value": value,
        "stacks_counted": coverage.scanned,
        "stacks_scannable": coverage.scannable,
        "stacks_total": coverage.total,
        "coverage_ratio": round(coverage.ratio, 4),
        "partial": coverage.scanned < coverage.scannable,
    }
