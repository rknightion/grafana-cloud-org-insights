"""Per-stack usage insights: the source and the pillar.

Two properties matter most here and both have bitten this project elsewhere:

- **Aggregate in Loki, not in Python.** Every query is a LogQL metric expression, so a stack that
  ingests a thousand times more than another returns the same handful of numbers. Pulling lines and
  counting them works on a small stack and falls over on a real one.
- **Coverage is never assumed.** A stack with no credential, no datasource or a refused token must
  produce a row saying which, not a zero that reads as "nobody looks at any dashboard here".
"""

from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

from collector.coverage import Coverage
from collector.pillars import insights
from collector.sources import usage_insights as ui


def vector(value):
    return {"status": "success", "data": {"resultType": "vector",
            "result": [{"metric": {}, "value": [0, str(value)]}]}}


def series(rows):
    return {"status": "success", "data": {"resultType": "vector",
                     "result": [{"metric": m, "value": [0, str(v)]} for m, v in rows]}}


class QueryShapeTest(unittest.TestCase):
    def test_every_scalar_query_aggregates_inside_loki(self):
        """A bare stream selector would stream every line to the collector."""
        for field, template in ui.SCALARS.items():
            with self.subTest(field=field):
                self.assertTrue(
                    any(fn in template for fn in ("count_over_time", "sum_over_time")),
                    f"{field} does not aggregate in Loki",
                )
                self.assertTrue(template.startswith(("sum(", "count(")),
                                f"{field} does not reduce to a scalar")

    def test_every_breakdown_is_bounded(self):
        """An unbounded `sum by (dashboardUid)` on a stack with thousands of dashboards is a huge
        response and, worse, an unbounded set of rows in a view."""
        for field, (template, _labels) in ui.BREAKDOWNS.items():
            with self.subTest(field=field):
                bounded = template.startswith("topk(") or "by (datasourceType)" in template
                self.assertTrue(bounded, f"{field} is neither topk-bounded nor a closed label set")

    def test_the_window_is_one_definition(self):
        for template in list(ui.SCALARS.values()) + [e for e, _ in ui.BREAKDOWNS.values()]:
            self.assertIn(f"[{ui.WINDOW}]", template)

    def test_the_datasource_uid_matches_what_the_role_grants_QUERY_on(self):
        """The QUERY right is scoped to exactly this uid. A mismatch is a 403 that reads like a bug.

        `datasources:read` is deliberately WIDER than this - it lists every datasource on the stack and
        confers no query capability. Only the query right is uid-pinned, and that is the whole security
        property: this collector can enumerate what the customer has and can query exactly one
        Grafana-provisioned telemetry datasource.
        """
        from collector import provision as pr
        self.assertEqual(ui.DS_UID, pr.USAGE_INSIGHTS_DS_UID)
        query_scopes = {p.get("scope") for p in pr.DESIRED_PERMISSIONS
                        if p["action"] == "datasources:query"}
        self.assertEqual(query_scopes, {f"datasources:uid:{ui.DS_UID}"},
                         "the role must grant QUERY on this uid and nothing wider")

    def test_distinct_datasources_means_types_not_uids(self):
        """The decision is which backend technologies are in use. Counting uid instances makes the
        same Prometheus type look like many different capabilities on stacks with several tenants."""
        query = ui.SCALARS["datasources_queried"]
        self.assertIn("by (datasourceType)", query)
        self.assertNotIn("datasourceUid", query)

    def test_distinct_panels_are_dashboard_panel_pairs_with_both_ids_present(self):
        """Panel ids are dashboard-local. Missing ids must not collapse into one synthetic panel."""
        query = ui.SCALARS["panels_queried"]
        self.assertIn("by (dashboardUid, panelId)", query)
        self.assertIn('dashboardUid!=""', query)
        self.assertIn('panelId!=""', query)

    def test_panel_identity_coverage_counts_requests_with_both_ids(self):
        query = ui.SCALARS["panel_identity_requests"]
        self.assertIn('dashboardUid!=""', query)
        self.assertIn('panelId!=""', query)

    def test_datasource_cost_breakdowns_include_duration_ms_and_errors(self):
        duration, duration_labels = ui.BREAKDOWNS["datasource_duration_ms"]
        errors, error_labels = ui.BREAKDOWNS["datasource_errors"]
        self.assertIn("sum_over_time", duration)
        self.assertIn("unwrap duration", duration)
        self.assertIn("by (datasourceType)", duration)
        self.assertIn('error!=""', errors)
        self.assertEqual(duration_labels, ("datasourceType",))
        self.assertEqual(error_labels, ("datasourceType",))

    def test_public_dashboard_count_is_an_unbounded_scalar_not_the_top_ten_detail(self):
        query = ui.SCALARS["public_dashboards_distinct"]
        self.assertIn("by (publicDashboardUid)", query)
        self.assertNotIn("topk", query)
        self.assertIn("topk", ui.BREAKDOWNS["public_dashboards"][0])
        for expression in (
            ui.SCALARS["public_events"], query, ui.BREAKDOWNS["public_dashboards"][0],
        ):
            self.assertIn('eventName="dashboard-view"', expression)

    def test_authenticated_viewer_count_excludes_anonymous_and_missing_ids(self):
        query = ui.SCALARS["viewers"]
        self.assertIn('userId!="-1"', query)
        self.assertIn('userId!=""', query)


class ScalarParsingTest(unittest.TestCase):
    def test_an_empty_vector_is_zero_events_not_a_missing_measurement(self):
        self.assertEqual(ui._scalar({"status": "success", "data": {
            "resultType": "vector", "result": []}}), 0.0)

    def test_a_malformed_value_raises_instead_of_becoming_zero(self):
        with self.assertRaises(ui.InsightsError):
            ui._scalar({"status": "success", "data": {"resultType": "vector",
                       "result": [{"value": ["x"]}]}})

    def test_a_non_vector_response_raises_instead_of_becoming_zero(self):
        with self.assertRaises(ui.InsightsError):
            ui._scalar({"status": "success", "data": {"resultType": "streams", "result": []}})

    def test_a_malformed_breakdown_row_raises_instead_of_being_dropped(self):
        body = {"status": "success", "data": {"resultType": "vector",
                "result": [{"metric": {"dashboardName": "bad"}, "value": [0]}]}}
        with self.assertRaises(ui.InsightsError):
            ui._series(body, ("dashboardName",))

    def test_series_are_sorted_by_count_descending(self):
        out = ui._series(series([({"dashboardName": "a"}, 5), ({"dashboardName": "b"}, 50)]),
                         ("dashboardName",))
        self.assertEqual([r["dashboardName"] for r in out], ["b", "a"])

    def test_a_missing_label_becomes_empty_string_not_None(self):
        out = ui._series(series([({}, 1)]), ("dashboardName",))
        self.assertEqual(out[0]["dashboardName"], "")


class ProbeTest(unittest.TestCase):
    def test_estate_probe_skips_paused_and_slugless_inventory_entries(self):
        stacks = [
            {"slug": "active", "id": 1, "status": "active", "url": "https://active.grafana.net"},
            {"slug": "paused", "id": 2, "status": "paused", "url": "https://paused.grafana.net"},
            {"id": 3, "status": "active", "url": "https://missing.grafana.net"},
        ]
        errors = []
        available = {"available": True, "reason": None}
        with mock.patch.object(ui, "probe_stack", return_value=available) as probe:
            records = ui.probe_all(
                stacks, {"active": {"token": "token"}}, concurrency=1,
                on_error=lambda slug, reason: errors.append((slug, reason)),
            )

        self.assertEqual(records, {"active": available})
        probe.assert_called_once()
        self.assertEqual(errors, [])

    def test_inventory_url_is_validated_before_a_stack_token_can_be_sent(self):
        stack = {"slug": "s", "id": 1, "url": "http://169.254.169.254/latest/meta-data"}
        with mock.patch.object(ui, "probe_stack") as probe:
            records = ui.probe_all([stack], {"s": {"token": "secret"}}, concurrency=1)

        self.assertEqual(records["s"]["reason"], "invalid_url")
        probe.assert_not_called()

    def test_no_credential_is_reported_not_silently_zero(self):
        rec = ui.probe_stack("s", "https://s.grafana.net", "", instance_id="1")
        self.assertFalse(rec["available"])
        self.assertEqual(rec["reason"], ui.NO_CREDENTIAL)

    def test_a_403_gets_one_retry_because_rbac_caches(self):
        """Measured: the first call after a role patch 403'd and the next succeeded on the same
        token. One re-attempt, not a loop."""
        calls = []

        def fake(base, token, expr, *, expected_instance_id, timeout=90.0):
            calls.append(expr)
            if len(calls) == 1:
                raise urllib.error.HTTPError("u", 403, "forbidden", {}, None)
            return vector(1)

        original = ui._query
        ui._query = fake
        try:
            rec = ui.probe_stack("s", "https://s", "tok", instance_id="1", sleep=lambda _: None)
        finally:
            ui._query = original
        self.assertTrue(rec["available"])
        self.assertGreater(len(calls), len(ui.SCALARS))

    def test_a_401_is_never_retried(self):
        calls = []

        def fake(base, token, expr, *, expected_instance_id, timeout=90.0):
            calls.append(expr)
            raise urllib.error.HTTPError("u", 401, "no", {}, None)

        original = ui._query
        ui._query = fake
        try:
            rec = ui.probe_stack("s", "https://s", "tok", instance_id="1", sleep=lambda _: None)
        finally:
            ui._query = original
        self.assertEqual(rec["reason"], ui.UNAUTHORISED)
        self.assertEqual(len(calls), 1, "401 does not change in three seconds")

    def test_a_failing_breakdown_marks_the_whole_stack_unavailable(self):
        def fake(base, token, expr, *, expected_instance_id, timeout=90.0):
            if "topk" in expr:
                raise urllib.error.HTTPError("u", 500, "boom", {}, None)
            return vector(7)

        original = ui._query
        ui._query = fake
        try:
            rec = ui.probe_stack("s", "https://s", "tok", instance_id="1", sleep=lambda _: None)
        finally:
            ui._query = original
        self.assertFalse(rec["available"])
        self.assertEqual(rec["reason"], ui.HTTP_ERROR)
        self.assertIn("top_dashboards", rec["detail"])

    def test_a_malformed_scalar_marks_the_whole_stack_unavailable(self):
        def fake(base, token, expr, *, expected_instance_id, timeout=90.0):
            return {"status": "success", "data": {"resultType": "vector",
                    "result": [{"metric": {}, "value": [0]}]}}

        original = ui._query
        ui._query = fake
        try:
            rec = ui.probe_stack("s", "https://s", "tok", instance_id="1", sleep=lambda _: None)
        finally:
            ui._query = original
        self.assertFalse(rec["available"])
        self.assertEqual(rec["reason"], ui.MALFORMED_RESPONSE)
        self.assertIn("views", rec["detail"])

    def test_distinct_panel_pairs_cannot_exceed_identified_panel_requests(self):
        def fake(_base, _token, expr, *, expected_instance_id, timeout=90.0):
            if expr == ui.SCALARS["panels_queried"] % {"sel": ui.selector(instance_id="1")}:
                return vector(2)
            if expr == ui.SCALARS["panel_identity_requests"] % {
                "sel": ui.selector(instance_id="1")
            }:
                return vector(1)
            return vector(0)

        with mock.patch.object(ui, "_query", side_effect=fake):
            record = ui.probe_stack("s", "https://s.grafana.net", "tok", instance_id="1")

        self.assertFalse(record["available"])
        self.assertEqual(record["reason"], ui.MALFORMED_RESPONSE)
        self.assertIn("panel", record["detail"])


class PillarTest(unittest.TestCase):
    STACKS = [
        {"slug": "busy", "url": "https://busy.grafana.net", "dashboardCnt": 100},
        {"slug": "quiet", "url": "https://quiet.grafana.net", "dashboardCnt": 10},
        {"slug": "nocred", "url": "https://nocred.grafana.net", "dashboardCnt": 5},
    ]
    PAYLOAD = {
        "busy": {"slug": "busy", "available": True, "views": 1281, "viewers": 53,
                 "dashboards_viewed": 40, "public_events": 11363, "anonymous_views": 869,
                 "public_dashboards_distinct": 12,
                 "requests": 57542, "request_errors": 176, "queries_total": 83297,
                 "queries_cached": 7728, "panel_identity_requests": 5000,
                 "panels_queried": 186, "datasources_queried": 5,
                 "public_dashboards": [{"publicDashboardUid": "p1", "dashboardUid": "d1",
                                        "dashboardName": "Public one", "count": 11347}],
                 "top_dashboards": [{"dashboardUid": "d1", "dashboardName": "Public one",
                                     "folderName": "", "count": 867}],
                 "datasource_types": [{"datasourceType": "prometheus", "count": 21360}],
                 "datasource_duration_ms": [{"datasourceType": "prometheus", "count": 987654}],
                 "datasource_errors": [{"datasourceType": "prometheus", "count": 17}]},
        "quiet": {"slug": "quiet", "available": True, "views": 0, "viewers": 0,
                  "dashboards_viewed": 0, "public_events": 0, "anonymous_views": 0,
                  "public_dashboards_distinct": 0,
                  "requests": 3, "request_errors": 0, "queries_total": 3, "queries_cached": 0,
                  "panel_identity_requests": 1, "panels_queried": 1, "datasources_queried": 1,
                  "public_dashboards": [], "top_dashboards": [], "datasource_types": [],
                  "datasource_duration_ms": [], "datasource_errors": []},
        "nocred": {"slug": "nocred", "available": False, "reason": "no_credential", "detail": ""},
    }

    def setUp(self):
        cov = Coverage(tier="t2", total=len(self.STACKS))
        self.metrics, self.views = insights.build(self.STACKS, cov, self.PAYLOAD)
        # Value assertions stay about their business dimensions; the dedicated epoch test below
        # verifies the safety label independently on every emitted series.
        self.by = {
            (n, tuple(sorted((k, val) for k, val in labels.items() if k != "version"))): value
            for n, labels, value in self.metrics
        }

    def test_every_metric_uses_the_clean_epoch(self):
        """The first usage-insights sweep was region-wide, so every Pillar J range must exclude it."""
        for name, labels, _value in self.metrics:
            with self.subTest(metric=name):
                self.assertEqual(labels.get("version"), insights.METRIC_EPOCH)

    def test_the_budget_reserves_current_and_transition_epochs(self):
        """Budget the clean epoch alongside the retained unversioned samples during migration."""
        from collector.emit import budget

        for spec in budget.CATALOGUE:
            if spec.pillar == "J" and spec.store == "mimir":
                with self.subTest(metric=spec.name):
                    self.assertEqual(
                        spec.labels.get("version"), int(insights.METRIC_EPOCH),
                    )

    def test_nothing_is_emitted_without_the_input(self):
        """An hourly tier with no insights input must not write zeros over the daily tier's figures."""
        cov = Coverage(tier="t1", total=1)
        metrics, views = insights.build(self.STACKS, cov, None)
        self.assertEqual(metrics, [])
        self.assertEqual(views, {})

    def test_an_unmeasured_stack_appears_in_coverage_not_as_a_zero_row(self):
        usage = {r[" Stack"] for r in self.views["insights_dashboard_usage"]}
        self.assertNotIn("nocred", usage)
        cov = {r[" Stack"]: r["State"] for r in self.views["insights_coverage"]}
        self.assertEqual(cov["nocred"], "no credential yet")

    def test_the_public_dashboard_table_names_them(self):
        """A count is not actionable without the named activity behind it."""
        rows = self.views["insights_public_dashboards"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Public uid"], "p1")
        self.assertEqual(rows[0]["Dashboard"], "Public one")
        self.assertEqual(self.by[("gcinsight_dashboards_estate_public", ())], 12.0)

    def test_bounded_named_public_rows_are_not_used_as_the_estate_total(self):
        """A stack may have more than the top-N detail rows retained by the source."""
        self.assertEqual(len(self.views["insights_public_dashboards"]), 1)
        self.assertEqual(self.by[("gcinsight_dashboards_estate_public", ())], 12.0)
        summary = {row[" Metric"]: row["Value"] for row in self.views["insights_summary"]}
        self.assertEqual(summary["Distinct public dashboards observed in use"], 12)

    def test_a_zero_view_stack_is_still_measured(self):
        """Zero views is a finding. Absent from the table would hide it."""
        usage = {r[" Stack"]: r for r in self.views["insights_dashboard_usage"]}
        self.assertIn("quiet", usage)
        self.assertEqual(usage["quiet"]["Views"], 0)
        self.assertEqual(self.by[("gcinsight_dashboards_views", (("stack", "quiet"),))], 0.0)

    def test_the_cache_ratio_is_withheld_below_the_floor(self):
        """3 queries cannot produce a meaningful hit rate."""
        usage = {r[" Stack"]: r for r in self.views["insights_dashboard_usage"]}
        self.assertIsNone(usage["quiet"]["Cache hit %"])
        self.assertNotIn(("gcinsight_dashboards_cache_hit_ratio", (("stack", "quiet"),)), self.by)
        self.assertIsNotNone(usage["busy"]["Cache hit %"])

    def test_viewed_share_uses_the_provisioned_count_as_its_denominator(self):
        usage = {r[" Stack"]: r for r in self.views["insights_dashboard_usage"]}
        self.assertEqual(usage["busy"]["Viewed share %"], 40.0)

    def test_panel_identity_coverage_is_visible_and_named_as_a_pair(self):
        usage = {r[" Stack"]: r for r in self.views["insights_dashboard_usage"]}
        self.assertEqual(usage["busy"]["Panel identity coverage %"], 8.7)
        self.assertEqual(usage["busy"]["Identified panel requests"], 5000)
        self.assertEqual(usage["busy"]["Distinct dashboard-panel pairs"], 186)

    def test_datasource_breakdown_carries_requests_duration_and_errors(self):
        row = self.views["insights_datasource_types"][0]
        self.assertEqual(row[" Datasource type"], "prometheus")
        self.assertEqual(row["Data requests"], 21360)
        self.assertEqual(row["Cumulative duration (ms)"], 987654)
        self.assertEqual(row["Request errors"], 17)

    def test_a_share_with_no_denominator_is_None_not_zero(self):
        stacks = [{"slug": "busy", "url": "u", "dashboardCnt": 0}]
        _, views = insights.build(stacks, Coverage(tier="t2", total=1), self.PAYLOAD)
        self.assertIsNone(views["insights_dashboard_usage"][0]["Viewed share %"])

    def test_estate_stack_counts_split_measured_from_active(self):
        self.assertEqual(self.by[("gcinsight_dashboards_estate_stacks",
                                  (("kind", "measured"),))], 2.0)
        self.assertEqual(self.by[("gcinsight_dashboards_estate_stacks",
                                  (("kind", "with_views"),))], 1.0)
        self.assertEqual(self.by[("gcinsight_dashboards_estate_stacks",
                                  (("kind", "with_public_dashboards"),))], 1.0)

    def test_no_measured_stack_emits_coverage_but_no_structural_estate_zeroes(self):
        payload = {
            str(stack["slug"]): {
                "slug": str(stack["slug"]), "available": False, "reason": "no_credential",
            }
            for stack in self.STACKS
        }
        metrics, _views = insights.build(
            self.STACKS, Coverage(tier="t2", total=len(self.STACKS)), payload
        )
        names = {name for name, _labels, _value in metrics}
        self.assertEqual(
            [value for name, labels, value in metrics
             if name == "gcinsight_dashboards_estate_stacks"
             and labels.get("kind") == "measured"],
            [0.0],
        )
        self.assertNotIn("gcinsight_dashboards_estate_views", names)
        self.assertNotIn("gcinsight_dashboards_estate_provisioned", names)

    def test_datasource_type_seen_only_in_duration_still_counts_its_stack(self):
        payload = {
            "busy": {
                **self.PAYLOAD["busy"],
                "datasource_types": [],
                "datasource_duration_ms": [{"datasourceType": "tempo", "count": 123}],
                "datasource_errors": [],
            }
        }
        metrics, views = insights.build(
            [self.STACKS[0]], Coverage(tier="t2", total=1), payload
        )
        self.assertTrue(metrics)
        row = views["insights_datasource_types"][0]
        self.assertEqual(row[" Datasource type"], "tempo")
        self.assertEqual(row["Stacks"], 1)

    def test_the_summary_states_its_denominator(self):
        rows = {r[" Metric"]: r["Value"] for r in self.views["insights_summary"]}
        self.assertIn("2 of 3", str(rows[f"Stacks measured (window {ui.WINDOW})"]))

    def test_the_summary_says_viewers_are_not_deduplicated_across_the_org(self):
        """Summing distinct-viewer counts per stack is not an org-wide distinct count, and presenting
        it as one would overstate reach on an estate where people use several stacks."""
        keys = " ".join(r[" Metric"] for r in self.views["insights_summary"])
        self.assertIn("not deduplicated", keys)

    def test_the_live_inventory_drives_the_rows_not_the_payload(self):
        """A stack that has left the org must vanish even if the payload still carries it."""
        stacks = [s for s in self.STACKS if s["slug"] != "busy"]
        _, views = insights.build(stacks, Coverage(tier="t2", total=2), self.PAYLOAD)
        self.assertNotIn("busy", {r[" Stack"] for r in views["insights_dashboard_usage"]})
        self.assertEqual(views["insights_public_dashboards"], [])

    def test_every_declared_schema_matches_the_view_it_describes(self):
        for name, schema in insights.VIEW_SCHEMAS.items():
            rows = self.views.get(name) or []
            if not rows:
                continue
            with self.subTest(view=name):
                self.assertEqual(list(rows[0]), [k for k, _ in schema])


class RegionalScopeTest(unittest.TestCase):
    """A stack's usage-insights datasource returns its WHOLE REGION, not just that stack.

    Measured 2026-08-20: obs-hub's datasource exposed 490 instance_ids belonging to 140 distinct
    stacks, and a `{instance_type="grafana"}` selector with no id filter returned every one of them.
    The first sweep built on that selector reported 340 public dashboards across 170 stacks - which was
    2 public dashboards counted 170 times, each with an identical event count, because every stack in a
    region was reporting its neighbours' events as its own.

    For `instance_type="grafana"` the `instance_id` label is the stack's own `id` (verified: obs-hub's
    654321 appears with 1,157 events while the region totals far more).
    """

    def test_every_query_filters_on_the_stacks_own_instance_id(self):
        sel = ui.selector(instance_id="654321")
        for field, template in ui.SCALARS.items():
            with self.subTest(field=field):
                self.assertIn('instance_id="654321"', template % {"sel": sel},
                              f"{field} would return the whole region, not this stack")
        for field, (template, _l) in ui.BREAKDOWNS.items():
            with self.subTest(breakdown=field):
                self.assertIn('instance_id="654321"', template % {"sel": sel})

    def test_no_query_can_be_issued_without_going_through_the_selector(self):
        """A template that forgot `%(sel)s` would render without any stream selector at all."""
        for field, template in ui.SCALARS.items():
            with self.subTest(field=field):
                self.assertIn("%(sel)s", template)
        for field, (template, _l) in ui.BREAKDOWNS.items():
            with self.subTest(breakdown=field):
                self.assertIn("%(sel)s", template)

    def test_the_filter_is_templated_per_stack_not_hardcoded(self):
        rendered = ui.selector(instance_id="123")
        self.assertIn('instance_id="123"', rendered)

    def test_a_stack_with_no_id_is_not_measured_rather_than_measured_regionally(self):
        """Without an id the only honest answer is 'not measured'. Querying unfiltered would attribute
        the whole region's activity to one stack."""
        rec = ui.probe_stack("s", "https://s.grafana.net", "tok", instance_id="")
        self.assertFalse(rec["available"])
        self.assertEqual(rec["reason"], ui.NO_INSTANCE_ID)


class RuntimeGuardTest(unittest.TestCase):
    """The template check catches a badly-written query at test time. This catches one at run time,
    because the failure mode is silent: an unfiltered query returns real numbers for the wrong scope."""

    def test_an_unfiltered_query_is_refused_not_executed(self):
        with self.assertRaises(ui.RegionalQueryRefused):
            ui._query("https://s", "tok", 'sum(count_over_time({instance_type="grafana"}[24h]))',
                      expected_instance_id="654321")

    def test_the_refusal_names_the_fix(self):
        try:
            ui._query("https://s", "tok", "sum(count_over_time({} [24h]))",
                      expected_instance_id="654321")
        except ui.RegionalQueryRefused as exc:
            self.assertIn("selector()", str(exc))
        else:
            self.fail("expected a refusal")

    def test_a_filtered_query_passes_the_guard(self):
        """It must reach the transport, not be refused. A connection failure proves it got that far."""
        expr = ui.SCALARS["views"] % {"sel": ui.selector(instance_id="654321")}
        with self.assertRaises(Exception) as caught:
            ui._query("http://127.0.0.1:1", "tok", expr,
                      expected_instance_id="654321", timeout=0.4)
        self.assertNotIsInstance(caught.exception, ui.RegionalQueryRefused)

    def test_a_scoped_selector_plus_an_unscoped_selector_is_refused(self):
        expr = (
            'sum(count_over_time({instance_type="grafana", instance_id="654321"}[24h])) '
            'or sum(count_over_time({instance_type="grafana"}[24h]))'
        )
        with self.assertRaises(ui.RegionalQueryRefused):
            ui._query("https://s", "tok", expr, expected_instance_id="654321")

    def test_a_selector_for_a_different_stack_is_refused(self):
        expr = ui.SCALARS["views"] % {"sel": ui.selector(instance_id="999")}
        with self.assertRaises(ui.RegionalQueryRefused):
            ui._query("https://s", "tok", expr, expected_instance_id="654321")


class EnvelopePersistenceTest(unittest.TestCase):
    """An input that is gathered but not PERSISTED cannot be hydrated by any other tier.

    `hydrate` reads inputs from `scans/<tier>/latest.json`, so omitting one from the scan envelope makes
    it invisible outside the run that gathered it - and the symptom is not an error, it is Pillar J
    panels carrying at most one sample in the dashboards' default window.
    """

    def test_the_t2_envelope_carries_every_input_that_hydration_declares_t2_owns(self):
        from types import SimpleNamespace

        import scan
        from collector.emit import hydrate

        stacks = [{"slug": "alpha", "status": "active"}]

        def detail(_client, _cfg, _selected, coverage, *, on_error):
            coverage.record_ok("alpha")
            return {"alpha": {"slug": "alpha"}}

        available = ({"alpha": {"available": True}}, [])
        service_accounts = ({"alpha": {"state": "ok", "accounts": []}}, [])
        client = SimpleNamespace(attempts=SimpleNamespace(requests=0, retries=0))
        cfg = SimpleNamespace(
            tier="t2", stack=None, limit=None, concurrency=1, cap="read", org_id="1",
        )
        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail),
            mock.patch.object(scan, "gather_service_accounts", return_value=service_accounts),
            mock.patch.object(scan, "gather_assistant", return_value=available),
            mock.patch.object(scan, "gather_insights", return_value=available),
            mock.patch.object(scan, "gather_dashboard_inventory", return_value=available),
            mock.patch.object(scan, "gather_datasource_query_cost", return_value=available),
            mock.patch.object(scan, "gather_adaptive_logs", return_value=available),
            mock.patch.object(scan, "gather_public_dashboards", return_value=available),
            mock.patch.object(scan, "gather_alert_routing", return_value=available),
            mock.patch.object(
                scan.hydrate, "hydrate",
                side_effect=lambda _tier, own, **_kwargs: (dict(own), hydrate.Provenance()),
            ),
            mock.patch.object(scan.compose, "build_all", return_value=([], {})),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
        ):
            envelope = scan.run_t2(client, cfg)

        owned = {name for name, tier in hydrate.INPUT_OWNER.items() if tier == "t2"}
        self.assertTrue(owned, "expected t2 to own at least one input")
        self.assertLessEqual(
            owned, set(envelope["data"]),
            f"t2-owned inputs missing from the persisted envelope: {owned - set(envelope['data'])}",
        )


if __name__ == "__main__":
    unittest.main()
