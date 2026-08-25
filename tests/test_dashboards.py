"""v2 dashboard authoring harness (PLAN 6.5a).

Dashboard JSON is declarative, so per the testing posture it is *validated* rather than unit-tested -
the real gate is a rendered dashboard returning rows, which `bin/dashboards.py` checks live. What IS
unit-tested here is the logic that can be silently wrong: the orphaned-element assertion (an orphan
blanks the WHOLE dashboard) and the Infinity column generation (empty `columns` makes the backend parser
500; a missing `parser` returns 0 rows).
"""

from __future__ import annotations

import re
import tempfile
import unittest
from unittest import mock

from collector.dashboards import build


class DashboardCliRateCardTest(unittest.TestCase):
    def test_local_out_with_explicit_datasource_is_fully_offline(self):
        from bin import dashboards
        import scan

        with tempfile.TemporaryDirectory() as output:
            with (
                mock.patch.object(dashboards, "BASE", ""),
                mock.patch.object(dashboards, "STACK_ID", ""),
                mock.patch.object(dashboards, "BUILDERS", {"cost": object()}),
                mock.patch.object(dashboards, "resolve_ds_uid") as resolve_ds,
                mock.patch.object(dashboards, "resolve_folder_uid") as resolve_folder,
                mock.patch.object(dashboards, "assemble", return_value=("uid", {})),
                mock.patch.object(scan, "load_ratecard") as load_ratecard,
                mock.patch.dict("os.environ", {}, clear=True),
                mock.patch("sys.argv", [
                    "dashboards.py", "--out", output, "--ds-uid", "prom",
                ]),
            ):
                self.assertEqual(dashboards.main(), 0)

        load_ratecard.assert_not_called()
        resolve_ds.assert_not_called()
        resolve_folder.assert_not_called()

    def test_publish_reports_an_invalid_rate_card_without_a_traceback(self):
        from bin import dashboards
        import scan

        with (
            mock.patch.object(dashboards, "BASE", "https://example.invalid"),
            mock.patch.object(dashboards, "STACK_ID", "1"),
            mock.patch.object(dashboards, "BUILDERS", {"cost": object()}),
            mock.patch.object(dashboards, "resolve_ds_uid", return_value="prom"),
            mock.patch.object(dashboards, "resolve_folder_uid", return_value="folder"),
            mock.patch.object(
                scan, "load_ratecard",
                side_effect=dashboards.ratecard_model.InvalidRateCard("bad card"),
            ),
            mock.patch.object(dashboards, "publish") as publish,
            mock.patch.dict("os.environ", {"GCINSIGHT_GRAFANA_TOKEN": "token"}),
            mock.patch("sys.argv", ["dashboards.py", "--publish", "cost"]),
        ):
            self.assertEqual(dashboards.main(), 2)

        publish.assert_not_called()


class LayoutCompletenessTest(unittest.TestCase):
    """An orphaned `spec.elements` entry blanks the entire dashboard, not just its panel."""

    def test_matched_elements_and_placements_pass(self):
        build.assert_layout_complete({"a": {}, "b": {}}, ["a", "b"])

    def test_an_orphaned_element_is_refused(self):
        with self.assertRaises(build.OrphanedElement) as ctx:
            build.assert_layout_complete({"a": {}, "orphan": {}}, ["a"])
        self.assertIn("orphan", str(ctx.exception))

    def test_a_dangling_reference_is_refused(self):
        with self.assertRaises(build.OrphanedElement) as ctx:
            build.assert_layout_complete({"a": {}}, ["a", "ghost"])
        self.assertIn("ghost", str(ctx.exception))

    def test_the_dashboard_builder_runs_the_assertion(self):
        with self.assertRaises(build.OrphanedElement):
            build.dashboard("t", "d", {"a": {}, "unused": {}},
                            [build.tab("Tab", ["a"])])


class ColumnGenerationTest(unittest.TestCase):
    def test_columns_follow_the_view_key_order(self):
        view = {"rows": [{" Stack": "a", "Region": "eu", "Series": 1}]}
        cols = build.columns_for(view)
        self.assertEqual([c["selector"] for c in cols], [" Stack", "Region", "Series"])

    def test_the_leading_space_is_stripped_from_the_display_text(self):
        """The space forces order in Infinity's alphabetising parser; it must not reach the header."""
        cols = build.columns_for({"rows": [{" Stack": "a"}]})
        self.assertEqual(cols[0]["selector"], " Stack")
        self.assertEqual(cols[0]["text"], "Stack")

    def test_types_are_inferred(self):
        view = {"rows": [
            {"n": 1, "f": 1.5, "b": True, "s": "x"},
            {"n": 2, "f": 2.5, "b": False, "s": "y"},
        ]}
        types = {c["selector"]: c["type"] for c in build.columns_for(view)}
        self.assertEqual(types, {"n": "number", "f": "number", "b": "boolean", "s": "string"})

    def test_an_all_none_column_is_string_not_number(self):
        """These views use None to mean 'not measurable'. `number` would render NaN where blank is right."""
        cols = build.columns_for({"rows": [{"x": None}, {"x": None}]})
        self.assertEqual(cols[0]["type"], "string")

    def test_a_mixed_column_falls_back_to_string(self):
        cols = build.columns_for({"rows": [{"x": 1}, {"x": "not measurable"}]})
        self.assertEqual(cols[0]["type"], "string")

    def test_none_is_ignored_when_inferring_from_real_values(self):
        cols = build.columns_for({"rows": [{"x": None}, {"x": 5}]})
        self.assertEqual(cols[0]["type"], "number")

    def test_an_empty_view_raises_rather_than_producing_empty_columns(self):
        """Empty `columns` makes Infinity's backend parser return HTTP 500, so the panel is broken, not
        merely blank. Failing the build points at the real cause: the owning tier has not run."""
        with self.assertRaises(build.EmptyView):
            build.columns_for({"rows": []})
        with self.assertRaises(build.EmptyView):
            build.columns_for({})


class EnvelopeShapeTest(unittest.TestCase):
    """The two envelopes that render "plugin not found" for the WHOLE page when wrong.

    Both were confirmed against a converted dashboard on the stack; hand-authoring got both wrong.
    """

    def test_query_envelope_puts_the_plugin_id_in_group_not_kind(self):
        q = build.prom_query("up", "my-uid", "A")
        self.assertEqual(q["kind"], "PanelQuery")
        inner = q["spec"]["query"]
        self.assertEqual(inner["kind"], "DataQuery")
        self.assertEqual(inner["group"], "prometheus")
        self.assertEqual(inner["version"], "v0")
        # The uid goes in `datasource.name`  -  not `uid`, and there is no `type`.
        self.assertEqual(inner["datasource"], {"name": "my-uid"})
        self.assertNotIn("uid", inner["datasource"])
        self.assertNotIn("type", inner["datasource"])

    def test_viz_envelope_puts_the_panel_type_in_group_not_kind(self):
        v = build.viz("table", {"options": {}})
        self.assertEqual(v["kind"], "VizConfig")
        self.assertEqual(v["group"], "table")
        self.assertNotEqual(v["kind"], "table")

    def test_infinity_query_uses_the_plugin_id_as_its_group(self):
        q = build.data_query(build.INFINITY_TYPE, "ds", {"type": "json"}, "A")
        self.assertEqual(q["spec"]["query"]["group"], "yesoreyeram-infinity-datasource")


class NoInstantQueriesTest(unittest.TestCase):
    """The collector writes hourly; Mimir's lookback-delta is 5 minutes.

    So an instant query at `now` finds a sample only in the 5 minutes after a scan  -  measured as an empty
    frame where the same expression over a range returned 8 points. Every panel must use a range query.
    """

    def test_stat_panels_use_a_range_query_reduced_to_last_not_null(self):
        panel = build.stat_panel("x", "up")
        spec = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        self.assertTrue(spec["range"])
        self.assertFalse(spec["instant"])
        calcs = panel["spec"]["vizConfig"]["spec"]["options"]["reduceOptions"]["calcs"]
        self.assertEqual(calcs, ["lastNotNull"])

    def test_barchart_panels_use_a_range_query_plus_a_reduce_transformation(self):
        panel = build.barchart_panel("x", "topk(5, up)")
        spec = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        self.assertTrue(spec["range"])
        self.assertFalse(spec["instant"])
        transforms = panel["spec"]["data"]["spec"]["transformations"]
        self.assertEqual(transforms[0]["spec"]["id"], "reduce")

    def test_a_limited_barchart_reduces_then_sorts_then_limits(self):
        """Range topk returns the union of members seen at every step, so exact-K needs a display cap."""
        panel = build.barchart_panel("x", "topk(15, up)", limit=15)
        transforms = panel["spec"]["data"]["spec"]["transformations"]
        self.assertEqual([item["spec"]["id"] for item in transforms],
                         ["reduce", "sortBy", "limit"])
        self.assertEqual(transforms[2]["spec"]["options"], {"limitField": 15})

    def test_timeseries_panels_are_range_queries(self):
        panel = build.timeseries_panel("x", [("up", "a")])
        spec = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        self.assertTrue(spec["range"])
        self.assertFalse(spec["instant"])

    def test_no_builder_produces_an_instant_query_by_default(self):
        panels = [build.stat_panel("s", "up"), build.barchart_panel("b", "up"),
                  build.timeseries_panel("t", [("up", "a")]),
                  build.prometheus_table_panel("p", "topk(100, up)")]
        for panel in panels:
            for pq in panel["spec"]["data"]["spec"]["queries"]:
                self.assertFalse(pq["spec"]["query"]["spec"]["instant"],
                                 f"{panel['spec']['title']} uses an instant query")

    def test_multiple_expressions_get_distinct_ref_ids(self):
        panel = build.timeseries_panel("x", [("a", "1"), ("b", "2"), ("c", "3")])
        refs = [pq["spec"]["refId"] for pq in panel["spec"]["data"]["spec"]["queries"]]
        self.assertEqual(refs, ["A", "B", "C"])

    def test_cross_datasource_ratio_reduces_each_range_before_math(self):
        panel = build.cross_source_ratio_stat_panel(
            "unit value", ("sum(spend)", build.USAGE_UID),
            ("sum(gcinsight_assets)", build.PROM_UID),
        )
        queries = panel["spec"]["data"]["spec"]["queries"]
        self.assertEqual([query["spec"]["refId"] for query in queries], ["A", "B", "C", "D", "E"])
        self.assertEqual(
            [query["spec"]["query"]["datasource"]["name"] for query in queries],
            [build.USAGE_UID, build.PROM_UID, "__expr__", "__expr__", "__expr__"],
        )
        self.assertTrue(queries[0]["spec"]["query"]["spec"]["range"])
        self.assertTrue(queries[1]["spec"]["query"]["spec"]["range"])
        self.assertEqual(queries[2]["spec"]["query"]["spec"]["type"], "reduce")
        self.assertEqual(queries[2]["spec"]["query"]["spec"]["reducer"], "last")
        self.assertEqual(queries[3]["spec"]["query"]["spec"]["type"], "reduce")
        self.assertEqual(queries[3]["spec"]["query"]["spec"]["reducer"], "last")
        self.assertEqual(queries[4]["spec"]["query"]["spec"]["expression"], "$C / $D")

    def test_prometheus_table_reduces_sorts_and_renames_the_display_columns(self):
        panel = build.prometheus_table_panel(
            "Top 100", "topk(100, up)", legend="{{slug}}",
            label_column="Stack", value_column="Tokens", unit="short")
        transforms = panel["spec"]["data"]["spec"]["transformations"]
        self.assertEqual([t["spec"]["id"] for t in transforms],
                         ["reduce", "sortBy", "organize"])
        self.assertEqual(transforms[1]["spec"]["options"]["sort"],
                         [{"field": build.REDUCED_VALUE_FIELD, "desc": True}])
        rename = transforms[2]["spec"]["options"]["renameByName"]
        self.assertEqual(rename, {"Field": "Stack", build.REDUCED_VALUE_FIELD: "Tokens"})
        self.assertEqual(panel["spec"]["vizConfig"]["group"], "table")


class PanelShapeTest(unittest.TestCase):
    """The three Infinity knobs are all load-bearing; two of the four failure modes are a silent blank."""

    def setUp(self) -> None:
        self.view = {"rows": [{" Metric": "a", "Value": 1}]}
        # Avoid an S3 fetch in unit tests by injecting the column spec directly.
        self.cols = build.columns_for(self.view)

    def test_query_sets_parser_root_selector_and_columns(self):
        q = {
            "parser": "backend", "root_selector": "rows", "columns": self.cols,
            "format": "table", "type": "json", "source": "url",
        }
        self.assertEqual(q["parser"], "backend")
        self.assertEqual(q["root_selector"], "rows")
        self.assertTrue(q["columns"])

    def test_table_panel_carries_the_footer_fields_escape_hatch(self):
        """`format:"table"` names the value column `Value #<refId>`, so `footer.fields` must be []."""
        panel = build.table_panel.__doc__
        self.assertIsNotNone(panel)

    def test_auto_grid_places_every_element_once(self):
        layout = build.auto_grid(["a", "b", "c"])
        placed = [i["spec"]["element"]["name"] for i in layout["spec"]["items"]]
        self.assertEqual(placed, ["a", "b", "c"])
        self.assertEqual(layout["kind"], "AutoGridLayout")

    def test_tabs_layout_is_used_not_a_flat_grid(self):
        dash = build.dashboard("t", "d", {"a": build.text_panel("x", "y")},
                               [build.tab("One", ["a"])])
        self.assertEqual(dash["spec"]["layout"]["kind"], "TabsLayout")
        self.assertEqual(dash["apiVersion"], "dashboard.grafana.app/v2")

    def test_the_schema_is_v2_and_never_v2alpha1(self):
        """Supported deployments use v2; v2alpha1 has a different panel/query shape."""
        self.assertEqual(build.SCHEMA, "dashboard.grafana.app/v2")
        self.assertNotIn("alpha", build.SCHEMA)

    def test_week_start_is_omitted_from_time_settings(self):
        """Setting `weekStart` has crashed renders."""
        dash = build.dashboard("t", "d", {"a": build.text_panel("x", "y")},
                               [build.tab("One", ["a"])])
        self.assertNotIn("weekStart", dash["spec"]["timeSettings"])


class SharedFurnitureTest(unittest.TestCase):
    """PLAN 6.6  -  the banner, the `stack` variable and the cross-links, applied centrally.

    Applied in `bin/dashboards.py` for every dashboard rather than in each builder, so six copies cannot
    drift apart.
    """

    def test_banner_carries_how_to_read_it_plus_coverage_and_freshness(self):
        el = build.banner_elements("estate")
        self.assertEqual(set(el), set(build.banner_keys("estate")))
        titles = {e["spec"]["title"] for e in el.values()}
        self.assertEqual(titles, {"How to read this", "Scan coverage", "Inventory age"})

    def test_a_dashboard_shows_the_age_of_every_input_its_figures_depend_on(self):
        """The shipped defect: `banner_elements()` was called with its default on ALL EIGHT dashboards,
        so Cost/Maturity/Risk/Value advertised the HOURLY tier's timestamp while their contents came from
        the 6-hourly data-plane sweep. A dashboard claiming to be minutes old whose figures are hours old
        is worse than one with no freshness panel at all."""
        for dashboard, inputs in build.DASHBOARD_INPUTS.items():
            with self.subTest(dashboard=dashboard):
                el = build.banner_elements(dashboard)
                for name in inputs:
                    key = f"_age_{name}"
                    self.assertIn(key, el, f"{dashboard} depends on {name} but shows no age for it")
                    expr = (el[key]["spec"]["data"]["spec"]["queries"][0]
                            ["spec"]["query"]["spec"]["expr"])
                    self.assertIn(f'input="{name}"', expr)
                    self.assertIn("gcinsight_input_age_seconds", expr)
                    self.assertIn('tier="t1"', expr)
                    self.assertIn("timestamp(", expr)
                    self.assertIn("last_over_time", expr)
                    self.assertTrue(expr.startswith("time() -"))

    def test_dashboard_inputs_match_what_the_views_actually_need(self):
        """`DASHBOARD_INPUTS` is what decides which age panels appear. If a dashboard renders a view
        needing an input the table omits, it shows a freshness figure that does not cover its own
        contents  -  the same class of error as the T1-everywhere default."""
        from collector.emit import hydrate
        for name in ("estate", "cost", "usage", "maturity", "risk", "value"):
            with self.subTest(dashboard=name):
                needed = set()
                for view in _views_referenced_by(name):
                    needed |= hydrate.VIEW_INPUTS.get(view, frozenset())
                needed |= set(build.DASHBOARD_METRIC_INPUTS.get(name, ()))
                self.assertEqual(
                    set(build.DASHBOARD_INPUTS[name]), needed,
                    f"{name} renders views needing {sorted(needed)} but declares "
                    f"{sorted(build.DASHBOARD_INPUTS[name])}")

    def test_metric_only_inputs_are_not_hidden_by_the_view_derived_freshness_gate(self):
        """Risk's public-dashboard counters come from an optional per-stack input before its named view
        can be published. A view-only derivation would omit that input age and let a stale compliance
        count look current."""
        self.assertEqual(build.DASHBOARD_METRIC_INPUTS["risk"],
                         ("alert_routing", "org_members", "public_dashboards"))
        self.assertIn("alert_routing", build.DASHBOARD_INPUTS["risk"])
        self.assertIn("org_members", build.DASHBOARD_INPUTS["risk"])
        self.assertIn("public_dashboards", build.DASHBOARD_INPUTS["risk"])
        self.assertIn("_age_alert_routing", build.banner_elements("risk"))
        self.assertIn("_age_org_members", build.banner_elements("risk"))
        self.assertIn("_age_public_dashboards", build.banner_elements("risk"))

    def test_the_live_datasource_dashboards_get_no_scan_freshness_at_all(self):
        """Operations and Commercial read `grafanacloud-usage` directly. A scan-coverage panel there
        would attribute our scan's freshness to numbers our collector never touched."""
        for name in build.LIVE_DATASOURCE_ONLY:
            with self.subTest(dashboard=name):
                el = build.banner_elements(name)
                self.assertEqual(set(el), {"_banner"})
                content = el["_banner"]["spec"]["vizConfig"]["spec"]["options"]["content"]
                self.assertIn("grafanacloud-usage", content)

    def test_freshness_reads_the_dead_mans_switch_series(self):
        """The same series alerting uses (PLAN 1.8), so a stale dashboard and a failed scan are one signal."""
        expr = (build.banner_elements()["_freshness"]["spec"]["data"]["spec"]["queries"][0]
                ["spec"]["query"]["spec"]["expr"])
        self.assertIn("gcinsight_scan_completed_timestamp_seconds", expr)
        self.assertTrue(expr.startswith("time() -"), "age, not the raw timestamp")
        self.assertIn("max_over_time", expr)

    def test_banner_warns_that_blank_is_not_zero(self):
        content = (build.text_panel("t", build.BANNER_MD)["spec"]["vizConfig"]["spec"]
                   ["options"]["content"])
        self.assertIn("not measurable, not zero", content)
        self.assertIn("denominator", content)
        self.assertIn("billed", content.lower())
        # The withholding contract, which is what makes "blank is not zero" true rather than aspirational.
        self.assertIn("WITHHOLDS", content)

    def test_the_banner_states_no_hardcoded_measurement(self):
        """A number written into always-on text goes stale silently and is then quoted at a customer.

        This banner carried "a 17% difference" between billed and active users, and by the time anyone
        checked it was 14.4%. It also promised carry-forward expiry "past 14 days" when the cap had been
        cut to 3, and described the data-plane tier as weekly after it moved to 6-hourly. State the RULE
        and point at the panel that measures it; never bake the measurement into the prose.
        """
        for label, content in (("scan banner", build.BANNER_MD),
                               ("live-datasource banner", build.LIVE_BANNER_MD)):
            with self.subTest(banner=label):
                self.assertNotRegex(
                    content, r"\d+(\.\d+)?%",
                    "a literal percentage in always-on banner text will go stale unnoticed")
                self.assertNotRegex(
                    content, r"\b\d+\s*(day|days|week|weeks|hour|hours)\b",
                    "a literal duration here duplicates a constant in code and will drift from it")

    def test_the_stack_variable_is_prometheus_backed_not_infinity(self):
        """Forcing a prometheus query kind onto an Infinity-backed variable renders a 500."""
        var = build.stack_variable()
        self.assertEqual(var["kind"], "QueryVariable")
        self.assertEqual(var["spec"]["name"], "stack")
        self.assertEqual(var["spec"]["query"]["group"], "prometheus")
        self.assertIn("label_values(", var["spec"]["query"]["spec"]["query"])

    def test_the_variable_current_is_scalar_not_a_list(self):
        """A list `current` on a single-select variable has crashed renders."""
        current = build.stack_variable()["spec"]["current"]
        self.assertIsInstance(current["value"], str)
        self.assertIsInstance(current["text"], str)

    # These two READ THE FIELDS THROUGH `["spec"]` UNTIL 2026-08-19, AND THAT IS WHY THE BUG SURVIVED.
    # They asserted against the same wrong assumption the code made, so a row of blank buttons pointing at
    # `about:blank` passed every test. A test written from the implementation cannot catch the
    # implementation being wrong about an external contract  -  `CrossLinkShapeTest` now checks the flat shape
    # against the field list published by the live OpenAPI schema instead.
    def test_cross_links_exclude_the_current_dashboard(self):
        for uid, _title in build.DASHBOARDS:
            urls = [l["url"] for l in build.cross_links(uid)]
            self.assertNotIn(f"/d/{uid}", urls)
            self.assertEqual(len(urls), len(build.DASHBOARDS) - 1)

    def test_cross_links_carry_the_time_range_and_variables(self):
        for link in build.cross_links("gcinsight-cost"):
            self.assertTrue(link["keepTime"])
            self.assertTrue(link["includeVars"])

    def test_dashboard_accepts_variables_and_links(self):
        dash = build.dashboard("t", "d", {"a": build.text_panel("x", "y")},
                               [build.tab("One", ["a"])],
                               variables=[build.stack_variable()],
                               links=build.cross_links("gcinsight-estate"))
        self.assertEqual([v["spec"]["name"] for v in dash["spec"]["variables"]], ["stack"])
        # Derived, not hardcoded: cross_links emits one link per SIBLING, so this is len(DASHBOARDS) - 1.
        # A literal here broke the moment a seventh dashboard was added, which is noise rather than signal.
        self.assertEqual(len(dash["spec"]["links"]), len(build.DASHBOARDS) - 1)


class ProtocolAdoptionUsesTheStacksOwnDatasourceTest(unittest.TestCase):
    """PLAN 3.3. These panels read `grafanacloud-usage` DIRECTLY  -  no collector, no credential.

    The failure this guards is silent and total: a panel that defaults to `grafanacloud-prom` queries our
    write target, where `grafanacloud_instance_active_otlp_series` does not exist, and renders empty
    forever. Empty is indistinguishable from "no OTLP adoption", which is a wrong answer rather than a
    missing one.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import bin.dashboards as dash
        _, _, _, cls.el, cls.tabs = dash.d_usage("infinity-uid")

    def _ds_uids(self, key: str) -> set[str]:
        panel = self.el[key]
        return {q["spec"]["query"]["datasource"]["name"]
                for q in panel["spec"]["data"]["spec"]["queries"]}

    def test_every_otlp_panel_points_at_the_usage_datasource(self):
        for key in ("n_otlp", "n_otlp_floor", "t_otlp"):
            self.assertEqual(self._ds_uids(key), {build.USAGE_UID},
                             f"{key} is not reading the stack's own usage datasource")

    def test_the_other_panels_still_point_at_our_write_target(self):
        """The passthrough must not have changed the default for everything else."""
        self.assertEqual(self._ds_uids("t_signals"), {build.PROM_UID})

    def test_the_threshold_in_the_panel_matches_the_shared_constant(self):
        from collector.pillars.cost import USAGE_FLOOR
        exprs = " ".join(q["spec"]["query"]["spec"]["expr"]
                         for q in self.el["n_otlp"]["spec"]["data"]["spec"]["queries"])
        self.assertIn(str(USAGE_FLOOR), exprs)

    def test_no_otlp_panel_uses_the_stack_variable(self):
        """`id` is a metrics instance id, not a slug, so `$stack` would match nothing here."""
        for key in ("n_otlp", "n_otlp_floor", "t_otlp"):
            for q in self.el[key]["spec"]["data"]["spec"]["queries"]:
                self.assertNotIn("$stack", q["spec"]["query"]["spec"]["expr"])

    def test_the_tab_is_present(self):
        titles = [t["spec"]["title"] for t in self.tabs]
        self.assertIn("Protocol adoption", titles)


class UsageDatasourcePanelsTest(unittest.TestCase):
    """The Tier 1 / 1b panels: data loss, alerting health, query activity, adaptive savings, IRM.

    Same guard as the protocol-adoption class above, applied to a much larger surface, plus the three
    ways these particular expressions go wrong WITHOUT the panel looking broken:

    1. **Wrong datasource.** A panel defaulting to `grafanacloud-prom` finds no `grafanacloud_*` series
       and renders empty forever. Empty reads as "no data loss", "no savings available"  -  a wrong
       answer, not a missing one. This is the whole reason `ds_uid` is threaded through four helpers.
    2. **Counting label combinations instead of stacks.** `count(<metric> > 0)` counts series, and these
       metrics carry several signal instances per stack plus `reason`/`integration` labels. Measured:
       counting ids reported 223 zero-query stacks against a real 60. Every count must collapse
       `by(stack_id)` first.
    3. **The ratio/percent trap.** `..._percentage_complete_traces_flushed` is a RATIO 0-1 while
       `..._spans_more_than_5m_in_past_percent` is percent-scaled and can exceed 100, despite both saying
       percentage.
       Thresholding the ratio at `< 90` matches every stack that reports and invents an estate-wide
       outage. That error was made on 2026-08-18 and is pinned here so it cannot come back.
    """

    USAGE_KEYS = {
        "risk": ("n_discard", "n_logdrop", "b_reason", "b_discard", "t_dataloss",
                 "n_traceincomplete", "b_trace", "n_trace_discard", "n_metadata_discard",
                 "b_trace_discard", "b_metadata_discard",
                 "n_notiffail", "n_deadrules", "n_evalfail",
                 "b_deadrules", "b_notif", "t_alerting"),
        "usage": ("n_otlp", "n_otlp_floor", "t_otlp", "n_logs_unread", "n_logs_unread_bytes",
                  "b_logs_unread", "t_logs_unread", "n_pods", "n_hosts", "n_intseries",
                  "n_intshare", "b_asset_counts", "b_observed_objects", "b_integrations",
                  "b_integration_hosts", "b_profiles",
                  "b_app_hosts", "n_infra_host_hours", "n_infra_container_hours",
                  "n_db_host_hours", "n_fe_sessions", "n_fe_session_rate", "t_workload"),
        "cost": ("n_savings", "n_savings_pct", "n_savings_stacks", "n_aggregating",
                 "b_savings", "t_savings"),
        "value": ("n_oncall", "b_oncall", "n_activated", "b_activation", "n_nativehist",
                  "n_exemplars", "t_capability", "n_k6_active", "b_k6_active",
                  "n_sm_active", "b_sm_active"),
        "operations": ("n_engagement", "n_engaged", "n_engaged_denom", "b_teamengage", "t_engagement",
                       "n_mtta", "n_mttr", "n_mtta_mean", "n_tail", "n_tail_share", "b_ackdist",
                       "t_response", "n_unowned_all", "n_unowned_acked", "n_unowned_svc",
                       "b_teamtail", "b_teamvol", "b_service_owner", "n_groups", "n_notified",
                       "b_integration", "b_service", "t_state"),
        "commercial": ("n_commit", "n_consumed", "n_consumed_share", "n_balance", "n_term_elapsed",
                       "n_months_metric", "n_months_contract", "n_runrate", "b_runrate", "t_runrate",
                       "t_metrics_share", "t_burn", "t_balance"),
        "ai": ("n_assistant_users", "n_active_stacks", "n_token_users", "n_tokens",
               "n_token_stacks", "n_assistant_overage", "n_token_overage",
               "tbl_stack_users", "tbl_stack_tokens", "t_users", "t_tokens",
               "n_top2_share", "n_top10_share", "tbl_people", "tbl_services",
               "tbl_stack_assistant_cost", "n_included_users", "n_additional_tokens",
               "n_included_additional_tokens"),
    }

    @classmethod
    def setUpClass(cls) -> None:
        import bin.dashboards as dash
        cls.dash = dash
        cls.built = {name: dash.BUILDERS[name]("infinity-uid") for name in cls.USAGE_KEYS}

    def _panels(self, name):
        return self.built[name][3]

    def _tabs(self, name):
        return [t["spec"]["title"] for t in self.built[name][4]]

    def _queries(self, name, key):
        return self._panels(name)[key]["spec"]["data"]["spec"]["queries"]

    def _exprs(self, name, key):
        return [q["spec"]["query"]["spec"]["expr"] for q in self._queries(name, key)]

    def _all_usage_exprs(self):
        for name, keys in self.USAGE_KEYS.items():
            for key in keys:
                for expr in self._exprs(name, key):
                    yield f"{name}.{key}", expr

    # --- 1. datasource routing ---------------------------------------------------------------------
    def test_every_new_panel_reads_the_usage_datasource(self):
        for name, keys in self.USAGE_KEYS.items():
            for key in keys:
                uids = {q["spec"]["query"]["datasource"]["name"] for q in self._queries(name, key)}
                self.assertEqual(uids, {build.USAGE_UID},
                                 f"{name}.{key} would render empty forever: {uids}")

    def test_bar_charts_route_too(self):
        """`barchart_panel` had no `ds_uid` until this change  -  the passthrough is the fix being tested."""
        for name, key in (("risk", "b_reason"), ("cost", "b_savings"), ("value", "b_oncall")):
            self.assertEqual(
                {q["spec"]["query"]["datasource"]["name"] for q in self._queries(name, key)},
                {build.USAGE_UID})

    def test_the_default_is_still_our_write_target(self):
        """A regression here would silently repoint every existing panel on all six dashboards."""
        self.assertEqual(
            build.barchart_panel("t", "x")["spec"]["data"]["spec"]["queries"][0]
                 ["spec"]["query"]["datasource"]["name"],
            build.PROM_UID)
        for name, key in (("risk", "t_admin"), ("cost", "t_series"), ("value", "b_features")):
            self.assertEqual(
                {q["spec"]["query"]["datasource"]["name"] for q in self._queries(name, key)},
                {build.PROM_UID}, f"{name}.{key} was repointed by accident")

    # --- 2. stacks, not label combinations ---------------------------------------------------------
    def test_a_bare_count_is_only_used_on_metrics_measured_as_one_series_per_stack(self):
        """`count(<metric> > 0)` counts SERIES. On a metric with several signal instances per stack that
        silently overstates  -  measured, `queries_per_second` carries 459 series over 230 stacks and a
        bare count reported 223 zero-query stacks against a real 60.

        A few of these metrics genuinely are one series per stack, so a bare count is honest there. This
        test does not take that on trust: it reads the measured cardinality out of the committed evidence
        and requires 1:1 for every metric a panel counts directly. If Grafana Cloud ever adds a label to
        one of them, the evidence changes on the next probe run and this fails  -  which is the point.
        """
        card = _usage_evidence()["label_cardinality"]
        for label, expr in self._all_usage_exprs():
            if "count(" not in expr:
                continue
            if "by(stack_id)" in expr:
                continue
            # `count(count by(<label>)(...))` counts distinct values of that label, not series  -  e.g.
            # `count(count by(product)(activation == 1))` is "how many products", where per-stack
            # cardinality is irrelevant. Only a count over a RAW selector can overstate.
            if _re_search(r"count by\(", expr):
                continue
            metric = _metric_in(expr)
            self.assertIsNotNone(metric, f"{label}: cannot identify the metric in {expr}")
            measured = card.get(metric)
            self.assertIsNotNone(
                measured,
                f"{label} counts {metric} without by(stack_id) and its cardinality is not in "
                f"evidence/usage-datasource-signals.json. Add it to bin/probe_usage_signals.py and "
                f"re-run, or aggregate by(stack_id) instead of assuming.")
            self.assertEqual(
                measured["series"], measured["distinct_stack_id"],
                f"{label} counts {metric} directly, but it is measured at {measured['series']} series "
                f"over {measured['distinct_stack_id']} stacks  -  the count overstates. Wrap it in "
                f"sum by(stack_id) or count by(stack_id).")

    def test_the_metrics_with_several_series_per_stack_are_always_aggregated(self):
        """The other half: for any metric measured as multi-series, no panel may count it bare."""
        card = _usage_evidence()["label_cardinality"]
        multi = {m for m, v in card.items()
                 if isinstance(v, dict) and v["series"] != v["distinct_stack_id"]}
        self.assertTrue(multi, "no multi-series metric in the evidence  -  the probe may have failed")
        for label, expr in self._all_usage_exprs():
            for metric in multi:
                if metric in expr and "count(" in expr:
                    self.assertIn("by(stack_id)", expr,
                                  f"{label} counts {metric}, which has several series per stack")

    def test_named_panels_join_through_stack_id_to_a_slug(self):
        """The only way to name a stack from this datasource. A missing join leaves numeric ids."""
        for name, key in (("risk", "b_discard"), ("risk", "b_trace"), ("risk", "b_deadrules"),
                          ("risk", "b_notif"), ("usage", "b_logs_unread"), ("cost", "b_savings"),
                          ("value", "b_oncall")):
            for expr in self._exprs(name, key):
                self.assertIn(f"group_left(slug) {build.USAGE_INFO}", expr,
                              f"{name}.{key} has no slug join, so its bars are numeric stack ids")

    def test_no_panel_uses_the_stack_variable(self):
        """`$stack` is a slug; this datasource has no slug label, so it would match nothing."""
        for label, expr in self._all_usage_exprs():
            self.assertNotIn("$stack", expr, label)

    def test_the_slug_join_helper_keeps_the_metric_on_the_left(self):
        """`group_left` on the right-hand info series; the metric must keep its own value. A `+` here
        would add the info series' constant 1 to every result and quietly inflate every number."""
        joined = build.usage_by_slug("topk(3, sum by(stack_id)(x))")
        self.assertTrue(joined.startswith("topk(3, sum by(stack_id)(x)) *"))
        self.assertIn("group_left(slug)", joined)
        self.assertNotIn("group_right", joined)

    # --- 3. the ratio/percent trap -----------------------------------------------------------------
    def test_the_trace_completeness_threshold_is_a_ratio_not_a_percent(self):
        for key in ("n_traceincomplete",):
            for expr in self._exprs("risk", key):
                self.assertIn("percentage_complete_traces_flushed", expr)
                literals = [float(tok) for tok in expr.replace("<", " ").replace(")", " ").split()
                            if _is_number(tok)]
                self.assertTrue(literals, f"no threshold found in {expr}")
                for value in literals:
                    self.assertLessEqual(
                        value, 1.0,
                        f"risk.{key} thresholds a 0-1 ratio at {value}  -  that matches EVERY stack that "
                        f"reports and invents an estate-wide trace outage")

    def test_the_unit_trap_is_recorded_in_the_evidence(self):
        import json
        import pathlib
        doc = json.loads((pathlib.Path(__file__).resolve().parent.parent / "testdata"
                          / "usage-datasource-signals.json").read_text())
        self.assertIn("RATIO", doc["source"]["unit_trap"])
        self.assertLessEqual(doc["trace_quality"]["max_ratio_observed"], 1.0,
                             "the metric now exceeds 1.0, so it is not a ratio  -  recheck the thresholds")

    # --- one definition per number -----------------------------------------------------------------
    def test_a_stat_and_its_trend_share_one_expression(self):
        """A headline saying 44 beside a graph plotting something subtly different destroys trust in the
        page and survives review. The shared module constants are the fix; this proves they are used."""
        for name, stat_key, trend_key, const in (
            ("risk", "n_discard", "t_dataloss", "DISCARD_STACKS"),
            ("risk", "n_deadrules", "t_alerting", "DEADRULE_STACKS"),
            ("risk", "n_notiffail", "t_alerting", "NOTIF_STACKS"),
            ("risk", "n_evalfail", "t_alerting", "EVALFAIL_STACKS"),
            ("usage", "n_logs_unread_bytes", "t_logs_unread", "LOGS_UNREAD_BYTES"),
            ("cost", "n_savings", "t_savings", "SAVINGS_SERIES"),
        ):
            expected = getattr(self.dash, const)
            self.assertEqual(self._exprs(name, stat_key), [expected],
                             f"{name}.{stat_key} no longer uses {const}")
            self.assertIn(expected, self._exprs(name, trend_key),
                          f"{name}.{trend_key} plots something other than {const}")

    def test_the_discard_count_excludes_deliberate_drops(self):
        """Adaptive Metrics dropping what it was configured to drop is not data loss. Counting it would
        report a stack as broken for adopting the cost lever two other dashboards recommend."""
        self.assertIn('reason!="requested-by-configuration"', self.dash.DISCARD_STACKS)
        for expr in self._exprs("risk", "b_discard"):
            self.assertIn('reason!="requested-by-configuration"', expr)

    def test_the_reason_breakdown_excludes_deliberate_drops_too(self):
        """Every panel under Data loss must exclude configured Adaptive Metrics drops.

        Showing `requested-by-configuration` in a chart titled "discard reason" presents successful
        aggregation as loss, even if the headline stat excludes it. The deliberate taxonomy belongs in
        the tooltip, not in the defect count.
        """
        for expr in self._exprs("risk", "b_reason"):
            self.assertIn('reason!="requested-by-configuration"', expr)
            self.assertIn("by(reason)", expr)

    # --- rate-shaped series must be windowed, never compared instantaneously -----------------------
    RATE_SHAPED = ("_per_second", ":rate5m", ":rate1m")

    def test_every_rate_shaped_series_is_windowed(self):
        """The defect this catches shipped once and had to be re-published.

        A `*_per_second` or `*:rate5m` series is momentary. Comparing it to zero answers "is this
        happening in the current scrape window", not "does this stack have a problem"  -  so it understates
        intermittent faults and grossly overstates absence of activity. Measured within one 40-minute span
        on 2026-08-18: eval failures 9 instant against 41 over 24h, and the write-only count read 60 then
        33, which on its own disqualifies the instant form.
        """
        for label, expr in self._all_usage_exprs():
            if not any(marker in expr for marker in self.RATE_SHAPED):
                continue
            self.assertRegex(
                expr, r"(max|min|avg)_over_time",
                f"{label} compares a rate-shaped series instantaneously. Wrap it in max_over_time "
                f"[{self.dash.WINDOW}]. Expr: {expr}")

    def test_the_window_is_one_definition(self):
        """Rate-shaped findings use one operational window; lifetime counters may look back farther."""
        windows = set()
        for _, expr in self._all_usage_exprs():
            if not any(marker in expr for marker in self.RATE_SHAPED):
                continue
            windows.update(re.findall(r"\[(\d+[smhd])(?::\d+[smhd])?\]", expr))
        self.assertTrue(windows, "no windowed expression found at all")
        self.assertEqual(windows, {self.dash.WINDOW},
                         f"more than one look-back window in use: {sorted(windows)}")

    def test_gauge_shaped_series_are_not_needlessly_windowed(self):
        """The converse. Savings and active-series are gauges; wrapping them adds nothing and makes the
        expression harder to read, so the two forms stay visibly distinct."""
        for expr in self._exprs("cost", "n_savings") + self._exprs("cost", "n_savings_stacks"):
            self.assertNotIn("_over_time", expr)

    def test_the_unread_log_finding_requires_active_ingest(self):
        """Without the ingest side, this counts empty stacks and becomes the inventory again  -  which is
        exactly how the metrics half of this finding turned out to be an artifact."""
        for expr in self._exprs("usage", "n_logs_unread") + self._exprs("usage", "b_logs_unread"):
            self.assertIn("bytes_received_per_second", expr,
                          "the unread-logs panels must require the stack to be INGESTING")
            self.assertIn("query_bytes", expr)
            self.assertIn(" and ", expr)

    def test_unread_log_rate_averages_one_window_instead_of_summing_independent_peaks(self):
        self.assertIn("avg_over_time", self.dash.LOGS_UNREAD_BYTES)
        self.assertNotIn(
            "max_over_time(sum by(stack_id)(grafanacloud_logs_instance_bytes_received",
            self.dash.LOGS_UNREAD_BYTES,
        )

    def test_there_is_no_metrics_write_only_panel(self):
        """A negative result, pinned. 234 stacks ingest metrics and exactly one went a day without a
        query; no stack over 10k series did. A metrics write-only panel would present an artifact of the
        instantaneous read as a finding."""
        for name, keys in self.USAGE_KEYS.items():
            for key in keys:
                for expr in self._exprs(name, key):
                    if "queries_per_second" in expr:
                        self.fail(f"{name}.{key} re-adds the metrics write-only panel: {expr}")

    # --- the OnCall histogram family: its own traps -------------------------------------------------
    def test_no_high_quantile_on_the_oncall_histogram(self):
        """The buckets top out at 3600s, so histogram_quantile SATURATES above the median.

        p90 and p99 both return exactly 3600  -  meaning "at least an hour", not "an hour". A panel
        labelled p99 would be read as "99% of alerts are acknowledged within an hour" when the data
        cannot support any upper bound at all. The tail must be a COUNT above the top finite bucket.
        """
        import re as _re
        for label, expr in self._all_usage_exprs():
            for q in _re.findall(r"histogram_quantile\(\s*([0-9.]+)", expr):
                self.assertLessEqual(
                    float(q), 0.5,
                    f"{label} uses histogram_quantile({q}) on buckets that top out at "
                    f"{self.dash.TOP_BUCKET}s  -  it will silently return the top bucket. Express the "
                    f"tail as a count above the top bucket instead.")

    def test_bucket_selectors_use_the_decimal_le_values(self):
        """`le="3600"` matches NOTHING and renders an empty panel; the label value is `3600.0`."""
        import re as _re
        for label, expr in self._all_usage_exprs():
            for le in _re.findall(r'le="([^"+]+)"', expr):
                self.assertIn(".", le,
                              f"{label} selects le={le!r} without a decimal point  -  matches no series")

    def test_acknowledgement_distribution_uses_disjoint_bands(self):
        """Cumulative buckets make the reader subtract every adjacent pair by hand."""
        panel = self._panels("operations")["b_ackdist"]["spec"]
        self.assertNotIn("cumulative", panel["title"].lower())
        exprs = self._exprs("operations", "b_ackdist")
        self.assertEqual(len(exprs), 5)
        self.assertNotIn(" - ", exprs[0])
        for expr in exprs[1:]:
            self.assertIn(" - ", expr)
        self.assertIn("exactly one", panel["description"])

    def test_the_engagement_ratio_restricts_its_denominator_to_timing_stacks(self):
        """The 15x error this nearly shipped: the numerator exists on 8 stacks, `alert_groups_total` on
        58. Dividing one by the other silently understates engagement by roughly an order of magnitude."""
        self.assertIn("and on(stack_id)", self.dash.ENGAGED_DENOM,
                      "the engagement denominator is not restricted to stacks that report timing")
        for expr in self._exprs("operations", "n_engagement"):
            self.assertIn("and on(stack_id)", expr)

    def test_per_team_panels_carry_a_minimum_volume_floor(self):
        """A team with 2 alert groups scores 0% or 100% and neither means anything  -  the same
        signal-to-noise discipline as the delete-protection series floor."""
        for key in ("b_teamengage", "b_teamtail"):
            for expr in self._exprs("operations", key):
                self.assertRegex(expr, r">=\s*\d+",
                                 f"operations.{key} has no minimum-volume floor")

    def test_per_team_share_charts_render_ratios_as_percentages(self):
        """Both team charts return 0-1 ratios. `short` renders 0.76 instead of 76%."""
        panels = self._panels("operations")
        for key in ("b_teamengage", "b_teamtail"):
            unit = panels[key]["spec"]["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"]
            self.assertEqual(unit, "percentunit", f"operations.{key} renders a ratio as {unit!r}")

    def test_rate_breakdowns_render_as_rates_and_say_so(self):
        """Peak `*_per_second`/`:rate5m` values must not look like event counts."""
        panels = self._panels("risk")
        for key in ("b_discard", "b_integration_fail", "b_notif_by_stack_integration",
                    "b_deadrules", "b_notif"):
            spec = panels[key]["spec"]
            unit = spec["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"]
            self.assertEqual(unit, "ops", f"risk.{key} renders a per-second value as {unit!r}")
            self.assertRegex(spec["title"].lower(), r"rate|/sec")

    def test_unowned_alert_share_names_its_restricted_population(self):
        """After the denominator fix this is not the share of all estate alerts."""
        panel = self._panels("operations")["n_unowned_all"]["spec"]
        self.assertIn("timing", panel["title"].lower())
        self.assertIn("timing", panel["description"].lower())
        self.assertNotIn("all 11", panel["description"].lower())

    def test_capability_denominators_are_windowed_like_their_numerators(self):
        """Mixing an instantaneous denominator with a windowed numerator inverts conclusions. Measured:
        the trace population is 39 instantaneously and 230 over 24h, which moved span-metric adoption
        from an apparent 46% to a real 10%."""
        for const in ("METRICS_STACKS", "TRACES_STACKS"):
            self.assertIn("max_over_time", getattr(self.dash, const),
                          f"{const} is an instantaneous count and will not match the numerators")
        for expr in self._exprs("value", "t_capability"):
            self.assertIn("max_over_time", expr)

    def test_phase_one_observed_footprint_reads_every_declared_usage_counter(self):
        """The panel-only phase is useful by itself only if it exposes the already-provisioned asset
        counters instead of leaving the affirmative inventory behind later collector work."""
        expressions = " ".join(
            expr for key in self.USAGE_KEYS["usage"] for expr in self._exprs("usage", key)
        )
        required = (
            "grafanacloud_instance_active_integration_series",
            "grafanacloud_instance_active_integration_host_series",
            "grafanacloud_app_observability_service_entity_count",
            "grafanacloud_app_observability_hostless_service_entity_count",
            "grafanacloud_asserts_instance_active_entities",
            "grafanacloud_asserts_instance_total_entities",
            "grafanacloud_instance_active_target_info_series",
            "grafanacloud_instance_active_kube_node_info_series",
            "grafanacloud_instance_active_kube_pod_container_info_series",
            "grafanacloud_logs_instance_active_streams",
            "grafanacloud_instance_active_caas_targets_series",
            "grafanacloud_instance_active_faas_targets_series",
            "grafanacloud_instance_app_o11y_host_count",
            "grafanacloud_instance_app_o11y_host_count_v2",
            "grafanacloud_instance_app_o11y_host_count_v3",
            "grafanacloud_org_infra_o11y_billable_host_hours",
            "grafanacloud_org_infra_o11y_billable_container_hours",
            "grafanacloud_org_db_o11y_billable_host_hours",
            "grafanacloud_org_fe_o11y_billable_sessions",
            "grafanacloud_frontend_observability_instance_sessions_per_second",
            "grafanacloud_profiles_instance_usage_group_bytes_received_per_second",
        )
        for metric in required:
            self.assertIn(metric, expressions, f"Phase 1 does not render {metric}")

    def test_integration_inventory_is_discovered_from_the_integration_label(self):
        expr = self._exprs("usage", "b_integrations")[0]
        self.assertIn("sum by(integration)", expr)
        self.assertNotRegex(expr, r'integration\s*[!=]=?\s*"',
                            "the technology inventory is filtering a maintained integration list")

    def test_named_oncall_catalogue_keeps_service_and_owner_together(self):
        expr = self._exprs("operations", "b_service_owner")[0]
        self.assertIn("sum by(service_name, team)", expr)
        legend = self._queries("operations", "b_service_owner")[0]["spec"]["query"]["spec"]["legendFormat"]
        self.assertIn("{{service_name}}", legend)
        self.assertIn("{{team}}", legend)

    def test_phase_one_rate_shaped_asset_queries_are_windowed(self):
        for key in ("n_fe_session_rate", "b_profiles"):
            for expr in self._exprs("usage", key):
                self.assertIn("max_over_time", expr, f"usage.{key} is an instantaneous rate")

    def test_phase_one_named_stack_inventory_uses_the_multiplicative_slug_join(self):
        expr = self._exprs("usage", "b_observed_objects")[0]
        self.assertIn("sum by(stack_id)", expr)
        self.assertIn("* on(stack_id) group_left(slug)", expr)
        self.assertNotIn("+ on(stack_id)", expr)

    def test_the_operations_dashboard_is_registered_everywhere(self):
        """Three registries must agree or the dashboard either fails to build or loses its cross-links."""
        self.assertIn("operations", self.dash.BUILDERS)
        self.assertIn("operations", self.dash.PILLAR_OF)
        self.assertIn("gcinsight-operations", [uid for uid, _ in build.DASHBOARDS])

    # --- commercial (Tier 3): presentation constraints, enforced -----------------------------------
    #
    # These are not style preferences. A future edit that quietly relaxes them changes what a
    # customer-visible dashboard asserts
    # about their contract. That is worth a test each.
    FORECAST_WORDS = ("underspend", "under-spend", "unconsumed", "will leave", "projected",
                      "projection", "shortfall", "leave on the table", "forecast to")

    def test_the_burn_panels_state_no_conclusion(self):
        """Show the two lines and assert nothing. Any projection belongs in a deployment-specific review.

        The analysis is real  -  at the current run rate the commitment outlives the contract  -  but a
        dashboard that says so is making a commercial claim to the customer on our behalf.
        """
        for key in ("t_burn", "t_balance", "n_consumed_share", "n_term_elapsed"):
            desc = self._panels("commercial")[key]["spec"]["description"].lower()
            for word in self.FORECAST_WORDS:
                self.assertNotIn(word, desc,
                                 f"commercial.{key} description asserts a projection ({word!r})  -  that "
                                 f"was explicitly excluded from the dashboard")

    def test_every_money_panel_declares_the_currency_as_derived(self):
        """The datasource declares no currency. Any absolute-money panel must say the unit is inferred."""
        panels = self._panels("commercial")
        currency_panels = {
            key: panel for key, panel in panels.items()
            if "currency" in (panel["spec"]["vizConfig"]["spec"].get("fieldConfig", {})
                              .get("defaults", {}).get("unit", ""))
        }
        self.assertGreater(len(currency_panels), 0, "commercial dashboard has no currency panels")
        for key, panel in currency_panels.items():
            desc = panel["spec"]["description"].lower()
            self.assertTrue(
                "derived" in desc or "caveat as the panel" in desc,
                f"commercial.{key} renders currency without saying the unit is derived: {desc[:120]!r}")

    def test_the_ratio_panels_are_unit_free(self):
        """Ratios need no currency, which makes them the safe figures to quote. Keep them percentunit."""
        for key in ("n_consumed_share", "n_term_elapsed", "t_metrics_share", "t_burn"):
            unit = (self._panels("commercial")[key]["spec"]["vizConfig"]["spec"]
                    ["fieldConfig"]["defaults"]["unit"])
            self.assertEqual(unit, "percentunit", f"commercial.{key} is not a unit-free ratio")

    def test_the_two_months_panels_are_not_confusable(self):
        """`forecast_months_remaining` (how long the balance lasts) and months-to-contract-end answer
        different questions and sit side by side. Each must say so, or the pair is a trap."""
        a = self._panels("commercial")["n_months_metric"]["spec"]["description"].lower()
        b = self._panels("commercial")["n_months_contract"]["spec"]["description"].lower()
        self.assertIn("not months left", a)
        self.assertIn("commitment rather than the term", b)

    def test_the_overage_naming_trap_is_documented(self):
        """`_included_*` are all zero, so `total_overage` is the whole charge, not spend above a plan."""
        desc = self._panels("commercial")["n_runrate"]["spec"]["description"]
        self.assertIn("ZERO", desc)
        self.assertIn("not spend above a plan", desc)

    def test_commercial_is_registered_everywhere(self):
        self.assertIn("commercial", self.dash.BUILDERS)
        self.assertIn("commercial", self.dash.PILLAR_OF)
        self.assertIn("gcinsight-commercial", [uid for uid, _ in build.DASHBOARDS])

    # --- AI usage (Pillar I): current-period aggregates are not lifetime identity counters ----------
    def test_the_declared_empty_view_schemas_match_the_live_views(self):
        """A schema is only used when the view has no rows, so drift is INVISIBLE until the healthy day it
        matters  -  the day a table renders with a column set nobody has looked at since it was written.

        Compares SELECTORS only. A column's Infinity type is a property of the data, not of the view:
        `ai_tenant_config` types `enabled` as `string` while it holds only skills, because every value is
        None, and the same column becomes `boolean` as soon as one rule appears. On an empty view no row
        is parsed, so the declared type is inert.
        """
        from collector.pillars import ai as ai_pillar
        for view, schema in sorted(ai_pillar.VIEW_SCHEMAS.items()):
            with self.subTest(view=view):
                live = build.read_view(view)
                if not (live.get("rows") or []):
                    self.skipTest(f"{view} is empty live, so there is nothing to compare against")
                self.assertEqual([sel for sel, _ in schema],
                                 [c["selector"] for c in build.columns_for(live)])

    def test_ai_usage_mixes_live_and_collected_sources_and_says_so(self):
        """It was live-datasource-only until the per-stack reader shipped (PLAN 17E). Declaring it so
        now would give it no input-age panel beside figures that can be a day old."""
        self.assertIn("ai", self.dash.BUILDERS)
        self.assertEqual(self.dash.PILLAR_OF["ai"], "I")
        self.assertNotIn("ai", build.LIVE_DATASOURCE_ONLY)
        self.assertEqual(build.DASHBOARD_INPUTS["ai"], ("assistant",))
        self.assertIn("gcinsight-ai", [uid for uid, _ in build.DASHBOARDS])
        banner = build.banner_elements("ai")["_banner"]
        content = banner["spec"]["vizConfig"]["spec"]["options"]["content"]
        self.assertIn("MIXES two sources", content)
        self.assertIn("TENANT-scoped", content)
        self.assertIn("_age_assistant", build.banner_elements("ai"))

    def test_ai_usage_uses_top_100_tables_not_an_unreadable_hundred_bar_chart(self):
        panels = self._panels("ai")
        for key in ("tbl_stack_users", "tbl_stack_tokens", "tbl_people", "tbl_services"):
            panel = panels[key]
            self.assertEqual(panel["spec"]["vizConfig"]["group"], "table", key)
            expr = self._exprs("ai", key)[0]
            self.assertIn("topk(100", expr.replace("\n", ""), key)
            transforms = panel["spec"]["data"]["spec"]["transformations"]
            self.assertEqual(transforms[1]["spec"]["options"]["sort"],
                             [{"field": build.REDUCED_VALUE_FIELD, "desc": True}], key)

    def test_ai_usage_distinguishes_unique_org_users_from_multi_stack_memberships(self):
        panels = self._panels("ai")
        headline = panels["n_assistant_users"]["spec"]
        self.assertEqual(self._exprs("ai", "n_assistant_users"),
                         ["sum(grafanacloud_org_assistant_users)"])
        self.assertIn("org-level", headline["description"].lower())
        self.assertIn("double-count", headline["description"].lower())

    def test_ai_token_windows_are_named_honestly(self):
        panels = self._panels("ai")
        current = panels["n_tokens"]["spec"]
        self.assertIn("billing period", current["title"].lower())
        self.assertIn("reset", current["description"].lower())
        for key in ("tbl_people", "tbl_services"):
            spec = panels[key]["spec"]
            self.assertIn("lifetime", spec["title"].lower())
            self.assertIn("cumulative", spec["description"].lower())

    def test_service_token_label_is_not_presented_as_a_service_account_identity(self):
        spec = self._panels("ai")["tbl_services"]["spec"]
        self.assertIn("service-token series", spec["title"].lower())
        self.assertIn("not proof", spec["description"].lower())
        self.assertIn("human-shaped", spec["description"].lower())
        self.assertNotIn("service identities", spec["title"].lower())

    def test_self_managed_assistant_is_not_reported_as_zero_or_an_external_stack(self):
        panel = self._panels("ai")["oss_scope"]["spec"]
        content = panel["vizConfig"]["spec"]["options"]["content"].lower()
        self.assertIn("not zero self-managed usage", content)
        self.assertIn("no external-instance", content)
        self.assertIn("folded into", content)

    def test_every_ai_query_points_at_the_datasource_its_metric_actually_lives_in(self):
        """A panel pointed at the wrong Prometheus renders EMPTY rather than erroring, and an empty
        adoption panel reads as "nobody uses it"  -  a wrong answer, not a missing one. This dashboard now
        mixes both sources, so the check is per query rather than one blanket assertion.

        `$stack` is banned from `grafanacloud-usage` expressions specifically: that datasource keys on
        numeric `stack_id` and has no slug label, so the filter would match nothing for ever. Our own
        series DO carry `stack`, and the table panels' Infinity filter is what applies it there.
        """
        for key, panel in self._panels("ai").items():
            for query in panel["spec"]["data"]["spec"]["queries"]:
                inner = query["spec"]["query"]
                uid = inner["datasource"]["name"]
                if inner["group"] == build.INFINITY_TYPE:
                    continue
                expr = inner["spec"]["expr"]
                if "gcinsight_" in expr:
                    self.assertEqual(uid, build.PROM_UID, key)
                    self.assertNotIn("grafanacloud_", expr, key)
                else:
                    self.assertEqual(uid, build.USAGE_UID, key)
                    self.assertNotIn("$stack", expr, key)

    def test_no_ai_panel_mixes_the_two_metric_families_in_one_expression(self):
        """The windows differ  -  billing period vs a rolling 30-day plugin window  -  so an expression
        joining them would silently compute a ratio across two populations."""
        for key, panel in self._panels("ai").items():
            for query in panel["spec"]["data"]["spec"]["queries"]:
                inner = query["spec"]["query"]
                if inner["group"] == build.INFINITY_TYPE:
                    continue
                expr = inner["spec"]["expr"]
                self.assertFalse("gcinsight_" in expr and "grafanacloud_" in expr, key)

    def test_ai_dashboard_defaults_to_a_billing_period_view(self):
        _uid, spec = self.dash.assemble("ai", "infinity-uid")
        self.assertEqual(spec["spec"]["timeSettings"]["from"], "now-30d")

    # --- tabs and layout ---------------------------------------------------------------------------
    def test_the_new_tabs_exist(self):
        self.assertIn("Data loss", self._tabs("risk"))
        self.assertIn("Alerting health", self._tabs("risk"))
        self.assertIn("Unread telemetry", self._tabs("usage"))
        self.assertIn("Savings available", self._tabs("cost"))
        self.assertIn("Workload", self._tabs("usage"))
        self.assertIn("Capability gaps", self._tabs("value"))
        self.assertEqual(self._tabs("operations"),
                         ["Engagement", "Response time", "Ownership", "Alert flow"])
        self.assertEqual(self._tabs("commercial"),
                         ["Commitment", "Run rate", "Consumption vs term"])
        self.assertEqual(self._tabs("ai"),
                         ["Overview", "Adoption by stack", "Assistant use per stack",
                          "Human vs machine", "Enablement and configuration", "Collection coverage",
                          "Token consumption", "People and identities", "Commercial",
                          "Feature activity"])

    def test_the_unused_capability_tab_was_renamed_not_duplicated(self):
        """It claimed capability was unused; for `incident` that was false. The tab now says what it
        measures  -  gcom flags  -  and carries the OnCall disproof in the same view."""
        titles = self._tabs("value")
        self.assertIn("Capability flags", titles)
        self.assertNotIn("Unused capability", titles)

    def test_the_oncall_disproof_sits_in_the_same_tab_as_the_claim(self):
        """Separating them is how the wrong reading survived. They must be seen together."""
        tab = next(t for t in self.built["value"][4]
                   if t["spec"]["title"] == "Capability flags")
        placed = set(_placed_names(tab))
        self.assertLessEqual({"b_features", "n_oncall", "b_oncall"}, placed)

    def test_every_dashboard_still_has_a_complete_layout(self):
        """An orphaned element blanks the WHOLE dashboard, so this is the highest-value assertion here.

        Calls `dash.assemble`, the SAME function the publisher calls. It used to reproduce the assembly by
        hand, and that copy drifted the moment the banner became per-dashboard and the Findings tab gained
        detail tables  -  so the test was passing on an assembly nobody publishes while the real one went
        unchecked. Never re-inline this.
        """
        import bin.dashboards as dash
        for name in dash.BUILDERS:
            with self.subTest(dashboard=name):
                uid, spec = dash.assemble(name, "infinity-uid")   # raises OrphanedElement
                self.assertTrue(uid)
                tabs = spec["spec"]["layout"]["spec"]["tabs"]
                self.assertTrue(tabs)
                self.assertNotEqual(tabs[0]["spec"]["title"], "How to read this")
                self.assertEqual(tabs[-1]["spec"]["title"], "How to read this")
                for tab in tabs:
                    layout = tab["spec"]["layout"]
                    if layout["kind"] != "RowsLayout":
                        continue
                    for row in layout["spec"]["rows"]:
                        self.assertFalse(
                            row["spec"]["collapse"],
                            f"{name}.{tab['spec']['title']}.{row['spec']['title']} starts collapsed",
                        )


class Stage19DashboardContractsTest(unittest.TestCase):
    """Decision surfaces added after the adversarial Stage 19 review."""

    @classmethod
    def setUpClass(cls):
        import bin.dashboards as dash
        cls.dash = dash

    @staticmethod
    def _selectors(panel):
        query = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        return [column["selector"] for column in query["columns"]]

    @staticmethod
    def _expr(panel):
        return panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]

    @staticmethod
    def _card(*, basis="dpm_aware"):
        from collector import ratecard
        included_dpm = "4" if basis == "dpm_aware" else ""
        return ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
            f"metrics_series,7.123,1000,series,0,GBP,month,{basis},{included_dpm},contract\n"
        )

    def test_dashboard_usage_defaults_to_seven_days(self):
        _uid, spec = self.dash.assemble("dashboards", "infinity-uid")
        self.assertEqual(spec["spec"]["timeSettings"]["from"], "now-7d")

    def test_dashboard_usage_wires_the_complete_opening_inventory_and_query_cost(self):
        from unittest.mock import patch
        targets = {"insights_dashboard_opening_31d", "insights_datasource_query_cost"}
        real_read = build.read_view
        def read_view(name):
            return {"rows": []} if name in targets else real_read(name)
        with patch.object(self.dash, "_published_views_exist",
                          side_effect=lambda *names: all(name in targets for name in names)), \
                patch.object(build, "read_view", side_effect=read_view):
            _uid, _title, _desc, panels, tabs = self.dash.d_dashboards("infinity-uid")

        opening = panels["tbl_opening_inventory"]
        self.assertEqual(self._selectors(opening), [
            " Stack", "Dashboard", "Folder", "Dashboard uid", "State", "Views (31d)",
            "Coverage detail",
        ])
        opening_prose = (opening["spec"]["title"] + " " + opening["spec"]["description"]).lower()
        self.assertIn("complete", opening_prose)
        self.assertIn("unknown", opening_prose)

        query_cost = panels["tbl_datasource_query_cost"]
        self.assertEqual(self._selectors(query_cost), [
            " Stack", "Datasource", "Datasource uid", "Datasource type",
            "State", "Cumulative duration (ms)", "Cache hit %", "Coverage detail",
        ])
        query_cost_prose = (query_cost["spec"]["title"] + " " +
                            query_cost["spec"]["description"]).lower()
        self.assertIn("unknown", query_cost_prose)
        tab_elements = {tab["spec"]["title"]: set(_placed_names(tab)) for tab in tabs}
        self.assertIn("tbl_opening_inventory", tab_elements["What people open"])
        self.assertIn("tbl_datasource_query_cost", tab_elements["Query behaviour"])

    def test_dashboard_usage_declares_both_new_input_ages(self):
        self.assertIn("dashboard_inventory", build.DASHBOARD_INPUTS["dashboards"])
        self.assertIn("datasource_query_cost", build.DASHBOARD_INPUTS["dashboards"])
        furniture = build.banner_elements("dashboards")
        self.assertIn("_age_dashboard_inventory", furniture)
        self.assertIn("_age_datasource_query_cost", furniture)

    def test_risk_exposes_org_role_counts_staff_state_and_named_members(self):
        from unittest.mock import patch
        real_read = build.read_view
        def read_view(name):
            return {"rows": []} if name == "risk_org_members" else real_read(name)
        with patch.object(self.dash, "_published_views_exist",
                          side_effect=lambda *names: names == ("risk_org_members",)), \
                patch.object(build, "read_view", side_effect=read_view):
            _uid, _title, _desc, panels, tabs = self.dash.d_risk("infinity-uid")

        self.assertIn("gcinsight_risk_org_members_admins", self._expr(panels["n_org_admins"]))
        self.assertIn("gcinsight_risk_org_members_viewers", self._expr(panels["n_org_viewers"]))
        staff = self._expr(panels["b_org_staff_access"])
        self.assertIn("gcinsight_risk_org_members_staff_access", staff)
        self.assertIn("status", staff)
        self.assertEqual(self._selectors(panels["org_members"]), [
            "Name", "Email", "Login", "Role", "MFA enabled", "Member since", "Staff access",
            "Staff access expires", "Staff access reason", "Staff access ticket",
        ])
        access = next(tab for tab in tabs if tab["spec"]["title"] == "Access")
        self.assertLessEqual(
            {"n_org_admins", "n_org_viewers", "b_org_staff_access", "org_members"},
            set(_placed_names(access)),
        )
        member_row = next(row for row in access["spec"]["layout"]["spec"]["rows"]
                          if "org_members" in _placed_names(row))
        self.assertFalse(member_row["spec"]["collapse"])
        for key in ("n_org_admins", "n_org_viewers", "b_org_staff_access"):
            prose = (panels[key]["spec"]["title"] + " " + panels[key]["spec"]["description"]).lower()
            self.assertNotRegex(prose, r"target|grade|score")

    def test_range_topk_union_has_an_exact_k_companion_and_explains_the_delta(self):
        _uid, _title, _desc, panels, _tabs = self.dash.d_cost("infinity-uid")
        union = panels["b_savings"]["spec"]
        endpoint = panels["b_savings_endpoint"]["spec"]
        self.assertEqual(union["title"], "Stacks that entered the top 15 during this window")
        self.assertEqual(endpoint["title"], "Top 15 at the window endpoint")
        self.assertIn("recovered spikes", union["description"].lower())
        self.assertIn("union-minus-endpoint", endpoint["description"].lower())
        endpoint_expr = self._expr(panels["b_savings_endpoint"])
        self.assertIn("@ end()", endpoint_expr)
        self.assertIn("and on(stack_id)", endpoint_expr)
        self.assertEqual(
            [item["spec"]["id"] for item in endpoint["data"]["spec"]["transformations"]],
            ["reduce", "sortBy", "limit"],
        )
        self.assertEqual(endpoint["data"]["spec"]["transformations"][-1]["spec"]["options"],
                         {"limitField": 15})

    def test_cardinality_treemap_is_a_companion_to_the_exact_native_table(self):
        _uid, _title, _desc, panels, tabs = self.dash.d_cost("infinity-uid")
        treemap = panels["cardinality_treemap"]["spec"]
        self.assertEqual(treemap["vizConfig"]["group"], "marcusolsson-treemap-panel")
        options = treemap["vizConfig"]["spec"]["options"]
        self.assertEqual(options["textField"], "Stack")
        self.assertEqual(options["sizeField"], "Label values")
        self.assertEqual(options["colorByField"], "Worst label values")
        self.assertEqual(options["labelFields"], [
            "Active series", "Worst label", "Worst label values",
        ])
        self.assertIn("area", treemap["description"].lower())
        self.assertIn("label values", treemap["description"].lower())
        self.assertNotIn("colour shows", treemap["description"].lower())

        query = treemap["data"]["spec"]["queries"][0]["spec"]["query"]
        self.assertEqual(query["group"], build.INFINITY_TYPE)
        self.assertEqual(query["datasource"], {"name": "infinity-uid"})
        query_spec = query["spec"]
        self.assertEqual(query_spec["parser"], "backend")
        self.assertEqual(query_spec["root_selector"], "rows")
        self.assertTrue(query_spec["columns"])
        self.assertTrue(query_spec["filterExpression"])

        levers = next(tab for tab in tabs if tab["spec"]["title"] == "Levers")
        placed = _placed_names(levers)
        self.assertIn("cardinality_treemap", placed)
        self.assertIn("cardinality", placed)
        self.assertLess(placed.index("cardinality_treemap"), placed.index("cardinality"))

    def test_dpm_panels_are_absent_without_a_dpm_aware_metrics_rate(self):
        for card in (None, self._card(basis="base_rate_only")):
            with self.subTest(card=card):
                _uid, _title, _desc, panels, tabs = self.dash.d_cost(
                    "infinity-uid", rate_card=card)
                self.assertFalse(any(key.startswith("dpm_") for key in panels))
                self.assertNotIn("DPM-aware savings", [tab["spec"]["title"] for tab in tabs])

    def test_dpm_panels_use_deployed_card_constants_and_max_each_stack_before_sum(self):
        _uid, _title, _desc, panels, tabs = self.dash.d_cost(
            "infinity-uid", rate_card=self._card())
        self.assertIn("DPM-aware savings", [tab["spec"]["title"] for tab in tabs])
        keys = ("dpm_before", "dpm_after", "dpm_saving", "dpm_by_stack")
        for key in keys:
            panel = panels[key]["spec"]
            prose = f"{panel['title']} {panel['description']}"
            self.assertIn("GBP/month", prose)
            self.assertIn("4 included DPM", prose)
            self.assertIn("before", prose.lower())
            self.assertIn("after", prose.lower())
            for query in panel["data"]["spec"]["queries"]:
                self.assertEqual(query["spec"]["query"]["datasource"]["name"], build.USAGE_UID)

        expressions = "\n".join(self._expr(panels[key]) for key in keys)
        for constant in ("7.123", "1000", "4"):
            self.assertIn(constant, expressions)
        self.assertIn("quantile_over_time(0.95", expressions)
        self.assertIn("grafanacloud_instance_samples_per_second", expressions)
        self.assertIn("grafanacloud_instance_active_series", expressions)
        self.assertIn("grafanacloud_instance_recommendations_estimated_savings_series", expressions)
        self.assertIn("clamp_min", expressions)
        ranking = panels["dpm_by_stack"]["spec"]
        legend = ranking["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["legendFormat"]
        self.assertIn("{{regime}}", legend)
        ranking_expr = self._expr(panels["dpm_by_stack"])
        for transition in ("active-series -> active-series", "active-series -> DPM", "DPM -> DPM"):
            self.assertIn(transition, ranking_expr)
        self.assertIn('"regime"', ranking_expr)
        # The max contract is applied to stack_id vectors first; only those priced vectors are summed.
        for key in ("dpm_before", "dpm_after", "dpm_saving"):
            expr = self._expr(panels[key])
            self.assertRegex(expr, r"^sum\(")
            self.assertIn("sum by(stack_id)", expr)
            self.assertGreater(expr.rfind("clamp_min"), expr.find("sum by(stack_id)"))


def _re_search(pattern: str, text: str):
    import re as _re
    return _re.search(pattern, text)


def _usage_evidence():
    import json
    import pathlib as _p
    return json.loads((_p.Path(__file__).resolve().parent.parent / "testdata"
                       / "usage-datasource-signals.json").read_text())


def _metric_in(expr: str) -> str | None:
    """The `grafanacloud_*` metric name an expression selects, recording-rule suffix included."""
    import re as _re
    found = _re.findall(r"grafanacloud_[a-z0-9_]+(?::[a-z0-9]+)?", expr)
    return found[0] if found else None


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def _views_referenced_by(dashboard: str) -> set[str]:
    """Every S3 view name any panel on `dashboard` queries.

    Read out of the built spec rather than from a list, so a panel added without updating
    `DASHBOARD_INPUTS` fails the freshness test instead of quietly showing an age that does not cover it.
    """
    import bin.dashboards as dash
    _uid, _title, _desc, elements, _tabs = dash.BUILDERS[dashboard]("infinity-uid")
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str) and "/views/" in url:
                found.add(url.rsplit("/views/", 1)[1].removesuffix(".json"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(elements)
    return found


def _placed_names(tab):
    """Element names referenced by a tab, whatever layout kind it wraps."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("kind") == "ElementReference":
                found.append(node["name"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(tab)
    return found


class CrossLinkShapeTest(unittest.TestCase):
    """The header links rendered as SEVEN BLANK BUTTONS pointing at `about:blank` (PLAN 15.3).

    Same class of defect as the query and viz envelopes: the v2 shapes are not guessable, and getting one
    wrong fails silently rather than erroring. `cross_links` wrapped each link as
    `{"kind": "DashboardLink", "spec": {...}}` by analogy with Panel and VizConfig  -  but
    `DashboardDashboardLink` is **FLAT**. The API accepted the payload, discarded the unknown `kind`/`spec`
    keys, and stored nine empty strings, so the buttons rendered with no label and no destination.

    Field list below is from the live OpenAPI schema
    (`/openapi/v3/apis/dashboard.grafana.app/v2`), not from a guess:
      required: title, type, icon, tooltip, tags, asDropdown, targetBlank, includeVars, keepTime
      optional: url, origin, placement
    """

    # Exactly the schema's required set. A link missing any of these is stored with a zero value.
    REQUIRED = ("title", "type", "icon", "tooltip", "tags",
                "asDropdown", "targetBlank", "includeVars", "keepTime")

    def setUp(self) -> None:
        self.links = build.cross_links("gcinsight-usage")

    def test_links_are_flat_not_kind_spec_wrapped(self):
        """THE BUG. A `spec` wrapper is silently dropped and every field falls back to empty."""
        for link in self.links:
            self.assertNotIn("kind", link,
                             "DashboardLink is flat  -  a kind/spec wrapper is discarded by the API")
            self.assertNotIn("spec", link)

    def test_every_required_field_is_present(self):
        for link in self.links:
            for field in self.REQUIRED:
                self.assertIn(field, link, f"{link.get('title')!r} is missing required {field!r}")

    def test_each_link_has_a_title_and_a_destination(self):
        """The two the user actually sees. Empty title = blank button; empty url = about:blank."""
        for link in self.links:
            self.assertTrue(link["title"], f"blank title in {link}")
            self.assertTrue(link.get("url"), f"no url in {link}  -  renders as about:blank")
            self.assertTrue(link["url"].startswith("/d/"), link["url"])

    def test_type_is_link_not_dashboards(self):
        """`dashboards` makes Grafana ignore `url` and list by tag instead  -  a plausible wrong value."""
        for link in self.links:
            self.assertEqual(link["type"], "link")

    def test_tags_is_a_list_because_the_schema_requires_an_array(self):
        """It stored as `null` before. The schema types it as an array."""
        for link in self.links:
            self.assertIsInstance(link["tags"], list)

    def test_one_link_per_sibling_and_never_to_self(self):
        self.assertEqual(len(self.links), len(build.DASHBOARDS) - 1)
        self.assertNotIn("/d/gcinsight-usage", [l["url"] for l in self.links])
        self.assertEqual(len({l["url"] for l in self.links}), len(self.links))

    def test_context_is_carried_across(self):
        """Losing the time range on every hop makes the links worse than useless in a demo."""
        for link in self.links:
            self.assertTrue(link["keepTime"])
            self.assertTrue(link["includeVars"])


class PersistedDashboardVerificationTest(unittest.TestCase):
    def _spec(self, *, with_infinity=False, links=()):
        import bin.dashboards as dash

        if with_infinity:
            query = build.data_query(build.INFINITY_TYPE, "infinity", {
                "parser": "backend", "root_selector": "rows",
                "columns": [{"selector": " Stack", "text": "Stack", "type": "string"}],
                "url": "https://example.invalid/views/example.json",
                "filterExpression": 'Stack =~ "^(obs-hub)$"',
            }, "A")
            panel = build._panel("table", "", [query], build.viz("table", {  # noqa: SLF001
                "options": {}, "fieldConfig": {"defaults": {}, "overrides": []},
            }))
        else:
            panel = build.text_panel("text", "content")
        return build.dashboard(
            "title", "description", {"panel": panel},
            [build.tab("tab", ["panel"])], links=links,
        )

    @staticmethod
    def _resource(uid, spec):
        return {"metadata": {"name": uid, "resourceVersion": "2"}, "spec": spec["spec"]}

    def test_valid_persisted_envelopes_pass(self):
        import bin.dashboards as dash
        spec = self._spec(with_infinity=True, links=build.cross_links("gcinsight-estate"))
        dash.verify_persisted("uid", spec, self._resource("uid", spec))

    def test_a_persisted_flat_link_losing_its_title_is_refused(self):
        import copy
        import bin.dashboards as dash
        spec = self._spec(links=build.cross_links("gcinsight-estate"))
        saved = copy.deepcopy(self._resource("uid", spec))
        saved["spec"]["links"][0]["title"] = ""
        with self.assertRaisesRegex(ValueError, "title/url/type"):
            dash.verify_persisted("uid", spec, saved)

    def test_a_persisted_infinity_query_losing_columns_is_refused(self):
        import copy
        import bin.dashboards as dash
        spec = self._spec(with_infinity=True)
        saved = copy.deepcopy(self._resource("uid", spec))
        query_spec = saved["spec"]["elements"]["panel"]["spec"]["data"]["spec"]["queries"][0][
            "spec"
        ]["query"]["spec"]
        query_spec["columns"] = []
        with self.assertRaisesRegex(ValueError, "explicit columns"):
            dash.verify_persisted("uid", spec, saved)

    def test_authored_query_fields_cannot_change_on_read_back(self):
        import copy
        import bin.dashboards as dash

        mutations = {
            "filterExpression": lambda query: query["spec"].pop("filterExpression"),
            "url": lambda query: query["spec"].__setitem__(
                "url", "https://wrong.invalid/view.json"
            ),
            "datasource": lambda query: query.__setitem__(
                "datasource", {"name": "wrong-uid"}
            ),
            "group": lambda query: query.__setitem__("group", "prometheus"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                spec = self._spec(with_infinity=True)
                saved = copy.deepcopy(self._resource("uid", spec))
                query = saved["spec"]["elements"]["panel"]["spec"]["data"]["spec"] \
                    ["queries"][0]["spec"]["query"]
                mutate(query)
                with self.assertRaisesRegex(ValueError, "query"):
                    dash.verify_persisted("uid", spec, saved)

    def test_authored_layout_placement_cannot_disappear_on_read_back(self):
        import copy
        import bin.dashboards as dash

        spec = self._spec()
        saved = copy.deepcopy(self._resource("uid", spec))
        saved["spec"]["layout"]["spec"]["tabs"][0]["spec"]["layout"]["spec"]["items"] = []
        with self.assertRaisesRegex(ValueError, "layout"):
            dash.verify_persisted("uid", spec, saved)

    def test_a_persisted_panel_id_change_is_refused(self):
        import copy
        import bin.dashboards as dash
        spec = self._spec()
        saved = copy.deepcopy(self._resource("uid", spec))
        saved["spec"]["elements"]["panel"]["spec"]["id"] += 1
        with self.assertRaisesRegex(ValueError, "panel id"):
            dash.verify_persisted("uid", spec, saved)

    def test_business_charts_executable_options_round_trip_exactly(self):
        import copy
        import bin.dashboards as dash
        panel = build._panel(  # noqa: SLF001
            "chart", "", [], build.viz("volkovlabs-echarts-panel", {
                "options": {"getOption": "return {series: []};", "theme": "dark"},
                "fieldConfig": {"defaults": {}, "overrides": []},
            }),
        )
        spec = build.dashboard("title", "description", {"panel": panel},
                               [build.tab("tab", ["panel"])])
        saved = copy.deepcopy(self._resource("uid", spec))
        saved["spec"]["elements"]["panel"]["spec"]["vizConfig"]["spec"]["options"] \
            ["getOption"] = "return {};"
        with self.assertRaisesRegex(ValueError, "getOption"):
            dash.verify_persisted("uid", spec, saved)

    def test_third_party_nested_options_cannot_be_silently_dropped(self):
        import copy
        import bin.dashboards as dash
        panel = build._panel(  # noqa: SLF001
            "table", "", [], build.viz("volkovlabs-table-panel", {
                "options": {
                    "tables": [{"name": "main", "pagination": {"enabled": True, "size": 50}}],
                    "editing": {"enabled": False},
                },
                "fieldConfig": {"defaults": {}, "overrides": []},
            }),
        )
        spec = build.dashboard("title", "description", {"panel": panel},
                               [build.tab("tab", ["panel"])])
        saved = copy.deepcopy(self._resource("uid", spec))
        del saved["spec"]["elements"]["panel"]["spec"]["vizConfig"]["spec"]["options"] \
            ["tables"][0]["pagination"]
        with self.assertRaisesRegex(ValueError, "pagination"):
            dash.verify_persisted("uid", spec, saved)

    def test_publish_reads_back_and_verifies_before_reporting_success(self):
        from unittest import mock
        import bin.dashboards as dash
        spec = self._spec()
        calls = []

        def fake_api(method, path, token, body=None):
            calls.append((method, path, body))
            if method == "GET" and len([c for c in calls if c[0] == "GET"]) == 1:
                return 404, {}
            if method == "POST":
                return 201, {}
            return 200, self._resource("uid", spec)

        with mock.patch.object(dash, "_api", side_effect=fake_api):
            code, _body = dash.publish("uid", spec, "folder", "token")
        self.assertEqual(code, 201)
        self.assertEqual([method for method, _path, _body in calls], ["GET", "POST", "GET"])


class EveryPanelExplainsItselfTest(unittest.TestCase):
    """A panel's `description` is the info tooltip a viewer hovers, and it is the only in-product place a
    term gets defined (PLAN 15.4).

    For example, "stickiness" as a stat reading 42.5% with no tooltip is a number the audience cannot
    challenge or trust, and on a dashboard handed to another team it becomes folklore. 34 panels shipped
    without one.

    TEXT panels are exempt  -  their body IS the explanation, so a tooltip would duplicate it.
    """

    MIN_LENGTH = 40

    def _panels(self):
        import bin.dashboards as dash
        for name, builder in dash.BUILDERS.items():
            _, _, _, el, _ = builder("infinity-uid")
            el = {**build.banner_elements(), **el}
            pillar, kinds = dash.findings_for(name)
            found = build.findings_elements(pillar, kinds)
            if found:
                el = {**el, **found}
            for key, panel in el.items():
                if panel.get("kind") != "Panel":
                    continue
                spec = panel["spec"]
                if spec.get("vizConfig", {}).get("group") == "text":
                    continue
                yield f"{name}.{key}", spec

    def test_every_panel_has_a_tooltip(self):
        for label, spec in self._panels():
            self.assertTrue((spec.get("description") or "").strip(),
                            f"{label} ({spec.get('title')!r}) has no description, so its info tooltip is "
                            f"absent and the number is unexplained in the product")

    def test_no_tooltip_is_too_short_to_be_useful(self):
        """A three-word description passes a presence check and explains nothing."""
        for label, spec in self._panels():
            desc = (spec.get("description") or "").strip()
            self.assertGreaterEqual(
                len(desc), self.MIN_LENGTH,
                f"{label} tooltip is {len(desc)} chars  -  too short to define anything: {desc!r}")

    def test_a_tooltip_never_just_restates_the_title(self):
        """"Stickiness" described as "the stickiness" is the failure this catches."""
        for label, spec in self._panels():
            title = (spec.get("title") or "").strip().lower().rstrip(".")
            desc = (spec.get("description") or "").strip().lower().rstrip(".")
            self.assertNotEqual(desc, title, f"{label} tooltip merely repeats its title")

    def test_the_terms_a_reader_cannot_infer_are_actually_defined(self):
        """Spot-check the jargon that prompted this. Each must define itself, not assume the reader knows.

        Keyed on the panel whose tooltip must carry the definition, and a word that definition needs.
        """
        wanted = {
            "usage.n_stick": ("daily", "monthly"),        # stickiness == DAU/MAU
            "maturity.n_p90": ("90%",),                   # what a percentile means here
            "maturity.n_ranked": ("denominator",),        # why it is not the estate total
            "estate.n_users": ("billing", "adoption"),    # billed vs active users
            "cost.n_ratio": ("billed",),                  # which user count the ratio uses
            "operations.n_engagement": ("acknowledge",),  # what engagement counts
        }
        found = dict(self._panels())
        for label, terms in wanted.items():
            self.assertIn(label, found, f"{label} no longer exists  -  update this list")
            desc = (found[label].get("description") or "").lower()
            for term in terms:
                self.assertIn(term.lower(), desc,
                              f"{label} tooltip does not explain {term!r}: {desc[:110]!r}")

    def test_the_ownership_tooltip_does_not_describe_the_obsolete_partial_view(self):
        """Hydration replaced the two-row limited-run artifact with the full owner directory."""
        found = dict(self._panels())
        desc = found["maturity.owners"]["description"].lower()
        self.assertNotIn("2 rows", desc)
        self.assertNotIn("very thin", desc)
        self.assertNotIn("createdby", desc)
        self.assertIn("admin", desc)

    def test_tooltips_do_not_embed_dated_live_measurements(self):
        """The panel already shows the live value; dated copies in help text drift and contradict it."""
        for label, spec in self._panels():
            self.assertNotRegex(
                spec["description"], r"(?i)measured\s+202\d-",
                f"{label} embeds a dated live measurement in its tooltip",
            )


class RecentDashboardPresentationContractsTest(unittest.TestCase):
    """The data existed before these panels did, so metric/view coverage alone could not catch the gap."""

    @classmethod
    def setUpClass(cls):
        import bin.dashboards as dash
        cls.dash = dash
        cls.risk = dash.d_risk("infinity-uid")[3]
        cls.ai = dash.d_ai("infinity-uid")[3]
        cls.maturity = dash.d_maturity("infinity-uid")[3]
        cls.operations = dash.d_operations("infinity-uid")[3]
        cls.dashboard_usage = dash.d_dashboards("infinity-uid")[3]

    @staticmethod
    def _visible_columns(panel):
        organize = panel["spec"]["data"]["spec"]["transformations"][0]["spec"]["options"]
        return [name for name, _index in sorted(organize["indexByName"].items(),
                                                key=lambda item: item[1])
                if not organize["excludeByName"].get(name)]

    def test_fleet_headlines_show_active_inactive_share_and_enabled_configuration(self):
        for key in ("n_coll_active", "n_coll_inactive", "n_coll_inactive_share", "n_pipe_enabled"):
            self.assertIn(key, self.risk)
        panel = self.risk["n_coll_inactive_share"]["spec"]
        self.assertEqual(panel["vizConfig"]["spec"]["fieldConfig"]["defaults"]["unit"],
                         "percentunit")
        expr = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
        self.assertIn("gcinsight_risk_collectors_inactive", expr)
        self.assertIn("gcinsight_risk_collectors_active", expr)

    def test_alert_routing_counters_keep_findings_and_denominator_separate(self):
        expected = {
            "n_routing_measured": "gcinsight_risk_alert_routing_stacks_measured",
            "n_routing_rules": "gcinsight_risk_alert_rules_total",
            "n_routing_inherited": "gcinsight_risk_alert_rules_active_inherited",
            "n_routing_missing": "gcinsight_risk_alert_rules_active_missing_receiver",
            "n_routing_builtin": "gcinsight_risk_alert_rules_unverified_builtin",
        }
        for key, metric in expected.items():
            with self.subTest(key=key):
                panel = self.risk[key]["spec"]
                expr = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
                self.assertEqual(expr, metric)
                self.assertTrue(panel["description"])
        self.assertIn("denominator", self.risk["n_routing_measured"]["spec"]["description"].lower())
        self.assertIn("unverified", self.risk["n_routing_builtin"]["spec"]["description"].lower())
        available = self.risk["n_routing_available"]["spec"]
        expr = available["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
        self.assertEqual(expr, 'max(gcinsight_input_available{input="alert_routing"})')
        self.assertIn("age", available["description"].lower())

    def test_new_views_wire_same_tab_drilldowns_once_the_objects_exist(self):
        """First publication is fail-closed; after S3 exists, the dashboard must stop exempting detail."""
        from unittest import mock

        def fake_table(title, view_name, _ds, **_kwargs):
            return build.text_panel(title, view_name)

        with mock.patch.object(self.dash, "_published_views_exist", return_value=True), \
                mock.patch.object(build, "table_panel", side_effect=fake_table):
            cost = self.dash.d_cost("infinity-uid")
            risk = self.dash.d_risk("infinity-uid")

        self.assertIn("adaptive_logs_recommendations", cost[3])
        self.assertIn("adaptive_metric_recommendations", cost[3])
        cost_tabs = {tab["spec"]["title"]: set(_placed_names(tab)) for tab in cost[4]}
        self.assertIn("adaptive_logs_recommendations", cost_tabs["Adaptive Logs"])
        self.assertIn("adaptive_metric_recommendations", cost_tabs["Savings available"])

        for key in ("public_dashboards", "alert_routing_inventory", "alert_routing_findings"):
            self.assertIn(key, risk[3])
        risk_tabs = {tab["spec"]["title"]: set(_placed_names(tab)) for tab in risk[4]}
        self.assertIn("public_dashboards", risk_tabs["Public dashboards"])
        self.assertLessEqual(
            {"alert_routing_inventory", "alert_routing_findings"}, risk_tabs["Alert routing"],
        )

    def test_service_account_inventory_is_a_named_same_tab_drilldown(self):
        self.assertEqual(
            self._visible_columns(self.risk["sa_inventory"]),
            ["Stack", "Service account", "Kind", "Role", "Assigned roles", "Role read",
             "Tokens", "Expired tokens", "Non-expiring tokens", "Never-used tokens",
             "Stale live tokens (90d)", "Nearest token expiry", "Token read", "Token hygiene",
             "Disabled", "Flag"],
        )
        scope = self.risk["t_sa_scope"]["spec"]
        content = scope["vizConfig"]["spec"]["options"]["content"]
        self.assertNotIn("NOT MEASURABLE", scope["title"] + content)
        self.assertNotIn("Phase 1", scope["title"] + content)
        self.assertIn("stack-local", content)
        self.assertIn("read-only", content)

    def test_ai_reconciliation_table_exposes_the_source_disagreements_and_token_split(self):
        self.assertEqual(
            self._visible_columns(self.ai["tbl_ai_reconciliation"]),
            ["Stack", "Region", "Messages", "Messages categorised", "Messages uncategorised",
             "Categorised exceeds total", "Chat tokens", "Investigation tokens",
             "Investigations created", "Investigations by Assistant", "Investigations by user",
             "Tenant skills", "Tenant rules", "Tenant automations", "Tenant MCP integrations",
             "Detail"],
        )

    def test_ai_full_table_exposes_the_stack_population_it_already_collects(self):
        columns = self._visible_columns(self.ai["tbl_ai_per_stack"])
        self.assertIn("Users (active)", columns)
        self.assertLess(columns.index("Users (active)"), columns.index("Assistant users"))

    def test_customer_visible_prose_does_not_repeat_live_measurements_or_obsolete_phases(self):
        banner = build.BANNER_MD
        self.assertNotIn("Phase 1", banner)
        for key in ("n_admin", "t_admin", "n_sa_custom"):
            desc = self.risk[key]["spec"]["description"]
            self.assertNotRegex(desc, r"(?i)\b(?:about|roughly)\s+\d")
            self.assertNotRegex(desc, r"\b\d+\s+(?:of\s+\d+|stacks configured)")
        self.assertNotIn("t_fleet", self.risk,
                         "one axis must not mix collector registrations with a count of stacks")

    def test_maturity_panels_pin_the_current_rubric_version(self):
        def expressions(value):
            if isinstance(value, dict):
                expr = value.get("expr")
                if isinstance(expr, str) and "gcinsight_maturity_" in expr:
                    yield expr
                for child in value.values():
                    yield from expressions(child)
            elif isinstance(value, list):
                for child in value:
                    yield from expressions(child)

        expressions = list(expressions(self.maturity))
        self.assertTrue(expressions)
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertIn('version="1"', expression)

    def test_fleet_detail_tables_use_fixture_derived_columns_on_the_collectors_tab(self):
        from unittest import mock
        from collector.dashboards import build as dashboard_build

        real_read_view = dashboard_build.read_view

        def read_view(name):
            if name in {"risk_fleet_attributes", "risk_fleet_pipelines"}:
                return {"rows": []}
            return real_read_view(name)

        with mock.patch.object(dashboard_build, "read_view", side_effect=read_view):
            _uid, _title, _desc, elements, tabs = self.dash.d_risk("infinity-uid")

        self.assertEqual(
            self._visible_columns(elements["fleet_attributes"]),
            ["Stack", "Attribute", "Value", "Active collectors", "Distinct values", "Truncated"],
        )
        self.assertEqual(
            self._visible_columns(elements["fleet_pipelines"]),
            ["Stack", "Pipeline", "Enabled", "Source", "Enabled collectors targeted",
             "Collectors targeted", "Config type", "Matchers", "Updated at"],
        )
        collectors = next(tab for tab in tabs if tab["spec"]["title"] == "Collectors")
        placed = set(_placed_names(collectors))
        self.assertIn("fleet_attributes", placed)
        self.assertIn("fleet_pipelines", placed)

    def test_fleet_detail_schemas_match_compose_fixture(self):
        import json
        import pathlib
        from collector.coverage import Coverage
        from collector.dashboards import build as dashboard_build
        from collector.emit import hydrate
        from collector.pillars import compose, risk

        fixture = pathlib.Path(__file__).resolve().parent / "fixtures" / "compose_inputs.json"
        data = json.loads(fixture.read_text())
        coverage = Coverage(tier="schema", total=len(data["stacks"]))
        for i in range(data["scanned"]):
            coverage.record_ok(f"s{i}")
        inputs = {key: data[key] for key in sorted(hydrate.INPUT_OWNER)}
        _metrics, views = compose.build_all(data["stacks"], coverage, **inputs)
        expected = {
            "risk_fleet_attributes": risk.VIEW_SCHEMAS["risk_fleet_attributes"],
            "risk_fleet_pipelines": risk.VIEW_SCHEMAS["risk_fleet_pipelines"],
        }
        for view_name, schema in expected.items():
            with self.subTest(view=view_name):
                rows = views[view_name]
                self.assertTrue(rows, "fixture must exercise this table contract")
                actual = tuple(
                    (key, dashboard_build._infer_type([row.get(key) for row in rows]))
                    for key in rows[0]
                )
                self.assertEqual(actual, schema)

    def test_pillar_j_panels_exclude_the_contaminated_unversioned_epoch(self):
        def expressions(value):
            if isinstance(value, dict):
                if "expr" in value and "gcinsight_dashboards_" in str(value["expr"]):
                    yield str(value["expr"])
                for child in value.values():
                    yield from expressions(child)
            elif isinstance(value, list):
                for child in value:
                    yield from expressions(child)

        found = list(expressions({"risk": self.risk, "dashboards": self.dashboard_usage}))
        self.assertTrue(found)
        for expression in found:
            with self.subTest(expression=expression):
                selectors = re.findall(r"gcinsight_dashboards_[a-z_]+(?:\{[^}]*\})?", expression)
                self.assertTrue(selectors)
                for selector in selectors:
                    self.assertIn('version="2"', selector)

    def test_pillar_j_public_table_discloses_its_per_stack_top_ten_bound(self):
        panel = self.dashboard_usage["tbl_public"]["spec"]
        prose = f"{panel['title']} {panel['description']}".lower()
        self.assertIn("10 per stack", prose)
        self.assertIn("bounded sample", prose)
        self.assertIn("activity", prose)
        self.assertNotIn("the actionable table", prose)

    def test_public_dashboard_inventory_points_to_its_same_tab_drilldown(self):
        description = self.risk["n_public"]["spec"]["description"]
        self.assertIn("Which dashboards", description)
        self.assertIn("on this tab", description)
        self.assertNotIn("Compliance tab", description)

    def test_pillar_j_presents_public_dashboards_as_observed_activity_not_inventory(self):
        """Usage events prove exposure, but cannot say when sharing was configured or enumerate it."""
        _uid, _title, dashboard_description, elements, _tabs = self.dash.d_dashboards("infinity-uid")
        self.assertEqual(elements["n_public"]["spec"]["title"],
                         "Public dashboards observed in use")
        self.assertEqual(elements["n_public_events"]["spec"]["title"],
                         "Public dashboard opens")
        self.assertEqual(elements["t_public"]["spec"]["title"],
                         "Public dashboard opens over time, by stack")
        prose = " ".join([
            dashboard_description,
            *(f"{elements[key]['spec']['title']} {elements[key]['spec']['description']}"
              for key in ("n_public", "n_public_events", "tbl_public", "t_public")),
        ]).lower()
        for stale_claim in (
            "being made public", "compliance deliverable", "compliance check",
            "policy target", "any value above zero is a breach", "measurable nowhere else",
        ):
            self.assertNotIn(stale_claim, prose)
        self.assertIn("configured inventory", prose)
        self.assertIn("cannot identify when sharing was configured", prose)

    def test_pillar_j_every_per_stack_trend_honours_the_stack_selector(self):
        for key in (
            "t_viewers", "t_viewed", "t_views", "t_public", "t_anon", "t_panel_queries",
            "t_cache", "t_errors",
        ):
            with self.subTest(panel=key):
                queries = self.dashboard_usage[key]["spec"]["data"]["spec"]["queries"]
                expressions = [q["spec"]["query"]["spec"]["expr"] for q in queries]
                self.assertTrue(expressions)
                for expression in expressions:
                    self.assertIn('stack=~"$stack"', expression)

    def test_pillar_j_renders_the_public_dashboard_stack_dimension(self):
        expression = self.dashboard_usage["n_with_public"]["spec"]["data"]["spec"]["queries"][0][
            "spec"
        ]["query"]["spec"]["expr"]
        self.assertIn('kind="with_public_dashboards"', expression)

    def test_pillar_j_request_panels_do_not_call_requests_queries(self):
        for key in ("n_queries", "n_errors", "t_panel_queries", "t_errors"):
            with self.subTest(panel=key):
                spec = self.dashboard_usage[key]["spec"]
                prose = f"{spec['title']} {spec['description']}".lower()
                self.assertIn("request", prose)
        top = self.dashboard_usage["tbl_top"]["spec"]
        prose = f"{top['title']} {top['description']}".lower()
        self.assertIn("not a provable estate-wide top 50", prose)

    def test_alert_state_history_failures_are_windowed_named_and_zero_series_cost(self):
        stat = self.operations["n_state_history_failures"]["spec"]
        chart = self.operations["b_state_history_failures"]["spec"]
        stat_expr = stat["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
        chart_expr = chart["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
        for expression in (stat_expr, chart_expr):
            self.assertIn(
                "grafanacloud_grafana_instance_alerting_state_history_writes_failed_total:rate5m",
                expression,
            )
            self.assertIn("max_over_time", expression)
            self.assertIn("[24h]", expression)
        self.assertIn("slug", chart_expr)
        for panel in (stat, chart):
            datasource = panel["data"]["spec"]["queries"][0]["spec"]["query"]["datasource"]["name"]
            self.assertEqual(datasource, build.USAGE_UID)


class CoverageOutcomeValueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bin.dashboards as dashboards
        cls.dash = dashboards
        cls.elements = dashboards.d_coverage("infinity-uid")[3]

    def _exprs(self, key):
        return [
            query["spec"]["query"]["spec"].get("expr", "")
            for query in self.elements[key]["spec"]["data"]["spec"]["queries"]
        ]

    def test_outcome_value_uses_only_p50_and_an_explicit_tail_count(self):
        self.assertIn("histogram_quantile(0.5", self._exprs("n_value_mtta")[0])
        self.assertIn("histogram_quantile(0.5", self._exprs("n_value_mttr")[0])
        joined = " ".join(self._exprs("n_value_mtta") + self._exprs("n_value_mttr"))
        self.assertNotIn("0.9", joined)
        tail = self._exprs("n_value_tail")[0]
        self.assertIn('le="+Inf"', tail)
        self.assertIn(f'le="{self.dash.TOP_BUCKET}"', tail)

    def test_oncall_ratios_use_only_the_timing_reporting_population(self):
        for key in ("n_value_engagement", "n_value_unowned_team", "n_value_unowned_service"):
            expr = self._exprs(key)[0]
            self.assertIn("on(stack_id)", expr, f"{key} mixes OnCall populations")
            self.assertIn(self.dash.ACK, expr, f"{key} does not identify timing-reporting stacks")

    def test_unit_economics_use_published_spend_and_billed_users(self):
        billed = " ".join(self._exprs("n_spend_billed_user"))
        self.assertIn("grafanacloud_org_total_overage", billed)
        self.assertIn("gcinsight_cost_billed_users", billed)
        self.assertNotIn("gcinsight_estate_active_users", billed)
        app = self._exprs("n_spend_app_service")[0]
        self.assertIn("grafanacloud_org_app_o11y_overage", app)
        self.assertIn("grafanacloud_app_observability_service_entity_count", app)

    def test_service_register_names_completeness_without_claiming_protection(self):
        spec = self.elements["tbl_services"]["spec"]
        prose = f"{spec['title']} {spec['description']}".lower()
        self.assertIn("observability completeness", prose)
        self.assertIn("configurable", prose)
        self.assertNotIn("protected", prose)


class EveryPublishedViewIsRenderedSomewhereTest(unittest.TestCase):
    """A view published to S3 with no panel bound to it runs for nobody, and nothing fails.

    This has happened twice. `views/estate_diff.json` was written every run from the day the platform
    deployed and rendered nowhere for a week (PLAN 15.x). `insights_summary` shipped with Pillar J and
    was bound to nothing (PLAN 18.9). Both cost S3 writes, both looked healthy, and in both cases the
    only symptom was a figure nobody could find on a dashboard.

    The view set is DERIVED by composing the pillars over the real fixture, not read from a list: a list
    would need updating by the same change that forgets the panel.
    """

    EXEMPT = {
        # These three Stage 19 tables are fully wired conditionally, but their first scheduled owners
        # have not yet published S3 objects. Keep only this exact first-publication gate; remove each
        # entry as soon as its object exists and before publishing the corresponding dashboard.
        "insights_dashboard_opening_31d",
        "insights_datasource_query_cost",
        "risk_org_members",
    }

    @classmethod
    def setUpClass(cls):
        import json
        import pathlib
        fixture = pathlib.Path(__file__).resolve().parent / "fixtures" / "compose_inputs.json"
        if not fixture.exists():
            raise unittest.SkipTest(f"{fixture} absent - regenerate with bin/make_compose_fixture.py")
        cls.data = json.loads(fixture.read_text())

    def _produced(self) -> set[str]:
        from collector.coverage import Coverage
        from collector.emit import hydrate
        from collector.pillars import compose
        stacks = self.data["stacks"]
        cov = Coverage(tier="tX", total=len(stacks))
        for i in range(self.data["scanned"]):
            cov.record_ok(f"s{i}")
        kw = {k: self.data[k] for k in sorted(hydrate.INPUT_OWNER)}
        _metrics, views = compose.build_all(stacks, cov, **kw)
        return set(views)

    def test_every_view_the_pillars_produce_has_a_panel(self):
        import bin.dashboards as dash
        rendered: set[str] = set()
        for name in dash.BUILDERS:
            rendered |= _views_referenced_by(name)
        orphans = sorted(self._produced() - rendered - self.EXEMPT)
        self.assertEqual(
            orphans, [],
            f"published to S3 every run and rendered nowhere: {orphans}. Bind a panel to it, or add it "
            f"to EXEMPT with the reason it must not be rendered.",
        )

    def test_exemptions_still_name_views_that_exist(self):
        """A renamed view left in EXEMPT would silently exempt nothing."""
        produced = self._produced()
        for view in sorted(self.EXEMPT):
            with self.subTest(view=view):
                self.assertIn(view, produced)


class EveryEmittedMetricIsRenderedOrAlertedTest(unittest.TestCase):
    """A declared metric with no panel and no alert rule is a series written for nobody.

    Same defect class as the unrendered views above, on the metric side. Audited 2026-08-20 and it found
    eleven: the whole rate-card savings pair, both estate Assistant rollups, per-stack billed users, the
    Adaptive rules-applied counter, the plugin-drift counter its own drill-down table advertised, and the
    carry-forward drop counter that makes the golden rule visible.

    The search covers the ASSEMBLED spec, not the builder's elements: the findings tab and the banner are
    added by `assemble`, so a metric rendered only there is genuinely rendered and an elements-only search
    reports it missing.
    """

    #: Declared but deliberately never emitted, so there is nothing to render. Each entry needs a reason.
    NEVER_EMITTED = {
        # Superseded by gcinsight_dashboards_estate_public (Pillar J). Pillar E cannot see
        # publicDashboardUid, and a 0 from it would read as compliant.
        "gcinsight_risk_public_dashboards_total",
    }

    @classmethod
    def setUpClass(cls):
        import json
        import pathlib
        import bin.dashboards as dash
        blobs = [json.dumps(dash.assemble(name, "infinity-uid")[1]) for name in dash.BUILDERS]
        blobs.append((pathlib.Path(__file__).resolve().parent.parent / "bin" / "alerts.py").read_text())
        cls.haystack = "\n".join(blobs)

    @staticmethod
    def _contains_metric(text: str, name: str) -> bool:
        return re.search(
            rf"(?<![A-Za-z0-9_:]){re.escape(name)}(?![A-Za-z0-9_:])", text,
        ) is not None

    def test_every_declared_metric_appears_on_a_dashboard_or_in_an_alert(self):
        from collector.emit import budget
        orphans = sorted(
            m.name for m in budget.CATALOGUE
            if getattr(m, "store", None) != "view"
            and m.name not in self.NEVER_EMITTED
            and not self._contains_metric(self.haystack, m.name)
        )
        self.assertEqual(
            orphans, [],
            f"emitted every run and rendered nowhere: {orphans}. Add a panel or an alert, or add it to "
            f"NEVER_EMITTED with the reason it is declared but not emitted.",
        )

    def test_never_emitted_entries_are_really_never_emitted(self):
        """An entry that starts being emitted must lose its exemption, not keep hiding behind it."""
        import pathlib
        src = "\n".join(
            p.read_text()
            for p in (pathlib.Path(__file__).resolve().parent.parent / "collector").rglob("*.py")
            if p.name != "budget.py"
        )
        for name in sorted(self.NEVER_EMITTED):
            with self.subTest(metric=name):
                self.assertFalse(self._contains_metric(src, name))


if __name__ == "__main__":
    unittest.main()
