"""T4 estate diff (PLAN 5.6). Test-first on the SELECTION, not just the subtraction.

"Diff the two most recent scans" is the obvious implementation and produces an hour-over-hour delta
under a weekly label - plausible numbers answering the wrong question.
"""

from __future__ import annotations

import datetime as dt
import unittest

from collector.emit import diff

NOW = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.timezone.utc)


def _scans(*ages_hours: float) -> list[tuple[str, dt.datetime]]:
    out = []
    for hours in ages_hours:
        stamp = NOW - dt.timedelta(hours=hours)
        out.append((f"scans/t1/{stamp.strftime('%Y%m%dT%H%M%S%z')}.json", stamp))
    return out


class KeyParsingTest(unittest.TestCase):
    def test_the_real_key_format_written_by_the_s3_emitter_parses(self):
        stamp = diff.parse_key_timestamp("scans/t1/20260817T200302+0000.json")
        self.assertEqual(stamp, dt.datetime(2026, 8, 17, 20, 3, 2, tzinfo=dt.timezone.utc))

    def test_latest_json_and_junk_are_ignored(self):
        self.assertIsNone(diff.parse_key_timestamp("scans/t1/latest.json"))
        self.assertIsNone(diff.parse_key_timestamp("scans/t1/notatimestamp.json"))


class ListScansKeyTest(unittest.TestCase):
    def test_listed_keys_carry_the_full_prefix(self):
        """`aws s3 ls <prefix>/` prints only the object NAME. Returning it bare made load_scan look at
        the bucket root and 404 - caught on a live run, not by a unit test."""
        import unittest.mock as mock
        stdout = ("2026-08-10 20:30:57     888681 20260810T203057+0000.json\n"
                  "2026-08-17 20:27:10     888681 20260817T202710+0000.json\n"
                  "2026-08-17 20:27:12     888681 latest.json\n")
        with mock.patch("subprocess.run",
                        return_value=mock.Mock(returncode=0, stdout=stdout, stderr="")):
            scans = diff.list_scans("t3", bucket="b")
        self.assertEqual([key for key, _ in scans],
                         ["scans/t3/20260817T202710+0000.json",
                          "scans/t3/20260810T203057+0000.json"])
        for key, _ in scans:
            self.assertTrue(key.startswith("scans/t3/"))
        self.assertTrue(all("latest" not in key for key, _ in scans))


class SelectionTest(unittest.TestCase):
    def test_it_picks_the_scan_nearest_seven_days_not_the_second_most_recent(self):
        """The whole point. Hourly scans plus 'two most recent' = an hourly delta labelled weekly."""
        scans = _scans(0, 1, 2, 24, 168, 336)
        latest, baseline = diff.select_baseline(scans, now=NOW)
        self.assertEqual(latest[1], NOW)
        self.assertEqual(baseline[1], NOW - dt.timedelta(hours=168))

    def test_it_prefers_the_closest_candidate_on_either_side_of_the_target(self):
        for hours, expected in ((150, 150), (180, 180)):
            scans = _scans(0, 24, hours)
            _latest, baseline = diff.select_baseline(scans, now=NOW)
            self.assertEqual(baseline[1], NOW - dt.timedelta(hours=expected))
        # Given both, the nearer to 168 wins.
        _latest, baseline = diff.select_baseline(_scans(0, 150, 180), now=NOW)
        self.assertEqual(baseline[1], NOW - dt.timedelta(hours=180 if abs(180 - 168) < abs(150 - 168)
                                                          else 150))

    def test_a_baseline_closer_than_a_day_is_refused(self):
        """Better no weekly report than a one-hour delta presented as one."""
        with self.assertRaises(diff.NoBaseline):
            diff.select_baseline(_scans(0, 1, 2, 3), now=NOW)

    def test_a_baseline_beyond_the_max_window_is_refused(self):
        with self.assertRaises(diff.NoBaseline):
            diff.select_baseline(_scans(0, 24 * 30), now=NOW)

    def test_one_scan_cannot_be_diffed(self):
        with self.assertRaises(diff.NoBaseline):
            diff.select_baseline(_scans(0), now=NOW)

    def test_unordered_input_is_handled(self):
        scans = _scans(168, 0, 24)
        latest, baseline = diff.select_baseline(scans, now=NOW)
        self.assertEqual(latest[1], NOW)
        self.assertEqual(baseline[1], NOW - dt.timedelta(hours=168))


class SummariseTest(unittest.TestCase):
    def _scan(self, stacks=None, dataplane=None):
        return {"meta": {}, "data": {"stacks": stacks or [], "dataplane": dataplane or {}}}

    def test_inventory_figures_are_summed(self):
        scan = self._scan(stacks=[
            {"slug": "a", "hmInstancePromCurrentActiveSeries": 100, "billingActiveUsers": 3,
             "currentActiveUsers": 4, "dashboardCnt": 10, "alertCnt": 2},
            {"slug": "b", "hmInstancePromCurrentActiveSeries": 50, "billingActiveUsers": 1,
             "currentActiveUsers": 1, "dashboardCnt": 5, "alertCnt": 0},
        ])
        got = diff.summarise(scan)
        self.assertEqual(got["stacks"], 2)
        self.assertEqual(got["active_series"], 150)
        self.assertEqual(got["billed_users"], 4)
        self.assertEqual(got["dashboards"], 15)

    def test_an_unmeasured_figure_is_absent_rather_than_zero(self):
        """A T1 scan has no data plane. Zero would claim 'no Adaptive recommendations'."""
        got = diff.summarise(self._scan(stacks=[{"slug": "a"}]))
        self.assertNotIn("adaptive_pending", got)
        self.assertNotIn("collectors", got)
        self.assertNotIn("label_values", got)

    def test_dataplane_figures_appear_when_present(self):
        scan = self._scan(
            stacks=[{"slug": "a"}],
            dataplane={"a": {
                "adaptive_metrics": {"available": True, "rules_applied": 5,
                                     "recommendations_pending": 20},
                "fleet": {"available": True, "collectors": 7},
                "cardinality": {"available": True, "label_values_count_total": 1234},
            }},
        )
        got = diff.summarise(scan)
        self.assertEqual(got["adaptive_pending"], 20)
        self.assertEqual(got["adaptive_applied"], 5)
        self.assertEqual(got["collectors"], 7)
        self.assertEqual(got["label_values"], 1234)


class DiffTest(unittest.TestCase):
    def _pair(self, then_series, now_series):
        mk = lambda n: {"meta": {}, "data": {"stacks": [
            {"slug": "a", "hmInstancePromCurrentActiveSeries": n, "billingActiveUsers": 10,
             "currentActiveUsers": 12, "dashboardCnt": 5, "alertCnt": 1}]}}
        return mk(now_series), mk(then_series)

    def test_change_and_percentage_are_computed(self):
        latest, baseline = self._pair(1000, 1100)
        report = diff.diff(latest, baseline, NOW, NOW - dt.timedelta(days=7))
        rows = {r[" Metric"]: r for r in report["rows"]}
        self.assertEqual(rows["Active series"]["Change"], 100)
        self.assertEqual(rows["Active series"]["Change %"], 10.0)

    def test_both_timestamps_and_the_real_interval_are_reported(self):
        latest, baseline = self._pair(1, 1)
        report = diff.diff(latest, baseline, NOW, NOW - dt.timedelta(days=4, hours=12))
        self.assertEqual(report["interval_days"], 4.5)
        self.assertEqual(report["target_interval_days"], 7)
        self.assertFalse(report["on_target"])
        self.assertIn("2026-08-17", report["latest_at"])
        self.assertIn("2026-08-13", report["baseline_at"])

    def test_on_target_within_a_day(self):
        latest, baseline = self._pair(1, 1)
        self.assertTrue(diff.diff(latest, baseline, NOW,
                                  NOW - dt.timedelta(days=7)).get("on_target"))
        self.assertTrue(diff.diff(latest, baseline, NOW,
                                  NOW - dt.timedelta(days=6, hours=12)).get("on_target"))

    def test_a_figure_missing_from_one_side_reports_a_note_not_a_zero_change(self):
        latest = {"meta": {}, "data": {"stacks": [{"slug": "a"}], "dataplane": {
            "a": {"fleet": {"available": True, "collectors": 3}}}}}
        baseline = {"meta": {}, "data": {"stacks": [{"slug": "a"}]}}
        rows = {r[" Metric"]: r for r in
                diff.diff(latest, baseline, NOW, NOW - dt.timedelta(days=7))["rows"]}
        self.assertIsNone(rows["Fleet collectors"]["Change"])
        self.assertEqual(rows["Fleet collectors"]["Note"], "not measured in both scans")

    def test_zero_baseline_yields_no_percentage_rather_than_a_division_error(self):
        latest, baseline = self._pair(0, 500)
        rows = {r[" Metric"]: r for r in
                diff.diff(latest, baseline, NOW, NOW - dt.timedelta(days=7))["rows"]}
        self.assertEqual(rows["Active series"]["Change"], 500)
        self.assertIsNone(rows["Active series"]["Change %"])

    def test_every_tracked_figure_appears_as_a_row(self):
        latest, baseline = self._pair(1, 1)
        report = diff.diff(latest, baseline, NOW, NOW - dt.timedelta(days=7))
        self.assertEqual(len(report["rows"]), len(diff.TRACKED))


class ViewTest(unittest.TestCase):
    def test_the_view_leads_with_the_real_comparison_window(self):
        """So no reader assumes seven days when it was four."""
        latest = {"meta": {}, "data": {"stacks": [{"slug": "a"}]}}
        report = diff.diff(latest, latest, NOW, NOW - dt.timedelta(days=4))
        view = diff.as_view(report)
        self.assertEqual(view[0][" Metric"], "COMPARISON WINDOW")
        self.assertEqual(view[0]["Change"], "4.0 days")
        self.assertIn("target was 7 days", view[0]["Note"])

    def test_an_on_target_window_says_so_and_names_itself(self):
        """The note gained the window label when T4 started publishing two diffs (PLAN 13.2).

        Naming it is not decoration: two diff tables on one dashboard are indistinguishable otherwise,
        and a reader who takes the daily table for the weekly one draws a conclusion 7x too strong.
        """
        latest = {"meta": {}, "data": {"stacks": [{"slug": "a"}]}}
        view = diff.as_view(diff.diff(latest, latest, NOW, NOW - dt.timedelta(days=7)))
        self.assertIn("on target", view[0]["Note"])
        self.assertIn("week over week", view[0]["Note"])


if __name__ == "__main__":
    unittest.main()


# --- Two diff windows (PLAN 13.2) -------------------------------------------------------------------
#
# T4 moved to daily and now publishes a 1-day diff alongside the 7-day one. The whole reason this module
# exists is that "diff the two most recent scans" produces a plausible number answering the wrong
# question, and adding a second window multiplies the ways that can happen:
#
#   * the DAILY window accepting a 7-day-old baseline and labelling it daily;
#   * the WEEKLY window relaxing to a 20-hour baseline because the daily one needed a smaller floor;
#   * both windows publishing to the same view key, so whichever runs last wins silently.
#
# Each window therefore carries its OWN target, minimum and maximum, and every assertion below is about
# keeping them from bleeding into each other.

class DiffWindowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)

    def _scans(self, *ages_hours):
        return [(f"scans/t3/{h}h.json", self.now - dt.timedelta(hours=h)) for h in ages_hours]

    def _window(self, name):
        return next(w for w in diff.WINDOWS if w.name == name)

    def test_both_windows_are_declared(self):
        names = [w.name for w in diff.WINDOWS]
        self.assertEqual(names, ["weekly", "daily"], "window order is the publish order - keep it stable")

    def test_each_window_publishes_to_its_own_view(self):
        """Sharing a view key would make whichever ran last silently overwrite the other."""
        keys = [w.view for w in diff.WINDOWS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(self._window("weekly").view, "estate_diff",
                         "the weekly view key must not change - a dashboard panel is bound to it")

    def test_the_daily_window_rejects_a_baseline_that_is_too_recent(self):
        """A 'daily' change measured over two hours is worse than no report."""
        with self.assertRaises(diff.NoBaseline):
            diff.select_baseline(self._scans(0, 2), now=self.now, window=self._window("daily"))

    def test_the_daily_window_accepts_a_baseline_near_a_day(self):
        latest, baseline = diff.select_baseline(
            self._scans(0, 20), now=self.now, window=self._window("daily"))
        self.assertEqual(latest[1] - baseline[1], dt.timedelta(hours=20))

    def test_the_daily_window_refuses_a_week_old_baseline(self):
        """The failure that makes a daily diff a lie. With T3 down for a week the only candidate is 7
        days old, and labelling that 'daily' is exactly the defect this module exists to prevent."""
        with self.assertRaises(diff.NoBaseline):
            diff.select_baseline(self._scans(0, 24 * 7), now=self.now, window=self._window("daily"))

    def test_the_daily_window_picks_the_candidate_nearest_one_day(self):
        latest, baseline = diff.select_baseline(
            self._scans(0, 13, 25, 60), now=self.now, window=self._window("daily"))
        self.assertEqual(latest[1] - baseline[1], dt.timedelta(hours=25))

    def test_the_weekly_window_still_needs_a_full_day(self):
        """Regression guard: the daily window needed a smaller floor, and it must not have leaked."""
        self.assertGreaterEqual(self._window("weekly").min_interval, dt.timedelta(days=1))
        with self.assertRaises(diff.NoBaseline):
            diff.select_baseline(self._scans(0, 20), now=self.now, window=self._window("weekly"))

    def test_the_weekly_window_picks_the_candidate_nearest_seven_days(self):
        latest, baseline = diff.select_baseline(
            self._scans(0, 26, 24 * 7, 24 * 20), now=self.now, window=self._window("weekly"))
        self.assertEqual(latest[1] - baseline[1], dt.timedelta(days=7))

    def test_each_windows_maximum_is_no_looser_than_its_target(self):
        for w in diff.WINDOWS:
            self.assertGreater(w.max_interval, w.target, w.name)
            self.assertLess(w.min_interval, w.target, w.name)

    def test_the_daily_maximum_is_much_tighter_than_the_weekly_one(self):
        """A shared MAX_INTERVAL of 21 days would let the daily diff run 3 weeks stale."""
        self.assertLess(self._window("daily").max_interval, self._window("weekly").target)

    def test_the_report_states_its_own_target_not_a_hardcoded_seven(self):
        scans = self._scans(0, 25)
        w = self._window("daily")
        latest, baseline = diff.select_baseline(scans, now=self.now, window=w)
        report = diff.diff({"data": {"stacks": [{"slug": "a"}]}},
                           {"data": {"stacks": [{"slug": "a"}]}},
                           latest[1], baseline[1], window=w)
        self.assertEqual(report["target_interval_days"], 1)
        self.assertAlmostEqual(report["interval_days"], 25 / 24, places=2)

    def test_the_view_header_names_the_window(self):
        """Two diff tables on one dashboard are indistinguishable unless each says which it is."""
        for name, expected in (("weekly", 7), ("daily", 1)):
            w = self._window(name)
            latest, baseline = diff.select_baseline(
                self._scans(0, 25 if name == "daily" else 24 * 7), now=self.now, window=w)
            report = diff.diff({"data": {"stacks": [{"slug": "a"}]}},
                               {"data": {"stacks": [{"slug": "a"}]}},
                               latest[1], baseline[1], window=w)
            header = diff.as_view(report)[0]
            self.assertEqual(header[" Metric"], "COMPARISON WINDOW")
            self.assertIn(str(expected), str(header["Note"]) + str(header["Change"]))

    def test_on_target_tolerance_scales_with_the_window(self):
        """A 1-day tolerance is right for a 7-day target and absurd for a 1-day one - it would call a
        2-day interval 'on target' for a daily diff."""
        w = self._window("daily")
        self.assertLess(w.tolerance, w.target)
        latest, baseline = diff.select_baseline(self._scans(0, 47), now=self.now, window=w)
        report = diff.diff({"data": {"stacks": [{"slug": "a"}]}},
                           {"data": {"stacks": [{"slug": "a"}]}},
                           latest[1], baseline[1], window=w)
        self.assertFalse(report["on_target"], "a 47-hour interval is not an on-target daily diff")


class PopulationGuardTest(unittest.TestCase):
    """The diff sums across whatever stacks each scan measured - so a COVERAGE change looks like an
    ESTATE change, and nothing said so (PLAN 15.1).

    Found the hard way on 2026-08-19: the daily diff showed Fleet collectors +47.7% and label values
    -29.3% in one day. Both turned out to be real (one stack doubled its collectors, two others cut
    cardinality ~70%), but proving that took a hand-comparison of the two scans' per-signal availability.
    If a future scan had partial data-plane coverage the same shape of movement would appear and there was
    no way to tell the two apart from the view.

    This does not change any computed figure. It surfaces the measured population so a reader can see
    whether the two sides are comparable at all.
    """

    def _scan(self, n_stacks, n_dataplane):
        stacks = [{"slug": f"s{i}", "hmInstancePromCurrentActiveSeries": 10} for i in range(n_stacks)]
        dataplane = {
            f"s{i}": {"slug": f"s{i}",
                      "cardinality": {"available": True, "label_values_count_total": 100},
                      "fleet": {"available": True, "collectors": 5},
                      "adaptive_metrics": {"available": True, "rules_applied": 1,
                                           "recommendations_pending": 2}}
            for i in range(n_dataplane)
        }
        return {"meta": {}, "data": {"stacks": stacks, "dataplane": dataplane}}

    def test_the_measured_population_is_reported_for_both_sides(self):
        report = diff.diff(self._scan(273, 269), self._scan(271, 267),
                           NOW, NOW - dt.timedelta(days=1), window=diff.DAILY)
        self.assertEqual(report["population"]["now"]["dataplane"], 269)
        self.assertEqual(report["population"]["then"]["dataplane"], 267)
        self.assertEqual(report["population"]["now"]["inventory"], 273)

    def test_comparable_populations_are_not_flagged(self):
        """267 vs 269 of ~270 is the normal case and must not cry wolf."""
        report = diff.diff(self._scan(273, 269), self._scan(271, 267),
                           NOW, NOW - dt.timedelta(days=1), window=diff.DAILY)
        self.assertTrue(report["population"]["comparable"])

    def test_a_materially_different_population_IS_flagged(self):
        """The case that would make every summed row misleading: half the estate missing from one side."""
        report = diff.diff(self._scan(273, 269), self._scan(271, 130),
                           NOW, NOW - dt.timedelta(days=1), window=diff.DAILY)
        self.assertFalse(report["population"]["comparable"])

    def test_the_view_shows_the_population_row_only_when_it_matters(self):
        """A clean diff should not carry a scary row; a skewed one must."""
        clean = diff.as_view(diff.diff(self._scan(273, 269), self._scan(271, 267),
                                       NOW, NOW - dt.timedelta(days=1), window=diff.DAILY))
        skewed = diff.as_view(diff.diff(self._scan(273, 269), self._scan(271, 130),
                                        NOW, NOW - dt.timedelta(days=1), window=diff.DAILY))
        self.assertNotIn("POPULATION", [r[" Metric"] for r in clean])
        row = next(r for r in skewed if r[" Metric"] == "POPULATION")
        self.assertIn("130", f"{row['Then']}")
        self.assertIn("coverage", str(row["Note"]).lower())

    def test_a_t1_scan_with_no_dataplane_reports_zero_not_a_crash(self):
        """T1 has no data plane at all. That is already handled per-row; the population must not blow up."""
        t1 = {"meta": {}, "data": {"stacks": [{"slug": "a"}]}}
        report = diff.diff(t1, t1, NOW, NOW - dt.timedelta(days=1), window=diff.DAILY)
        self.assertEqual(report["population"]["now"]["dataplane"], 0)
        self.assertTrue(report["population"]["comparable"],
                        "both sides having no data plane is comparable, not a skew")
