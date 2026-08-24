"""A deliberately-failed stack must read as REDUCED COVERAGE, never as a smaller estate (PLAN 8.4).

This is the collector's worst silent-wrongness path, and the reason `collector/coverage.py` exists: a
scan that loses 27 of 271 stacks renders "7,416 dashboards" as "6,700" and puts a dip in an adoption
curve that is a scan failure, not a customer behaviour. Nothing errors, and the number is wrong in the
direction that looks like news.

There are TWO defences and they are not the same, which is why this file tests both:

  * **Inventory-derived figures cannot shrink at all.** The estate size, the per-region split and the
    headline counts come from the single `/instances` listing, so a per-stack failure leaves them
    untouched. If one of these ever moves under failure it means a pillar started deriving it by
    iterating stacks, and the guarantee is gone.
  * **Per-stack aggregates DO shrink, and must be visibly partial.** T2/T3 sum over stacks they
    actually reached, so the value legitimately drops - `rollup()` attaches the denominator and a
    `partial` flag so the smaller number can never be presented as an estate total.

The tier-ownership contract in `test_compose.py` is the other half of this: a tier that cannot compute
a metric omits it rather than emitting a zero.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage, rollup
from collector.pillars import compose

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

# The share of the estate this test fails on purpose. Chosen to sit just above the 10% abort ratio so
# the same fixture exercises the abort guard, and to match the 27-of-271 case in the SPEC.
FAILED = 27
REASON = "http_500"


def _inventory() -> list[dict]:
    return json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]


def _healthy(stacks: list[dict], tier: str = "t1") -> Coverage:
    cov = Coverage(tier=tier, total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            cov.record_skipped(str(s["slug"]), "paused")
        else:
            cov.record_ok(str(s["slug"]))
    return cov


def _degraded(stacks: list[dict], tier: str = "t1", failed: int = FAILED) -> Coverage:
    """The same estate, with `failed` of the scannable stacks deliberately failing."""
    cov = Coverage(tier=tier, total=len(stacks))
    budget = failed
    for s in stacks:
        slug = str(s["slug"])
        if s.get("status") == "paused":
            cov.record_skipped(slug, "paused")
        elif budget > 0:
            cov.record_failure(slug, REASON)
            budget -= 1
        else:
            cov.record_ok(slug)
    assert budget == 0, "fixture too small to fail the requested number of stacks"
    return cov


def _by_name(metrics) -> dict[tuple[str, tuple], float]:
    return {(n, tuple(sorted(l.items()))): v for n, l, v in metrics}


class TheEstateDoesNotShrinkTest(unittest.TestCase):
    """Inventory-derived figures must be byte-identical under failure."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = _inventory()
        cls.ok, _ = compose.build_all(cls.stacks, _healthy(cls.stacks))
        cls.bad, _ = compose.build_all(cls.stacks, _degraded(cls.stacks))
        cls.ok_by, cls.bad_by = _by_name(cls.ok), _by_name(cls.bad)

    def test_the_estate_size_is_unchanged(self):
        """The flagship assertion: 271 stacks stay 271 when 27 of them fail to be scanned."""
        for status in ("total", "active", "paused"):
            key = ("gcinsight_estate_stacks", (("status", status),))
            self.assertEqual(
                self.ok_by[key], self.bad_by[key],
                f"estate_stacks{{status={status}}} moved under failure - the estate appeared to shrink",
            )

    def test_every_inventory_derived_metric_is_identical(self):
        """Catches a future pillar deriving a headline number by iterating stacks instead.

        Scan-health metrics are excluded because they are *supposed* to move - they are the signal.
        """
        moved = {
            name: (self.ok_by[key], self.bad_by[key])
            for key in self.ok_by
            for name in [key[0]]
            if not name.startswith("gcinsight_scan_")
            and key in self.bad_by
            and self.ok_by[key] != self.bad_by[key]
        }
        self.assertEqual(moved, {}, f"inventory-derived metrics moved under failure: {moved}")

    def test_no_metric_disappears_entirely_under_failure(self):
        """A vanishing series reads as "not measured" on a dashboard; the estate figures were measured."""
        lost = {k[0] for k in self.ok_by} - {k[0] for k in self.bad_by}
        self.assertEqual(lost, set(), f"metrics present in a healthy scan vanished in a degraded one: {lost}")


class TheFailureIsVisibleTest(unittest.TestCase):
    """The other half: reduced coverage must be loudly reported, not merely not-lied-about."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = _inventory()
        cls.cov_ok = _healthy(cls.stacks)
        cls.cov_bad = _degraded(cls.stacks)
        cls.ok_by = _by_name(compose.build_all(cls.stacks, cls.cov_ok)[0])
        cls.bad_by = _by_name(compose.build_all(cls.stacks, cls.cov_bad)[0])

    def test_coverage_ratio_drops_below_one(self):
        ratio = ("gcinsight_scan_coverage_ratio", (("tier", "t1"),))
        self.assertEqual(self.ok_by[ratio], 1.0)
        self.assertLess(self.bad_by[ratio], 1.0)

    def test_the_ratio_is_against_scannable_not_total(self):
        """Paused stacks must not count against coverage, or the estate's 4 cap it at 98.5% forever."""
        self.assertEqual(self.cov_ok.ratio, 1.0, "paused stacks leaked into the coverage denominator")
        self.assertEqual(
            self.cov_bad.ratio, self.cov_bad.scanned / self.cov_bad.scannable
        )

    def test_the_scanned_count_drops_but_the_total_does_not(self):
        total = ("gcinsight_scan_stacks_total", (("tier", "t1"),))
        scanned = ("gcinsight_scan_stacks_scanned", (("tier", "t1"),))
        self.assertEqual(self.ok_by[total], self.bad_by[total], "the denominator moved")
        self.assertEqual(self.bad_by[scanned], self.ok_by[scanned] - FAILED)

    def test_failures_are_reported_by_reason_and_absent_when_there_are_none(self):
        """Absent, not zero - a `stacks_failed = 0` series is indistinguishable from a healthy scan
        that never ran, which is exactly the confusion the dead-man's switch exists to avoid."""
        key = ("gcinsight_scan_stacks_failed", (("reason", REASON), ("tier", "t1")))
        self.assertNotIn(key, self.ok_by)
        self.assertEqual(self.bad_by[key], float(FAILED))

    def test_a_per_stack_aggregate_is_flagged_partial(self):
        """T2/T3 sum over stacks they reached, so the value legitimately drops. `rollup()` is what
        stops the smaller number being presented as an estate total."""
        healthy = rollup("dashboards_total", 7416, self.cov_ok)
        degraded = rollup("dashboards_total", 6700, self.cov_bad)

        self.assertFalse(healthy["partial"])
        self.assertTrue(degraded["partial"], "a thin aggregate was not flagged partial")
        self.assertEqual(degraded["stacks_total"], healthy["stacks_total"])
        self.assertLess(degraded["stacks_counted"], degraded["stacks_scannable"])

    def test_losing_more_than_a_tenth_of_the_estate_aborts_the_tier(self):
        """Past the abort ratio the tier exits non-zero rather than publishing a thin scan at all."""
        self.assertFalse(self.cov_ok.should_abort)
        self.assertTrue(self.cov_bad.should_abort, f"{FAILED} of {self.cov_bad.scannable} did not abort")

    def test_a_small_failure_is_reported_without_aborting(self):
        """The abort guard must not be the only signal - most bad scans are under the threshold."""
        cov = _degraded(self.stacks, failed=3)
        self.assertFalse(cov.should_abort)
        self.assertLess(cov.ratio, 1.0)
        self.assertEqual(cov.failed, 3)

    def test_the_meta_block_names_the_failed_stacks(self):
        """S3 scan objects carry this, so a partial scan is diagnosable a week later."""
        meta = self.cov_bad.as_meta()
        self.assertEqual(meta["stacks_failed"], FAILED)
        self.assertEqual(meta["failures_by_reason"], {REASON: FAILED})
        self.assertEqual(len(meta["failed_stacks"]), FAILED)
        self.assertLess(meta["coverage_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
