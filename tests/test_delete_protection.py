"""Stacks carrying real load that can be deleted without a guard (Pillar E).

**Measured 2026-08-18: `deleteProtection` is true on 2 of 271 stacks - and both are paused
`teststack*` automated-test leftovers.** Every one of the top ten stacks by active series is
unprotected, including `stack094` at 3.04M series. So the only two stacks in the estate that cannot be
deleted are the two that arguably should be, and a three-million-series stack can go on a misclick.

The field was already in every scan, sitting as a boolean column in two 271-row tables where nobody
would ever notice that only two rows say `true`. That is the defect this fixes: **data collected but not
surfaced is not surfaced.**

**Why a threshold.** 269 findings is not a findings list, it is the inventory again - the same
signal-to-noise failure that once reported 4,964 "service account risks". A stack with no users and no
series being unprotected is not a risk, it is a stack somebody should delete. So the finding is
*unprotected AND materially in use*, and the threshold is justified from the measured distribution
rather than picked.

**It composes with admin sprawl, and that is the real exposure.** `stack094` is 15 of 16 admins, 3.04M
series, and unprotected - every one of those admins can delete it. Neither finding says that alone.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit.budget import CATALOGUE
from collector.pillars import findings as findings_mod
from collector.pillars import risk

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

VIEW = "risk_delete_protection"
KIND = "no_delete_protection"
METRIC = "gcinsight_risk_stacks_without_delete_protection"


def _stacks():
    return json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]


def _coverage(stacks):
    cov = Coverage(tier="t1", total=len(stacks))
    for s in stacks:
        cov.record_ok(str(s["slug"]))
    return cov


def _build(stacks):
    return risk.build(stacks, _coverage(stacks))


def _stack(slug, *, protected=False, series=0, users=0, admins=0):
    return {
        "slug": slug, "regionSlug": "prod-eu-west-2", "deleteProtection": protected,
        "hmInstancePromCurrentActiveSeries": series, "billingActiveUsers": users,
        "currentActiveUsers": users, "currentActiveAdminUsers": admins, "alertCnt": 0,
    }


class TheThresholdSeparatesLoadFromEmptyTest(unittest.TestCase):
    def test_an_unprotected_stack_with_real_load_is_a_finding(self):
        _, views = _build([_stack("big", series=risk.DELETE_PROTECTION_SERIES_FLOOR, users=5)])
        self.assertEqual([r[" Stack"] for r in views[VIEW]], ["big"])

    def test_an_unprotected_but_empty_stack_is_NOT_a_finding(self):
        """It is a deletion candidate, not a deletion risk. Reporting it inverts the advice."""
        _, views = _build([_stack("empty", series=0, users=0)])
        self.assertEqual(views[VIEW], [])

    def test_a_stack_just_below_the_floor_is_excluded(self):
        _, views = _build([_stack("small", series=risk.DELETE_PROTECTION_SERIES_FLOOR - 1)])
        self.assertEqual(views[VIEW], [])

    def test_a_protected_stack_is_never_a_finding_however_large(self):
        _, views = _build([_stack("safe", protected=True, series=5_000_000, users=100)])
        self.assertEqual(views[VIEW], [])

    def test_the_view_is_sorted_by_what_is_at_stake(self):
        """A reader works top-down, so the largest exposure must be the first row."""
        floor = risk.DELETE_PROTECTION_SERIES_FLOOR
        _, views = _build([
            _stack("mid", series=floor * 2),
            _stack("huge", series=floor * 10),
            _stack("small", series=floor),
        ])
        self.assertEqual([r[" Stack"] for r in views[VIEW]], ["huge", "mid", "small"])


class TheMetricTest(unittest.TestCase):
    def test_it_counts_every_unprotected_stack_not_just_the_material_ones(self):
        """The metric is the governance number (269 of 271); the view is the actionable subset. They
        are deliberately different, because 'almost nothing is protected' is the leadership point."""
        stacks = [_stack("a"), _stack("b", series=999_999), _stack("c", protected=True)]
        metrics, _ = _build(stacks)
        value = next(v for n, _, v in metrics if n == METRIC)
        self.assertEqual(value, 2.0)

    def test_it_is_absent_when_every_stack_is_protected(self):
        """Absent, never 0 - a 0 here would be indistinguishable from a scan that read nothing."""
        metrics, _ = _build([_stack("a", protected=True)])
        self.assertNotIn(METRIC, {n for n, _, _ in metrics})

    def test_it_carries_no_unbounded_label(self):
        metrics, _ = _build([_stack("a", series=999_999)])
        for name, labels, _ in metrics:
            if name == METRIC:
                self.assertEqual(labels, {})

    def test_it_is_declared_in_the_budget(self):
        self.assertIsNotNone(next((s for s in CATALOGUE if s.name == METRIC), None),
                             f"{METRIC} is not declared in budget.py")


class TheFindingIsWiredTest(unittest.TestCase):
    def test_the_kind_is_registered(self):
        self.assertIn(KIND, findings_mod.KINDS)

    def test_the_spec_points_at_the_view(self):
        spec = next(s for s in findings_mod.SPECS if s.kind == KIND)
        self.assertEqual(spec.view, VIEW)
        self.assertEqual(spec.pillar, "E")

    def test_the_view_needs_no_row_filter_because_the_pillar_filters_it(self):
        """The module's own rule: a filter here admits the view is unfiltered upstream. It is not."""
        spec = next(s for s in findings_mod.SPECS if s.kind == KIND)
        self.assertEqual(spec.require, ())
        self.assertEqual(spec.at_least, ())

    def test_findings_are_derived_from_the_real_estate(self):
        _, views = _build(_stacks())
        derived, totals = findings_mod.derive(views)
        self.assertGreater(totals.get(KIND, 0), 0, "no delete-protection findings on the real estate")
        self.assertLess(totals[KIND], 271, "this must be a filtered subset, not the whole inventory")


class AgainstTheRealEstateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = _stacks()
        cls.metrics, cls.views = _build(cls.stacks)

    def test_almost_nothing_in_the_estate_is_protected(self):
        """Pins the headline. If this ever fails because the fixture changed, that is the good outcome -
        update the number, do not delete the test."""
        unprotected = next(v for n, _, v in self.metrics if n == METRIC)
        self.assertGreater(unprotected, 250)

    def test_the_only_protected_stacks_are_test_leftovers(self):
        """The finding that makes the point: protection is on the two stacks that need it least."""
        protected = [str(s["slug"]) for s in self.stacks if s.get("deleteProtection")]
        self.assertTrue(protected, "expected at least one protected stack in the fixture")
        for slug in protected:
            self.assertTrue(slug.startswith(("teststack", "testsrobot")),
                            f"{slug} is protected and is NOT a test leftover - update this test")

    def test_the_biggest_stack_in_the_estate_is_in_the_finding(self):
        biggest = max(self.stacks, key=lambda s: s.get("hmInstancePromCurrentActiveSeries") or 0)
        self.assertIn(str(biggest["slug"]), [r[" Stack"] for r in self.views[VIEW]])

    def test_the_actionable_list_stays_readable(self):
        """A findings list nobody reads is the failure mode this threshold exists to avoid."""
        self.assertLessEqual(len(self.views[VIEW]), 60)

    def test_every_row_carries_what_is_needed_to_act(self):
        for row in self.views[VIEW]:
            for column in (" Stack", "Active series", "Admins", "Delete protection"):
                self.assertIn(column, row)
            self.assertFalse(row["Delete protection"], "a protected stack leaked into the view")


if __name__ == "__main__":
    unittest.main()
