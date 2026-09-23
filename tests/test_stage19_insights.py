"""Stage 19 dashboard-opening inventory and per-datasource query-cost contracts."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import scan
from collector.httpclient import Response
from collector.coverage import Coverage
from collector.emit import hydrate
from collector.pillars import compose
from collector.pillars import insights
from collector.pillars import insights_inventory
from collector.sources import stack_catalog
from collector.sources import usage_insights as ui


class DashboardOpeningViewTest(unittest.TestCase):
    STACKS = [
        {"slug": "measured"},
        {"slug": "unknown"},
    ]
    INPUT = {
        "measured": {
            "available": True,
            "activity_available": True,
            "window": "31d",
            "dashboards": [
                {"uid": "opened", "title": "Opened", "folder": "Team"},
                {"uid": "unopened", "title": "Unopened", "folder": ""},
            ],
            "opened": [{"dashboardUid": "opened", "count": 7}],
        },
        "unknown": {
            "available": True,
            "activity_available": False,
            "activity_reason": "forbidden_403",
            "activity_detail": "HTTP 403",
            "window": "31d",
            "dashboards": [
                {"uid": "unknown-one", "title": "Unknown one", "folder": "Ops"},
            ],
            "opened": [],
        },
        # A departed stack must never leak back in from a stale owner envelope.
        "removed": {
            "available": True,
            "activity_available": True,
            "window": "31d",
            "dashboards": [{"uid": "stale", "title": "Stale", "folder": ""}],
            "opened": [],
        },
    }

    def test_full_inventory_is_joined_to_activity_without_top_n_truncation(self):
        _metrics, views = insights_inventory.build(
            self.STACKS, dashboard_inventory=self.INPUT,
        )
        rows = views["insights_dashboard_opening_31d"]
        by_uid = {row["Dashboard uid"]: row for row in rows}
        self.assertEqual(set(by_uid), {"opened", "unopened", "unknown-one"})
        self.assertEqual(by_uid["opened"]["State"], "opened")
        self.assertEqual(by_uid["opened"]["Views (31d)"], 7)
        self.assertEqual(by_uid["unopened"]["State"], "unopened")
        self.assertEqual(by_uid["unopened"]["Views (31d)"], 0)

    def test_unmeasured_activity_is_unknown_never_unopened_and_remains_visible(self):
        _metrics, views = insights_inventory.build(
            self.STACKS, dashboard_inventory=self.INPUT,
        )
        row = next(
            row for row in views["insights_dashboard_opening_31d"]
            if row["Dashboard uid"] == "unknown-one"
        )
        self.assertEqual(row["State"], "unknown")
        self.assertIsNone(row["Views (31d)"])
        self.assertEqual(row["Coverage detail"], "forbidden_403: HTTP 403")

    def test_view_emits_no_metric_series(self):
        metrics, _views = insights_inventory.build(
            self.STACKS, dashboard_inventory=self.INPUT,
        )
        self.assertEqual(metrics, [])


class DatasourceQueryCostViewTest(unittest.TestCase):
    def test_uid_is_resolved_without_dropping_unresolved_rows(self):
        payload = {
            "alpha": {
                "available": True,
                "window": "24h",
                "inventory_available": True,
                "datasources": [
                    {"uid": "prom", "name": "Primary Prometheus", "type": "prometheus"},
                ],
                "costs": [
                    {"datasourceUid": "prom", "datasourceType": "prometheus",
                     "cost_ms": 1500, "cache_hit_ratio": 0.25},
                    {"datasourceUid": "gone", "datasourceType": "loki",
                     "cost_ms": 900, "cache_hit_ratio": None},
                ],
            },
        }
        metrics, views = insights_inventory.build(
            [{"slug": "alpha"}], datasource_query_cost=payload,
        )
        self.assertEqual(metrics, [])
        rows = {row["Datasource uid"]: row
                for row in views["insights_datasource_query_cost"]}
        self.assertEqual(rows["prom"]["Datasource"], "Primary Prometheus")
        self.assertEqual(rows["prom"]["Datasource type"], "prometheus")
        self.assertEqual(rows["prom"]["Cumulative duration (ms)"], 1500)
        self.assertEqual(rows["prom"]["Cache hit %"], 25.0)
        self.assertEqual(rows["gone"]["Datasource"], "(unresolved uid)")
        self.assertEqual(rows["gone"]["Datasource type"], "loki")
        self.assertIsNone(rows["gone"]["Cache hit %"])

    def test_live_inventory_drives_rows_and_stale_payload_cannot_leak_back_in(self):
        payload = {
            "removed": {
                "available": True,
                "datasources": [],
                "costs": [{"datasourceUid": "x", "cost_ms": 1}],
            },
        }
        _metrics, views = insights_inventory.build(
            [{"slug": "current"}], datasource_query_cost=payload,
        )
        rows = views["insights_datasource_query_cost"]
        self.assertEqual([row[" Stack"] for row in rows], ["current"])
        self.assertEqual(rows[0]["State"], "unknown")

    def test_ten_percent_unmeasured_stacks_remain_visible_as_unknown(self):
        stacks = [{"slug": f"stack-{index}"} for index in range(10)]
        payload = {
            stack["slug"]: {
                "available": True,
                "window": "24h",
                "datasources": [],
                "costs": [],
            }
            for stack in stacks[:-1]
        }
        payload["stack-9"] = {
            "available": False,
            "reason": "forbidden_403",
            "detail": "datasource_query_cost: HTTP 403",
        }

        _metrics, views = insights_inventory.build(
            stacks, datasource_query_cost=payload,
        )

        self.assertEqual(views["insights_datasource_query_cost"], [{
            " Stack": "stack-9",
            "Datasource": "(query cost unavailable)",
            "Datasource uid": "",
            "Datasource type": "",
            "State": "unknown",
            "Cumulative duration (ms)": None,
            "Cache hit %": None,
            "Coverage detail": "forbidden_403: datasource_query_cost: HTTP 403",
        }])

    def test_failed_name_resolution_makes_the_stack_unknown_not_a_bare_uid_finding(self):
        stacks = [{"slug": "alpha", "status": "active"}]
        with (
            mock.patch.object(scan.credentials, "load_all", return_value={"alpha": {"token": "x"}}),
            mock.patch.object(scan.stack_catalog, "probe_datasources_all", return_value={
                "alpha": {"available": False, "reason": "forbidden_403", "detail": "HTTP 403"},
            }),
            mock.patch.object(scan.usage_insights, "probe_datasource_cost_all", return_value={
                "alpha": {"available": True, "costs": [
                    {"datasourceUid": "opaque", "datasourceType": "loki", "cost_ms": 42},
                ]},
            }),
        ):
            payload, _errors = scan.gather_datasource_query_cost(
                object(), SimpleNamespace(concurrency=1), stacks,
            )

        self.assertFalse(payload["alpha"]["available"])
        self.assertEqual(payload["alpha"]["reason"], "forbidden_403")
        _metrics, views = insights_inventory.build(stacks, datasource_query_cost=payload)
        self.assertEqual(views["insights_datasource_query_cost"][0]["State"], "unknown")
        self.assertEqual(views["insights_datasource_query_cost"][0]["Datasource uid"], "")


class QueryMixViewTest(unittest.TestCase):
    def test_nonfinite_hydrated_mix_is_withheld(self):
        base = {
            "requests": 10, "query_mix_datasource_types_requests": 10,
            "query_mix_datasource_types_distinct": 1,
            "query_mix_datasource_types": [{"datasourceType": "prometheus", "count": 10}],
        }
        for change in (
            {"query_mix_datasource_types": [{"datasourceType": "prometheus", "count": float("nan")}]},
            {"query_mix_datasource_types_requests": float("inf")},
            {"requests": float("nan")},
        ):
            with self.subTest(change=change):
                record = {**base, **change}
                self.assertIsNone(insights._query_mix_rows(
                    "alpha", record, dimension="datasourceType",
                    breakdown="query_mix_datasource_types",
                    requests_field="query_mix_datasource_types_requests",
                    distinct_field="query_mix_datasource_types_distinct",
                ))

    def test_query_mix_view_is_scoped_to_the_insights_input_and_adds_no_metrics(self):
        stacks = [{"slug": "alpha"}]
        cov = Coverage(tier="t2", total=1)
        cov.record_ok("alpha")
        insight_input = {
            "alpha": {
                "available": True,
                "requests": 42,
                "datasources_queried": 2,
                "query_mix_datasource_types_requests": 35,
                "query_mix_datasource_types_distinct": 2,
                "query_mix_panel_plugins_requests": 27,
                "query_mix_panel_plugins_distinct": 3,
                "query_mix_complete": True,
                "query_mix_datasource_types": [
                    {"datasourceType": "prometheus", "count": 30},
                ],
                "query_mix_panel_plugins": [
                    {"panelPluginId": "timeseries", "count": 25},
                ],
            },
        }

        metrics, views = compose.build_all(stacks, cov, insights=insight_input)
        direct_metrics, _direct_views = insights.build(stacks, cov, insight_input)
        _baseline_metrics, baseline_views = compose.build_all(stacks, cov)
        legacy_record = dict(insight_input["alpha"])
        for field in (
            "query_mix_complete", "query_mix_datasource_types", "query_mix_panel_plugins",
            "query_mix_datasource_types_requests", "query_mix_datasource_types_distinct",
            "query_mix_panel_plugins_requests", "query_mix_panel_plugins_distinct",
        ):
            legacy_record.pop(field, None)
        legacy_metrics, _legacy_views = insights.build(stacks, cov, {"alpha": legacy_record})

        self.assertEqual(hydrate.VIEW_INPUTS.get("insights_query_mix"), frozenset({"insights"}))
        self.assertIn("insights_query_mix", views)
        self.assertNotIn("insights_query_mix", baseline_views)
        self.assertEqual(direct_metrics, legacy_metrics)
        self.assertTrue(all("prometheus" not in str(labels) and "timeseries" not in str(labels)
                            for _name, labels, _value in metrics))

        old_input = {"alpha": {"available": True, "requests": 42}}
        _old_metrics, old_views = compose.build_all(stacks, cov, insights=old_input)
        self.assertNotIn("insights_query_mix", old_views)


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        status, body = self.replies.pop(0)
        import json
        return Response(status=status, body=json.dumps(body).encode(), url=url)


class StackCatalogSourceTest(unittest.TestCase):
    STACK = {"slug": "alpha", "url": "https://authoritative.example", "dashboardCnt": 2}

    def test_dashboard_search_pages_to_a_short_page_and_keeps_every_dashboard(self):
        first = [
            {"uid": f"d-{index}", "title": f"Dashboard {index}", "type": "dash-db",
             "folderTitle": "Ops", "tags": ["service:checkout", "private:discard-me"]}
            for index in range(2)
        ]
        client = FakeClient([(200, first), (200, [])])
        with mock.patch.object(stack_catalog, "SEARCH_PAGE_SIZE", 2):
            out = stack_catalog.probe_dashboards_stack(client, self.STACK, "tok")
        self.assertTrue(out["available"])
        self.assertEqual([row["uid"] for row in out["dashboards"]], ["d-0", "d-1"])
        self.assertEqual(out["dashboards"][0]["service_tags"], ["service:checkout"])
        self.assertNotIn("private:discard-me", repr(out))
        self.assertEqual([call[1]["params"]["page"] for call in client.calls], [1, 2])
        self.assertTrue(all(call[0].startswith("https://authoritative.example/")
                            for call in client.calls))

    def test_dashboard_detail_keeps_only_allowlisted_literal_identity_selectors(self):
        """Query evidence is exact service_name equality; job and regex selectors are not bridges."""
        search = [
            {"uid": "d-0", "title": "Unrelated", "type": "dash-db", "tags": []},
            {"uid": "d-1", "title": "Also unrelated", "type": "dash-db", "tags": []},
        ]
        client = FakeClient([
            (200, search),
            (200, {"dashboard": {"panels": [{"targets": [{
                "expr": 'sum(rate(requests_total{service_name="checkout",job="checkout"}[5m]))',
            }]}]}}),
            (200, {"dashboard": {"panels": [{"targets": [{
                "expr": 'requests_total{service_name=~"inventory.*"}',
            }]}]}}),
        ])

        out = stack_catalog.probe_dashboards_stack(
            client, self.STACK, "tok", include_detail=True,
        )

        self.assertTrue(out["detail_available"])
        self.assertEqual(out["dashboards"][0]["identity_selectors"], ["checkout"])
        self.assertEqual(out["dashboards"][1]["identity_selectors"], [])
        self.assertNotIn("requests_total", repr(out))

    def test_dashboard_detail_lexes_promql_before_accepting_selector_evidence(self):
        """Comments and strings are not selectors; supported PromQL literals decode exactly."""
        search = [
            {"uid": "d-0", "title": "Noise", "type": "dash-db", "tags": []},
            {"uid": "d-1", "title": "Literals", "type": "dash-db", "tags": []},
        ]
        client = FakeClient([
            (200, search),
            (200, {"dashboard": {"panels": [{"targets": [{
                "expr": '# up{service_name="commented"}\n'
                        'label_replace(up, "dst", "service_name=\\"stringy\\"", "src", ".*")',
                "query": r"where value = 'bad\qescape'",
            }]}]}}),
            (200, {"dashboard": {"panels": [{"targets": [
                {"expr": r"up{service_name='check\x6fut'}"},
                {"expr": "up{service_name=`inventory`}"},
                {"expr": r'up{"service_name"="pay\155ents"}'},
            ]}]}}),
        ])

        out = stack_catalog.probe_dashboards_stack(
            client, self.STACK, "tok", include_detail=True,
        )

        self.assertTrue(out["detail_available"])
        self.assertEqual(out["dashboards"][0]["identity_selectors"], [])
        self.assertEqual(
            out["dashboards"][1]["identity_selectors"],
            ["checkout", "inventory", "payments"],
        )

    def test_malformed_promql_selector_makes_detail_evidence_unavailable(self):
        """Malformed selector syntax cannot be downgraded to trustworthy negative evidence."""
        search = [
            {"uid": "d-0", "title": "One", "type": "dash-db", "tags": []},
        ]
        for expression in (
            r'up{service_name="bad\qescape"}',
            r'up{service_name="bad\777escape"}',
            'up{service_name="checkout" job="api"}',
        ):
            with self.subTest(expression=expression):
                out = stack_catalog.probe_dashboards_stack(
                    FakeClient([
                        (200, search),
                        (200, {"dashboard": {"panels": [{"targets": [{
                            "expr": expression,
                        }]}]}}),
                    ]),
                    {**self.STACK, "dashboardCnt": 1},
                    "tok",
                    include_detail=True,
                )

                self.assertFalse(out["detail_available"])
                self.assertEqual(out["detail_reason"], stack_catalog.INVALID_RESPONSE)
                self.assertTrue(
                    all("identity_selectors" not in row for row in out["dashboards"]),
                )

    def test_one_failed_dashboard_detail_marks_stack_evidence_unavailable(self):
        """A partial detail census cannot support a no finding for any service on the stack."""
        search = [
            {"uid": "d-0", "title": "One", "type": "dash-db", "tags": []},
            {"uid": "d-1", "title": "Two", "type": "dash-db", "tags": []},
        ]
        out = stack_catalog.probe_dashboards_stack(
            FakeClient([
                (200, search),
                (200, {"dashboard": {"panels": []}}),
                (500, {}),
            ]),
            self.STACK,
            "tok",
            include_detail=True,
        )

        self.assertTrue(out["available"])
        self.assertFalse(out["detail_available"])
        self.assertTrue(all("identity_selectors" not in row for row in out["dashboards"]))

    def test_dashboard_search_refuses_duplicate_or_malformed_rows(self):
        duplicate = [
            {"uid": "same", "title": "One", "type": "dash-db"},
            {"uid": "same", "title": "Two", "type": "dash-db"},
        ]
        out = stack_catalog.probe_dashboards_stack(
            FakeClient([(200, duplicate)]), self.STACK, "tok",
        )
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], stack_catalog.INVALID_RESPONSE)

    def test_permission_filtered_empty_search_is_unknown_not_zero_dashboards(self):
        stack = {**self.STACK, "dashboardCnt": 1}
        out = stack_catalog.probe_dashboards_stack(FakeClient([(200, [])]), stack, "tok")

        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], stack_catalog.INCOMPLETE_INVENTORY)

    def test_missing_or_unsafe_inventory_url_never_falls_back_to_the_slug(self):
        for stack in ({"slug": "alpha"}, {"slug": "alpha", "url": "http://alpha.example"}):
            with self.subTest(stack=stack):
                client = FakeClient([])
                out = stack_catalog.probe_dashboards_stack(client, stack, "tok")
                self.assertFalse(out["available"])
                self.assertEqual(out["reason"], stack_catalog.INVALID_URL)
                self.assertEqual(client.calls, [])

    def test_datasource_list_keeps_only_the_join_fields_and_validates_them(self):
        client = FakeClient([(200, [{
            "uid": "prom", "name": "Primary", "type": "prometheus",
            "url": "https://secret-backend.example", "secureJsonFields": {"password": True},
        }])])
        out = stack_catalog.probe_datasources_stack(client, self.STACK, "tok")
        self.assertEqual(out["datasources"], [
            {"uid": "prom", "name": "Primary", "type": "prometheus"},
        ])
        self.assertNotIn("secret-backend", repr(out))


class Stage19UsageInsightsSourceTest(unittest.TestCase):
    def test_usage_queries_use_the_shared_deadline_aware_read_only_client(self):
        body = json.dumps({
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }).encode()
        client = mock.Mock()
        client.get.return_value = Response(status=200, body=body, url="https://alpha.example")

        with mock.patch.object(ui.urllib.request, "urlopen") as raw_urlopen:
            regular = ui.probe_stack(
                "alpha", "https://alpha.example", "tok", instance_id="123", client=client,
            )
            activity = ui.probe_dashboard_activity_stack(
                "alpha", "https://alpha.example", "tok", instance_id="123", client=client,
            )

        self.assertTrue(regular["available"])
        self.assertTrue(activity["available"])
        raw_urlopen.assert_not_called()
        self.assertEqual(client.get.call_count, len(ui.SCALARS) + len(ui.BREAKDOWNS) + 1)

    def test_dashboard_activity_is_full_and_exactly_31_days(self):
        self.assertIn(f"[{ui.ACTIVITY_WINDOW}]", ui.DASHBOARD_ACTIVITY_QUERY)
        self.assertEqual(ui.ACTIVITY_WINDOW, "31d")
        self.assertIn("sum by (dashboardUid)", ui.DASHBOARD_ACTIVITY_QUERY)
        self.assertNotIn("topk", ui.DASHBOARD_ACTIVITY_QUERY)
        self.assertIn("%(sel)s", ui.DASHBOARD_ACTIVITY_QUERY)

    def test_query_cost_is_top_n_per_stack_and_returns_cost_plus_cache_share(self):
        query = ui.DATASOURCE_COST_QUERY
        self.assertIn(f"topk({ui.TOP_DATASOURCES}", query)
        self.assertIn("datasourceUid", query)
        self.assertIn("unwrap duration", query)
        self.assertIn("unwrap cachedQueries", query)
        self.assertIn("unwrap totalQueries", query)
        self.assertIn('measure", "cost_ms"', query)
        self.assertIn('measure", "cache_hit_ratio"', query)
        self.assertGreaterEqual(query.count("%(sel)s"), 2)

    def test_query_cost_expression_has_balanced_parentheses(self):
        """Loki rejects an extra close at the end of the cache-ratio branch with HTTP 400."""
        query = ui.DATASOURCE_COST_QUERY % {"sel": ui.selector(instance_id="123")}
        self.assertEqual(query.count("("), query.count(")"), query)
        ui._assert_scoped(query, "123")

    def test_query_cost_cache_ratio_excludes_zero_query_denominators(self):
        """A datasource with totalQueries=0 otherwise produces NaN and poisons the full stack."""
        self.assertIn("> 0", ui._DS_CACHE_RATIO)

    def test_dashboard_activity_query_passes_the_same_regional_runtime_guard(self):
        rendered = ui.DASHBOARD_ACTIVITY_QUERY % {"sel": ui.selector(instance_id="123")}
        ui._assert_scoped(rendered, "123")

    def test_dashboard_activity_refuses_missing_or_duplicate_uids(self):
        for metrics in (
            [{}, {"dashboardUid": "ok"}],
            [{"dashboardUid": "same"}, {"dashboardUid": "same"}],
        ):
            with self.subTest(metrics=metrics):
                body = {
                    "status": "success",
                    "data": {"resultType": "vector", "result": [
                        {"metric": metric, "value": [0, "1"]} for metric in metrics
                    ]},
                }
                with mock.patch.object(ui, "_query", return_value=body):
                    out = ui.probe_dashboard_activity_stack(
                        "alpha", "https://alpha.example", "tok", instance_id="123",
                    )

                self.assertFalse(out["available"])
                self.assertEqual(out["reason"], ui.MALFORMED_RESPONSE)

    def test_query_cost_parser_merges_measures_and_keeps_missing_ratio_unknown(self):
        body = {
            "status": "success",
            "data": {"resultType": "vector", "result": [
                {"metric": {"datasourceUid": "a", "datasourceType": "prometheus",
                            "measure": "cost_ms"}, "value": [0, "1000"]},
                {"metric": {"datasourceUid": "a", "datasourceType": "prometheus",
                            "measure": "cache_hit_ratio"}, "value": [0, "0.5"]},
                {"metric": {"datasourceUid": "b", "datasourceType": "loki",
                            "measure": "cost_ms"}, "value": [0, "500"]},
            ]},
        }
        with mock.patch.object(ui, "_query", return_value=body):
            out = ui.probe_datasource_cost_stack(
                "alpha", "https://alpha.example", "tok", instance_id="123",
            )
        self.assertTrue(out["available"])
        by_uid = {row["datasourceUid"]: row for row in out["costs"]}
        self.assertEqual(by_uid["a"]["cost_ms"], 1000)
        self.assertEqual(by_uid["a"]["cache_hit_ratio"], 0.5)
        self.assertIsNone(by_uid["b"]["cache_hit_ratio"])


class CompositionAndHydrationContractTest(unittest.TestCase):
    def test_new_inputs_are_t2_owned_and_views_have_derived_dependencies(self):
        self.assertEqual(hydrate.INPUT_OWNER.get("dashboard_inventory"), "t2")
        self.assertEqual(hydrate.INPUT_OWNER.get("datasource_query_cost"), "t2")
        self.assertEqual(
            hydrate.VIEW_INPUTS.get("insights_dashboard_opening_31d"),
            frozenset({"dashboard_inventory"}),
        )
        self.assertEqual(
            hydrate.VIEW_INPUTS.get("insights_datasource_query_cost"),
            frozenset({"datasource_query_cost"}),
        )
        for view in (
            "insights_surface_usage", "insights_surface_usage_estate",
            "insights_surface_unmapped",
        ):
            with self.subTest(view=view):
                self.assertEqual(hydrate.VIEW_INPUTS.get(view), frozenset({"insights"}))

    def test_compose_emits_new_views_but_no_new_metrics(self):
        stacks = [{"slug": "alpha"}]
        cov = Coverage(tier="t2", total=1)
        cov.record_ok("alpha")
        dashboard_input = {
            "alpha": {"available": True, "activity_available": True, "window": "31d",
                      "dashboards": [], "opened": []},
        }
        cost_input = {
            "alpha": {"available": True, "window": "24h", "datasources": [], "costs": []},
        }
        baseline, _baseline_views = compose.build_all(stacks, cov)
        metrics, views = compose.build_all(
            stacks, cov, dashboard_inventory=dashboard_input,
            datasource_query_cost=cost_input,
        )
        self.assertEqual(metrics, baseline, "the two S3 views must add zero metric series")
        self.assertIn("insights_dashboard_opening_31d", views)
        self.assertIn("insights_datasource_query_cost", views)

    def test_surface_views_and_trends_compose_from_the_t2_insights_input(self):
        stacks = [{"slug": "alpha"}]
        cov = Coverage(tier="t2", total=1)
        cov.record_ok("alpha")
        insight_input = {
            "alpha": {
                "available": True,
                "requests": 4,
                "surface_users_available": {"app_scenes": True},
                "surface_requests": [{"surface": "app_scenes", "count": 4}],
                "surface_users": [{"surface": "app_scenes", "count": 2}],
                "surface_unmapped_sources": [],
            },
        }

        metrics, views = compose.build_all(stacks, cov, insights=insight_input)

        self.assertIn("insights_surface_usage", views)
        self.assertIn("insights_surface_usage_estate", views)
        self.assertIn("insights_surface_unmapped", views)
        self.assertEqual(views["insights_surface_usage"][0]["Surface"], "app_scenes")
        self.assertEqual(views["insights_surface_usage"][0]["Distinct identified users"], 2)
        self.assertEqual(views["insights_surface_usage_estate"][0]["Stacks queried"], 1)
        series = {
            (name, labels.get("surface"))
            for name, labels, _value in metrics
            if name.startswith("gcinsight_dashboards_estate_surface_")
        }
        self.assertEqual(series, {
            (f"gcinsight_dashboards_estate_surface_{suffix}", surface)
            for suffix in ("requests", "stacks")
            for surface in ui.SURFACE_VALUES
        })


if __name__ == "__main__":
    unittest.main()
