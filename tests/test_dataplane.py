"""Dataplane contracts whose absence can turn unknown savings into a confident zero."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from collector.sources import dataplane


def _record(metric: str, current: int | None, recommended: int | None) -> dict[str, object]:
    out: dict[str, object] = {"metric": metric, "recommended_action": "add"}
    if current is not None:
        out["current_series_count"] = current
    if recommended is not None:
        out["recommended_series_count"] = recommended
    return out


class RecommendationCoverageTest(unittest.TestCase):
    def test_successful_empty_payload_is_a_complete_zero(self):
        out = dataplane.summarise_recommendations([])

        self.assertEqual(out["recommendation_records_total"], 0)
        self.assertEqual(out["recommendation_records_with_series_counts"], 0)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 0)
        self.assertTrue(out["series_counts_complete"])
        self.assertEqual(out["remediable_series"], 0)

    def test_partial_verbose_payload_reports_its_missing_counts(self):
        out = dataplane.summarise_recommendations([
            _record("complete", 100, 10),
            _record("default-shape", None, None),
        ])

        self.assertEqual(out["recommendation_records_total"], 2)
        self.assertEqual(out["recommendation_records_with_series_counts"], 1)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 1)
        self.assertFalse(out["series_counts_complete"])
        self.assertFalse(out["verbose"], "legacy consumers must not mistake partial counts for verbose")

    def test_savings_record_without_metric_identity_withholds_savings(self):
        out = dataplane.summarise_recommendations([
            _record("valid", 200, 20),
            _record("", 100, 10),
        ])

        self.assertEqual(out["recommendation_records_missing_metric_identity"], 1)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 0)
        self.assertFalse(out["series_counts_complete"])
        self.assertFalse(out["verbose"])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["remediable_series_unused"], 0)
        self.assertEqual(out["sample_recommendations"], [])

    def test_duplicate_metric_identity_withholds_savings(self):
        out = dataplane.summarise_recommendations([
            _record("duplicate", 100, 10),
            _record("duplicate", 80, 20),
        ])

        self.assertEqual(out["recommendation_records_duplicate_metric_identity"], 1)
        self.assertFalse(out["series_counts_complete"])
        self.assertFalse(out["verbose"])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["remediable_series_unused"], 0)
        self.assertEqual(out["sample_recommendations"], [])

    def test_invalid_or_negative_series_counts_withhold_all_savings(self):
        for current, recommended in ((-10, -20), (50, -20), (10.5, 2), ("bad", 2)):
            with self.subTest(current=current, recommended=recommended):
                out = dataplane.summarise_recommendations([
                    _record("valid", 100, 10),
                    _record("invalid", current, recommended),
                ])

                self.assertEqual(out["recommendation_records_invalid_series_counts"], 1)
                self.assertFalse(out["series_counts_complete"])
                self.assertFalse(out["verbose"])
                self.assertEqual(out["remediable_series"], 0)
                self.assertEqual(out["remediable_series_unused"], 0)
                self.assertEqual(out["sample_recommendations"], [])

    def test_failed_recommendations_request_is_not_a_complete_empty_payload(self):
        class Response:
            def __init__(self, ok: bool, body: object, status: int) -> None:
                self.ok = ok
                self._body = body
                self.status = status

            def json(self) -> object:
                return self._body

        class Client:
            def get(self, url: str, basic: object = None) -> Response:
                if url.endswith("/aggregations/rules"):
                    return Response(True, [], 200)
                return Response(False, {}, 503)

        stack = {
            "slug": "one",
            "hmInstancePromUrl": "https://prom.example",
            "hmInstancePromId": "1",
        }
        out = dataplane.adaptive_metrics(Client(), stack, "cap")

        self.assertFalse(out["recommendations_available"])
        self.assertFalse(out["series_counts_complete"])

    def test_invalid_json_is_unavailable_instead_of_raising(self):
        class Response:
            ok = True
            status = 200

            def json(self):
                raise ValueError("bad json")

        class Client:
            def get(self, url: str, basic: object = None) -> Response:
                return Response()

        stack = {"slug": "one", "hmInstancePromUrl": "https://prom.example",
                 "hmInstancePromId": "1"}
        out = dataplane.adaptive_metrics(Client(), stack, "cap")
        self.assertFalse(out["available"])
        self.assertFalse(out["series_counts_complete"])

    def test_invalid_usage_counts_make_the_saving_incomplete_not_unused(self):
        record = _record("bad-usage", 100, 10)
        record["usages_in_rules"] = "not-a-count"
        out = dataplane.summarise_recommendations([record])
        self.assertFalse(out["series_counts_complete"])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["remediable_series_unused"], 0)

    def test_malformed_recommendations_payload_is_not_a_complete_empty_payload(self):
        class Response:
            ok = True
            status = 200

            def __init__(self, body: object) -> None:
                self._body = body

            def json(self) -> object:
                return self._body

        class Client:
            def get(self, url: str, basic: object = None) -> Response:
                return Response([] if url.endswith("/aggregations/rules") else {"items": []})

        stack = {
            "slug": "one",
            "hmInstancePromUrl": "https://prom.example",
            "hmInstancePromId": "1",
        }
        out = dataplane.adaptive_metrics(Client(), stack, "cap")

        self.assertFalse(out["recommendations_available"])
        self.assertFalse(out["series_counts_complete"])


class ConnectRpcTest(unittest.TestCase):
    def test_read_payload_is_sent_without_relaxing_the_path_guard(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"names":[]}'
        with mock.patch("urllib.request.urlopen", return_value=response) as open_url:
            out = dataplane._connect_rpc(
                "https://profiles.example/querier.v1.QuerierService/LabelValues",
                "123", "cap", payload={"name": "service_name", "start": 1, "end": 2},
            )
        self.assertEqual(out, {"names": []})
        request = open_url.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"name": "service_name", "start": 1, "end": 2})

        with self.assertRaises(ValueError):
            dataplane._connect_rpc(
                "https://profiles.example/write.v1.WriterService/Push", "123", "cap",
                payload={"series": []},
            )


if __name__ == "__main__":
    unittest.main()
