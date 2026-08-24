"""Carry-forward (PLAN 5.3). The failure mode being defended against is a panel that is confidently
wrong rather than one that is empty."""

from __future__ import annotations

import datetime as dt
import unittest

from collector.emit import carry, guard

NOW = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.timezone.utc)


def _state(age: dt.timedelta, metrics=None, tier="t3"):
    return {
        "generated_at": (NOW - age).isoformat(),
        "tier": tier,
        "metrics": metrics if metrics is not None else [
            ["gcinsight_maturity_score", {"stack": "obs-hub-dev", "version": "1"}, 49.0],
            ["gcinsight_maturity_percentile", {"kind": "median"}, 50.0],
        ],
    }


class CarryForwardTest(unittest.TestCase):
    def test_weekly_series_are_republished(self):
        extra, report = carry.carry_forward([], _state(dt.timedelta(days=3)), now=NOW)
        self.assertEqual(len(extra), 2)
        self.assertEqual(report["carried"], 2)
        self.assertEqual(report["age_seconds"], 3 * 86400)
        self.assertFalse(report["too_old"])

    def test_the_carried_value_is_preserved(self):
        extra, _ = carry.carry_forward([], _state(dt.timedelta(hours=1)), now=NOW)
        by = {(n, tuple(sorted(l.items()))): v for n, l, v in extra}
        self.assertEqual(by[("gcinsight_maturity_score",
                             (("stack", "obs-hub-dev"), ("version", "1")))], 49.0)

    def test_a_series_the_live_tier_computes_is_not_carried(self):
        """Carrying it too would put two samples for one series in one batch."""
        live = [("gcinsight_maturity_percentile", {"kind": "median"}, 61.0)]
        extra, report = carry.carry_forward(live, _state(dt.timedelta(hours=1)), now=NOW)
        self.assertEqual(report["skipped_live"], 1)
        self.assertEqual([n for n, _, _ in extra], ["gcinsight_maturity_score"])

    def test_the_combined_batch_has_no_duplicates(self):
        live = [("gcinsight_maturity_percentile", {"kind": "median"}, 61.0)]
        extra, _ = carry.carry_forward(live, _state(dt.timedelta(hours=1)), now=NOW)
        combined = live + extra
        self.assertEqual(guard.check_no_duplicates(combined), len(combined))

    def test_label_order_does_not_defeat_the_duplicate_filter(self):
        """`{stack,version}` and `{version,stack}` are the same series."""
        live = [("gcinsight_maturity_score", {"version": "1", "stack": "obs-hub-dev"}, 49.0)]
        _, report = carry.carry_forward(live, _state(dt.timedelta(hours=1)), now=NOW)
        self.assertEqual(report["skipped_live"], 1)

    def test_stale_state_is_refused_rather_than_republished(self):
        """If T3 breaks, republishing forever would show last month's scores as current."""
        extra, report = carry.carry_forward([], _state(dt.timedelta(days=15)), now=NOW)
        self.assertEqual(extra, [])
        self.assertTrue(report["too_old"])
        self.assertEqual(report["age_seconds"], 15 * 86400)

    def test_the_age_boundary_is_enforced_exactly_at_the_cap(self):
        """Tests the BEHAVIOUR at the boundary, derived from the constant rather than restating it.

        This used to assert `MAX_CARRY_AGE == timedelta(days=14)`, which meant re-tuning the cap for
        T3's new 6-hour cadence failed the test for the wrong reason - the value was the assertion. What
        actually matters is that state just inside the cap is republished and state just outside it is
        not; that holds whatever the cap is set to.
        """
        cap = carry.MAX_CARRY_AGE
        fresh, _ = carry.carry_forward([], _state(cap - dt.timedelta(minutes=1)), now=NOW)
        stale, _ = carry.carry_forward([], _state(cap + dt.timedelta(seconds=1)), now=NOW)
        self.assertEqual(len(fresh), 2, "state just inside the cap must still be republished")
        self.assertEqual(stale, [], "state past the cap must go empty rather than look current")

    def test_the_cap_allows_several_missed_runs_but_not_an_unbounded_number(self):
        """The cap is a judgement, but it has to stay in a defensible band relative to T3's cadence.

        Too tight and a weekend of trouble blanks the dashboards; too loose and a fortnight of stale
        figures presents as current, which is the failure the cap exists to prevent. T3 runs every 6
        hours, so this asserts the cap is worth between 4 and 30 missed runs.
        """
        cadence = dt.timedelta(hours=6)
        missed_runs = carry.MAX_CARRY_AGE / cadence
        self.assertGreaterEqual(missed_runs, 4, "too tight - ordinary downtime would blank the panels")
        self.assertLessEqual(missed_runs, 30, "too loose - stale figures would present as current")

    def test_no_state_is_not_an_error(self):
        extra, report = carry.carry_forward([], None, now=NOW)
        self.assertEqual(extra, [])
        self.assertFalse(report["available"])
        self.assertIsNone(report["age_seconds"])

    def test_unparseable_timestamp_refuses_to_carry(self):
        bad = {"generated_at": "not-a-date", "tier": "t3", "metrics": [["m", {}, 1.0]]}
        extra, report = carry.carry_forward([], bad, now=NOW)
        self.assertEqual(extra, [])
        self.assertTrue(report["too_old"])

    def test_missing_timestamp_refuses_to_carry(self):
        extra, report = carry.carry_forward([], {"tier": "t3", "metrics": []}, now=NOW)
        self.assertEqual(extra, [])
        self.assertTrue(report["too_old"])


class DecommissionedStackTest(unittest.TestCase):
    """A stack that has left the estate must leave the dashboards with it.

    Carry-forward republishes T3's series into every hourly T1 batch. Filtering only by
    `(name, labels)` and age means a DELETED stack's maturity score, Adaptive counts and cardinality
    figures keep being re-stamped with the current time for up to `MAX_CARRY_AGE` - three days of a
    stack that no longer exists reading as live. The estate is discovered fresh every run
    (`gcom.fetch_inventory`), so the live slug set is the authority and carry-forward must respect it.
    """

    def _state_two_stacks(self):
        return _state(dt.timedelta(hours=1), metrics=[
            ["gcinsight_maturity_score", {"stack": "alive", "version": "1"}, 49.0],
            ["gcinsight_maturity_score", {"stack": "decommissioned", "version": "1"}, 71.0],
            ["gcinsight_maturity_percentile", {"kind": "median"}, 50.0],
        ])

    def test_a_stack_absent_from_the_live_estate_is_not_carried(self):
        extra, report = carry.carry_forward(
            [], self._state_two_stacks(), now=NOW, live_stacks={"alive"})
        carried = {l.get("stack") for _, l, _ in extra}
        self.assertNotIn("decommissioned", carried)
        self.assertEqual(report["dropped_absent"], 1)

    def test_the_surviving_stack_is_still_carried(self):
        extra, _ = carry.carry_forward(
            [], self._state_two_stacks(), now=NOW, live_stacks={"alive"})
        self.assertIn("alive", {l.get("stack") for _, l, _ in extra})

    def test_estate_wide_series_carrying_no_stack_label_are_unaffected(self):
        """The percentile is an estate rollup. Dropping it would blank a panel for no reason."""
        extra, _ = carry.carry_forward(
            [], self._state_two_stacks(), now=NOW, live_stacks={"alive"})
        self.assertIn("gcinsight_maturity_percentile", [n for n, _, _ in extra])

    def test_omitting_live_stacks_carries_everything_as_before(self):
        """A caller with no inventory to hand must not silently blank every per-stack series."""
        extra, report = carry.carry_forward([], self._state_two_stacks(), now=NOW)
        self.assertEqual(len(extra), 3)
        self.assertEqual(report["dropped_absent"], 0)

    def test_an_empty_live_estate_is_treated_as_unknown_not_as_zero_stacks(self):
        """An inventory call that returned nothing is a failure, not an estate of zero stacks.

        Honouring it literally would drop every per-stack series at once - the confidently-wrong
        outcome this module exists to prevent.
        """
        extra, report = carry.carry_forward(
            [], self._state_two_stacks(), now=NOW, live_stacks=set())
        self.assertEqual(len(extra), 3)
        self.assertEqual(report["dropped_absent"], 0)

    def test_dropped_count_is_reported_even_when_nothing_was_dropped(self):
        _, report = carry.carry_forward([], self._state_two_stacks(), now=NOW,
                                        live_stacks={"alive", "decommissioned"})
        self.assertEqual(report["dropped_absent"], 0)


class ReportMetricsTest(unittest.TestCase):
    def test_age_is_emitted_so_staleness_is_alertable(self):
        _, report = carry.carry_forward([], _state(dt.timedelta(days=3)), now=NOW)
        metrics = carry.report_metrics(report, "t1")
        by = {n: v for n, _, v in metrics}
        self.assertEqual(by["gcinsight_carry_forward_age_seconds"], float(3 * 86400))
        self.assertEqual(by["gcinsight_carry_forward_series"], 2.0)

    def test_a_refused_carry_still_reports_its_age(self):
        """The whole point: the panels are empty AND the reason is queryable."""
        _, report = carry.carry_forward([], _state(dt.timedelta(days=30)), now=NOW)
        by = {n: v for n, _, v in carry.report_metrics(report, "t1")}
        self.assertEqual(by["gcinsight_carry_forward_series"], 0.0)
        self.assertEqual(by["gcinsight_carry_forward_age_seconds"], float(30 * 86400))

    def test_report_metrics_pass_the_label_guard_and_are_declared(self):
        from collector.emit.budget import CATALOGUE
        _, report = carry.carry_forward([], _state(dt.timedelta(days=1)), now=NOW)
        metrics = carry.report_metrics(report, "t1")
        self.assertEqual(guard.check_all(metrics), len(metrics))
        declared = {(s.name, tuple(sorted(s.labels))) for s in CATALOGUE if s.store == "mimir"}
        for name, labels, _ in metrics:
            self.assertIn((name, tuple(sorted(labels))), declared, f"{name} undeclared")

    def test_no_state_emits_the_count_but_not_an_age(self):
        """A zero age would read as 'fresh'."""
        _, report = carry.carry_forward([], None, now=NOW)
        names = {n for n, _, _ in carry.report_metrics(report, "t1")}
        self.assertIn("gcinsight_carry_forward_series", names)
        self.assertNotIn("gcinsight_carry_forward_age_seconds", names)


class StateKeyTest(unittest.TestCase):
    def test_state_is_keyed_per_tier(self):
        self.assertEqual(carry.state_key("t3"), "state/t3-metrics.json")
        self.assertNotEqual(carry.state_key("t3"), carry.state_key("t2"))

    def test_state_lives_outside_the_views_prefix(self):
        """`views/` is the only prefix the Grafana Infinity user can read (PLAN 6.1)."""
        self.assertFalse(carry.state_key("t3").startswith("views/"))
        self.assertFalse(carry.state_key("t3").startswith("scans/"))

    def test_save_state_round_trips_shape_in_dry_run(self):
        uri = carry.save_state([("m", {"stack": "a"}, 1.0)], "t3", bucket="b", dry_run=True)
        self.assertIn("DRY-RUN", uri)
        self.assertIn("state/t3-metrics.json", uri)


if __name__ == "__main__":
    unittest.main()
