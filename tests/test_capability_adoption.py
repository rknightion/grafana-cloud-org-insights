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
        self.assertEqual(len(client.calls), len(source.QUERIES) + 4)
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

    def test_frozen_payload_queries_windows_live_ids_and_minimization(self):
        body = prometheus([(101, 0), (202, 3), (999, 8)])
        for row in body["data"]["result"]:
            row["metric"].update({"org_id": "private-upstream", "policy": "private-upstream"})
        result = self.probe({FOOTPRINT_EXPRESSIONS["adaptive_traces"]: body})
        self.assertTrue(result["available"])
        self.assertEqual(result["values"], {key: {"101": 7.0} for key in source.QUERIES})
        footprint = result["footprint"]
        self.assertEqual(set(footprint), set(FOOTPRINT_EXPRESSIONS) | {"db_observability"})
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
            "available": False, "reason": "no_verified_stack_source", "basis": "per_stack_unknown",
            "window": None, "window_start": None, "window_end": None,
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
                         set(FOOTPRINT_EXPRESSIONS.values()))
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
        for key, query in FOOTPRINT_EXPRESSIONS.items():
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
        # The source seam now has an authorized consumer: only the adoption view may change.
        # Preserve the complete metric series, unaffected views and publication metadata contract.
        self.assertEqual(result[0], legacy[0])
        self.assertEqual(result[2], legacy[2])
        self.assertEqual(set(result[1]), set(legacy[1]))
        for view in result[1]:
            if view != coverage.ADOPTION_VIEW:
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
        self.assertEqual(ai.build(stacks, cov, inputs["assistant"]), ai.build(
            stacks, cov, inputs["assistant"], capability_adoption=inputs["capability_adoption"]))


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
