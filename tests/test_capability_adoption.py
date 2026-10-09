"""Capability opportunity input and Pillar K denominator decisions.

These tests pin the parts most likely to make an adoption gap look better than it is: using an
instantaneous rate, iterating a stale payload instead of live inventory, or turning an unmeasured
absence into a measured zero.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from collector.coverage import Coverage
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import ai, compose, coverage
from collector.sources import capability_adoption as source


NOW = dt.datetime(2026, 8, 25, 12, 0, tzinfo=dt.timezone.utc)


def prometheus(rows):
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"stack_id": str(stack_id)}, "value": [0, str(value)]}
                for stack_id, value in rows
            ],
        },
    }


class _Client:
    def __init__(self, by_query):
        self.by_query = by_query
        self.calls = []

    def get(self, url, *, params=None, bearer=None):
        self.calls.append((url, dict(params or {}), bearer))
        body = self.by_query.get(params["query"], prometheus([]))
        import json
        return Response(200, json.dumps(body).encode(), url)


class _FailingClient:
    def get(self, *_args, **_kwargs):
        raise RuntimeError("transport retries exhausted")


class SourceContractTest(unittest.TestCase):
    def test_datasource_uid_matches_the_write_stack_only_permission(self):
        from collector import provision
        self.assertEqual(source.DS_UID, provision.USAGE_DS_UID)
        ordinary = provision.permission_pairs(provision.desired_permissions(write_stack=False))
        write = provision.permission_pairs(provision.desired_permissions(write_stack=True))
        pair = ("datasources:query", f"datasources:uid:{source.DS_UID}")
        self.assertNotIn(pair, ordinary)
        self.assertIn(pair, write)

    def test_every_rate_shaped_query_uses_the_same_explicit_window(self):
        """A bursty instantaneous trace denominator once inverted the adoption conclusion."""
        for name in source.RATE_QUERIES:
            with self.subTest(name=name):
                self.assertIn(f"[{source.WINDOW}:", source.QUERIES[name])

    def test_probe_uses_only_the_live_write_stack_and_preserves_measured_zeros(self):
        """The live inventory is authoritative; a zero returned by this source is the finding."""
        client = _Client({query: prometheus([(101, 0)]) for query in source.QUERIES.values()})
        stacks = [
            {"slug": "hub", "id": 101, "status": "active", "url": "https://hub.example.test"},
            {"slug": "other", "id": 202, "status": "active", "url": "https://other.example.test"},
        ]
        result = source.probe(
            client, stacks,
            {"hub": {"token": "write-reader"}, "departed": {"token": "stale"}},
            write_stack="hub", now=NOW,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["values"]["traces"], {"101": 0.0})
        self.assertEqual(len(client.calls), len(source.QUERIES) + len(source.FOOTPRINT_QUERIES))
        self.assertTrue(all(call[0].startswith("https://hub.example.test/") for call in client.calls))
        self.assertTrue(all(call[2] == "write-reader" for call in client.calls))

    def test_missing_write_stack_credential_is_unavailable_not_an_estate_of_zero(self):
        result = source.probe(
            _Client({}),
            [{"slug": "hub", "id": 101, "status": "active", "url": "https://hub.example.test"}],
            {}, write_stack="hub", now=NOW,
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], source.NO_CREDENTIAL)

    def test_transport_failure_withholds_the_input_instead_of_crashing_the_tier(self):
        result = source.probe(
            _FailingClient(),
            [{"slug": "hub", "status": "active", "url": "https://hub.example.test"}],
            {"hub": {"token": "write-reader"}}, write_stack="hub", now=NOW,
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], source.TRANSPORT_ERROR)
        self.assertEqual(result["detail"], "metrics: transport error")


# Frozen consumer contract: literals intentionally independent of the implementation's query table.
FOOTPRINT_EXPRESSIONS = {
    "adaptive_traces": "max_over_time(sum by(stack_id)("
        "grafanacloud_traces_instance_adaptivetraces_bytes_received_per_second)[24h:5m])",
    "app_observability": "max_over_time(sum by(stack_id)("
        "grafanacloud_app_observability_service_entity_count)[24h:5m])",
    "agent_observability": "max_over_time(sum by(stack_id)("
        "grafanacloud_agent_observability_instance_generation_items_per_second)[30d:5m])",
    "assistant_org_users": "sum(grafanacloud_org_assistant_users)",
}


class FootprintBoundaryTest(unittest.TestCase):
    stacks = [
        {"slug": "hub", "id": 101, "status": "active", "url": "https://hub.example.test"},
        {"slug": "other", "id": 202, "status": "active", "url": "https://other.example.test"},
    ]

    def probe(self, overrides=None, *, stacks=None, credentials=None):
        self.requests = []
        bodies = {query: prometheus([(101, 7)]) for query in source.QUERIES.values()}
        bodies.update({query: prometheus([(101, 0), (202, 3), (999, 8)])
                       for key, query in FOOTPRINT_EXPRESSIONS.items()
                       if key != "assistant_org_users"})
        bodies[FOOTPRINT_EXPRESSIONS["assistant_org_users"]] = {
            "status": "success", "data": {"resultType": "vector", "result": [
                {"metric": {"private": "private-upstream"}, "value": [0, "5"]}]}}
        # New reporting families are deliberately absent from the historical fixture.
        # Only tests with explicit reporting observations may populate them.
        bodies.update({query: prometheus([]) for query in REPORTING_EXPRESSIONS.values()})
        bodies.update(overrides or {})

        def transport(request, _timeout):
            self.requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)["query"][0]
            outcome = bodies[query]
            if isinstance(outcome, Exception):
                raise outcome
            status, body = outcome if isinstance(outcome, tuple) else (200, outcome)
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            return Response(status, raw, request.full_url)

        return source.probe(
            ReadOnlyClient(transport=transport, max_attempts=1, timeout=1),
            self.stacks if stacks is None else stacks,
            {"hub": {"token": "write-reader"}} if credentials is None else credentials,
            write_stack="hub", now=NOW,
        )

    def test_real_source_to_compose_preserves_positive_mapping_and_unknown_controls(self):
        # The HTTP transport boundary supplies a per-stack rate and an empty org vector.
        # Legacy failure cannot suppress independently available footprint evidence.
        payload = self.probe({source.QUERIES["metrics"]: (503, {}),
                             FOOTPRINT_EXPRESSIONS["assistant_org_users"]: prometheus([])})
        self.assertFalse(payload["available"])
        _, views, _ = compose.build_all(self.stacks, Coverage(tier="t2", total=2),
                                        capability_adoption=payload, now=NOW)
        rows = {r[" Stack"]: r for r in views["ai_agent_observability"]}
        self.assertEqual(set(rows), {"hub", "other"})
        self.assertEqual(rows["other"]["Maximum generation items/s (30d)"], 3)
        self.assertTrue(rows["other"]["Positive rate reported (30d)"])
        self.assertFalse(rows["hub"]["Positive rate reported (30d)"])
        empty = self.probe({FOOTPRINT_EXPRESSIONS["agent_observability"]: prometheus([])})
        _, unknown, _ = compose.build_all(self.stacks, Coverage(tier="t2", total=2),
                                          capability_adoption=empty, now=NOW)
        self.assertTrue(all(r["Positive rate reported (30d)"] is None
                            for r in unknown["ai_agent_observability"]))

    def test_frozen_payload_queries_windows_live_ids_and_minimization(self):
        body = prometheus([(101, 0), (202, 3), (999, 8)])
        for row in body["data"]["result"]:
            row["metric"].update({"org_id": "private-upstream", "policy": "private-upstream"})
        result = self.probe({FOOTPRINT_EXPRESSIONS["adaptive_traces"]: body})
        self.assertTrue(result["available"])
        self.assertEqual(result["values"], {key: {"101": 7.0} for key in source.QUERIES})
        footprint = result["footprint"]
        self.assertEqual(set(footprint), set(FOOTPRINT_EXPRESSIONS) | set(REPORTING_EXPRESSIONS))
        for key, basis, days in (
            ("adaptive_traces", "maximum_bytes_per_second", 1),
            ("app_observability", "maximum_service_entity_count", 1),
            ("agent_observability", "maximum_generation_items_per_second", 30),
        ):
            self.assertEqual(footprint[key], {
                "available": True, "values": {"101": 0.0, "202": 3.0}, "basis": basis,
                "window": "24h" if days == 1 else "30d",
                "window_start": (NOW - dt.timedelta(days=days)).isoformat(),
                "window_end": NOW.isoformat(),
            })
        self.assertEqual(footprint["assistant_org_users"], {
            "available": True, "value": 5.0, "basis": "current_billing_period_org_gauge",
            "window": "service_default_lookback_unknown", "window_start": None,
            "window_end": NOW.isoformat(),
        })
        self.assertEqual(footprint["db_observability"], {
            "available": False, "reason": "empty_response", "basis": "reporting_marker_presence",
            "window": "24h query observation; producer window and units unverified",
            "window_start": (NOW - dt.timedelta(days=1)).isoformat(),
            "window_end": NOW.isoformat(),
        })
        self.assertNotIn("private-upstream", json.dumps(result))
        observed = []
        for request in self.requests:
            parts = urlsplit(request.full_url)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(parts.netloc, "hub.example.test")
            self.assertEqual(parts.path,
                             "/api/datasources/proxy/uid/grafanacloud-usage/api/v1/query")
            self.assertEqual(request.get_header("Authorization"), "Bearer write-reader")
            params = parse_qs(parts.query)
            self.assertEqual(params["time"], [str(int(NOW.timestamp()))])
            observed.append(params["query"][0])
        self.assertEqual(set(observed), set(source.QUERIES.values()) |
                         set(FOOTPRINT_EXPRESSIONS.values()) | set(REPORTING_EXPRESSIONS.values()))
        self.assertEqual(len(observed), len(set(observed)))

    def test_optional_errors_are_independent_closed_and_never_zero(self):
        cases = [
            (prometheus([]), "empty_response"),
            (prometheus([(999, 3)]), "empty_response"),
            ((206, prometheus([(101, 1)])), "http_error"),
            ((201, prometheus([(101, 1)])), "http_error"),
            ((503, b"private-upstream"), "http_error"),
            (RuntimeError("private-upstream"), "transport_error"),
            (b"private-upstream", "malformed_response"),
            ({"status": "error", "error": "private-upstream"}, "malformed_response"),
            ({"status": "success", "data": {"resultType": "matrix", "result": []}},
             "malformed_response"),
            (prometheus([(101, 1), (101, 2)]), "malformed_response"),
            (prometheus([(101, "NaN")]), "malformed_response"),
            (prometheus([(101, "Inf")]), "malformed_response"),
            (prometheus([(101, "-Inf")]), "malformed_response"),
            (prometheus([(101, -1)]), "malformed_response"),
            (prometheus([(101, "not-numeric")]), "malformed_response"),
            ({"status": "success", "data": {"resultType": "vector", "result": [
                {"metric": {}, "value": [0, "1"]}]}}, "malformed_response"),
        ]
        for key in ("adaptive_traces", "app_observability", "agent_observability"):
            for body, reason in cases:
                with self.subTest(key=key, reason=reason, body=body):
                    result = self.probe({FOOTPRINT_EXPRESSIONS[key]: body})
                    self.assertTrue(result["available"])
                    self.assertEqual(set(result["values"]), set(source.QUERIES))
                    entry = result["footprint"][key]
                    self.assertFalse(entry["available"])
                    self.assertEqual(entry["reason"], reason)
                    self.assertEqual(set(entry), {"available", "reason", "basis", "window",
                                                  "window_start", "window_end"})
                    self.assertNotIn("private-upstream", json.dumps(result))
                    for other in FOOTPRINT_EXPRESSIONS.keys() - {key}:
                        self.assertTrue(result["footprint"][other]["available"])

    def test_org_gauge_single_finite_vector_empty_errors_and_measured_zero(self):
        def scalar(values):
            return {"status": "success", "data": {"resultType": "vector", "result": [
                {"metric": {"private": "private-upstream"}, "value": [0, value]}
                for value in values]}}
        for outcome, reason in (
            (scalar([]), "empty_response"),
            (scalar(["1", "2"]), "malformed_response"),
            (scalar(["NaN"]), "malformed_response"),
            (scalar(["Inf"]), "malformed_response"),
            (scalar(["-1"]), "malformed_response"),
            ((206, scalar(["1"])), "http_error"),
            (RuntimeError("private-upstream"), "transport_error"),
            (b"private-upstream", "malformed_response"),
        ):
            with self.subTest(reason=reason, outcome=outcome):
                result = self.probe({FOOTPRINT_EXPRESSIONS["assistant_org_users"]: outcome})
                self.assertTrue(result["available"])
                entry = result["footprint"]["assistant_org_users"]
                self.assertFalse(entry["available"])
                self.assertEqual(entry["reason"], reason)
                self.assertNotIn("value", entry)
                self.assertNotIn("values", entry)
                self.assertNotIn("private-upstream", json.dumps(result))
        result = self.probe({FOOTPRINT_EXPRESSIONS["assistant_org_users"]: scalar(["0"])})
        self.assertTrue(result["footprint"]["assistant_org_users"]["available"])
        self.assertEqual(result["footprint"]["assistant_org_users"]["value"], 0.0)

    def test_malformed_sample_shapes_are_unavailable_not_measurements(self):
        rows = [None, {}, {"metric": []}, {"metric": {}, "value": [0]},
                {"metric": {}, "value": [0, True]},
                {"metric": {}, "value": [0, None]},
                {"metric": {}, "value": [0, {}]}]
        for key, query in (FOOTPRINT_EXPRESSIONS | REPORTING_EXPRESSIONS).items():
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("metric"), dict):
                    row = {**row, "metric": {"stack_id": "101"}}
                with self.subTest(key=key, row=row):
                    result = self.probe({query: {"status": "success", "data": {
                        "resultType": "vector", "result": [row]}}})
                    self.assertTrue(result["available"])
                    entry = result["footprint"][key]
                    self.assertEqual(entry["reason"], "malformed_response")
                    self.assertNotIn("values", entry)
                    self.assertNotIn("value", entry)

    def test_legacy_errors_and_empty_results_keep_their_contract(self):
        for outcome, reason in (
            (RuntimeError("private-upstream"), "transport_error"),
            ((503, b"private-upstream"), "http_error"),
            (b"private-upstream", "malformed_response"),
            (prometheus([(101, "NaN")]), "malformed_response"),
            (prometheus([(101, 1), (101, 2)]), "malformed_response"),
        ):
            with self.subTest(reason=reason):
                result = self.probe({source.QUERIES["traces"]: outcome})
                self.assertFalse(result["available"])
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("values", result)
                self.assertNotIn("private-upstream", json.dumps(result))
                self.assertTrue(result["footprint"]["adaptive_traces"]["available"])
        result = self.probe({source.QUERIES["traces"]: prometheus([])})
        self.assertTrue(result["available"])
        self.assertEqual(result["values"]["traces"], {})

    def test_preflight_failures_do_not_call_upstream_or_invent_measurements(self):
        for stacks, credentials, reason in (
            ([], None, "write_stack_missing"),
            ([{**self.stacks[0], "status": "paused"}], None, "write_stack_missing"),
            ([{**self.stacks[0], "url": "http://invalid.example.test"}], None, "invalid_url"),
            (self.stacks, {}, "no_credential"),
        ):
            with self.subTest(reason=reason):
                result = self.probe(stacks=stacks, credentials=credentials)
                self.assertFalse(result["available"])
                self.assertEqual(result["reason"], reason)
                self.assertEqual(self.requests, [])
                for key in FOOTPRINT_EXPRESSIONS:
                    self.assertFalse(result["footprint"][key]["available"])
                    self.assertEqual(result["footprint"][key]["reason"], reason)
                    self.assertNotIn("values", result["footprint"][key])
                    self.assertNotIn("value", result["footprint"][key])

    def test_legacy_maps_also_drop_departed_ids_and_partial_http_is_unavailable(self):
        result = self.probe({query: prometheus([(101, 0), (999, 2)])
                             for query in source.QUERIES.values()})
        self.assertTrue(result["available"])
        self.assertEqual(result["values"], {key: {"101": 0.0} for key in source.QUERIES})
        result = self.probe({source.QUERIES["metrics"]: (206, prometheus([(101, 1)]))})
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "http_error")


# Frozen observation contract, independent of the implementation's registry and query helper.
NEW_OBSERVATIONS = {
    "synthetic_monitoring": ("Synthetic Monitoring", "billable-check execution",
        "max_over_time(sum by(stack_id)(grafanacloud_sm_billable_check_executions_per_second)[24h:5m])"),
    "kubernetes": ("Kubernetes", "pod-info series",
        "max_over_time(sum by(stack_id)(grafanacloud_instance_active_kube_pod_info_series)[24h:5m])"),
    "knowledge_graph": ("Knowledge Graph", "active-entity",
        "max_over_time(sum by(stack_id)(grafanacloud_asserts_instance_active_entities)[24h:5m])"),
    "pdc": ("Private Datasource Connect", "connected-agent",
        "max_over_time(sum by(stack_id)(grafanacloud_grafana_pdc_connected_agents)[24h:5m])"),
}


class NewObservationBoundaryTest(unittest.TestCase):
    stacks = [
        {"slug": "hub", "id": 101, "status": "active", "url": "https://hub.example.test"},
        {"slug": "zero", "id": 202, "status": "active"},
        {"slug": "unknown", "id": 303, "status": "active"},
        {"slug": "paused", "id": 404, "status": "paused"},
    ]

    def probe(self, overrides=None):
        bodies = {query: prometheus([(101, 7), (202, 0), (404, 9), (999, 9)])
                  for _title, _basis, query in NEW_OBSERVATIONS.values()}
        bodies.update(overrides or {})
        return FootprintBoundaryTest.probe(self, bodies)

    def compose(self, payload, stacks=None):
        stacks = self.stacks if stacks is None else stacks
        return compose.build_all(stacks, Coverage(tier="t2", total=len(stacks)),
                                 signal_inventory={}, capability_adoption=payload, now=NOW)

    def test_guarded_source_compose_view_and_dashboard_call_list(self):
        import shutil
        import tempfile
        from bin import dashboards
        from collector.dashboards import build
        from collector.emit import s3

        payload = self.probe()
        observed = {parse_qs(urlsplit(r.full_url).query)["query"][0] for r in self.requests}
        for _title, _basis, query in NEW_OBSERVATIONS.values():
            self.assertIn(query, observed)
        for request in self.requests:
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(urlsplit(request.full_url).netloc, "hub.example.test")
            self.assertEqual(urlsplit(request.full_url).path,
                             "/api/datasources/proxy/uid/grafanacloud-usage/api/v1/query")
        metrics, views, meta = self.compose(payload)
        rows = {row["Capability"]: row for row in views["coverage_capability_adoption"]}
        for key, (title, basis, _query) in NEW_OBSERVATIONS.items():
            row = rows[title]
            self.assertEqual((row["Population stacks"], row["Stacks using capability"],
                              row["Opportunity stacks"]), (2, 1, 1))
            for text in ("Non-paused live stacks", basis, "absent", "unknown"):
                self.assertIn(text, row["Population basis"])
            self.assertIn("not human adoption", row["Finding"])
            self.assertIn("producer window unverified", row["Window"])
            self.assertIn("units unverified", row["Population basis"])
            self.assertIn(("gcinsight_coverage_capability_gap", {"kind": key}, 1.0), metrics)
            self.assertEqual([r[" Stack"] for r in views["coverage_capability_opportunities"]
                              if r["Capability"] == title], ["zero"])
        with tempfile.TemporaryDirectory() as tmp:
            local = pathlib.Path(tmp)
            for existing in (pathlib.Path(__file__).resolve().parent.parent /
                             "testdata" / "views").glob("*.json"):
                shutil.copyfile(existing, local / existing.name)
            for name in ("coverage_capability_adoption", "coverage_capability_opportunities"):
                (local / (name + ".json")).write_text(json.dumps(s3.view_payload(views[name], meta)))
            with mock.patch.object(build, "VIEWS_DIR", tmp), mock.patch.object(build, "BUCKET", "offline"):
                _, artifact = dashboards.assemble("coverage", "infinity-offline")
            for panel_key in ("tbl_adoption", "tbl_adoption_targets"):
                spec = artifact["spec"]["elements"][panel_key]["spec"]
                query = spec["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
                self.assertEqual(query["parser"], "backend")
                self.assertEqual(query["root_selector"], "rows")
                public = json.loads((local / query["url"].rsplit("/", 1)[-1]).read_text())
                self.assertTrue({title for title, _, _ in NEW_OBSERVATIONS.values()}.issubset(
                    {row["Capability"] for row in public["rows"]}))
                self.assertIn("not human adoption", spec["description"])

    def test_empty_departed_paused_and_nullable_observations_are_unknown_not_zero(self):
        for outcome in (prometheus([]), prometheus([(999, 4)]), prometheus([(404, 4)])):
            with self.subTest(outcome=outcome):
                payload = self.probe({query: outcome for _, _, query in NEW_OBSERVATIONS.values()})
                metrics, views, _ = self.compose(payload)
                rows = {r["Capability"]: r for r in views["coverage_capability_adoption"]}
                for key, (title, _, _) in NEW_OBSERVATIONS.items():
                    for column in ("Population stacks", "Stacks using capability", "Opportunity stacks"):
                        self.assertIsNone(rows[title][column])
                    self.assertNotIn(key, {labels["kind"] for name, labels, _ in metrics
                                          if name == "gcinsight_coverage_capability_gap"})
                    self.assertNotIn(title, {r["Capability"]
                                            for r in views["coverage_capability_opportunities"]})
        payload = self.probe()
        for key in NEW_OBSERVATIONS:
            payload["values"][key] = {"101": None}
        metrics, views, _ = self.compose(payload)
        rows = {r["Capability"]: r for r in views["coverage_capability_adoption"]}
        self.assertTrue(all(rows[title]["Population stacks"] is None
                            for title, _, _ in NEW_OBSERVATIONS.values()))

    def test_new_query_failures_preserve_atomic_source_unavailability(self):
        for _key, (title, _, query) in NEW_OBSERVATIONS.items():
            for outcome in ((206, prometheus([(101, 1)])), RuntimeError("private-upstream"),
                            prometheus([(101, "NaN")]), prometheus([(101, None)])):
                with self.subTest(title=title, outcome=outcome):
                    payload = self.probe({query: outcome})
                    self.assertFalse(payload["available"])
                    self.assertNotIn("values", payload)
                    metrics, views, _ = self.compose(payload)
                    self.assertFalse(any(name == "gcinsight_coverage_capability_gap"
                                         for name, _, _ in metrics))
                    self.assertFalse({t for t, _, _ in NEW_OBSERVATIONS.values()} & {
                        r["Capability"] for r in views["coverage_capability_adoption"]})
                    self.assertNotIn("private-upstream", json.dumps(payload))

    def test_fresh_consumer_inventory_drops_stale_source_and_measured_zero_gap_remains(self):
        payload = self.probe()
        metrics, views, _ = self.compose(payload, [self.stacks[0], self.stacks[2]])
        rows = {r["Capability"]: r for r in views["coverage_capability_adoption"]}
        for key, (title, _, _) in NEW_OBSERVATIONS.items():
            self.assertEqual(rows[title]["Population stacks"], 1)
            self.assertEqual(rows[title]["Opportunity stacks"], 0)
            self.assertIn(("gcinsight_coverage_capability_gap", {"kind": key}, 0.0), metrics)
            self.assertNotIn(title, {r["Capability"]
                                    for r in views["coverage_capability_opportunities"]})

    def test_oncall_is_a_gauge_without_an_invented_period_or_cohort(self):
        _, views, _ = self.compose(self.probe())
        row = next(r for r in views["coverage_capability_adoption"] if r["Capability"] == "IRM / OnCall")
        self.assertIn("gauge", row["Population basis"])
        self.assertIn("gauge", row["Window"])
        self.assertNotIn("cumulative", json.dumps(row))
        self.assertNotIn("counter", json.dumps(row))


# Reporting-only queries: count label-bearing markers, never interpret their values as units.
REPORTING_EXPRESSIONS = {
    "db_observability": "max_over_time(count by(stack_id)("
        "grafanacloud_instance_active_dbo11y_instance_count)[24h:5m])",
    "db_observability_series": "max_over_time(count by(stack_id)("
        "grafanacloud_instance_active_dbo11y_series)[24h:5m])",
    "db_observability_stats": "max_over_time(count by(stack_id)("
        "grafanacloud_instance_active_dbo11y_stats)[24h:5m])",
    "app_host_count": "max_over_time(count by(stack_id)("
        "grafanacloud_instance_app_o11y_host_count)[24h:5m])",
    "app_host_v2_count": "max_over_time(count by(stack_id)("
        "grafanacloud_instance_app_o11y_host_v2_count)[24h:5m])",
    "app_host_v3_count": "max_over_time(count by(stack_id)("
        "grafanacloud_instance_app_o11y_host_v3_count)[24h:5m])",
    "app_billable_host_hours": "max_over_time(grafanacloud_org_app_o11y_billable_host_hours[24h])",
    "app_included_host_hours": "max_over_time(grafanacloud_org_app_o11y_included_host_hours[24h])",
    "infra_billable_host_hours": "max_over_time(grafanacloud_org_infra_o11y_billable_host_hours[24h])",
    "infra_included_host_hours": "max_over_time(grafanacloud_org_infra_o11y_included_host_hours[24h])",
}
REPORTING_ORG = frozenset({"app_billable_host_hours", "app_included_host_hours",
                           "infra_billable_host_hours", "infra_included_host_hours"})


class ReportingFootprintTest(unittest.TestCase):
    stacks = [
        {"slug": "hub", "id": 101, "status": "active", "url": "https://hub.example.test"},
        {"slug": "zero-marker", "id": 202, "status": "active"},
        {"slug": "unknown", "id": 303, "status": "active"},
        {"slug": "paused", "id": 404, "status": "paused"},
    ]

    def probe(self, overrides=None):
        # Count queries report marker presence even when the original gauge value was zero.
        bodies = {query: prometheus([(101, 2), (202, 1), (404, 1), (999, 1)])
                  for key, query in REPORTING_EXPRESSIONS.items() if key not in REPORTING_ORG}
        bodies.update({REPORTING_EXPRESSIONS[key]: {"status": "success", "data": {
            "resultType": "vector", "result": [{"metric": {}, "value": [0, "12"]}]}}
                       for key in REPORTING_ORG})
        bodies.update(overrides or {})
        return FootprintBoundaryTest.probe(self, bodies)

    def compose(self, payload, stacks=None):
        stacks = self.stacks if stacks is None else stacks
        return compose.build_all(stacks, Coverage(tier="t2", total=len(stacks)),
                                 signal_inventory={}, capability_adoption=payload, now=NOW)

    def test_exact_reporting_queries_compose_without_inventing_adoption_or_units(self):
        payload = self.probe()
        observed = {parse_qs(urlsplit(r.full_url).query)["query"][0] for r in self.requests}
        self.assertTrue(set(REPORTING_EXPRESSIONS.values()).issubset(observed))
        for key in REPORTING_EXPRESSIONS:
            entry = payload["footprint"][key]
            self.assertTrue(entry["available"], key)
            self.assertEqual(entry["window"], "24h query observation; producer window and units unverified")
            self.assertEqual(entry["window_start"], (NOW - dt.timedelta(days=1)).isoformat())
            self.assertEqual(entry["window_end"], NOW.isoformat())
        metrics, views, _ = self.compose(payload)
        rows = {r["Capability"]: r for r in views[coverage.ADOPTION_VIEW]}
        for title in ("Database Observability", "Application Observability host reporting"):
            row = rows[title]
            self.assertEqual(row["Population stacks"], 2)
            self.assertIsNone(row["Stacks using capability"])
            self.assertIsNone(row["Opportunity stacks"])
            self.assertIn("1 of 3", row["Finding"])
            self.assertIn("marker presence", row["Population basis"])
            self.assertIn("not configured", row["Finding"])
            self.assertIn("units unverified", row["Window"])
        for title, metric in (
            ("Application Observability org host-hour reporting",
             "grafanacloud_org_app_o11y_billable_host_hours"),
            ("Infrastructure Observability", "grafanacloud_org_infra_o11y_billable_host_hours"),
        ):
            row = rows[title]
            self.assertIn("Org-only", row["Population basis"])
            self.assertIn(metric + "=12", row["Finding"])
            self.assertIn("not verified host hours", row["Finding"])
            self.assertIn("no per-stack sum", row["Population basis"])
            for column in ("Population stacks", "Stacks using capability", "Opportunity stacks"):
                self.assertIsNone(row[column])
        baseline = {**payload, "footprint": {
            key: entry for key, entry in payload["footprint"].items()
            if key not in REPORTING_EXPRESSIONS}}
        base_metrics, _, _ = self.compose(baseline)
        self.assertEqual(metrics, base_metrics, "reporting observations add no series")
        self.assertFalse(any(r["Capability"] == "Database Observability"
                             for r in views[coverage.ADOPTION_TARGET_VIEW]))

    def test_missing_families_partial_reads_and_org_ambiguity_stay_unknown(self):
        for key, query in REPORTING_EXPRESSIONS.items():
            outcomes = [prometheus([]), (206, prometheus([(101, 1)])),
                        RuntimeError("private-upstream"), prometheus([(101, "NaN")])]
            if key in REPORTING_ORG:
                outcomes.extend([prometheus([(101, 1)]), prometheus([(101, 1), (202, 2)])])
            else:
                outcomes.extend([prometheus([(999, 1)]), prometheus([(101, 1), (101, 2)])])
            for outcome in outcomes:
                with self.subTest(key=key, outcome=outcome):
                    payload = self.probe({query: outcome})
                    entry = payload["footprint"][key]
                    self.assertFalse(entry["available"])
                    self.assertNotIn("value", entry)
                    self.assertNotIn("values", entry)
                    self.assertNotIn("private-upstream", json.dumps(payload))
        payload = self.probe({query: prometheus([]) for query in REPORTING_EXPRESSIONS.values()})
        _, views, _ = self.compose(payload)
        rows = {r["Capability"]: r for r in views[coverage.ADOPTION_VIEW]}
        for title in ("Database Observability", "Application Observability host reporting",
                      "Application Observability org host-hour reporting", "Infrastructure Observability"):
            self.assertIsNone(rows[title]["Population stacks"])
            self.assertIn("unknown", rows[title]["Finding"].lower())
            self.assertNotIn("=0", rows[title]["Finding"])

    def test_disjoint_marker_families_deduplicate_and_org_precision_is_preserved(self):
        value = 1234567.891234567
        overrides = {query: prometheus([]) for key, query in REPORTING_EXPRESSIONS.items()
                     if key not in REPORTING_ORG}
        overrides.update({
            REPORTING_EXPRESSIONS["db_observability"]: prometheus([(101, 2)]),
            REPORTING_EXPRESSIONS["db_observability_stats"]: prometheus([(202, 1), (404, 1)]),
            REPORTING_EXPRESSIONS["app_host_v2_count"]: prometheus([(202, 1)]),
            REPORTING_EXPRESSIONS["app_billable_host_hours"]: {"status": "success", "data": {
                "resultType": "vector", "result": [{"metric": {}, "value": [0, str(value)]}]}},
        })
        payload = self.probe(overrides)
        self.assertEqual(payload["footprint"]["db_observability"]["values"], {"101": 1.0})
        _, views, _ = self.compose(payload)
        rows = {r["Capability"]: r for r in views[coverage.ADOPTION_VIEW]}
        self.assertEqual(rows["Database Observability"]["Population stacks"], 2)
        self.assertIn("grafanacloud_instance_active_dbo11y_series: unknown",
                      rows["Database Observability"]["Finding"])
        self.assertEqual(rows["Application Observability host reporting"]["Population stacks"], 1)
        self.assertIn("grafanacloud_org_app_o11y_billable_host_hours=" + str(value),
                      rows["Application Observability org host-hour reporting"]["Finding"])

    def test_reporting_rows_are_read_back_through_the_assembled_dashboard(self):
        import shutil
        import tempfile
        from bin import dashboards
        from collector.dashboards import build
        from collector.emit import s3

        _, views, meta = self.compose(self.probe())
        with tempfile.TemporaryDirectory() as tmp:
            local = pathlib.Path(tmp)
            for existing in (pathlib.Path(__file__).resolve().parent.parent /
                             "testdata" / "views").glob("*.json"):
                shutil.copyfile(existing, local / existing.name)
            (local / (coverage.ADOPTION_VIEW + ".json")).write_text(
                json.dumps(s3.view_payload(views[coverage.ADOPTION_VIEW], meta)))
            with mock.patch.object(build, "VIEWS_DIR", tmp), mock.patch.object(build, "BUCKET", "offline"):
                _, document = dashboards.assemble("coverage", "infinity-offline")
            panel = document["spec"]["elements"]["tbl_adoption"]["spec"]
            query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
            self.assertEqual(query["parser"], "backend")
            self.assertEqual(query["root_selector"], "rows")
            public = json.loads((local / query["url"].rsplit("/", 1)[-1]).read_text())
            rendered = {column["selector"] for column in query["columns"]}
            self.assertTrue({"Population basis", "Finding", "Window"}.issubset(rendered))
            rows = {r["Capability"]: r for r in public["rows"]}
            self.assertEqual(rows["Database Observability"]["Population stacks"], 2)
            for title in ("Database Observability", "Application Observability host reporting",
                          "Application Observability org host-hour reporting", "Infrastructure Observability"):
                self.assertEqual(set(rows[title]), rendered)
                self.assertIn("unverified", rows[title]["Window"])
            self.assertIn("grafanacloud_org_app_o11y_billable_host_hours=12",
                          rows["Application Observability org host-hour reporting"]["Finding"])

    def test_fresh_inventory_filters_reporting_and_org_zero_is_a_returned_observation(self):
        zero = {"status": "success", "data": {"resultType": "vector", "result": [
            {"metric": {}, "value": [0, "0"]}]}}
        payload = self.probe({REPORTING_EXPRESSIONS["infra_billable_host_hours"]: zero})
        _, views, _ = self.compose(payload, [self.stacks[2], self.stacks[3]])
        rows = {r["Capability"]: r for r in views[coverage.ADOPTION_VIEW]}
        self.assertIsNone(rows["Database Observability"]["Population stacks"])
        self.assertIn("0 of 1", rows["Database Observability"]["Finding"])
        self.assertIn("grafanacloud_org_infra_o11y_billable_host_hours=0",
                      rows["Infrastructure Observability"]["Finding"])
        self.assertIsNone(rows["Infrastructure Observability"]["Stacks using capability"])


class ComposeSeamTest(unittest.TestCase):
    def test_forwarding_changes_only_authorized_adoption_observations(self):
        fixture = json.loads((pathlib.Path(__file__).parent / "fixtures" /
                              "compose_inputs.json").read_text())
        from collector.emit.hydrate import INPUT_OWNER
        stacks = fixture["stacks"]
        inputs = {key: value for key, value in fixture.items() if key in INPUT_OWNER}
        cov = Coverage(tier="t3", total=len(stacks))
        with mock.patch.object(coverage, "build", wraps=coverage.build) as coverage_build, \
                mock.patch.object(ai, "build", wraps=ai.build) as ai_build:
            result = compose.build_all(stacks, cov, now=NOW, **inputs)
        self.assertIs(coverage_build.call_args.kwargs["dataplane"], inputs["dataplane"])
        self.assertIs(coverage_build.call_args.kwargs["adaptive_logs"], inputs["adaptive_logs"])
        self.assertIs(ai_build.call_args.kwargs["capability_adoption"], inputs["capability_adoption"])
        legacy_inputs = dict(inputs)
        legacy_inputs["capability_adoption"] = {
            key: value for key, value in inputs["capability_adoption"].items() if key != "footprint"}
        legacy = compose.build_all(stacks, cov, now=NOW, **legacy_inputs)
        # Authorized consumers now include the org Assistant summary and independent Agent view.
        # Preserve the complete metric series, unaffected views and publication metadata contract.
        self.assertEqual(result[0], legacy[0])
        self.assertEqual(result[2], legacy[2])
        self.assertEqual(set(result[1]), set(legacy[1]))
        for view in result[1]:
            if view not in {coverage.ADOPTION_VIEW, "ai_summary", "ai_agent_observability"}:
                with self.subTest(view=view):
                    self.assertEqual(result[1][view], legacy[1][view])
        observed_rows = {row["Capability"]: row for row in result[1][coverage.ADOPTION_VIEW]}
        legacy_rows = {row["Capability"]: row for row in legacy[1][coverage.ADOPTION_VIEW]}
        self.assertEqual(set(observed_rows), set(legacy_rows))
        changed = {title for title in observed_rows if observed_rows[title] != legacy_rows[title]}
        self.assertEqual(changed, {"Adaptive Traces", "Application Observability"})
        for title in changed:
            with self.subTest(capability=title):
                self.assertEqual(observed_rows[title]["Population stacks"], 2)
                self.assertEqual(observed_rows[title]["Stacks using capability"], 1)
                self.assertEqual(observed_rows[title]["Opportunity stacks"], 1)
                self.assertEqual(observed_rows[title]["Window"], "24h")
                for column in ("Population stacks", "Stacks using capability", "Opportunity stacks"):
                    self.assertIsNone(legacy_rows[title][column])
        self.assertEqual(coverage.build(stacks, inputs["signal_inventory"]), coverage.build(
            stacks, inputs["signal_inventory"], dataplane=inputs["dataplane"],
            adaptive_logs=inputs["adaptive_logs"]))
        baseline_metrics, baseline_views = ai.build(stacks, cov, inputs["assistant"])
        observed_metrics, observed_views = ai.build(
            stacks, cov, inputs["assistant"], capability_adoption=inputs["capability_adoption"])
        # The new consumer intentionally adds Agent reporting and changes the org usage summary,
        # while leaving every existing metric and unrelated Assistant view untouched.
        self.assertEqual(baseline_metrics, observed_metrics)
        for name, rows in baseline_views.items():
            if name != "ai_summary":
                self.assertEqual(rows, observed_views[name], name)
        self.assertIn("ai_agent_observability", observed_views)


class OpportunityArithmeticTest(unittest.TestCase):
    def test_populations_reuse_score_evidence_and_targets_rank_by_active_series(self):
        """Profiles and SLOs must be the same finding the score unscored, not a second census."""
        stacks = [
            {"slug": "large", "id": 101, "status": "active", "hpInstanceId": 501,
             "htInstanceId": 601, "k6OrgId": 701, "hmInstancePromCurrentActiveSeries": 1000},
            {"slug": "small", "id": 202, "status": "active", "hpInstanceId": 502,
             "htInstanceId": 602, "k6OrgId": None, "hmInstancePromCurrentActiveSeries": 10},
        ]
        signal_inventory = {
            "large": {
                "available": True, "window_end": "2026-08-25T11:00:00+00:00",
                "metric_names": [], "metric_services": ["checkout"], "log_services": [],
                "trace_services": ["checkout"], "profile_services": [], "slo_services": [],
                "legacy_metric_services": [], "clusters": [],
            },
            "small": {
                "available": True, "window_end": "2026-08-25T12:00:00+00:00",
                "metric_names": ["grafana_slo_objective"], "metric_services": ["worker"],
                "log_services": [], "trace_services": [], "profile_services": ["worker"],
                "slo_services": ["worker"], "legacy_metric_services": [], "clusters": [],
            },
        }
        usage = {
            "available": True,
            "window_start": "2026-08-24T12:00:00+00:00",
            "window_end": "2026-08-25T12:00:00+00:00",
            "values": {
                "metrics": {"101": 1000.0, "202": 10.0},
                "traces": {"101": 5.0, "202": 0.0},
                "span_metrics": {"101": 0.0},
                "service_graphs": {"101": 1.0},
                "native_histograms": {"101": 0.0, "202": 1.0},
                "exemplars": {"101": 0.0, "202": 0.0},
                "irm_oncall": {"101": 0.0},
                "k6": {"101": 0.0},
                "frontend_observability": {"101": 0.0},
                "synthetic_monitoring": {"101": 0.0},
                "kubernetes": {"101": 0.0},
                "knowledge_graph": {"101": 0.0},
                "pdc": {"101": 0.0},
            },
        }

        metrics, views = coverage.build(stacks, signal_inventory, capability_adoption=usage)
        rows = {row["Capability"]: row for row in views[coverage.ADOPTION_VIEW]}
        self.assertEqual(rows["Continuous profiling"]["Population stacks"], 2)
        self.assertEqual(rows["Continuous profiling"]["Stacks using capability"], 1)
        self.assertEqual(rows["Continuous profiling"]["Opportunity stacks"], 1)
        self.assertEqual(rows["SLOs"]["Stacks using capability"], 1)
        self.assertEqual(rows["Span metrics"]["Population stacks"], 1,
                         "derived trace features use the matched trace-ingesting population")
        self.assertEqual(rows["Continuous profiling"]["Last seen"],
                         "2026-08-25T11:00:00+00:00")
        self.assertEqual(rows["SLOs"]["Last seen"], "2026-08-25T11:00:00+00:00")

        targets = views[coverage.ADOPTION_TARGET_VIEW]
        self.assertEqual(targets[0][" Stack"], "large")
        self.assertTrue(all(
            targets[i]["Active series"] >= targets[i + 1]["Active series"]
            for i in range(len(targets) - 1)
        ))

        gaps = {
            labels["kind"]: value for name, labels, value in metrics
            if name == "gcinsight_coverage_capability_gap"
        }
        self.assertEqual(set(gaps), set(coverage.ADOPTION_CAPABILITIES))
        self.assertEqual(gaps["service_graphs"], 0.0,
                         "a measured zero gap is deliberately emitted on this adoption surface")


if __name__ == "__main__":
    unittest.main()
