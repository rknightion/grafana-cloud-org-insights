from __future__ import annotations

import datetime as dt
import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit.guard import ALLOWED_LABELS, UnboundedLabel, check, check_all, series_count
from collector.pillars import estate

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


class GuardTest(unittest.TestCase):
    def test_allowed_labels_pass(self):
        check("gcinsight_x", {"stack": "obs-hub-dev", "region": "prod-eu-west-2", "role": "admin"})

    def test_unknown_label_key_is_an_error(self):
        for key in ("dashboard_uid", "user", "login", "email", "rule_name", "metric"):
            with self.assertRaises(UnboundedLabel, msg=f"{key} should be refused"):
                check("gcinsight_x", {key: "whatever"})

    def test_email_shaped_value_is_refused_even_under_an_allowed_key(self):
        with self.assertRaises(UnboundedLabel):
            check("gcinsight_x", {"stack": "a.b@example.com"})

    def test_grafana_build_string_is_refused(self):
        """258 stacks share one build and 13 do not; the string churns on every upgrade."""
        with self.assertRaises(UnboundedLabel):
            check("gcinsight_x", {"version": "13.2.0-31000685436"})

    def test_short_rubric_version_is_allowed(self):
        check("gcinsight_maturity_score", {"stack": "a", "version": "1"})

    def test_coverage_component_is_a_closed_enum(self):
        """Allowing the key without its fixed values would make the new dimension unbounded."""
        check("gcinsight_coverage_unscored", {"component": "profiles", "reason": "not_in_use"})
        check("gcinsight_coverage_unscored", {"component": "row", "reason": "ephemeral"})
        with self.assertRaises(UnboundedLabel):
            check("gcinsight_coverage_unscored", {"component": "tenant-authored", "reason": "x"})

    def test_overlong_value_is_refused(self):
        with self.assertRaises(UnboundedLabel):
            check("gcinsight_x", {"kind": "k" * 65})

    def test_allow_list_excludes_every_known_unbounded_dimension(self):
        for banned in ("metric", "metric_name", "dashboard_uid", "dashboardUid", "user", "login",
                       "email", "email_domain", "rule_name", "sa_name", "slug_name"):
            self.assertNotIn(banned, ALLOWED_LABELS)


class EstatePillarTest(unittest.TestCase):
    """The guard is only worth anything if the real pillars pass through it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]

    def setUp(self) -> None:
        self.coverage = Coverage(tier="t1", total=len(self.stacks))
        for s in self.stacks:
            if s.get("status") == "paused":
                self.coverage.record_skipped(str(s["slug"]), "paused")
            else:
                self.coverage.record_ok(str(s["slug"]))
        self.metrics, self.views = estate.build(
            self.stacks, self.coverage, now=dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc)
        )

    def test_every_emitted_metric_passes_the_guard(self):
        self.assertEqual(check_all(self.metrics), len(self.metrics))

    def test_pillar_a_series_count_is_modest(self):
        """Pillar A is estate-level rollups, so it must not scale with stack count."""
        total = len(self.metrics)
        self.assertLess(total, 60, f"Pillar A emitted {total} series: {series_count(self.metrics)}")

    def test_headline_figures_match_the_findings_register(self):
        by = {}
        for name, labels, value in self.metrics:
            by[(name, tuple(sorted(labels.items())))] = value
        self.assertEqual(by[("gcinsight_estate_stacks", (("status", "total"),))], 271)
        self.assertEqual(by[("gcinsight_estate_stacks", (("status", "paused"),))], 4)
        self.assertEqual(by[("gcinsight_estate_dashboards", ())], 7416)
        self.assertEqual(by[("gcinsight_estate_active_users", ())], 973)
        self.assertEqual(by[("gcinsight_cost_billed_users", ())], 811)
        self.assertEqual(by[("gcinsight_estate_test_leftover_stacks", (("kind", "idle"),))], 41)
        self.assertEqual(by[("gcinsight_estate_test_leftover_stacks", (("kind", "billing"),))], 2)
        self.assertEqual(by[("gcinsight_estate_us_region_stacks", ())], 78)

    def test_view_leads_with_a_space_prefixed_column(self):
        """Infinity's backend parser alphabetises columns; a leading space forces stack first."""
        self.assertEqual(list(self.views["estate"][0])[0], " Stack")

    def test_leftovers_are_split_by_whether_they_cost_anything(self):
        """The review's F1: conflating free leftovers with billing ones produced a bogus saving."""
        idle = self.views["estate_leftovers_idle"]
        billing = self.views["estate_leftovers_billing"]
        self.assertEqual(len(idle), 41)
        self.assertEqual(len(billing), 2)
        for row in idle + billing:
            self.assertTrue(row[" Stack"].startswith("test"))
        for row in idle:
            self.assertEqual(row["Active series"], 0, "an idle leftover must cost nothing")
        self.assertEqual(billing[0][" Stack"], "testlab001")
        self.assertEqual(billing[0]["Active series"], 68825)

    def test_admin_share_is_none_rather_than_zero_when_there_are_no_users(self):
        """A stack with no users has no meaningful admin share; 0% would read as 'healthy'."""
        nousers = [r for r in self.views["estate"] if r["Users (active)"] == 0]
        self.assertTrue(nousers)
        for row in nousers:
            self.assertIsNone(row["Admin share %"])


if __name__ == "__main__":
    unittest.main()
