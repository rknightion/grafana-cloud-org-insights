"""Alert rule construction (PLAN 7.3).

The rules themselves are declarative and mostly not worth testing. Two things are, because both fail
SILENTLY  -  the rule exists, looks right in the UI, and never fires:

  1. A `max_over_time` window shorter than the rule's own threshold. The series stops existing exactly
     when the condition becomes true, so the rule degrades to NoData instead of firing on age.
  2. The staleness rules not treating NoData as alerting. NoData is the deadest case there is.
"""

from __future__ import annotations

import re
import pathlib
import tempfile
import unittest
from unittest import mock

from bin import alerts


def parse_duration(text: str) -> int:
    """PromQL duration -> seconds. Only the units the module actually uses."""
    m = re.fullmatch(r"(\d+)([smhd])", text)
    if not m:
        raise AssertionError(f"unparseable duration {text!r}")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def _cadences_from_terraform() -> dict[str, int]:
    """Parse each tier's schedule interval in seconds out of `terraform/variables.tf`.

    Only the EventBridge cron shapes this project actually uses are handled  -  a 6-field
    `cron(min hour dom month dow year)`:

        hour == "*"                 -> hourly
        hour is a comma list of N   -> 86400 / N   (e.g. `2,8,14,20` = every 6 hours)
        single hour, dow == "?"     -> daily
        single hour, dow is a day   -> weekly

    Anything else raises rather than guessing, because a silently-wrong cadence here turns every
    threshold assertion below into a check against a number nobody chose.
    """
    import re
    text = (pathlib.Path(__file__).resolve().parent.parent
            / "terraform" / "variables.tf").read_text()
    out: dict[str, int] = {}
    for tier, expr in re.findall(
            r'^\s*(t\d)\s*=\s*\{[^}]*?schedule_expression\s*=\s*"cron\(([^)]*)\)"',
            text, re.MULTILINE | re.DOTALL):
        fields = expr.split()
        if len(fields) != 6:
            raise AssertionError(f"{tier}: unexpected cron arity in {expr!r}")
        _minute, hour, _dom, _month, dow, _year = fields
        if hour == "*":
            out[tier] = 3600
        elif "," in hour:
            out[tier] = 86400 // len(hour.split(","))
        elif dow not in ("?", "*"):
            out[tier] = 7 * 86400
        else:
            out[tier] = 86400
    return out


class TestWindowsExceedThresholds(unittest.TestCase):
    def test_every_staleness_window_outlives_its_own_threshold(self):
        """The defect that makes a dead-man's switch undetectably dead."""
        for tier, (window, threshold, _) in alerts.TIERS.items():
            with self.subTest(tier=tier):
                self.assertGreater(
                    parse_duration(window),
                    threshold,
                    f"{tier}: max_over_time[{window}] is not longer than its {threshold}s threshold, so "
                    f"the series vanishes at the moment the rule should fire",
                )

    def test_coverage_window_spans_more_than_the_slowest_daily_tier(self):
        """`last_over_time` needs to reach back past the previous daily run or the rule sees NoData
        between scans and silently stops evaluating."""
        self.assertGreater(parse_duration(alerts.COVERAGE_WINDOW), 24 * 3600)

    # How often each tier is scheduled, PARSED from terraform/variables.tf rather than restated.
    #
    # This used to be a hand-written mirror and it silently went stale the moment a cadence changed: t3
    # moved weekly -> 6-hourly and t4 weekly -> daily on 2026-08-19, and the table still claimed weekly,
    # so the thresholds were being checked against cadences that no longer existed. Reading the real
    # source means a future cadence change either passes these checks or fails them honestly.
    CADENCE = _cadences_from_terraform()

    def test_the_cadences_were_actually_parsed(self):
        """A parser that silently returns {} would make every check below vacuously pass."""
        self.assertEqual(set(self.CADENCE), set(alerts.TIERS),
                         f"could not parse a cadence for every tier: {self.CADENCE}")

    def test_no_threshold_pages_on_a_single_late_run(self):
        """Must exceed one full cadence, or an ordinary slow run trips the alert every cycle."""
        for tier, (_, threshold, _) in alerts.TIERS.items():
            with self.subTest(tier=tier):
                self.assertGreater(threshold, self.CADENCE[tier])

    def test_staleness_is_detected_within_about_two_missed_runs(self):
        """The operational bound: a stale tier must be caught before anyone reads it as current.

        The budget is one missed run plus a margin, capped so it can never exceed two days beyond the
        cadence  -  two missed weekly runs would have been a fortnight of dashboards quietly showing
        carried-forward figures, which is why t3 was 9d rather than 14d when it was weekly.
        """
        for tier, (_, threshold, _) in alerts.TIERS.items():
            with self.subTest(tier=tier):
                self.assertLessEqual(threshold, self.CADENCE[tier] + 2 * 86400)

    def test_every_threshold_fires_before_carry_forward_stops_republishing(self):
        """Ordering that must hold or the failure presents backwards: panels would go blank BEFORE any
        alert fired, so the first symptom would be a customer asking why a dashboard is empty."""
        from collector.emit import carry
        cap = carry.MAX_CARRY_AGE.total_seconds()
        for tier, (_, threshold, _) in alerts.TIERS.items():
            with self.subTest(tier=tier):
                self.assertLess(threshold, cap,
                                f"{tier} alerts at {threshold / 3600:.0f}h but carry-forward stops at "
                                f"{cap / 3600:.0f}h  -  the panels blank before the alert fires")


class TestQueryShape(unittest.TestCase):
    def test_no_rule_uses_a_bare_instant_selector(self):
        """The collector writes hourly at best and Mimir's lookback-delta is 5 minutes, so a bare
        instant query returns an empty result at almost any evaluation time. Every expression must wrap
        its selector in a range function."""
        for rule in alerts.build_all():
            expr = rule["data"][0]["model"]["expr"]
            with self.subTest(rule=rule["title"]):
                self.assertRegex(
                    expr,
                    r"(max_over_time|last_over_time|min_over_time|avg_over_time)\(",
                    f"{expr!r} has no range function; it will evaluate empty between writes",
                )

    def test_queries_are_instant_not_range(self):
        """`max_over_time` already does the looking back. A range query on top would return a series
        where the threshold node expects one value per series."""
        for rule in alerts.build_all():
            model = rule["data"][0]["model"]
            with self.subTest(rule=rule["title"]):
                self.assertTrue(model["instant"])
                self.assertFalse(model["range"])

    def test_threshold_references_the_query_node(self):
        """An expression pointing at a refId that does not exist saves fine and errors on evaluation."""
        for rule in alerts.build_all():
            with self.subTest(rule=rule["title"]):
                ref_ids = {node["refId"] for node in rule["data"]}
                self.assertIn(rule["data"][1]["model"]["expression"], ref_ids)
                self.assertEqual(rule["condition"], rule["data"][-1]["refId"])


class TestNoDataSemantics(unittest.TestCase):
    def test_staleness_rules_fire_on_no_data(self):
        for tier in alerts.TIERS:
            with self.subTest(tier=tier):
                self.assertEqual(alerts.staleness_rule(tier)["noDataState"], "Alerting")

    def test_coverage_rule_does_not_fire_on_no_data(self):
        """A dead tier has no coverage series either, and it already has its own rule. Alerting here
        would page twice for one fault."""
        self.assertEqual(alerts.coverage_rule()["noDataState"], "OK")

    def test_no_rule_escalates_on_a_query_error(self):
        """A Mimir blip is not an outage of the platform. `execErrState: Error` on a shared fleet is a
        known source of phantom incidents."""
        for rule in alerts.build_all():
            with self.subTest(rule=rule["title"]):
                self.assertEqual(rule["execErrState"], "OK")


class TestBlastRadius(unittest.TestCase):
    def test_configured_title_separator_preserves_spacing(self):
        with mock.patch.object(alerts, "TITLE_SEPARATOR", "-"):
            self.assertEqual(alerts.alert_title("scan coverage below floor"),
                             "Estate insights - scan coverage below floor")

    def test_every_rule_is_confined_to_our_own_folder_and_group(self):
        """The stack carries 662 alert rules owned by the organisation's teams. Publishing must be incapable of
        reaching one."""
        for rule in alerts.build_all():
            with self.subTest(rule=rule["title"]):
                self.assertEqual(rule["folderUID"], alerts.FOLDER_UID)
                self.assertEqual(rule["ruleGroup"], alerts.RULE_GROUP)

    def test_rules_are_identifiable_by_a_routing_label(self):
        """the organisation route on labels; a rule with no service label cannot be routed anywhere but the default."""
        for rule in alerts.build_all():
            with self.subTest(rule=rule["title"]):
                self.assertEqual(rule["labels"]["service"], "gcinsight")
                self.assertIn(rule["labels"]["severity"], {"critical", "warning"})

    def test_titles_are_unique(self):
        """Titles are presentation now, but duplicates still make live state ambiguous to a human."""
        titles = [r["title"] for r in alerts.build_all()]
        self.assertEqual(len(titles), len(set(titles)))

    def test_uids_are_declared_and_unique(self):
        """Normal updates key on uid, so every rule needs one stable identity from its first POST."""
        rules = alerts.build_all()
        uids = [r["uid"] for r in rules]
        self.assertTrue(all(uids))
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(set(uids), set(alerts.RULE_UIDS.values()))


class TestNotificationRouting(unittest.TestCase):
    """The guards that stop a late scanner notifying an unrelated customer receiver.

    A rule with `notification_settings` unset inherits the write stack's notification policy.
    """

    def test_rules_publish_paused_by_default(self):
        for rule in alerts.build_all():
            with self.subTest(rule=rule["title"]):
                self.assertTrue(rule["isPaused"])

    def test_default_build_declares_no_routing(self):
        """Paused AND unrouted. Either alone would be enough; both means a single mistake is not enough
        to notify anyone."""
        for rule in alerts.build_all():
            with self.subTest(rule=rule["title"]):
                self.assertIsNone(rule["notification_settings"])

    def test_a_named_receiver_is_applied_to_every_rule(self):
        for rule in alerts.build_all(paused=False, receiver="gcinsight-dev"):
            with self.subTest(rule=rule["title"]):
                self.assertEqual(rule["notification_settings"], {"receiver": "gcinsight-dev"})

    def test_activating_without_a_receiver_is_refused(self):
        """The CLI guard. There must be no path that unpauses while leaving routing inherited."""
        rc = alerts.main(["--publish", "--activate"])
        self.assertEqual(rc, 2)

    def test_unpaused_rules_are_never_built_without_routing(self):
        """Belt and braces on the builder itself, independent of the CLI."""
        for rule in alerts.build_all(paused=False, receiver="x"):
            with self.subTest(rule=rule["title"]):
                self.assertFalse(rule["isPaused"])
                self.assertIsNotNone(rule["notification_settings"])

    def test_deactivate_implies_publish_and_reaches_the_live_update_path(self):
        with (
            mock.patch.object(alerts, "BASE", "https://example.invalid"),
            mock.patch.object(alerts, "FOLDER_UID", "folder"),
            mock.patch.object(alerts, "publish", return_value=0) as publish,
            mock.patch.dict("os.environ", {"GCINSIGHT_GRAFANA_TOKEN": "token"}),
        ):
            self.assertEqual(alerts.main(["--deactivate"]), 0)

        publish.assert_called_once_with(
            "token", paused=True, receiver=None, preserve_live_state=False,
        )

    def test_dry_run_is_refused_for_every_write_mode_except_title_migration(self):
        with (
            mock.patch.object(alerts, "BASE", "https://example.invalid"),
            mock.patch.object(alerts, "FOLDER_UID", "folder"),
            mock.patch.object(alerts, "contact_points", return_value=["receiver"]),
            mock.patch.object(alerts, "publish", return_value=0) as publish,
            mock.patch.dict("os.environ", {"GCINSIGHT_GRAFANA_TOKEN": "token"}),
        ):
            for mode in (
                ["--publish"],
                ["--activate", "--receiver", "receiver"],
                ["--deactivate"],
            ):
                with self.subTest(mode=mode):
                    self.assertEqual(alerts.main([*mode, "--dry-run"]), 2)

        publish.assert_not_called()

    def test_conflicting_state_options_are_refused_before_publication(self):
        with (
            mock.patch.object(alerts, "BASE", "https://example.invalid"),
            mock.patch.object(alerts, "FOLDER_UID", "folder"),
            mock.patch.object(alerts, "contact_points", return_value=["receiver"]),
            mock.patch.object(alerts, "publish", return_value=0) as publish,
            mock.patch.dict("os.environ", {"GCINSIGHT_GRAFANA_TOKEN": "token"}),
        ):
            for argv in (
                ["--activate", "--deactivate", "--receiver", "receiver"],
                ["--deactivate", "--receiver", "receiver"],
            ):
                with self.subTest(argv=argv):
                    self.assertEqual(alerts.main(argv), 2)

        publish.assert_not_called()

    def test_contact_point_listing_does_not_require_a_rule_folder(self):
        with (
            mock.patch.object(alerts, "BASE", "https://example.invalid"),
            mock.patch.object(alerts, "FOLDER_UID", ""),
            mock.patch.object(alerts, "contact_points", return_value=["receiver"]),
            mock.patch.dict("os.environ", {"GCINSIGHT_GRAFANA_TOKEN": "token"}),
        ):
            self.assertEqual(alerts.main(["--contact-points"]), 0)


class TestJsonOutput(unittest.TestCase):
    def test_rule_filenames_drop_the_title_separator(self):
        with tempfile.TemporaryDirectory() as output:
            self.assertEqual(alerts.main(["--out", output]), 0)
            names = [path.name for path in pathlib.Path(output).glob("*.json")]

        self.assertTrue(names)
        self.assertTrue(all(":" not in name for name in names), names)


class TestPublishPreservesLiveState(unittest.TestCase):
    """A plain `--publish` silently paused and unrouted five LIVE rules on 2026-08-20.

    Nothing failed. The output read `updated: ...` seven times and the platform stopped alerting, which
    is the worst shape a regression can take on an alerting tool: the thing that would have told you is
    the thing that broke.
    """

    # The title is READ OFF THE BUILDER, not written here. A hardcoded copy makes this whole class pass
    # or KeyError on a rename rather than on the behaviour it exists to pin, and it did: renaming the
    # rules (PLAN 18.8) broke two tests that were only ever asserting a string literal.
    BUILT = alerts.build_all(paused=True, receiver=None)[0]
    LIVE = {
        "uid": BUILT["uid"],
        "title": BUILT["title"],
        "folderUID": alerts.FOLDER_UID,
        "ruleGroup": alerts.RULE_GROUP,
        "isPaused": False,
        "notification_settings": {"receiver": "gcinsight-platform-health"},
    }

    def _publish(self, **kwargs):
        sent: list[dict] = []

        def fake_api(method, path, token, body=None):
            if method == "GET" and path.endswith("alert-rules"):
                return 200, [self.LIVE]
            # The rule-GROUP interval PUT also carries a `title`, so key on a rule-only field.
            if body is not None and "isPaused" in body:
                sent.append(body)
            return 200, {}

        original = alerts._api
        alerts._api = fake_api
        try:
            alerts.publish("tok", **kwargs)
        finally:
            alerts._api = original
        return {r["title"]: r for r in sent}

    def test_an_existing_live_rule_keeps_its_pause_and_routing(self):
        sent = self._publish(paused=True, receiver=None, preserve_live_state=True)
        rule = sent[self.LIVE["title"]]
        self.assertFalse(rule["isPaused"])
        self.assertEqual(rule["notification_settings"],
                         {"receiver": "gcinsight-platform-health"})

    def test_a_source_title_change_updates_the_same_uid_in_place(self):
        """A title edit must be an ordinary PUT, never a second POST plus an orphaned live rule."""
        old = self.LIVE
        self.LIVE = {**old, "title": "the previous human-facing title"}
        try:
            sent = self._publish(paused=True, receiver=None, preserve_live_state=True)
        finally:
            self.LIVE = old
        rule = sent[self.BUILT["title"]]
        self.assertEqual(rule["uid"], self.BUILT["uid"])
        self.assertFalse(rule["isPaused"])
        self.assertEqual(rule["notification_settings"],
                         {"receiver": "gcinsight-platform-health"})

    def test_a_new_rule_still_lands_paused_and_unrouted_in_the_same_run(self):
        """The two defaults must differ: safe for new, unchanged for existing."""
        sent = self._publish(paused=True, receiver=None, preserve_live_state=True)
        new = [r for title, r in sent.items() if title != self.LIVE["title"]]
        self.assertTrue(new)
        for rule in new:
            with self.subTest(rule=rule["title"]):
                self.assertTrue(rule["isPaused"])
                self.assertIsNone(rule["notification_settings"])

    def test_deactivate_really_does_pause_a_live_rule(self):
        """Otherwise there would be no way back down, and preservation would be a trap of its own."""
        sent = self._publish(paused=True, receiver=None, preserve_live_state=False)
        self.assertTrue(sent[self.LIVE["title"]]["isPaused"])
        self.assertIsNone(sent[self.LIVE["title"]]["notification_settings"])

    def test_activate_overrides_the_live_state_on_purpose(self):
        sent = self._publish(paused=False, receiver="r", preserve_live_state=False)
        for rule in sent.values():
            with self.subTest(rule=rule["title"]):
                self.assertFalse(rule["isPaused"])
                self.assertEqual(rule["notification_settings"], {"receiver": "r"})


class TestPublishRefusesAmbiguousIdentity(unittest.TestCase):
    def _run(self, live_rules):
        calls: list[tuple[str, str, dict | None]] = []

        def fake_api(method, path, token, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return 200, live_rules
            return 200, {}

        original = alerts._api
        alerts._api = fake_api
        try:
            with self.assertRaises(SystemExit):
                alerts.publish("tok", preserve_live_state=True)
        finally:
            alerts._api = original
        return calls

    def test_a_title_not_declared_by_the_migration_is_not_adopted_by_title(self):
        """Only the explicit migration table may authorise adoption of a legacy uid."""
        built = alerts.build_all()[0]
        future = {**built, "title": "a future title not in the migration table"}
        live = {**future, "uid": "different-live-uid"}
        original = alerts.build_all
        alerts.build_all = lambda **_kwargs: [future]
        try:
            calls = self._run([live])
        finally:
            alerts.build_all = original
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_an_unrecognised_rule_in_our_group_blocks_all_writes(self):
        """An orphan left by an old title-based publish is not harmless: it can still be live and routed."""
        built = alerts.build_all()[0]
        orphan = {**built, "uid": "orphan", "title": "obsolete title"}
        calls = self._run([orphan])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_an_expected_uid_outside_our_folder_is_never_updated(self):
        """UID matching must retain the folder/group blast-radius boundary."""
        built = alerts.build_all()[0]
        foreign = {**built, "folderUID": "somebody-elses-folder"}
        calls = self._run([foreign])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_duplicate_titles_in_our_group_are_refused_before_any_write(self):
        built = alerts.build_all()[0]
        calls = self._run([built, {**built, "uid": "duplicate-title-uid"}])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_duplicate_live_uids_are_refused_before_any_write(self):
        built = alerts.build_all()[0]
        calls = self._run([built, {**built, "title": "different title"}])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_missing_pause_state_is_refused_before_any_write(self):
        live = alerts.build_all()[0]
        live.pop("isPaused")
        calls = self._run([live])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_missing_routing_state_is_refused_before_any_write(self):
        live = alerts.build_all()[0]
        live.pop("notification_settings")
        calls = self._run([live])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])

    def test_malformed_routing_state_is_refused_before_any_write(self):
        live = {**alerts.build_all()[0], "notification_settings": {}}
        calls = self._run([live])
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])


class TestFreshInstallIdentity(unittest.TestCase):
    def test_first_publish_posts_the_declared_stable_uids(self):
        calls: list[tuple[str, str, dict | None]] = []

        def fake_api(method, path, token, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return 200, []
            return 200, {}

        original = alerts._api
        alerts._api = fake_api
        try:
            self.assertEqual(alerts.publish("tok"), 0)
        finally:
            alerts._api = original
        posted = [body for method, path, body in calls
                  if method == "POST" and path.endswith("/alert-rules")]
        self.assertEqual({rule["uid"] for rule in posted}, set(alerts.RULE_UIDS.values()))


class TestCoverageFloor(unittest.TestCase):
    def test_floor_is_below_one_so_paused_stacks_do_not_trip_it(self):
        """Coverage is against `stacks_scannable`, so it should reach 1.0  -  but a floor of exactly 1.0
        would page on a single unlucky stack."""
        self.assertLess(alerts.COVERAGE_FLOOR, 1.0)
        self.assertGreater(alerts.COVERAGE_FLOOR, 0.5)


class TestTitleMigration(unittest.TestCase):
    """Historical migration for rules created while title still was identity (PLAN 18.8).

    The old publisher keyed on title, so editing one created a second paused, unrouted rule and left the
    original live and routed. New updates key on `RULE_UIDS`; these tests retain the one-time migration's
    pause/routing safety for deployments which still need it.
    """

    OLD = "Estate insights - t1 scan is stale"
    NEW = "Estate insights: t1 scan is stale"

    def _live(self, **over):
        return {
            "uid": "u1",
            "title": self.OLD,
            "folderUID": alerts.FOLDER_UID,
            "ruleGroup": alerts.RULE_GROUP,
            "isPaused": False,
            "notification_settings": {"receiver": "gcinsight-platform-health"},
            "annotations": {"summary": "unchanged"},
            **over,
        }

    def _run(self, live_rules, *, dry_run=False):
        calls: list[tuple[str, str, dict | None]] = []

        def fake_api(method, path, token, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return 200, live_rules
            return 200, {}

        original = alerts._api
        alerts._api = fake_api
        try:
            rc = alerts.migrate_titles("tok", dry_run=dry_run)
        finally:
            alerts._api = original
        return rc, calls

    def test_the_table_covers_every_rule_the_builder_produces(self):
        """A rule left out of the table keeps its old title live for ever."""
        built = {r["title"] for r in alerts.build_all(paused=True, receiver=None)}
        self.assertEqual(set(alerts.RENAMED_TITLES.values()), built)

    def test_no_new_title_still_contains_an_em_dash(self):
        for old, new in alerts.RENAMED_TITLES.items():
            with self.subTest(title=new):
                self.assertNotIn(" - ", new)
                self.assertIn(" - ", old, f"{old!r} is not an old title, so it renames nothing")

    def test_it_puts_at_the_existing_uid_and_changes_only_the_title(self):
        """PUT at the uid, carrying the LIVE body. Rebuilding would re-apply the source's pause state."""
        rc, calls = self._run([self._live()])
        self.assertEqual(rc, 0)
        puts = [(path, body) for method, path, body in calls if method == "PUT"]
        self.assertEqual(len(puts), 1)
        path, body = puts[0]
        self.assertTrue(path.endswith("/alert-rules/u1"), path)
        self.assertEqual(body["title"], self.NEW)
        # Everything else survives verbatim - this is the property that stops a rename unrouting a rule.
        self.assertFalse(body["isPaused"])
        self.assertEqual(body["notification_settings"],
                         {"receiver": "gcinsight-platform-health"})
        self.assertEqual(body["annotations"], {"summary": "unchanged"})

    def test_it_refuses_when_both_titles_already_exist(self):
        """A --publish has already created the new rule; picking one to delete is not this tool's call."""
        rc, calls = self._run([self._live(), self._live(uid="u2", title=self.NEW)])
        self.assertEqual(rc, 1)
        self.assertEqual([m for m, _p, _b in calls if m == "PUT"], [])

    def test_it_is_idempotent_once_the_rename_has_landed(self):
        rc, calls = self._run([self._live(title=self.NEW)])
        self.assertEqual(rc, 0)
        self.assertEqual([m for m, _p, _b in calls if m == "PUT"], [])

    def test_the_next_publish_adopts_the_migrated_rule_at_its_existing_uid(self):
        calls: list[tuple[str, str, dict | None]] = []
        live = self._live(title=self.NEW)

        def fake_api(method, path, token, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return 200, [live]
            return 200, {}

        original = alerts._api
        alerts._api = fake_api
        try:
            rc = alerts.publish("tok", preserve_live_state=True)
        finally:
            alerts._api = original

        self.assertEqual(rc, 0)
        puts = [(path, body) for method, path, body in calls if method == "PUT"]
        self.assertTrue(any(path.endswith("/alert-rules/u1") for path, _body in puts))
        self.assertFalse(any(
            method == "POST" and body and body.get("title") == self.NEW
            for method, _path, body in calls
        ))

    def test_dry_run_writes_nothing(self):
        rc, calls = self._run([self._live()], dry_run=True)
        self.assertEqual(rc, 0)
        self.assertEqual([m for m, _p, _b in calls if m != "GET"], [])


if __name__ == "__main__":
    unittest.main()
