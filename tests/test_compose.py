"""Tier interaction (PLAN 4.0, 5.3).

The defect this file exists for was invisible to every per-pillar test and showed up only on a live
PromQL query: **T1 emitted `gcinsight_cost_stacks_without_adaptive = 0` and every
`maturity_stacks_by_tier = 0`**, because those are structurally zero without the data plane. T1 runs
hourly and T3 weekly, so the zeros landed at a later timestamp and erased the real weekly values  -  and
the carry-forward could not rescue them, because it correctly refuses to republish a series the live
tier claims to own.

The rule, enforced below: **a pillar emits a metric only when it has the input to compute it.** A gap
must be an absent series, never a zero.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit import carry, guard
from collector.emit.budget import CATALOGUE, CEILING
from collector.pillars import compose
from collector.sources.gcom import user_record

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

# Metrics that cannot exist without the T3 data-plane sweep. Named explicitly because the whole failure
# mode is one of these quietly appearing as 0 on an hourly tier.
DATAPLANE_ONLY = frozenset({
    "gcinsight_adaptive_recommendations",
    "gcinsight_cost_adaptive_rules_applied_total",
    "gcinsight_cost_stacks_without_adaptive",
    "gcinsight_maturity_score",
    "gcinsight_maturity_percentile",
    "gcinsight_maturity_stacks_by_tier",
    "gcinsight_maturity_unscored",
    "gcinsight_risk_collectors_total",
    "gcinsight_risk_stacks_pipelines_no_collectors",
    "gcinsight_value_savings_identified_series",
})

# Metrics that need the T2 per-stack detail sweep.
DETAIL_ONLY = frozenset({
    "gcinsight_usage_users_last_seen_bucket",
    "gcinsight_risk_plugin_drift_stacks",
})

SERVICE_ACCOUNTS_ONLY = frozenset({
    "gcinsight_risk_service_accounts_total",
})


def _coverage(stacks, tier="t1"):
    coverage = Coverage(tier=tier, total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            coverage.record_skipped(str(s["slug"]), "paused")
        else:
            coverage.record_ok(str(s["slug"]))
    return coverage


def _load():
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())
    # This historical envelope predates `?verbose=true`. The tier-contract test needs one complete
    # synthetic recommendations measurement so it can prove the savings series is not permanently
    # silenced; the source-specific tests cover parsing the real verbose fields.
    for record in dataplane.values():
        am = record.get("adaptive_metrics") or {}
        if not am.get("available"):
            continue
        pending = am.get("recommendations_pending") or 0
        am.update({
            "recommendations_available": True,
            "recommendation_records_total": pending,
            "recommendation_records_with_series_counts": pending,
            "recommendation_records_missing_series_counts": 0,
            "series_counts_complete": True,
            "remediable_series": pending * 10,
            "remediable_series_unused": pending * 5,
        })
    users = json.loads((TESTDATA / "gcom-instance-users.json").read_text())["items"]
    # `service_accounts_state: "ok"` is what makes an EMPTY list mean "none" rather than "not read".
    # Without it the SA metric is correctly withheld, which is the behaviour this fixture is not testing.
    detail = {"obs-hub": {"slug": "obs-hub", "users": [user_record(u) for u in users],
                            "service_accounts": [], "service_accounts_state": "ok", "plugins": []}}
    return stacks, dataplane, detail


class GapsAreAbsentNotZeroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane, cls.detail = _load()
        cls.t1, _ = compose.build_all(cls.stacks, _coverage(cls.stacks))
        cls.t3, _ = compose.build_all(cls.stacks, _coverage(cls.stacks, "t3"),
                                      dataplane=cls.dataplane)
        cls.t2, _ = compose.build_all(cls.stacks, _coverage(cls.stacks, "t2"),
                                      stack_detail=cls.detail,
                                      service_accounts={
                                          "obs-hub": {"state": "ok", "accounts": [], "total": 0}
                                      })

    def test_no_dataplane_only_metric_is_emitted_without_the_dataplane(self):
        emitted = {n for n, _, _ in self.t1}
        leaked = emitted & DATAPLANE_ONLY
        self.assertEqual(leaked, set(), f"T1 emitted data-plane metrics as zeros: {sorted(leaked)}")

    def test_no_detail_only_metric_is_emitted_without_the_detail_sweep(self):
        emitted = {n for n, _, _ in self.t1}
        leaked = emitted & DETAIL_ONLY
        self.assertEqual(leaked, set(), f"T1 emitted T2-only metrics: {sorted(leaked)}")

    def test_no_service_account_metric_is_emitted_without_its_own_sweep(self):
        emitted = {n for n, _, _ in self.t1}
        self.assertEqual(emitted & SERVICE_ACCOUNTS_ONLY, set())

    def test_the_dataplane_metrics_do_appear_when_the_dataplane_is_present(self):
        """The other half of the contract  -  the guard must not have silenced them permanently."""
        emitted = {n for n, _, _ in self.t3}
        missing = DATAPLANE_ONLY - emitted
        self.assertEqual(missing, set(), f"T3 failed to emit: {sorted(missing)}")

    def test_the_detail_metrics_do_appear_with_the_detail_sweep(self):
        emitted = {n for n, _, _ in self.t2}
        self.assertEqual(DETAIL_ONLY - emitted, set())

    def test_the_service_account_metric_appears_with_its_own_sweep(self):
        emitted = {n for n, _, _ in self.t2}
        self.assertEqual(SERVICE_ACCOUNTS_ONLY - emitted, set())

    def test_stack_detail_cannot_mask_a_failed_service_account_sweep(self):
        """The old merged input made service-account failure look fresh whenever users/plugins worked."""
        metrics, views = compose.build_all(
            self.stacks, _coverage(self.stacks, "t2"), stack_detail=self.detail,
        )
        self.assertNotIn("gcinsight_risk_service_accounts_total", {n for n, _, _ in metrics})
        self.assertNotIn("risk_service_accounts", views)

    def test_t1_is_a_strict_subset_of_t3_by_metric_name(self):
        """Anything T1 knows, T3 knows. A name only T1 emits would be a tier-ownership mistake."""
        only_t1 = {n for n, _, _ in self.t1} - {n for n, _, _ in self.t3}
        self.assertEqual(only_t1, set(), f"emitted by T1 but not T3: {sorted(only_t1)}")

    def test_the_headline_findings_survive_a_t1_run_landing_after_a_t3_run(self):
        """End-to-end reproduction of the live defect: T3 publishes, then T1 publishes, and the
        combined view must still carry the real values."""
        state = {"generated_at": "2026-08-17T20:00:00+00:00", "tier": "t3",
                 "metrics": [[n, dict(l), v] for n, l, v in self.t3]}
        import datetime as dt
        carried, report = carry.carry_forward(
            self.t1, state, now=dt.datetime(2026, 8, 17, 20, 30, tzinfo=dt.timezone.utc)
        )
        combined = self.t1 + carried
        guard.check_no_duplicates(combined)
        by = {(n, tuple(sorted(l.items()))): v for n, l, v in combined}
        self.assertEqual(by[("gcinsight_cost_stacks_without_adaptive", ())], 106.0)
        self.assertEqual(by[("gcinsight_risk_stacks_pipelines_no_collectors", ())], 77.0)
        tiers = {l["kind"]: v for (n, ls), v in by.items() if n == "gcinsight_maturity_stacks_by_tier"
                 for l in [dict(ls)]}
        self.assertGreater(sum(tiers.values()), 0, "the leaderboard was flattened to zero")
        self.assertGreater(report["carried"], 0)


class ViewsAreNeverBlankedByAThinTierTest(unittest.TestCase):
    """The views analogue of the zeros defect, and it bit harder.

    Every tier writes every view it returns, to the same S3 keys. So a tier without the data must **omit**
    the view, not return an empty one  -  otherwise it overwrites a richer tier's table.
    **Measured: a T3 run blanked `views/risk_access_policies.json` from 754 rows to 0**, because only T1
    fetches access policies. An empty security table reads as "there are no access policies".
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane, cls.detail = _load()
        cls.policies = [{"name": "p", "region": "us", "realms": [{"type": "org"}],
                         "scopes": ["stacks:read"], "createdAt": "2026-01-01"}]
        cls.rich, cls.rich_views = compose.build_all(
            cls.stacks, _coverage(cls.stacks, "t3"), dataplane=cls.dataplane,
            stack_detail=cls.detail, access_policies=cls.policies)
        cls.thin, cls.thin_views = compose.build_all(cls.stacks, _coverage(cls.stacks))

    def test_a_thin_tier_emits_no_empty_view_that_a_rich_tier_populates(self):
        offenders = []
        for name, rows in self.thin_views.items():
            rich_rows = self.rich_views.get(name)
            if rich_rows and not rows:
                offenders.append(f"{name} (rich has {len(rich_rows)} rows, thin returns 0)")
        self.assertEqual(offenders, [], "these views would be blanked by a thin tier: "
                                        + "; ".join(offenders))

    def test_the_access_policy_view_is_absent_without_policies_not_empty(self):
        """The exact regression: T3 has no access policies and must not publish an empty table."""
        _, t3_views = compose.build_all(self.stacks, _coverage(self.stacks, "t3"),
                                        dataplane=self.dataplane)
        self.assertNotIn("risk_access_policies", t3_views)
        self.assertIn("risk_access_policies", self.rich_views)
        self.assertEqual(len(self.rich_views["risk_access_policies"]), 1)

    def test_the_fleet_view_is_absent_without_the_dataplane(self):
        self.assertNotIn("risk_fleet_dead", self.thin_views)
        self.assertEqual(len(self.rich_views["risk_fleet_dead"]), 77)

    def test_the_maturity_views_are_absent_without_the_dataplane(self):
        """The rubric is a T3 product end to end; a T1 leaderboard would be all nulls."""
        for name in ("maturity", "maturity_rubric", "maturity_dimensions", "maturity_summary"):
            self.assertNotIn(name, self.thin_views, f"{name} would be blanked by T1")
            self.assertIn(name, self.rich_views)

    def test_the_inventory_derived_views_are_published_by_every_tier(self):
        """The other half: a tier must not withhold what it genuinely has."""
        for name in ("estate", "cost", "cost_summary", "usage", "risk", "risk_summary",
                     "value_summary", "value_benchmarks"):
            self.assertIn(name, self.thin_views, f"{name} should be published from inventory alone")
            self.assertTrue(self.thin_views[name], f"{name} is published but empty")

    def test_every_view_a_thin_tier_publishes_is_also_published_by_a_rich_tier(self):
        only_thin = set(self.thin_views) - set(self.rich_views)
        self.assertEqual(only_thin, set(), f"published by T1 but not T3: {sorted(only_thin)}")


class ComposeContractTest(unittest.TestCase):
    def test_two_pillars_may_not_produce_a_view_of_the_same_name(self):
        stacks, dataplane, detail = _load()
        metrics, views = compose.build_all(stacks, _coverage(stacks), dataplane=dataplane,
                                           stack_detail=detail)
        self.assertGreater(len(views), 20)
        self.assertEqual(len(views), len(set(views)))

    def test_compose_gates_labels_and_duplicates(self):
        stacks, dataplane, detail = _load()
        metrics, _ = compose.build_all(stacks, _coverage(stacks), dataplane=dataplane,
                                        stack_detail=detail)
        self.assertEqual(guard.check_all(metrics), len(metrics))
        self.assertEqual(guard.check_no_duplicates(metrics), len(metrics))

    def test_the_richest_possible_batch_plus_carry_forward_stays_inside_the_ceiling(self):
        """The worst case for the budget: a T1 run republishing everything T3 knows."""
        stacks, dataplane, detail = _load()
        t3, _ = compose.build_all(stacks, _coverage(stacks, "t3"), dataplane=dataplane,
                                   stack_detail=detail)
        t1, _ = compose.build_all(stacks, _coverage(stacks))
        state = {"generated_at": "2026-08-17T20:00:00+00:00", "tier": "t3",
                 "metrics": [[n, dict(l), v] for n, l, v in t3]}
        import datetime as dt
        carried, report = carry.carry_forward(
            t1, state, now=dt.datetime(2026, 8, 17, 20, 30, tzinfo=dt.timezone.utc)
        )
        total = len(t1) + len(carried) + len(carry.report_metrics(report, "t1"))
        self.assertLessEqual(total, CEILING, f"{total} series with carry-forward, ceiling {CEILING}")

    def test_every_metric_in_the_richest_batch_is_declared(self):
        stacks, dataplane, detail = _load()
        metrics, _ = compose.build_all(stacks, _coverage(stacks, "t3"), dataplane=dataplane,
                                        stack_detail=detail)
        declared = {(s.name, tuple(sorted(s.labels))) for s in CATALOGUE if s.store == "mimir"}
        undeclared = {(n, tuple(sorted(l))) for n, l, _ in metrics} - declared
        self.assertEqual(undeclared, set(), f"undeclared: {sorted(undeclared)}")


if __name__ == "__main__":
    unittest.main()


class DisplayNumbersTest(unittest.TestCase):
    """Grafana renders a large float in scientific notation, so a series count reached the dashboard
    as `5.783425e+06`. Nobody reads that as 5.8 million."""

    def test_no_view_value_would_render_in_scientific_notation(self):
        stacks, dataplane, detail = _load()
        coverage = Coverage(tier="t3", total=len(stacks))
        for st in stacks:
            coverage.record_ok(str(st["slug"]))
        _, views = compose.build_all(stacks, coverage, dataplane=dataplane, stack_detail=detail)
        offenders = [
            (name, key, value)
            for name, rows in views.items()
            for row in rows
            for key, value in row.items()
            if isinstance(value, float) and ("e+" in repr(value) or "e-" in repr(value))
        ]
        self.assertEqual(offenders, [], f"these would render in scientific notation: {offenders}")

    def test_a_whole_number_stored_as_a_float_becomes_an_int(self):
        self.assertIsInstance(compose._display_number(5783425.0), int)
        self.assertEqual(compose._display_number(5783425.0), 5783425)

    def test_a_fractional_value_is_left_exactly_as_the_pillar_produced_it(self):
        """Rounding here would flatten a ratio, and a tiny volume would round to zero - turning
        "almost nothing" into "nothing"."""
        self.assertEqual(compose._display_number(0.446), 0.446)
        self.assertEqual(compose._display_number(8.884814276851345e-07), 8.884814276851345e-07)

    def test_booleans_are_not_mistaken_for_numbers(self):
        self.assertIs(compose._display_number(True), True)
        self.assertIs(compose._display_number(False), False)
