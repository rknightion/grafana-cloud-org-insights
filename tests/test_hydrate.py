"""Cross-tier input hydration (PLAN 16.1).

The defect being defended against is specific and it shipped: the hourly tier held inventory alone,
composed nine views the pillars could only fill with `None`, and wrote them over the 6-hourly tier's
real figures. `cost_summary` read "0 of 269 scannable measured for Adaptive" on the live dashboard
while `cost_adaptive_headroom` beside it listed 114 stacks - one dashboard disagreeing with itself by
the entire finding.

So the tests that matter here are not "does hydration merge dicts". They are:

  1. A view whose inputs are unsatisfied is WITHHELD, never written with zeros.
  2. A stale input is refused rather than presented as current.
  3. `VIEW_INPUTS` matches what the pillars ACTUALLY need - re-derived, not restated.
  4. A tier cannot hydrate an input from its own previous scan, which would make a broken gatherer
     look healthy indefinitely.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import pathlib
import unittest
from unittest import mock

from collector.coverage import Coverage
from collector.emit import guard, hydrate
from collector.pillars import compose

NOW = dt.datetime(2026, 8, 19, 20, 0, tzinfo=dt.timezone.utc)
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _scan(tier: str, key: str, payload, age: dt.timedelta = dt.timedelta(hours=1)):
    return {
        "meta": {"tier": tier, "generated_at": (NOW - age).isoformat()},
        "data": {key: payload},
    }


def _loader(**by_tier):
    """A `loader` stand-in so no test touches S3."""
    return lambda tier, bucket: by_tier.get(tier)


class HydrationSourcesTest(unittest.TestCase):
    def test_own_input_is_used_and_marked_own(self):
        inputs, prov = hydrate.hydrate("t3", {"dataplane": {"a": 1}}, now=NOW, loader=_loader())
        self.assertEqual(inputs["dataplane"], {"a": 1})
        self.assertEqual(prov["dataplane"]["source"], "own")
        self.assertEqual(prov["dataplane"]["age_seconds"], 0.0)

    def test_a_missing_input_is_pulled_from_the_owning_tier(self):
        inputs, prov = hydrate.hydrate(
            "t1", {"access_policies": [{"p": 1}]}, now=NOW,
            loader=_loader(t2=_scan("t2", "stack_detail", {"s": 1}, dt.timedelta(hours=14)),
                           t3=_scan("t3", "dataplane", {"d": 1}, dt.timedelta(hours=2))),
        )
        self.assertEqual(inputs["stack_detail"], {"s": 1})
        self.assertEqual(inputs["dataplane"], {"d": 1})
        self.assertEqual(prov["stack_detail"]["source"], "hydrated")
        self.assertEqual(prov["dataplane"]["age_seconds"], 2 * 3600)
        self.assertEqual(prov["access_policies"]["source"], "own")

    def test_the_age_recorded_is_the_inputs_age_not_the_running_tiers(self):
        """The whole point of the provenance record. T1 runs hourly; a dataplane it hydrated can be
        hours old, and a dashboard reading T1's own timestamp would call that data minutes old."""
        _, prov = hydrate.hydrate(
            "t1", {}, now=NOW, loader=_loader(t3=_scan("t3", "dataplane", {"d": 1}, dt.timedelta(hours=5))))
        self.assertEqual(prov["dataplane"]["age_seconds"], 5 * 3600)

    def test_a_tier_never_hydrates_its_own_input_from_its_own_last_scan(self):
        """T3's gatherer failing must show as unavailable, not as T3 quietly reusing last run's probe."""
        _, prov = hydrate.hydrate(
            "t3", {}, now=NOW, loader=_loader(t3=_scan("t3", "dataplane", {"d": 1})))
        self.assertFalse(prov.satisfied("dataplane"))
        self.assertEqual(prov["dataplane"]["source"], "missing")

    def test_no_scan_at_all_is_not_an_error(self):
        """A fresh deployment has no latest.json for any tier. T1 must still run."""
        inputs, prov = hydrate.hydrate("t1", {}, now=NOW, loader=_loader())
        self.assertEqual(inputs, {})
        self.assertEqual(prov.unsatisfied(), sorted(hydrate.INPUT_OWNER),
                         "derived from INPUT_OWNER so adding an input does not need this list edited")

    def test_a_scan_that_carries_no_such_input_is_unavailable(self):
        _, prov = hydrate.hydrate(
            "t1", {}, now=NOW, loader=_loader(t3=_scan("t3", "something_else", {"x": 1})))
        self.assertFalse(prov.satisfied("dataplane"))
        self.assertIn("carries no", prov["dataplane"]["reason"])

    def test_an_empty_input_counts_as_absent_not_as_measured_empty(self):
        """`{}` from a failed probe must not publish as 'we looked and there is nothing'."""
        _, prov = hydrate.hydrate("t3", {"dataplane": {}}, now=NOW, loader=_loader())
        self.assertFalse(prov.satisfied("dataplane"))

    def test_an_owner_rejected_partial_input_is_not_composed_as_available(self):
        inputs, prov = hydrate.hydrate(
            "t2",
            {"insights": {"one-stack": {"available": True}}},
            unavailable={
                "insights": {
                    "state": "partial",
                    "reason": "partial: 1 of 269 stacks available, below the publication floor",
                }
            },
            now=NOW,
            loader=_loader(),
        )
        self.assertNotIn("insights", inputs)
        self.assertFalse(prov.satisfied("insights"))
        self.assertEqual(prov["insights"]["state"], "partial")
        self.assertFalse(prov["insights"]["stale"], "current failure is not stale data")

    def test_a_downstream_tier_refuses_a_partial_owner_envelope_even_if_it_carries_payload(self):
        """Defence in depth for owner scans written by an older binary before rejection moved early."""
        partial = _scan("t2", "insights", {"one-stack": {"available": True}})
        partial["meta"]["sources"] = {
            "insights": {"expected": 269, "available": 1, "healthy": False}
        }
        inputs, prov = hydrate.hydrate(
            "t1", {}, now=NOW, loader=_loader(t2=partial)
        )
        self.assertNotIn("insights", inputs)
        self.assertFalse(prov.satisfied("insights"))
        self.assertEqual(prov["insights"]["state"], "partial")
        self.assertIn("1 of 269", prov["insights"]["reason"])

    def test_malformed_source_health_counts_withhold_instead_of_aborting_hydration(self):
        malformed = _scan("t2", "insights", {"one-stack": {"available": True}})
        malformed["meta"]["sources"] = {
            "insights": {"expected": {"not": "a count"}, "available": "many", "healthy": False}
        }

        inputs, prov = hydrate.hydrate("t1", {}, now=NOW, loader=_loader(t2=malformed))

        self.assertNotIn("insights", inputs)
        self.assertFalse(prov.satisfied("insights"))
        self.assertEqual(prov["insights"]["state"], "unavailable")
        self.assertIn("0 of 0", prov["insights"]["reason"])


class StalenessTest(unittest.TestCase):
    def test_an_input_past_the_cap_is_refused(self):
        _, prov = hydrate.hydrate(
            "t1", {}, now=NOW,
            loader=_loader(t3=_scan("t3", "dataplane", {"d": 1}, hydrate.MAX_INPUT_AGE + dt.timedelta(seconds=1))))
        self.assertFalse(prov.satisfied("dataplane"))
        self.assertEqual(prov["dataplane"]["source"], "stale")

    def test_an_input_just_inside_the_cap_is_accepted(self):
        inputs, prov = hydrate.hydrate(
            "t1", {}, now=NOW,
            loader=_loader(t3=_scan("t3", "dataplane", {"d": 1}, hydrate.MAX_INPUT_AGE - dt.timedelta(minutes=1))))
        self.assertIn("dataplane", inputs)
        self.assertTrue(prov.satisfied("dataplane"))

    def test_a_stale_input_still_reports_its_age(self):
        """Blank panels AND a queryable reason, same contract as carry-forward."""
        _, prov = hydrate.hydrate(
            "t1", {}, now=NOW,
            loader=_loader(t3=_scan("t3", "dataplane", {"d": 1}, dt.timedelta(days=30))))
        self.assertEqual(prov["dataplane"]["age_seconds"], 30 * 86400)

    def test_an_unparseable_timestamp_is_treated_as_infinitely_old(self):
        bad = {"meta": {"tier": "t3", "generated_at": "not-a-date"}, "data": {"dataplane": {"d": 1}}}
        _, prov = hydrate.hydrate("t1", {}, now=NOW, loader=_loader(t3=bad))
        self.assertFalse(prov.satisfied("dataplane"))
        self.assertIsNone(prov["dataplane"]["age_seconds"])

    def test_the_cap_matches_carry_forward_so_there_is_one_staleness_story(self):
        """Two caps that can drift apart would mean a view withheld while its metric is still carried,
        or the reverse - the dashboard and the metric disagreeing about whether data exists."""
        from collector.emit import carry
        self.assertEqual(hydrate.MAX_INPUT_AGE, carry.MAX_CARRY_AGE)


class WithholdingTest(unittest.TestCase):
    """The behaviour that actually stops the shipped defect."""

    def _prov(self, **satisfied):
        return hydrate.Provenance({
            name: {"available": ok, "source": "own" if ok else "missing",
                   "stale": not ok, "age_seconds": 0.0 if ok else None,
                   **({} if ok else {"reason": "gatherer failed"})}
            for name, ok in satisfied.items()
        })

    def test_a_view_needing_an_unsatisfied_input_is_withheld(self):
        views = {"cost_summary": [{"a": 1}], "estate": [{"b": 2}]}
        prov = self._prov(dataplane=False, stack_detail=True, access_policies=True)
        keep, withheld = hydrate.filter_views(views, prov)
        self.assertEqual(list(keep), ["estate"])
        self.assertIn("cost_summary", withheld)
        self.assertIn("gatherer failed", withheld["cost_summary"])

    def test_a_partial_input_preserves_the_last_good_view(self):
        prov = hydrate.Provenance({
            "insights": {
                "available": False, "source": "own", "tier": "t2", "stale": False,
                "age_seconds": None, "state": "partial",
                "reason": "partial: 1 of 269 stacks available",
            }
        })
        keep, withheld = hydrate.filter_views(
            {"insights_summary": [{"Value": 99}], "estate": [{"Stacks": 269}]}, prov
        )
        self.assertEqual(keep, {"estate": [{"Stacks": 269}]})
        self.assertIn("1 of 269", withheld["insights_summary"])

    def test_an_inventory_only_view_always_publishes(self):
        prov = self._prov(dataplane=False, stack_detail=False, access_policies=False)
        keep, _ = hydrate.filter_views({"estate": [1], "usage": [2], "cost_signal_usage": [3]}, prov)
        self.assertEqual(sorted(keep), ["cost_signal_usage", "estate", "usage"])

    def test_the_multi_input_views_need_every_one_of_their_inputs(self):
        """`risk_summary` is the view tier-ownership could not fix: it needs all three."""
        for missing in ("access_policies", "dataplane", "stack_detail"):
            with self.subTest(missing=missing):
                prov = self._prov(**{n: (n != missing) for n in
                                     ("access_policies", "dataplane", "stack_detail")})
                keep, withheld = hydrate.filter_views({"risk_summary": [1]}, prov)
                self.assertEqual(keep, {})
                self.assertIn("risk_summary", withheld)

    def test_maturity_owners_needs_two_tiers_inputs_together(self):
        """No production tier gathers both, which is why its published copy was a 2-row debug artifact."""
        self.assertEqual(hydrate.VIEW_INPUTS["maturity_owners"],
                         frozenset({"dataplane", "stack_detail"}))
        prov = self._prov(dataplane=True, stack_detail=False, access_policies=True)
        keep, _ = hydrate.filter_views({"maturity_owners": [1]}, prov)
        self.assertEqual(keep, {})

    def test_service_account_inventory_has_independent_freshness(self):
        """A healthy user/plugin sweep must not mask a failed service-account inventory."""
        self.assertEqual(hydrate.INPUT_OWNER.get("service_accounts"), "t2")
        self.assertEqual(
            hydrate.VIEW_INPUTS.get("risk_service_accounts"), frozenset({"service_accounts"})
        )

    def test_alert_routing_views_are_withheld_without_their_own_input(self):
        self.assertEqual(hydrate.INPUT_OWNER.get("alert_routing"), "t2")
        self.assertEqual(
            hydrate.VIEW_INPUTS.get("risk_alert_routing"), frozenset({"alert_routing"})
        )
        self.assertEqual(
            hydrate.VIEW_INPUTS.get("risk_alert_routing_findings"), frozenset({"alert_routing"})
        )

    def test_every_declared_view_input_is_a_real_hydratable_input(self):
        """A typo here would withhold a view for ever, since the name could never be satisfied."""
        for view, needed in hydrate.VIEW_INPUTS.items():
            with self.subTest(view=view):
                self.assertTrue(needed <= set(hydrate.INPUT_OWNER),
                                f"{view} needs {needed - set(hydrate.INPUT_OWNER)}, which no tier gathers")


class ProvenanceMetricsTest(unittest.TestCase):
    def test_availability_and_age_are_emitted(self):
        _, prov = hydrate.hydrate(
            "t1", {}, now=NOW,
            loader=_loader(t3=_scan("t3", "dataplane", {"d": 1}, dt.timedelta(hours=3))))
        by = {(name, labels["input"]): value
              for name, labels, value in hydrate.report_metrics(prov, "t1")}
        self.assertEqual(by[("gcinsight_input_available", "dataplane")], 1.0)
        self.assertEqual(by[("gcinsight_input_age_seconds", "dataplane")], 3 * 3600)
        self.assertEqual(by[("gcinsight_input_available", "stack_detail")], 0.0)

    def test_an_unavailable_input_emits_no_age(self):
        """A zero age would read as 'gathered just now' - the exact inversion of the truth."""
        _, prov = hydrate.hydrate("t1", {}, now=NOW, loader=_loader())
        names = {(name, labels["input"])
                 for name, labels, _value in hydrate.report_metrics(prov, "t1")}
        self.assertNotIn(("gcinsight_input_age_seconds", "dataplane"), names)
        self.assertIn(("gcinsight_input_available", "dataplane"), names)

    def test_a_failed_owner_scan_does_not_publish_its_envelope_age_as_data_age(self):
        """A fresh failed scan is not fresh data.

        The owner envelope can be minutes old while carrying no input at all. Publishing that envelope
        age made an unavailable source look young on the dashboards.
        """
        failed = {
            "meta": {"tier": "t3", "generated_at": (NOW - dt.timedelta(minutes=10)).isoformat()},
            "data": {"something_else": {"x": 1}},
        }
        _, prov = hydrate.hydrate("t1", {}, now=NOW, loader=_loader(t3=failed))
        names = {(name, labels["input"])
                 for name, labels, _value in hydrate.report_metrics(prov, "t1")}
        self.assertEqual(prov["dataplane"]["age_seconds"], 10 * 60)
        self.assertNotIn(("gcinsight_input_age_seconds", "dataplane"), names)
        self.assertIn(("gcinsight_input_available", "dataplane"), names)

    def test_metrics_pass_the_label_guard_and_are_declared(self):
        from collector.emit.budget import CATALOGUE
        _, prov = hydrate.hydrate(
            "t1", {}, now=NOW, loader=_loader(t3=_scan("t3", "dataplane", {"d": 1})))
        metrics = hydrate.report_metrics(prov, "t1")
        self.assertEqual(guard.check_all(metrics), len(metrics))
        declared = {(s.name, tuple(sorted(s.labels))) for s in CATALOGUE if s.store == "mimir"}
        for name, labels, _ in metrics:
            self.assertIn((name, tuple(sorted(labels))), declared, f"{name} undeclared in the budget")


class ViewInputsAreDerivedNotAssumed(unittest.TestCase):
    """Re-derive `VIEW_INPUTS` from the pillars and fail if the declaration has drifted.

    This is the test that keeps the fix working. `VIEW_INPUTS` is what decides whether a view is
    published or withheld, so a pillar quietly gaining a dependency on the data plane - with the
    declaration left alone - puts the platform straight back to publishing that view from a tier that
    cannot compute it. Rather than trusting a hand-maintained table, this composes every subset of the
    optional inputs and checks which ones reproduce the full-input output byte for byte.
    """

    @classmethod
    def setUpClass(cls):
        cls.fixture = FIXTURES / "compose_inputs.json"
        if not cls.fixture.exists():
            raise unittest.SkipTest(
                f"{cls.fixture} absent - regenerate with bin/make_compose_fixture.py")
        cls.data = json.loads(cls.fixture.read_text())

    def _build(self, subset):
        stacks = self.data["stacks"]
        cov = Coverage(tier="tX", total=len(stacks))
        for i in range(self.data["scanned"]):
            cov.record_ok(f"s{i}")
        for i in range(len(stacks) - self.data["scannable"]):
            cov.record_skipped(f"p{i}", "paused")
        kw = {k: self.data[k] for k in subset}
        # Every subset must see one instant. Several views contain age/recency values, so allowing
        # each composition to call the wall clock can invent a dependency when the loop crosses a
        # bucket boundary.
        _, views = compose.build_all(stacks, cov, now=NOW, **kw)
        return {n: json.dumps(r, default=str, sort_keys=True) for n, r in views.items()}

    def test_derivation_does_not_depend_on_the_wall_clock(self):
        """The same fixture must derive the same dependencies on either side of an age boundary.

        User-recency buckets and several age columns are time-relative. If this harness lets each
        composition read the wall clock independently, one of its many subset builds can cross a
        boundary and make an unchanged view appear input-dependent.
        """
        class Before(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 8, 19, 19, 59, tzinfo=tz)

        class After(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2027, 8, 19, 20, 1, tzinfo=tz)

        inputs = sorted(hydrate.INPUT_OWNER)
        with mock.patch("collector.pillars.usage.dt.datetime", Before):
            before = self._build(inputs)
        with mock.patch("collector.pillars.usage.dt.datetime", After):
            after = self._build(inputs)
        self.assertEqual(before, after)

    def test_declaration_matches_what_the_pillars_really_need(self):
        names = sorted(hydrate.INPUT_OWNER)
        built = {frozenset(s): self._build(s)
                 for r in range(len(names) + 1)
                 for s in itertools.combinations(names, r)}
        full = built[frozenset(names)]

        derived: dict[str, frozenset[str]] = {}
        for view in full:
            reproducing = [s for s in built
                           if view in built[s] and built[s][view] == full[view]]
            derived[view] = frozenset(min(reproducing, key=len)) if reproducing else frozenset(names)

        expected = {v: n for v, n in derived.items() if n}
        actual = {v: n for v, n in hydrate.VIEW_INPUTS.items() if v in full}
        self.assertEqual(
            actual, expected,
            "VIEW_INPUTS has drifted from what the pillars compute. A view here that needs an input the "
            "declaration omits WILL be published as zeros by a tier that lacks it.",
        )

    def test_every_declared_view_actually_exists(self):
        """A renamed view left in the declaration silently stops being guarded."""
        produced = set(self._build(sorted(hydrate.INPUT_OWNER)))
        for view in hydrate.VIEW_INPUTS:
            with self.subTest(view=view):
                self.assertIn(view, produced)


if __name__ == "__main__":
    unittest.main()
