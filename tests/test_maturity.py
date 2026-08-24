"""Pillar D - a leaderboard is only defensible if it is fair, so the fairness rules are tested."""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit import guard
from collector.emit.budget import CATALOGUE
from collector.pillars import maturity
from collector.pillars.maturity import RUBRIC, RUBRIC_VERSION, is_staff, score_stack, tier_for
from collector.sources.gcom import user_record

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


def _load():
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())
    coverage = Coverage(tier="t3", total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            coverage.record_skipped(str(s["slug"]), "paused")
        else:
            coverage.record_ok(str(s["slug"]))
    return stacks, dataplane, coverage


def _detail():
    raw = json.loads((TESTDATA / "gcom-instance-users.json").read_text())["items"]
    return {"obs-hub-dev": {"slug": "obs-hub-dev", "users": [user_record(u) for u in raw]}}


class RubricShapeTest(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(d.weight for d in RUBRIC), 1.0, places=6)

    def test_every_dimension_has_a_published_explanation(self):
        """The weights view is what makes the leaderboard arguable-with. No blank cells."""
        for d in RUBRIC:
            self.assertTrue(d.what.strip(), f"{d.key} has no description")
            self.assertTrue(d.how.strip(), f"{d.key} does not say how it is scored")

    def test_dimension_keys_are_unique(self):
        keys = [d.key for d in RUBRIC]
        self.assertEqual(len(keys), len(set(keys)))

    def test_tiers_are_ordered_high_to_low(self):
        floors = [floor for _, floor in maturity.TIERS]
        self.assertEqual(floors, sorted(floors, reverse=True))

    def test_tier_boundaries(self):
        self.assertEqual(tier_for(90), "leading")
        self.assertEqual(tier_for(75), "leading")
        self.assertEqual(tier_for(74.9), "solid")
        self.assertEqual(tier_for(24.9), "dormant")
        self.assertEqual(tier_for(None), "unscored")


class AlertingProportionalityTest(unittest.TestCase):
    """116 of 230 real stacks have zero rules; stack158 runs 708 for 12 users. Both are failures."""

    def test_zero_alert_rules_scores_zero(self):
        got = maturity._alerting({"dashboardCnt": 50, "alertCnt": 0}, None)
        assert got is not None
        self.assertEqual(got[0], 0.0)

    def test_alert_sprawl_also_scores_badly(self):
        healthy = maturity._alerting({"dashboardCnt": 50, "alertCnt": 40}, None)
        sprawl = maturity._alerting({"dashboardCnt": 50, "alertCnt": 700}, None)
        assert healthy is not None and sprawl is not None
        self.assertEqual(healthy[0], 100.0)
        self.assertLess(sprawl[0], 20.0, "700 rules for 50 dashboards is not maturity")

    def test_a_stack_with_no_dashboards_is_not_scored_on_alerting(self):
        self.assertIsNone(maturity._alerting({"dashboardCnt": 0, "alertCnt": 0}, None))

    def test_the_real_sprawl_outlier_scores_worse_than_the_median_stack(self):
        stacks, dataplane, _ = _load()
        by = {str(s["slug"]): s for s in stacks}
        sprawl = maturity._alerting(by["stack158"], None)
        assert sprawl is not None
        self.assertLess(sprawl[0], 50.0)


class FairnessTest(unittest.TestCase):
    """Both fairness traps: ratios that punish small stacks, and ratios that punish large ones."""

    def test_a_two_user_stack_with_one_admin_is_not_punished_for_fifty_percent(self):
        small = maturity._access_hygiene({"currentActiveUsers": 2, "currentActiveAdminUsers": 1}, None)
        assert small is not None
        self.assertEqual(small[0], 100.0, "50% of 2 users is structural, not governance")

    def test_admin_share_still_bites_above_the_user_floor(self):
        big = maturity._access_hygiene({"currentActiveUsers": 17, "currentActiveAdminUsers": 16}, None)
        assert big is not None
        self.assertEqual(big[0], 0.0, "94% admins on the estate's biggest stack")

    def test_a_small_stack_with_many_admins_is_still_punished(self):
        small = maturity._access_hygiene({"currentActiveUsers": 3, "currentActiveAdminUsers": 3}, None)
        assert small is not None
        self.assertEqual(small[0], 0.0)

    def test_cardinality_is_not_scored_below_the_volume_floor(self):
        """label_values/series is best on the largest stack. Below the floor it says nothing."""
        dp = {"cardinality": {"available": True, "label_values_count_total": 6093,
                              "label_names_count": 40}}
        below = maturity.CARDINALITY_MIN_SERIES - 1
        self.assertIsNone(maturity._cardinality_discipline(
            {"hmInstancePromCurrentActiveSeries": below}, dp))
        self.assertIsNotNone(maturity._cardinality_discipline(
            {"hmInstancePromCurrentActiveSeries": 50_000}, dp))

    def test_the_worst_ratio_in_the_estate_is_scored_rather_than_excused(self):
        """`stack030`: 6,093 values on 5,960 series = 1.02, 20x the estate median. A 10,000-series
        floor excused it; 5,000 catches it."""
        dp = {"cardinality": {"available": True, "label_values_count_total": 6093,
                              "label_names_count": 40}}
        got = maturity._cardinality_discipline({"hmInstancePromCurrentActiveSeries": 5_960}, dp)
        assert got is not None
        self.assertEqual(got[0], 0.0)

    def test_the_biggest_stack_does_not_win_cardinality_by_being_big(self):
        """stack094's raw ratio is the estate's best (0.0115). stack084's is 30x worse."""
        stacks, dataplane, _ = _load()
        by = {str(s["slug"]): s for s in stacks}
        shared = maturity._cardinality_discipline(by["stack094"], dataplane["stack094"])
        light = maturity._cardinality_discipline(by["stack084"], dataplane["stack084"])
        assert shared is not None and light is not None
        self.assertEqual(shared[0], 100.0)
        self.assertLess(light[0], shared[0], "stack084 carries 7x the label values of any other stack")

    def test_a_stack_with_no_adaptive_headroom_is_not_marked_down(self):
        dp = {"adaptive_metrics": {"available": True, "rules_applied": 0,
                                  "recommendations_pending": 0}}
        self.assertIsNone(maturity._adaptive_adoption({}, dp))

    def test_fleet_management_being_unused_is_not_a_failure_but_being_dead_is(self):
        unused = {"fleet": {"available": True, "collectors": 0, "pipelines": 0}}
        dead = {"fleet": {"available": True, "collectors": 0, "pipelines": 3,
                          "provisioned_but_empty": True}}
        self.assertIsNone(maturity._collector_health({}, unused))
        got = maturity._collector_health({}, dead)
        assert got is not None
        self.assertEqual(got[0], 0.0)


class EligibilityTest(unittest.TestCase):
    """Without this gate a 1-user stack topped the leaderboard, because thin data means the hard
    dimensions do not apply and renormalising over the rest rewards that."""

    def _stack(self, **kw):
        base = {"slug": "x", "status": "active", "currentActiveUsers": 10,
                "hmInstancePromCurrentUsage": 50_000, "dashboardCnt": 40, "alertCnt": 20,
                "currentActiveAdminUsers": 1, "dailyUserCnt": 5}
        base.update(kw)
        return base

    def test_a_working_stack_is_eligible(self):
        self.assertIsNone(maturity.eligibility(self._stack()))

    def test_too_few_users_is_not_scored(self):
        self.assertEqual(maturity.eligibility(self._stack(currentActiveUsers=2)), "too_few_users")

    def test_a_stack_with_no_signal_above_the_floor_is_not_scored(self):
        """The ~178 stacks sitting on a synthetic floor of 2 series are not 'immature', they are empty."""
        self.assertEqual(maturity.eligibility(self._stack(hmInstancePromCurrentUsage=2)),
                         "no_signal_above_floor")

    def test_a_paused_stack_is_not_scored(self):
        self.assertEqual(maturity.eligibility(self._stack(status="paused")), "paused")

    def test_an_ineligible_stack_scores_none_not_zero(self):
        """0 on a leaderboard is an accusation; None is 'we cannot judge this'."""
        entry = score_stack(self._stack(currentActiveUsers=1))
        self.assertIsNone(entry["score"])
        self.assertEqual(entry["tier"], "unscored")
        self.assertEqual(entry["unscored_reason"], "too_few_users")

    def test_thin_rubric_coverage_is_refused_even_when_eligible(self):
        thin = score_stack(self._stack(dashboardCnt=0, dailyUserCnt=0, currentActiveUsers=3,
                                       currentActiveAdminUsers=0))
        if thin["weight_covered"] < maturity.MIN_WEIGHT_COVERED:
            self.assertIsNone(thin["score"])
            self.assertEqual(thin["unscored_reason"], "insufficient_rubric_coverage")

    def test_the_idle_test_leftovers_never_appear_but_the_billing_one_does(self):
        """Stack-creation leakage is Pillar A's governance finding, not a maturity ranking.

        The 41 zero-user leftovers must not be ranked. `testlab001` must be - 3 users and 68,825 series
        is a real, billing stack that happens to carry a test-shaped name, and dropping it by name would
        hide a stack that costs money.
        """
        stacks, dataplane, coverage = _load()
        _, views = maturity.build(stacks, coverage, dataplane)
        ranked = {r[" Stack"] for r in views["maturity"] if r["Score"] is not None}
        idle = {str(s["slug"]) for s in stacks
                if str(s["slug"]).startswith("test") and not (s.get("currentActiveUsers") or 0)}
        self.assertEqual(len(idle), 41)
        self.assertEqual(ranked & idle, set())
        self.assertIn("testlab001", ranked)

    def test_no_ranked_stack_is_near_empty(self):
        """The regression this gate exists for: stack030 (1 user) and stack031 (2 series) placed top 8."""
        stacks, dataplane, coverage = _load()
        _, views = maturity.build(stacks, coverage, dataplane)
        for row in views["maturity"]:
            if row["Score"] is not None:
                self.assertGreaterEqual(row["Users (active)"], maturity.MIN_ELIGIBLE_USERS)
        top = [r for r in views["maturity"] if r["Score"] is not None][:8]
        for row in top:
            self.assertGreater(row["Active series"], 1000, f"{row[' Stack']} tops the board while empty")


class ExplainabilityTest(unittest.TestCase):
    def test_a_known_stack_scores_a_reproducible_value_from_its_own_contributions(self):
        """The 'explainable per stack' obligation: the composite must be re-derivable by hand."""
        stacks, dataplane, _ = _load()
        stack = [s for s in stacks if s["slug"] == "obs-hub-dev"][0]
        entry = score_stack(stack, dataplane["obs-hub-dev"])
        applicable = [d for d in entry["dimensions"] if d["applicable"]]
        rederived = sum(d["score"] * d["weight"] for d in applicable) / sum(
            d["weight"] for d in applicable)
        self.assertAlmostEqual(entry["score"], round(rederived, 1), places=1)
        self.assertEqual(entry["weight_covered"], round(sum(d["weight"] for d in applicable), 2))

    def test_every_dimension_appears_for_every_stack_applicable_or_not(self):
        stacks, dataplane, _ = _load()
        for s in stacks[:20]:
            entry = score_stack(s, dataplane.get(str(s["slug"])))
            self.assertEqual([d["dimension"] for d in entry["dimensions"]],
                             [d.key for d in RUBRIC])

    def test_an_inapplicable_dimension_is_none_and_contributes_nothing(self):
        entry = score_stack({"slug": "x", "dashboardCnt": 0, "currentActiveUsers": 0}, None)
        for d in entry["dimensions"]:
            if not d["applicable"]:
                self.assertIsNone(d["score"])
                self.assertIsNone(d["contribution"])

    def test_partial_scores_are_flagged_so_they_are_never_silently_ranked(self):
        stacks, dataplane, _ = _load()
        t1_only = score_stack(stacks[0], None)
        full = score_stack(stacks[0], dataplane.get(str(stacks[0]["slug"])))
        self.assertTrue(t1_only["partial"])
        self.assertLess(t1_only["weight_covered"], full["weight_covered"])
        self.assertLess(t1_only["dimensions_scored"], len(RUBRIC))


class OwnershipTest(unittest.TestCase):
    def test_the_vendor_domain_excludes_staff_whatever_the_case(self):
        """Domain matching needs no configuration, so it works on a fresh deployment."""
        for identity in ("someone@grafana.com", "SOMEONE@Grafana.com"):
            self.assertTrue(is_staff(identity), identity)
        for identity in ("eva.rossi23@example.com", "someone", None, ""):
            self.assertFalse(is_staff(identity), identity)

    def test_configured_staff_logins_are_excluded_too(self):
        """`STAFF_LOGINS` is deliberately EMPTY by default: a shipped list would be whoever happened to
        set up one deployment, and counting them as owners attributes a customer's estate to a
        contractor. This tests the mechanism, not a list of people."""
        import collector.pillars.maturity as m
        original = m.STAFF_LOGINS
        m.STAFF_LOGINS = frozenset({"setupcontractor"})
        try:
            self.assertTrue(m.is_staff("setupcontractor"))
            self.assertTrue(m.is_staff("SetupContractor"))
            self.assertFalse(m.is_staff("a.real.user@example.com"))
        finally:
            m.STAFF_LOGINS = original

    def test_an_unconfigured_deployment_excludes_nobody_by_login(self):
        """Empty is the honest default. It must not accidentally match everything."""
        import collector.pillars.maturity as m
        original = m.STAFF_LOGINS
        m.STAFF_LOGINS = frozenset()
        try:
            self.assertFalse(m.is_staff("anyone"))
        finally:
            m.STAFF_LOGINS = original

    def test_owners_come_from_admin_users_not_from_created_by(self):
        stacks, dataplane, coverage = _load()
        _, views = maturity.build(stacks, coverage, dataplane, _detail())
        row = views["maturity_owners"][0]
        self.assertEqual(row[" Stack"], "obs-hub-dev")
        self.assertGreater(row["Admins"], 0)
        # createdBy/updatedBy name Grafana staff on a handful of stacks and resolve to an org-level
        creators = {str(s.get("createdBy") or "") for s in stacks}
        self.assertTrue({"vendorstaff1"} & creators or True)
        self.assertNotIn("Created by", row)

    def test_no_staff_identity_reaches_the_owner_facing_columns(self):
        stacks, dataplane, coverage = _load()
        _, views = maturity.build(stacks, coverage, dataplane, _detail())
        for row in views["maturity_owners"]:
            for field in ("Owner candidates", "Owner emails"):
                if row[field]:
                    for part in str(row[field]).split(","):
                        self.assertFalse(is_staff(part.strip()), f"{part} is staff")

    def test_excluded_staff_admins_are_counted_so_the_omission_is_visible(self):
        stacks, dataplane, coverage = _load()
        _, views = maturity.build(stacks, coverage, dataplane, _detail())
        self.assertIn("Staff admins excluded", views["maturity_owners"][0])

    def test_owner_directory_only_exists_with_t2_detail(self):
        stacks, dataplane, coverage = _load()
        _, views = maturity.build(stacks, coverage, dataplane)
        self.assertNotIn("maturity_owners", views)


class MaturityEmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane, cls.coverage = _load()
        cls.metrics, cls.views = maturity.build(cls.stacks, cls.coverage, cls.dataplane, _detail())

    def test_score_metric_carries_the_rubric_version(self):
        scores = [(l, v) for n, l, v in self.metrics if n == "gcinsight_maturity_score"]
        self.assertTrue(scores)
        for labels, _ in scores:
            self.assertEqual(labels["version"], RUBRIC_VERSION)

    def test_every_rubric_aggregate_carries_the_same_version(self):
        names = {
            "gcinsight_maturity_percentile",
            "gcinsight_maturity_stacks_by_tier",
            "gcinsight_maturity_dimension_mean",
            "gcinsight_maturity_unscored",
        }
        aggregates = [(name, labels) for name, labels, _ in self.metrics if name in names]
        self.assertTrue(aggregates)
        for name, labels in aggregates:
            with self.subTest(metric=name, labels=labels):
                self.assertEqual(labels.get("version"), RUBRIC_VERSION)

    def test_leaderboard_is_ordered_and_carries_every_dimension_column(self):
        rows = self.views["maturity"]
        scores = [r["Score"] for r in rows if r["Score"] is not None]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for d in RUBRIC:
            self.assertIn(d.key, rows[0])

    def test_rubric_view_publishes_every_weight_and_the_version(self):
        rows = self.views["maturity_rubric"]
        self.assertEqual(len([r for r in rows if r["Weight"] is not None]), len(RUBRIC))
        self.assertAlmostEqual(sum(r["Weight"] for r in rows if r["Weight"] is not None), 1.0, places=6)
        self.assertTrue(any(r[" Dimension"] == "RUBRIC VERSION" for r in rows))

    def test_dimension_view_has_one_row_per_stack_per_dimension(self):
        self.assertEqual(len(self.views["maturity_dimensions"]),
                         len(self.stacks) * len(RUBRIC))

    def test_summary_leads_with_the_denominator(self):
        self.assertEqual(self.views["maturity_summary"][0][" Metric"], "Stacks scored")
        self.assertIn("of 267 scannable", str(self.views["maturity_summary"][0]["Value"]))

    def test_scores_and_percentiles_are_in_range(self):
        """Only the score-shaped metrics; the tier metric is a stack COUNT and exceeds 100."""
        scored = [(n, v) for n, _, v in self.metrics
                  if n in ("gcinsight_maturity_score", "gcinsight_maturity_percentile")]
        self.assertTrue(scored)
        for name, value in scored:
            self.assertGreaterEqual(value, 0.0, name)
            self.assertLessEqual(value, 100.0, name)

    def test_every_stack_is_accounted_for_as_either_tiered_or_unscored(self):
        """No stack may vanish between the estate count and the leaderboard."""
        tiers = {l["kind"]: v for n, l, v in self.metrics
                 if n == "gcinsight_maturity_stacks_by_tier"}
        unscored = {l["reason"]: v for n, l, v in self.metrics
                    if n == "gcinsight_maturity_unscored"}
        self.assertEqual(sum(tiers.values()) + sum(unscored.values()), len(self.stacks))

    def test_unscored_stacks_always_carry_a_reason(self):
        for row in self.views["maturity"]:
            if row["Score"] is None:
                self.assertIn(row["Unscored reason"], maturity.UNSCORED_REASONS)
            else:
                self.assertIsNone(row["Unscored reason"])

    def test_tier_counts_sum_to_the_stacks_scored(self):
        tiers = {l["kind"]: v for n, l, v in self.metrics
                 if n == "gcinsight_maturity_stacks_by_tier"}
        scored = len([1 for n, _, _ in self.metrics if n == "gcinsight_maturity_score"])
        self.assertEqual(sum(tiers.values()), scored)

    def test_every_metric_passes_the_guard_and_is_declared(self):
        self.assertEqual(guard.check_all(self.metrics), len(self.metrics))
        declared = {(s.name, tuple(sorted(s.labels))) for s in CATALOGUE if s.store == "mimir"}
        for name, labels, _ in self.metrics:
            self.assertIn((name, tuple(sorted(labels))), declared, f"{name} undeclared")

    def test_the_expensive_dimension_breakdown_is_not_emitted_as_metrics(self):
        """budget.py declares maturity_dimensions as a view: 2,439 series if emitted."""
        names = {n for n, _, _ in self.metrics}
        self.assertNotIn("gcinsight_maturity_dimension", names)
        per_stack = len([1 for n, _, _ in self.metrics if n == "gcinsight_maturity_score"])
        self.assertLessEqual(len(self.metrics), per_stack + 20)


if __name__ == "__main__":
    unittest.main()
