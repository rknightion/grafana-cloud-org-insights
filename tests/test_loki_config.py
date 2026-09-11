"""Contracts for the read-only Loki retention source."""

from __future__ import annotations

import unittest

from collector.sources import loki_config


class Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self.payload = payload

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> object:
        return self.payload


class Client:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> Response:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


STACK = {
    "slug": "alpha",
    "url": "https://alpha.example",
    "hlInstanceUrl": "https://logs.example",
    "hlInstanceId": "101",
}


class LokiConfigSourceTest(unittest.TestCase):
    def test_reads_effective_limits_with_loki_basic_auth_and_change_requests_with_reader(self):
        client = Client([
            Response(200, {"retention_stream": [
                {"period": "31d", "priority": 4, "selector": "{service=\"api\"}"},
            ]}),
            Response(200, {"items": []}),
        ])

        out = loki_config.probe_stack(client, STACK, "cap-token", "reader-token")

        self.assertTrue(out["limits"]["available"])
        self.assertEqual(out["limits"]["retention_stream"], [{
            "period": "31d", "priority": 4, "selector": "{service=\"api\"}",
        }])
        self.assertTrue(out["change_requests"]["available"])
        self.assertEqual(out["change_requests"]["items"], [])
        limits_url, limits_kwargs = client.calls[0]
        self.assertEqual(limits_url, "https://logs.example/config/tenant/v1/limits")
        self.assertEqual(limits_kwargs["basic"], ("101", "cap-token"))
        requests_url, requests_kwargs = client.calls[1]
        self.assertEqual(requests_url, (
            "https://alpha.example/api/plugins/grafana-dbcfg-app/resources/v1/"
            "lokiconfigretentions"
        ))
        self.assertEqual(requests_kwargs["bearer"], "reader-token")

    def test_change_request_parser_preserves_every_non_shared_spec_field(self):
        client = Client([
            Response(200, {}),
            Response(200, {"items": [{
                "spec": {
                    "author": "operator",
                    "message": "retain longer",
                    "request_timestamp": "2026-01-01T00:00:00Z",
                    "limit": {"period": "31d"},
                    "future_extension": ["keep", "verbatim"],
                },
                "status": {
                    "status": "pending",
                    "processed_timestamp": None,
                    "pr_info": {"number": 42},
                },
            }]}),
        ])

        request = loki_config.probe_stack(client, STACK, "cap", "reader")["change_requests"]["items"][0]

        self.assertEqual(request["author"], "operator")
        self.assertEqual(request["message"], "retain longer")
        self.assertEqual(request["request_timestamp"], "2026-01-01T00:00:00Z")
        self.assertEqual(request["limit"], {"period": "31d"})
        self.assertEqual(request["opaque"], {
            "limit": {"period": "31d"},
            "future_extension": ["keep", "verbatim"],
        })
        self.assertEqual(request["status"], "pending")
        self.assertEqual(request["pr_number"], 42)

    def test_non_200_limits_is_unreadable_and_does_not_turn_into_zero_streams(self):
        client = Client([Response(503, {}), Response(200, {"items": []})])

        out = loki_config.probe_stack(client, STACK, "cap", "reader")

        self.assertFalse(out["limits"]["available"])
        self.assertEqual(out["limits"]["state"], loki_config.HTTP_ERROR)
        self.assertNotIn("retention_stream", out["limits"])
        self.assertTrue(out["change_requests"]["available"], "the two reads are independent")

    def test_non_200_request_route_is_unreadable_and_has_no_items_to_publish(self):
        client = Client([Response(200, {"retention_stream": []}), Response(403, {})])

        out = loki_config.probe_stack(client, STACK, "cap", "reader")

        self.assertTrue(out["limits"]["available"])
        self.assertFalse(out["change_requests"]["available"])
        self.assertEqual(out["change_requests"]["state"], loki_config.FORBIDDEN)
        self.assertNotIn("items", out["change_requests"])

    def test_missing_reader_token_only_withholds_change_requests(self):
        client = Client([Response(200, {"retention_stream": []})])

        out = loki_config.probe_stack(client, STACK, "cap", "")

        self.assertTrue(out["limits"]["available"])
        self.assertFalse(out["change_requests"]["available"])
        self.assertEqual(out["change_requests"]["state"], loki_config.NO_CREDENTIAL)
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
