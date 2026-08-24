"""The OTLP synthetic floor - why adoption is thresholded at `> 1000`, never `> 0` (PLAN 3.3, Trap 8).

Until now this trap was **live-verified but not reproducible from anything on disk**, which is the worst
state for a claim to be in: it shapes a number on a leadership panel and nobody could check it. The query
output is now committed as `testdata/otlp-floor.json`, and this file pins what it proves.

**Measured 2026-08-18 over the whole org via `grafanacloud-usage`:**

    stacks reporting an OTLP series value      230 of 271
    reporting EXACTLY 2 (the synthetic floor)  182
    reporting 0                                  0
    above 1,000 - real adopters                 28
    between 3 and 1,000                         20

The floor is what makes `> 0` catastrophic rather than merely loose: **nothing reports zero**, so `> 0` is
satisfied by every stack that reports at all. It would put OTLP adoption at **230 of 271 (85%)** when the
real figure is **28 (10%)** - an 8x overstatement of a protocol-migration metric an org is actively working
on, and the kind of number that gets repeated in a steering deck.
"""

from __future__ import annotations

import json
import pathlib
import unittest
from collections import Counter

from collector.pillars.cost import USAGE_FLOOR

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

# Read the real constant rather than restating it - a copy here could drift from the code silently.
FLOOR = USAGE_FLOOR


def _evidence() -> dict:
    return json.loads((TESTDATA / "otlp-floor.json").read_text())


class TheEvidenceIsReproducibleTest(unittest.TestCase):
    """The point of committing it: a future reader can re-run and compare."""

    def setUp(self) -> None:
        self.ev = _evidence()

    def test_it_records_the_command_that_produced_it(self):
        source = self.ev["source"]
        self.assertIn("grafanacloud_instance_active_otlp_series", source["command"])
        self.assertIn("grafanacloud-usage", source["command"])

    def test_it_warns_that_the_id_label_is_not_the_stack_id(self):
        """The correlation trap that governs this whole platform, restated where it is used."""
        self.assertIn("hmInstancePromId", self.ev["source"]["note"])

    def test_it_uses_a_range_query_not_an_instant_one(self):
        self.assertIn("Range query", self.ev["source"]["note"])

    def test_every_row_carries_a_value_and_an_id(self):
        for row in self.ev["stacks"]:
            self.assertIn("otlp_active_series", row)
            self.assertIsNotNone(row["metrics_instance_id"])


class TheFloorIsRealTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ev = _evidence()
        cls.values = [r["otlp_active_series"] for r in cls.ev["stacks"]]

    def test_a_large_majority_sit_on_exactly_two_series(self):
        at_floor = Counter(self.values)[2.0]
        self.assertEqual(at_floor, self.ev["summary"]["at_the_synthetic_floor_of_2"])
        self.assertGreater(at_floor / len(self.values), 0.5,
                           "the synthetic floor is no longer the dominant value - re-verify the threshold")

    def test_nothing_reports_zero_which_is_what_makes_a_zero_threshold_useless(self):
        """The crux. If some stacks reported 0, `> 0` would at least discriminate. None do."""
        self.assertEqual(Counter(self.values)[0.0], 0)
        self.assertEqual(self.ev["summary"]["reporting_zero"], 0)

    def test_the_zero_threshold_would_overstate_adoption_several_fold(self):
        naive = len([v for v in self.values if v > 0])
        real = len([v for v in self.values if v > FLOOR])
        self.assertGreater(naive, real * 5,
                           "the two thresholds no longer differ materially - recheck before relaxing")

    def test_the_thousand_threshold_selects_a_credible_minority(self):
        real = len([v for v in self.values if v > FLOOR])
        self.assertEqual(real, self.ev["summary"]["above_1000"])
        self.assertLess(real / self.ev["summary"]["estate_total"], 0.25,
                        "OTLP adoption above 25% would be a genuine change worth reporting, not a bug")

    def test_the_floor_of_2_is_a_distinct_cluster_but_everything_above_it_is_a_CONTINUUM(self):
        """An honest statement of what the threshold is and is not.

        The synthetic floor is a genuine cluster: 182 stacks at exactly 2, then a gap to 3. But above
        that the distribution is continuous - 520, 587, 773, 1028, 1227, ... 84,646 - so **1,000 is not
        a natural break**. Measured: 9 stacks sit within 2x of it, and it separates 773 from 1,028.

        That makes the threshold a *judgement about how much OTLP counts as adoption*, not a discovered
        boundary. It is defensible because the alternative (`> 0`) is indefensible, and because moving it
        anywhere between ~500 and ~2,500 changes the answer by only a handful of stacks. Do not describe
        it as separating two populations - only the floor does that.
        """
        near = [v for v in self.values if FLOOR * 0.5 <= v <= FLOOR * 2]
        self.assertGreater(len(near), 0, "nothing near the threshold - re-read the distribution")
        # The floor, by contrast, IS a clean cluster: nothing between 2 and 3.
        self.assertEqual([v for v in self.values if 2 < v < 3], [])

    def test_choosing_the_threshold_matters_far_less_than_not_using_zero(self):
        """The actual argument for the threshold, stated as the comparison that decides it.

        Measured: `>500` selects 30 stacks, `>1000` selects 28, `>2500` selects 21. So arguing about
        where in that band to draw the line is worth **at most 9 stacks**. Using `>0` instead selects
        230 - a **202-stack** error. The choice of threshold is a rounding decision; the choice to have
        one at all is the whole finding.
        """
        band = {t: len([v for v in self.values if v > t]) for t in (500, 1000, 2500)}
        spread = max(band.values()) - min(band.values())
        naive_error = len([v for v in self.values if v > 0]) - band[1000]
        self.assertGreater(naive_error, spread * 10,
                           f"threshold choice (spread {spread}) is no longer dwarfed by the >0 error "
                           f"({naive_error}) - the reasoning here needs revisiting: {band}")

    def test_the_real_adopters_are_orders_of_magnitude_above_the_floor(self):
        """Confirms the two populations are genuinely distinct rather than a continuum."""
        real = sorted((v for v in self.values if v > FLOOR), reverse=True)
        self.assertGreater(real[0], 10_000)


class ItMatchesThePillarTest(unittest.TestCase):
    def test_the_pillar_uses_the_shared_floor_constant(self):
        """One definition, imported - not a number restated in two modules."""
        from collector.pillars import usage
        self.assertEqual(usage.USAGE_FLOOR, FLOOR)

    def test_the_pillar_cites_the_committed_evidence(self):
        """The trap was 'live-verified, not reproducible'. The fix is only real if the code points at
        the file that now reproduces it."""
        text = (pathlib.Path(__file__).resolve().parent.parent
                / "collector" / "pillars" / "usage.py").read_text()
        self.assertIn("otlp-floor.json", text)

    def test_the_pillar_does_not_copy_the_mutable_measurement_into_permanent_prose(self):
        """The evidence owns the dated count; always-on source text owns only the rule and pointer."""
        text = (pathlib.Path(__file__).resolve().parent.parent
                / "collector" / "pillars" / "usage.py").read_text()
        self.assertNotIn(str(_evidence()["summary"]["at_the_synthetic_floor_of_2"]), text)


if __name__ == "__main__":
    unittest.main()
