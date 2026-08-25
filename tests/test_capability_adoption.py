"""Capability opportunity input and Pillar K denominator decisions.

These tests pin the parts most likely to make an adoption gap look better than it is: using an
instantaneous rate, iterating a stale payload instead of live inventory, or turning an unmeasured
absence into a measured zero.
"""

from __future__ import annotations

import datetime as dt
import unittest

from collector.httpclient import Response
from collector.pillars import coverage
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
        body = self.by_query[params["query"]]
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
        self.assertEqual(len(client.calls), len(source.QUERIES))
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
        self.assertIn("metrics: transport retries exhausted", result["detail"])


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
