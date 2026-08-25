"""Contracts for the four-signal observed-estate label inventory."""

from __future__ import annotations

import datetime as dt
import json
import unittest
from unittest import mock

from collector.httpclient import Response
from collector.sources import signal_inventory as source


NOW = dt.datetime(2026, 8, 24, 12, 34, 56, tzinfo=dt.timezone.utc)
START_SECONDS = int((NOW - dt.timedelta(hours=24)).timestamp())
END_SECONDS = int(NOW.timestamp())


class Client:
    def __init__(self, responses: dict[str, tuple[int, object]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object], tuple[str, str]]] = []

    def get(self, url: str, *, params: dict[str, object], basic: tuple[str, str]) -> Response:
        self.calls.append((url, params, basic))
        lookup = f"{url}?slo" if params.get("match[]") else url
        status, body = self.responses[lookup]
        return Response(status, json.dumps(body).encode(), url)


STACK = {
    "slug": "example",
    "status": "active",
    "hmInstancePromUrl": "https://metrics.example",
    "hmInstancePromId": "11",
    "hlInstanceUrl": "https://logs.example",
    "hlInstanceId": "22",
    "htInstanceUrl": "https://traces.example",
    "htInstanceId": "33",
    "hpInstanceUrl": "https://profiles.example",
    "hpInstanceId": "44",
}


def responses(*, logs: object | None = None) -> dict[str, tuple[int, object]]:
    return {
        "https://metrics.example/api/prom/api/v1/label/__name__/values": (
            200, {"status": "success", "data": ["up", "node_uname_info"]},
        ),
        "https://logs.example/loki/api/v1/label/service_name/values": (
            200, {"status": "success", "data": [] if logs is None else logs},
        ),
        "https://metrics.example/api/prom/api/v1/label/service_name/values": (
            200, {"status": "success", "data": ["checkout"]},
        ),
        "https://metrics.example/api/prom/api/v1/label/service_name/values?slo": (
            200, {"status": "success", "data": ["checkout"]},
        ),
        "https://metrics.example/api/prom/api/v1/label/service/values": (
            200, {"status": "success", "data": ["legacy-api"]},
        ),
        "https://metrics.example/api/prom/api/v1/label/cluster/values": (
            200, {"status": "success", "data": ["compute-a"]},
        ),
        "https://traces.example/tempo/api/v2/search/tag/resource.service.name/values": (
            200, {"tagValues": [{"type": "string", "value": "checkout"}]},
        ),
    }


class SignalInventoryWindowTest(unittest.TestCase):
    def test_all_four_calls_have_the_verified_paths_auth_and_explicit_window(self):
        client = Client(responses())
        rpc_calls: list[tuple[str, str, str, dict[str, object]]] = []

        def rpc(url: str, user: str, cap: str, *, payload: dict[str, object]):
            rpc_calls.append((url, user, cap, payload))
            return {"names": []}

        with mock.patch.object(source.dataplane, "_connect_rpc", side_effect=rpc):
            out = source.probe_stack(client, STACK, "cap", now=NOW)

        self.assertTrue(out["available"])
        self.assertEqual(out["metric_names"], ["node_uname_info", "up"])
        self.assertEqual(out["metric_services"], ["checkout"])
        self.assertEqual(out["slo_services"], ["checkout"])
        self.assertEqual(out["legacy_metric_services"], ["legacy-api"])
        self.assertEqual(out["clusters"], ["compute-a"])
        self.assertEqual(out["log_services"], [])
        self.assertEqual(out["trace_services"], ["checkout"])
        self.assertEqual(out["profile_services"], [])
        self.assertEqual(out["window_start"], (NOW - dt.timedelta(hours=24)).isoformat())
        self.assertEqual(out["window_end"], NOW.isoformat())

        by_call = {(url, str(params.get("match[]") or "")): (params, basic)
                   for url, params, basic in client.calls}
        by_url = {url: value for (url, matcher), value in by_call.items() if not matcher}
        mimir = by_url["https://metrics.example/api/prom/api/v1/label/__name__/values"]
        self.assertEqual(mimir[0], {
            "start": START_SECONDS, "end": END_SECONDS, "limit": source.METRIC_NAME_LIMIT,
        })
        self.assertEqual(mimir[1], ("11", "cap"))
        for label in ("service_name", "service", "cluster"):
            params, basic = by_url[
                f"https://metrics.example/api/prom/api/v1/label/{label}/values"
            ]
            self.assertEqual(params, {
                "start": START_SECONDS, "end": END_SECONDS, "limit": source.LABEL_VALUE_LIMIT,
            })
            self.assertEqual(basic, ("11", "cap"))
        slo_params, slo_basic = by_call[(
            "https://metrics.example/api/prom/api/v1/label/service_name/values",
            '{grafana_slo_uuid!="",service_name!=""}',
        )]
        self.assertEqual(slo_params, {
            "start": START_SECONDS,
            "end": END_SECONDS,
            "limit": source.LABEL_VALUE_LIMIT,
            "match[]": '{grafana_slo_uuid!="",service_name!=""}',
        })
        self.assertEqual(slo_basic, ("11", "cap"))
        self.assertEqual(
            by_url["https://logs.example/loki/api/v1/label/service_name/values"],
            ({"start": START_SECONDS * 1_000_000_000, "end": END_SECONDS * 1_000_000_000},
             ("22", "cap")),
        )
        self.assertEqual(
            by_url[
                "https://traces.example/tempo/api/v2/search/tag/"
                "resource.service.name/values"
            ],
            ({"start": START_SECONDS, "end": END_SECONDS}, ("33", "cap")),
        )
        self.assertEqual(rpc_calls, [(
            "https://profiles.example/querier.v1.QuerierService/LabelValues",
            "44", "cap",
            {"name": "service_name", "start": START_SECONDS * 1000, "end": END_SECONDS * 1000},
        )])

    def test_successful_empty_lists_are_measured_absence(self):
        empty = responses()
        empty["https://metrics.example/api/prom/api/v1/label/__name__/values"] = (
            200, {"status": "success", "data": []},
        )
        empty["https://metrics.example/api/prom/api/v1/label/service_name/values?slo"] = (
            200, {"status": "success", "data": []},
        )
        empty[
            "https://traces.example/tempo/api/v2/search/tag/resource.service.name/values"
        ] = (200, {"tagValues": []})
        with mock.patch.object(source.dataplane, "_connect_rpc", return_value={"names": []}):
            out = source.probe_stack(Client(empty), STACK, "cap", now=NOW)

        self.assertEqual(out["available"], True)
        for key in (
            "metric_names", "slo_services", "log_services", "trace_services", "profile_services",
        ):
            self.assertEqual(out[key], [])

    def test_empty_connect_object_is_measured_profile_absence(self):
        with mock.patch.object(source.dataplane, "_connect_rpc", return_value={}):
            out = source.probe_stack(Client(responses()), STACK, "cap", now=NOW)

        self.assertEqual(out["available"], True)
        self.assertEqual(out["profile_services"], [])

    def test_failed_slo_lookup_withholds_the_atomic_stack_record(self):
        failed = responses()
        failed["https://metrics.example/api/prom/api/v1/label/service_name/values?slo"] = (
            503, {"status": "error"},
        )
        with mock.patch.object(source.dataplane, "_connect_rpc") as rpc:
            out = source.probe_stack(Client(failed), STACK, "cap", now=NOW)
        self.assertEqual(out, {
            "slug": "example", "available": False, "signal": "metrics",
            "reason": "http_5xx", "http": 503,
        })
        rpc.assert_not_called()

    def test_tempo_extracts_object_values_and_rejects_a_string_list(self):
        bad = responses()
        path = "https://traces.example/tempo/api/v2/search/tag/resource.service.name/values"
        bad[path] = (200, {"tagValues": ["checkout"]})
        with mock.patch.object(source.dataplane, "_connect_rpc", return_value={"names": []}):
            out = source.probe_stack(Client(bad), STACK, "cap", now=NOW)
        self.assertEqual(out, {
            "slug": "example", "available": False, "signal": "traces",
            "reason": "invalid_response",
        })

    def test_a_200_error_envelope_is_not_a_measured_empty_list(self):
        bad = responses()
        path = "https://metrics.example/api/prom/api/v1/label/__name__/values"
        bad[path] = (200, {"status": "error", "data": []})
        out = source.probe_stack(Client(bad), STACK, "cap", now=NOW)
        self.assertEqual(out["reason"], "invalid_response")
        self.assertFalse(out["available"])

        bad[path] = (200, {"data": []})
        out = source.probe_stack(Client(bad), STACK, "cap", now=NOW)
        self.assertEqual(out["reason"], "invalid_response")

    def test_a_response_reaching_the_bound_is_withheld_as_possibly_truncated(self):
        bounded = responses()
        path = "https://metrics.example/api/prom/api/v1/label/service_name/values"
        bounded[path] = (200, {"status": "success", "data": ["a", "b"]})
        with mock.patch.object(source, "LABEL_VALUE_LIMIT", 2):
            out = source.probe_stack(Client(bounded), STACK, "cap", now=NOW)
        self.assertEqual(out, {
            "slug": "example", "available": False, "signal": "metrics", "reason": "truncated",
        })


class SignalInventoryFailureTest(unittest.TestCase):
    def test_one_signal_failure_makes_the_whole_stack_row_absent(self):
        failed = responses()
        path = "https://logs.example/loki/api/v1/label/service_name/values"
        failed[path] = (503, {"status": "error"})
        with mock.patch.object(source.dataplane, "_connect_rpc") as rpc:
            out = source.probe_stack(Client(failed), STACK, "cap", now=NOW)

        self.assertEqual(out, {
            "slug": "example", "available": False, "signal": "logs",
            "reason": "http_5xx", "http": 503,
        })
        self.assertNotIn("metric_names", out, "a partial row must not survive a later signal failure")
        rpc.assert_not_called()

    def test_http_failures_use_the_closed_reason_vocabulary(self):
        cases = {401: "auth", 403: "auth", 404: "missing_endpoint", 429: "http_429",
                 500: "http_5xx", 599: "http_5xx", 418: "http_other"}
        path = "https://metrics.example/api/prom/api/v1/label/__name__/values"
        for status, reason in cases.items():
            with self.subTest(status=status):
                failed = responses()
                failed[path] = (status, {})
                out = source.probe_stack(Client(failed), STACK, "cap", now=NOW)
                self.assertEqual(out["reason"], reason)
                self.assertIn(out["reason"], source.FAILURE_REASONS)

    def test_missing_endpoint_and_timeout_are_closed_failures(self):
        missing = dict(STACK)
        missing.pop("hlInstanceUrl")
        out = source.probe_stack(Client(responses()), missing, "cap", now=NOW)
        self.assertEqual(out["reason"], "missing_endpoint")
        self.assertEqual(out["signal"], "logs")

        class TimeoutClient(Client):
            def get(self, *args, **kwargs):
                raise TimeoutError("late")

        out = source.probe_stack(TimeoutClient(responses()), STACK, "cap", now=NOW)
        self.assertEqual(out["reason"], "timeout")

    def test_probe_all_iterates_only_the_supplied_live_inventory(self):
        stacks = [STACK, {**STACK, "slug": "paused", "status": "paused"}]
        with mock.patch.object(source, "probe_stack", return_value={
            "slug": "example", "available": True,
        }) as probe:
            out = source.probe_all(Client({}), stacks, "cap", concurrency=2, now=NOW)
        self.assertEqual(out, {"example": {"slug": "example", "available": True}})
        probe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
