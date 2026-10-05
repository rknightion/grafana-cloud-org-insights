"""Pillar C - the two exclusions and the stickiness ratio, which is where this pillar goes wrong."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit import guard
from collector.emit.budget import CATALOGUE
from collector.pillars import cost, estate, usage
from collector.sources.gcom import user_record

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"
NOW = dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc)


def _load():
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    coverage = Coverage(tier="t2", total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            coverage.record_skipped(str(s["slug"]), "paused")
        else:
            coverage.record_ok(str(s["slug"]))
    return stacks, coverage


def _detail():
    raw = json.loads((TESTDATA / "gcom-instance-users.json").read_text())["items"]
    return {"obs-hub-dev": {"slug": "obs-hub-dev", "users": [user_record(u) for u in raw]}}


class PluginAdoptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        stacks, coverage = _load()
        cls.stacks = stacks
        cls.metrics, cls.views = usage.build(stacks, coverage, now=NOW)

    def test_the_auto_provisioned_datasource_is_excluded(self):
        """grafana-knowledgegraph-datasource is on 271/271. Counted, it is the estate's top plugin."""
        names = {r[" Plugin"] for r in self.views["usage_plugin_adoption"]}
        self.assertNotIn("grafana-knowledgegraph-datasource", names)
        for _, labels, _ in self.metrics:
            self.assertNotEqual(labels.get("kind"), "grafana-knowledgegraph-datasource")

    def test_adoption_matches_the_findings_register(self):
        by = {r[" Plugin"]: r["Stacks"] for r in self.views["usage_plugin_adoption"]}
        self.assertEqual(by["synthetic-monitoring-datasource"], 65)
        self.assertEqual(by["cloudwatch"], 32)
        self.assertEqual(by["yesoreyeram-infinity-datasource"], 27)
        self.assertEqual(by["prometheus"], 17)
        self.assertEqual(by["grafana-datadog-datasource"], 3)

    def test_adoption_counts_stacks_not_instances(self):
        """One stack with 12 Infinity datasources is not 12 stacks' worth of adoption."""
        infinity = [r for r in self.views["usage_plugin_adoption"]
                    if r[" Plugin"] == "yesoreyeram-infinity-datasource"][0]
        self.assertEqual(infinity["Stacks"], 27)
        self.assertGreater(infinity["Total instances"], infinity["Stacks"])

    def test_adoption_is_sorted_most_adopted_first(self):
        counts = [r["Stacks"] for r in self.views["usage_plugin_adoption"]]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_stack_type_counts_are_a_view_and_vendor_names_never_become_metric_labels(self):
        """Datasource types are discovered vendor strings, not a fixed enum, so they belong in S3."""
        expected = sorted(
            (str(stack["slug"]), kind, int(count))
            for stack in self.stacks
            for kind, count in (stack.get("datasourceCnts") or {}).items()
            if count and kind not in usage.EXCLUDED_DATASOURCES
        )
        actual = sorted(
            (row[" Stack"], row["Datasource type"], row["Provisioned instances"])
            for row in self.views["usage_datasource_inventory"]
        )
        self.assertEqual(actual, expected)
        self.assertFalse(any(labels for name, labels, _value in self.metrics
                             if name.startswith("gcinsight_usage_datasource")))
        emitted_names = {name for name, _labels, _value in self.metrics}
        self.assertNotIn("gcinsight_usage_plugin_adoption", emitted_names)
        self.assertEqual(
            [(name, labels, value) for name, labels, value in self.metrics
             if name == "gcinsight_usage_synthetic_monitoring_datasource_stacks"],
            [("gcinsight_usage_synthetic_monitoring_datasource_stacks", {}, 65.0)],
        )

    def test_only_the_distinct_type_count_is_published_as_the_estate_metric(self):
        """The billing total is a lossier inventory projection, so no per-stack count is justified."""
        emitted = [(name, labels, value) for name, labels, value in self.metrics
                   if name.startswith("gcinsight_usage_datasource_")]
        self.assertEqual(emitted, [("gcinsight_usage_datasource_types_distinct", {}, 35.0)])
        declared = {s.name: s for s in CATALOGUE if s.store == "mimir"}
        self.assertEqual(declared["gcinsight_usage_datasource_types_distinct"].series, 1)


class EnterpriseCatalogueTest(unittest.TestCase):
    def test_real_two_plugin_contract_reaches_composed_views_without_raw_metadata(self):
        from collector.httpclient import ReadOnlyClient, Response
        from collector.sources import plugin_catalog
        from collector.pillars import compose
        names = ("grafana-aurora-datasource", "yesoreyeram-infinity-datasource")
        stacks = [{"slug": "live", "datasourceCnts": dict.fromkeys(names, 2)}]
        requests = []

        def transport(request, timeout):
            requests.append(request)
            name = request.full_url.rsplit("/", 1)[-1]
            path = pathlib.Path(__file__).parent / "fixtures" / ("plugin_catalog." + name + ".json")
            body = json.loads(path.read_text())["body"]
            body["author"] = {"email": "discard@example.invalid"}
            body["details"] = "discard raw public details"
            return Response(200, json.dumps(body).encode(), request.full_url)

        catalogue = plugin_catalog.fetch_catalogue(ReadOnlyClient(transport=transport), stacks)
        _, views, _ = compose.build_all(
            stacks, Coverage(tier="t2", total=1),
            stack_detail={"live": {"plugin_catalogue": catalogue}},
        )
        by = {r[" Plugin"]: r for r in views["usage_enterprise_catalogue"]}
        self.assertIs(by[names[0]]["Enterprise (current catalogue)"], True)
        self.assertIs(by[names[1]]["Enterprise (current catalogue)"], False)
        self.assertEqual(len(requests), 2)
        self.assertNotIn("discard", json.dumps(catalogue))
        self.assertNotIn("discard", json.dumps(views))
        for name in names:
            self.assertEqual(by[name]["Catalogue stacks measured"], 1)
            self.assertEqual(by[name]["Configured instances (measured)"], 2)

    def test_current_catalogue_is_nullable_and_only_joins_live_stack_detail(self):
        stacks = [
            {"slug": "live", "datasourceCnts": {"aurora": 2, "infinity": 1}},
            {"slug": "unknown"},
        ]
        detail = {"live": {"plugin_catalogue": {
            "aurora": {"available": True, "enterprise": True, "status": "enterprise",
                       "basis": "current_public_catalogue"},
            "infinity": {"available": True, "enterprise": False, "status": "active",
                         "basis": "current_public_catalogue"},
        }}, "departed": {"plugin_catalogue": {"ghost": {"enterprise": True}}}}
        _, views = usage.build(stacks, Coverage(tier="t2", total=2), detail, NOW)
        by = {r[" Plugin"]: r for r in views["usage_enterprise_catalogue"]}
        self.assertEqual(set(by), {"aurora", "infinity"})
        self.assertIs(by["aurora"]["Enterprise (current catalogue)"], True)
        self.assertIs(by["infinity"]["Enterprise (current catalogue)"], False)
        self.assertEqual(by["aurora"]["Inventory stacks measured"], 1)
        self.assertEqual(by["aurora"]["Estate stacks"], 2)
        self.assertEqual(by["aurora"]["Configured instances (measured)"], 2)
        self.assertEqual(by["aurora"]["Catalogue stacks measured"], 1)
        _, unknown = usage.build(stacks, Coverage(tier="t2", total=2), now=NOW)
        for row in unknown["usage_enterprise_catalogue"]:
            self.assertIsNone(row["Enterprise (current catalogue)"])
            self.assertEqual(row["Catalogue stacks measured"], 0)
        self.assertIsNone(unknown["usage_plugin_adoption"][0]["Share of estate %"])

    def test_missing_metadata_never_becomes_false_or_empty_enterprise_result(self):
        stacks = [{"slug": "a", "datasourceCnts": {"aurora": 2}},
                  {"slug": "b", "datasourceCnts": {"aurora": 1}}]
        for record in ({}, {"available": False}, {"available": True, "enterprise": False}):
            _, views = usage.build(stacks, Coverage(tier="t2", total=2),
                                   {"a": {"plugin_catalogue": {"aurora": record}}}, NOW)
            row = views["usage_enterprise_catalogue"][0]
            self.assertIsNone(row["Enterprise (current catalogue)"])
            self.assertEqual(row["Configured instances (measured)"], 3)
            self.assertEqual(row["Catalogue stacks measured"], 0)
        _, views = usage.build([{"slug": "a"}], Coverage(tier="t2", total=1), now=NOW)
        self.assertIsNone(views["usage_enterprise_catalogue"][0]["Configured instances (measured)"])


class StickinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, coverage = _load()
        cls.metrics, cls.views = usage.build(cls.stacks, coverage, now=NOW)
        cls.by = {(n, tuple(sorted(l.items()))): v for n, l, v in cls.metrics}

    def test_stickiness_divides_daily_by_active_not_by_billed(self):
        """Deliberately not a money figure: 'of those with access, who showed up today'."""
        daily = sum(s.get("dailyUserCnt") or 0 for s in self.stacks)
        active = sum(s.get("currentActiveUsers") or 0 for s in self.stacks)
        billed = sum(s.get("billingActiveUsers") or 0 for s in self.stacks)
        self.assertEqual((daily, active, billed), (434, 973, 811))
        got = self.by[("gcinsight_usage_stickiness_ratio", ())]
        self.assertEqual(got, round(daily / active, 4))
        self.assertNotEqual(got, round(daily / billed, 4))

    def test_missing_daily_activity_is_not_reported_as_dormancy_or_zero_stickiness(self):
        """Unavailable daily counts are not evidence that active users were dormant."""
        for stack in (
            {"slug": "missing-daily", "currentActiveUsers": 5},
            {"slug": "null-daily", "currentActiveUsers": 5, "dailyUserCnt": None},
        ):
            with self.subTest(stack=stack["slug"]):
                metrics, views = usage.build([stack], Coverage(tier="t1", total=1), now=NOW)
                row = views["usage"][0]
                self.assertIsNone(row["Users (daily)"])
                self.assertIsNone(row["Stickiness"])
                self.assertEqual(views["usage_dormant_stacks"], [])
                self.assertNotIn("gcinsight_usage_stickiness_ratio", {name for name, _, _ in metrics})
                self.assertIsNone(views["usage_summary"][0]["Value"])

    def test_incomplete_daily_counts_withhold_the_unqualified_total_and_estate_ratio(self):
        for unknown in ({}, {"dailyUserCnt": None}):
            with self.subTest(unknown=unknown):
                stacks = [
                    {"slug": "measured", "currentActiveUsers": 5, "dailyUserCnt": 2},
                    {"slug": "unknown", "currentActiveUsers": 5, **unknown},
                ]
                metrics, views = usage.build(stacks, Coverage(tier="t1", total=2), now=NOW)
                summary = {row[" Metric"]: row["Value"] for row in views["usage_summary"]}
                self.assertIsNone(summary["Daily users"])
                self.assertEqual(summary["Active users"], 10)
                self.assertIsNone(summary["Stickiness (daily / active users, estate)"])
                self.assertNotIn("gcinsight_usage_stickiness_ratio", {n for n, _, _ in metrics})
                self.assertEqual(views["usage_dormant_stacks"], [])
                rows = {row[" Stack"]: row for row in views["usage"]}
                self.assertEqual(rows["measured"]["Stickiness"], 0.4)
                self.assertIsNone(rows["unknown"]["Stickiness"])

    def test_incomplete_active_counts_withhold_the_unqualified_total_and_estate_ratio(self):
        for unknown in ({}, {"currentActiveUsers": None}):
            with self.subTest(unknown=unknown):
                stacks = [
                    {"slug": "measured", "currentActiveUsers": 5, "dailyUserCnt": 2},
                    {"slug": "unknown", "dailyUserCnt": 1, **unknown},
                ]
                metrics, views = usage.build(stacks, Coverage(tier="t1", total=2), now=NOW)
                summary = {row[" Metric"]: row["Value"] for row in views["usage_summary"]}
                self.assertIsNone(summary["Active users"])
                self.assertEqual(summary["Daily users"], 3)
                self.assertIsNone(summary["Stickiness (daily / active users, estate)"])
                self.assertNotIn("gcinsight_usage_stickiness_ratio", {n for n, _, _ in metrics})
                rows = {row[" Stack"]: row for row in views["usage"]}
                self.assertEqual(rows["measured"]["Stickiness"], 0.4)
                self.assertIsNone(rows["unknown"]["Stickiness"])
                self.assertEqual(views["usage_dormant_stacks"], [])

    def test_fully_measured_counts_preserve_zero_and_positive_totals(self):
        for daily in (0, 2):
            with self.subTest(daily=daily):
                stacks = [
                    {"slug": "measured", "currentActiveUsers": 5, "dailyUserCnt": daily},
                    {"slug": "zero", "currentActiveUsers": 0, "dailyUserCnt": 0},
                ]
                metrics, views = usage.build(stacks, Coverage(tier="t1", total=2), now=NOW)
                summary = {row[" Metric"]: row["Value"] for row in views["usage_summary"]}
                self.assertEqual(summary["Active users"], 5)
                self.assertEqual(summary["Daily users"], daily)
                self.assertEqual(summary["Stickiness (daily / active users, estate)"], daily / 5)
                self.assertEqual(
                    [value for name, _, value in metrics
                     if name == "gcinsight_usage_stickiness_ratio"], [daily / 5],
                )
        metrics, views = usage.build(
            [{"slug": "zero", "currentActiveUsers": 0, "dailyUserCnt": 0}],
            Coverage(tier="t1", total=1), now=NOW,
        )
        summary = {row[" Metric"]: row["Value"] for row in views["usage_summary"]}
        self.assertEqual(summary["Active users"], 0)
        self.assertEqual(summary["Daily users"], 0)
        self.assertIsNone(summary["Stickiness (daily / active users, estate)"])
        self.assertNotIn("gcinsight_usage_stickiness_ratio", {n for n, _, _ in metrics})

    def test_known_daily_activity_retains_measured_dormancy_and_stickiness(self):
        stacks = [
            {"slug": "active-today", "currentActiveUsers": 5, "dailyUserCnt": 2},
            {"slug": "dormant", "currentActiveUsers": 5, "dailyUserCnt": 0},
            {"slug": "no-active-users", "currentActiveUsers": 0, "dailyUserCnt": 0},
        ]
        metrics, views = usage.build(stacks, Coverage(tier="t1", total=3), now=NOW)
        rows = {row[" Stack"]: row for row in views["usage"]}
        self.assertEqual(rows["active-today"]["Stickiness"], 0.4)
        self.assertEqual(rows["dormant"]["Stickiness"], 0.0)
        self.assertIsNone(rows["no-active-users"]["Stickiness"])
        self.assertEqual([row[" Stack"] for row in views["usage_dormant_stacks"]], ["dormant"])
        self.assertEqual(
            next(value for name, _, value in metrics if name == "gcinsight_usage_stickiness_ratio"),
            0.2,
        )

    def test_estate_stickiness_is_absent_without_an_active_user_denominator(self):
        metrics, _ = usage.build(
            [{"slug": "no-users", "currentActiveUsers": 0, "dailyUserCnt": 0}],
            Coverage(tier="t1", total=1),
            now=NOW,
        )
        self.assertNotIn("gcinsight_usage_stickiness_ratio", {name for name, _, _ in metrics})

    def test_per_stack_stickiness_is_none_when_there_are_no_users(self):
        """0.0 would render as 'nobody uses it'; the truth is there is nobody to use it."""
        nousers = [r for r in self.views["usage"] if r["Users (active)"] == 0]
        self.assertTrue(nousers)
        for r in nousers:
            self.assertIsNone(r["Stickiness"])

    def test_dormant_stacks_exclude_the_zero_user_test_leftovers(self):
        """A stack with no users at all is Pillar A's leakage finding, not a dormancy finding."""
        for r in self.views["usage_dormant_stacks"]:
            self.assertGreater(r["Users (active)"], 0)
            self.assertEqual(r["Users (daily)"], 0)


class SignalAdoptionTest(unittest.TestCase):
    def test_signal_adoption_thresholds_at_the_floor_not_at_zero(self):
        """~178 stacks report exactly 2 series. '>0' claims near-universal adoption of everything."""
        stacks, coverage = _load()
        metrics, _ = usage.build(stacks, coverage, now=NOW)
        by = {l["signal"]: v for n, l, v in metrics if n == "gcinsight_usage_stacks_by_signal"}
        above_zero = len([s for s in stacks if (s.get("hmInstancePromCurrentUsage") or 0) > 0])
        self.assertLess(by["metrics"], above_zero)
        self.assertEqual(usage.USAGE_FLOOR, cost.USAGE_FLOOR, "one floor, shared with Pillar B")

    def test_graphite_is_used_by_very_few_stacks(self):
        """The Graphite mis-attribution trap: a naive breakdown reported ~136 stacks; it is a handful."""
        stacks, coverage = _load()
        metrics, _ = usage.build(stacks, coverage, now=NOW)
        by = {l["signal"]: v for n, l, v in metrics if n == "gcinsight_usage_stacks_by_signal"}
        self.assertLess(by["graphite"], 10)


class UserRecencyTest(unittest.TestCase):
    def test_recency_buckets_only_appear_when_t2_detail_is_present(self):
        stacks, coverage = _load()
        metrics, views = usage.build(stacks, coverage, now=NOW)
        self.assertNotIn("gcinsight_usage_users_last_seen_bucket", {n for n, _, _ in metrics})
        self.assertNotIn("usage_user_recency", views)

    def test_recency_buckets_are_emitted_with_detail_and_sum_to_the_user_count(self):
        stacks, coverage = _load()
        detail = _detail()
        metrics, views = usage.build(stacks, coverage, stack_detail=detail, now=NOW)
        buckets = {l["kind"]: v for n, l, v in metrics
                   if n == "gcinsight_usage_users_last_seen_bucket"}
        self.assertEqual(set(buckets), set(usage.LAST_SEEN_BUCKETS))
        self.assertEqual(sum(buckets.values()), 12)
        self.assertEqual(len(views["usage_user_recency"]), 12)

    def test_a_user_who_has_never_logged_in_buckets_as_never_not_as_old(self):
        self.assertEqual(usage._bucket(None), "never")
        self.assertEqual(usage._bucket(0.5), "7d")
        self.assertEqual(usage._bucket(45), "90d")
        self.assertEqual(usage._bucket(400), "older")

    def test_displayed_age_and_bucket_use_the_same_rounded_value(self):
        stacks = [{"slug": "example", "currentActiveUsers": 1}]
        coverage = Coverage(tier="t2", total=1)
        detail = {"example": {"users": [{
            "login": "boundary@example.test",
            "lastSeenAt": "2026-08-09T23:02:24+00:00",
        }]}}
        _, views = usage.build(stacks, coverage, stack_detail=detail,
                               now=dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc))
        row = views["usage_user_recency"][0]
        self.assertEqual(row["Last seen (days)"], 7.0)
        self.assertEqual(row["Recency"], "7d")

    def test_identities_are_in_the_view_and_never_in_a_label(self):
        """PII is in scope by decision. The rule that survives is CARDINALITY: never a metric label."""
        stacks, coverage = _load()
        metrics, views = usage.build(stacks, coverage, stack_detail=_detail(), now=NOW)
        emails = {r["User"] for r in views["usage_user_recency"]}
        # An email-shaped identity from the fixture. The point of the assertion is that an address
        # reaches the VIEW while the loop below proves none reaches a metric label.
        self.assertIn("eva.rossi23@example.com", emails)
        for name, labels, _ in metrics:
            for value in labels.values():
                self.assertNotIn("@", value, f"{name} carries an email-shaped label value")

    def test_detail_summary_states_its_denominator(self):
        stacks, coverage = _load()
        _, views = usage.build(stacks, coverage, stack_detail=_detail(), now=NOW)
        self.assertEqual(views["usage_summary"][0][" Metric"], "Stacks with user detail")
        self.assertIn("1 of 267", str(views["usage_summary"][0]["Value"]))


class UsageGuardAndBudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        stacks, coverage = _load()
        cls.metrics, _ = usage.build(stacks, coverage, stack_detail=_detail(), now=NOW)
        cls.stacks, cls.coverage = stacks, coverage

    def test_every_metric_passes_the_label_guard(self):
        self.assertEqual(guard.check_all(self.metrics), len(self.metrics))

    def test_every_emitted_metric_is_declared_in_the_budget(self):
        declared = {(s.name, tuple(sorted(s.labels))) for s in CATALOGUE if s.store == "mimir"}
        for name, labels, _ in self.metrics:
            self.assertIn((name, tuple(sorted(labels))), declared, f"{name} undeclared")

    def test_all_three_pillars_together_emit_no_duplicate_series(self):
        dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())
        combined = (
            estate.build(self.stacks, self.coverage)[0]
            + cost.build(self.stacks, self.coverage, dataplane)[0]
            + self.metrics
        )
        self.assertEqual(guard.check_no_duplicates(combined), len(combined))

    def test_dashboard_analytics_live_capability_is_stated_without_stale_coverage(self):
        _, views = usage.build(self.stacks, self.coverage, now=NOW)
        row = [r for r in views["usage_summary"]
               if "per-panel" in r[" Metric"] or "per-dashboard" in r[" Metric"].lower()]
        self.assertTrue(row)
        value = str(row[0]["Value"])
        self.assertIn("Live", value)
        self.assertIn("Dashboard usage", value)
        for stale_claim in ("Phase 2", "8 regional", "94 stacks"):
            self.assertNotIn(stale_claim, value)


if __name__ == "__main__":
    unittest.main()
