"""Exercise actual outgoing request objects, including mixed-signal collectors."""
import json
from unittest import mock
from urllib.parse import urlsplit

import pytest

from collector.httpclient import ReadOnlyClient, Response
from collector.sources import (
    label_inventory, label_risk, loki_config, loki_volume, rule_inventory,
    signal_inventory, usage_insights,
)

STACK = {"slug": "synthetic", "status": "active"}
for signal, (host, tenant, _) in label_risk.SIGNALS.items():
    STACK.update({host: f"https://{signal}.example", tenant: "123"})
STACK.update(amInstanceUrl="https://alertmanager.example", amInstanceId="123")
HEADER = "x-loki-disable-pipeline-wrappers"


@pytest.mark.parametrize("source", [label_risk, label_inventory])
def test_label_reads_protect_only_logs(source):
    requests = []

    def send(req, timeout):
        requests.append(req)
        return Response(403, b"", req.full_url)

    client = ReadOnlyClient(transport=send, max_attempts=1, deadline=60)
    for signal in label_risk.SIGNALS:
        for key in (None, ("", "service_name")):
            with pytest.raises(ValueError):
                if source is label_risk:
                    source._read(client, STACK, "cap", signal, 1, 2, source.Bounds(), key, send)
                else:
                    source._read(client, STACK, "cap", signal, 1, 2, source.Bounds(), send, key)
    assert len(requests) == 8
    for req in requests:
        headers = dict((k.lower(), v) for k, v in req.header_items())
        assert headers.get(HEADER) == ("true" if urlsplit(req.full_url).hostname == "logs.example" else None)
        assert "authorization" in headers


def test_other_native_loki_routes_and_non_loki_rules():
    requests = []

    def send(req, timeout):
        requests.append(req)
        return Response(403, b"", req.full_url)

    client = ReadOnlyClient(transport=send, max_attempts=1, deadline=60)
    payload = {"inputs": {}, "state": "partial", "reason": "missing_input"}
    label_inventory._loki_inputs(client, STACK, "cap", 1, 2, label_inventory.Bounds(), payload)
    label_inventory._loki_config_inputs(client, STACK, "cap", label_inventory.Bounds(), payload)
    loki_config._limits_record(client, STACK, "cap")
    loki_volume._probe(client, STACK, "cap")
    for family in ("loki", "mimir", "alertmanager"):
        with pytest.raises(rule_inventory._Unavailable):
            rule_inventory._read(client, STACK, "cap", family, 0)
    assert len(requests) == 7
    for req in requests:
        headers = {k.lower(): v for k, v in req.header_items()}
        assert headers.get(HEADER) == ("true" if urlsplit(req.full_url).hostname == "logs.example" else None)
        assert req.get_method() == "GET"
        assert "authorization" in headers


def test_signal_inventory_scopes_header_to_logs():
    requests = []

    def send(req, timeout):
        requests.append(req)
        body = {"status": "success", "data": []}
        if urlsplit(req.full_url).hostname == "traces.example":
            body = {"tagValues": []}
        return Response(200, json.dumps(body).encode(), req.full_url)

    client = ReadOnlyClient(transport=send, max_attempts=1, deadline=60)
    with mock.patch.object(signal_inventory.dataplane, "_connect_rpc", return_value=Response(200, b'{"names":[]}', "")):
        signal_inventory.probe_stack(client, STACK, "cap")
    assert any(urlsplit(req.full_url).hostname == "logs.example" for req in requests)
    assert any(urlsplit(req.full_url).hostname == "metrics.example" for req in requests)
    for req in requests:
        assert dict((k.lower(), v) for k, v in req.header_items()).get(HEADER) == (
            "true" if urlsplit(req.full_url).hostname == "logs.example" else None)


@pytest.mark.parametrize("shared_client", [True, False])
def test_usage_insights_real_request_and_instance_guard(shared_client):
    requests = []
    body = {"status": "success", "data": {"resultType": "vector", "result": []}}

    def send(req, timeout):
        requests.append(req)
        return Response(200, json.dumps(body).encode(), req.full_url)

    client = ReadOnlyClient(transport=send, max_attempts=1, deadline=60) if shared_client else None
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(body).encode()

    def urlopen(req, timeout):
        requests.append(req)
        return response

    with mock.patch.object(usage_insights.urllib.request, "urlopen", side_effect=urlopen):
        expr = usage_insights.SCALARS["views"] % {"sel": usage_insights.selector(instance_id="123")}
        assert usage_insights._query("https://grafana.example", "token", expr,
                                    expected_instance_id="123", client=client) == body
        with pytest.raises(usage_insights.RegionalQueryRefused):
            usage_insights._query("https://grafana.example", "token", '{job="unscoped"}',
                                  expected_instance_id="123", client=client)
    assert len(requests) == 1
    headers = {k.lower(): v for k, v in requests[0].header_items()}
    assert headers[HEADER] == "true"
    assert headers["authorization"] == "Bearer token"
    assert requests[0].get_method() == "GET"
