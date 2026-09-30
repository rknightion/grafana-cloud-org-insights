"""Captured SLO list contracts through the real GET client and compose boundary."""
import http.client
from email.message import Message
import io
import json
import urllib.request
import urllib.response

import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import scan

from collector.coverage import Coverage
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose
from collector.sources import slo

FIXTURE = Path(__file__).parent / "fixtures" / "slo_list.json"
STACK = {"slug": "obs-hub", "url": "https://inventory.example.test"}


def client_for(body, status=200):
    def transport(request, timeout):
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + slo.PATH
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


def test_captured_list_minimized_at_source_and_view():
    body = json.loads(FIXTURE.read_text())
    result = slo.fetch_slo_inventory(client_for(body), STACK, "synthetic-token")
    assert result["count"] == 3
    assert result["configured_alerting_count"] == 3
    assert result["source_counts"] == {"metrics": 2, "knowledge_graph": 1, "unknown": 0}
    assert result["status_counts"] == {"created": 2, "updated": 1, "unknown": 0}
    cov = Coverage(tier="t2", total=1)
    metrics, views = compose.build_all([STACK], cov, slo_inventory={"obs-hub": result})
    assert not any("slo" in name for name, _, _ in metrics)
    row = views["coverage_slo_inventory"][0]
    assert row["SLO definitions"] == 3
    assert row["Configured alerting"] == 3
    assert row["Knowledge graph source"] == 1
    encoded = json.dumps({"input": result, "views": views["coverage_slo_inventory"]})
    for field in ("uuid", "name", "query", "labels", "annotations", "objectives", "uid"):
        assert f'"{field}"' not in encoded
    assert "synthetic-sensitive" not in encoded


def test_api_provenance_is_not_metrics_and_unknowns_are_bounded():
    body = {"slos": [
        {"readOnly": {"provenance": "api"}, "alerting": {}},
        {"readOnly": {"provenance": "synthetic-sensitive", "status": {"type": "synthetic-sensitive"},
                      "sourceDatasource": {"type": "synthetic-sensitive"}}},
        {"readOnly": {"provenance": "asserts"}, "alerting": {"fastBurn": {}}},
    ]}
    result = slo.fetch_slo_inventory(client_for(body), STACK, "synthetic-token")
    assert result["source_counts"] == {"metrics": 0, "knowledge_graph": 1, "unknown": 2}
    assert result["configured_alerting_count"] == 1
    assert result["status_counts"]["unknown"] == 3
    assert "synthetic-sensitive" not in json.dumps(result)


def test_empty_measured_vs_unreadable_and_inventory_left_join():
    empty = slo.fetch_slo_inventory(client_for({"slos": []}), STACK, "synthetic-token")
    assert empty["count"] == 0
    for body, status in (({}, 200), ({"slos": [None]}, 200), ({"slos": []}, 403),
                         ({"slos": []}, 404)):
        assert slo.fetch_slo_inventory(client_for(body, status), STACK, "synthetic-token") is None
    records = {"obs-hub": empty, "departed": {**empty, "count": 99}}
    _, views = compose.build_all([STACK], Coverage(tier="t2", total=1), slo_inventory=records)
    assert len(views["coverage_slo_inventory"]) == 1
    assert views["coverage_slo_inventory"][0]["SLO definitions"] == 0
    _, absent = compose.build_all([STACK], Coverage(tier="t2", total=1), slo_inventory={})
    assert "coverage_slo_inventory" not in absent
    assert slo.probe_all(client_for({"slos": []}), [STACK], {}) == {
        "obs-hub": {"available": False, "reason": "no_credential"}}


def test_provisioning_policy_disables_slo_reads_without_masking_enabled_failures():
    cfg = SimpleNamespace(concurrency=1)
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}):
        with mock.patch.object(scan.credentials, "load_all") as credentials:
            assert scan.gather_slo_inventory(None, cfg, [STACK]) == ({}, [])
            credentials.assert_not_called()
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "slo"}):
        with mock.patch.object(scan.credentials, "load_all", return_value={
            "obs-hub": {"token": "synthetic-token"}
        }):
            data, errors = scan.gather_slo_inventory(client_for({}, 403), cfg, [STACK])
            assert data == {"obs-hub": {"available": False, "reason": "unreadable"}}
            assert errors == ["obs-hub: slo_inventory: unreadable"]
            report = scan.source_report(1, data, available=lambda r: r.get("available"), errors=errors)
            assert not report["healthy"]


class WireBody(io.BytesIO):
    def __init__(self, body, *, forbid=False, tick=None):
        super().__init__(body)
        self.forbid = forbid
        self.tick = tick
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        assert not self.forbid, "forbidden response body read"
        if self.tick:
            self.tick()
        return super().read(size)

    def read1(self, size=-1):
        return self.read(size)


def wire(monkeypatch, responder):
    """Fake only HTTPS I/O; keep urllib's real status/redirect machinery."""
    calls = []

    def open_https(handler, connection, req, **kwargs):
        calls.append(req)
        status, headers, body = responder(req)
        message = Message()
        for key, value in headers.items():
            message[key] = value
        result = urllib.response.addinfourl(body, message, req.full_url, status)
        result.msg = "synthetic"
        return result

    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", open_https)
    # The legacy urlopen global opener must also use the fake network edge.
    monkeypatch.setattr(urllib.request, "_opener", None)
    return calls


@pytest.mark.parametrize("location", ["https://attacker.example.test/capture",
                                      STACK["url"] + "/off-route"])
def test_fixed_readers_never_follow_real_urllib_redirects(monkeypatch, location):
    from collector.sources import adaptive_traces
    calls = wire(monkeypatch, lambda req: (
        (200, {}, WireBody(b'{}')) if req.full_url == location else
        (302, {"Location": location}, WireBody(b""))))
    client = ReadOnlyClient(max_attempts=1)
    assert slo.fetch_slo_inventory(client, STACK, "synthetic-token") is None
    result = adaptive_traces.probe_stack(client, STACK, "synthetic-token")
    assert not result["available"]
    assert len(calls) == 5
    assert all(req.full_url != location for req in calls)


@pytest.mark.parametrize("url", ["http://inventory.example.test", "https://u:p@host.test",
                                   "https://host.test/?query=x", "https://host.test/#x"])
def test_slo_rejects_unsafe_origin_before_transport(url):
    calls = []
    client = ReadOnlyClient(transport=lambda *args: calls.append(args), max_attempts=1)
    assert slo.fetch_slo_inventory(client, {**STACK, "url": url}, "synthetic-token") is None
    assert calls == []


@pytest.mark.parametrize("status", [200, 404, 500])
def test_health_status_only_real_transport_and_independent_domains(monkeypatch, status):
    from collector.sources import adaptive_traces
    health = WireBody(b'not JSON and must not be read', forbid=True)
    def respond(req):
        resource = req.full_url.rsplit("/", 1)[-1]
        return (status, {}, health) if resource == "health" else (
            200, {}, WireBody(b'{}' if resource == "config" else b'[]'))
    calls = wire(monkeypatch, respond)
    result = adaptive_traces.probe_stack(ReadOnlyClient(max_attempts=1), STACK, "synthetic-token")
    assert calls[0].full_url.endswith("/health")
    assert health.reads == 0
    assert result["available"] and result["policy_count"] == 0
    assert result["health_state"] == {200: "ok", 404: "not_found_404", 500: "http_error"}[status]


@pytest.mark.parametrize("field", ["apiKey", "api_key", "grafanaApiKey", "clientSecret",
                                    "password", "authorization", "accessToken"])
def test_known_credential_schema_is_deferred_not_counted(field):
    result = slo.probe_all(client_for({"slos": [{"nested": {field: "synthetic"}}]}),
                           [STACK], {"obs-hub": {"token": "synthetic-token"}})
    assert result == {"obs-hub": {"available": False, "reason": "unsafe_schema"}}


def test_oversize_and_trickling_bodies_fail_through_source(monkeypatch):
    oversized = WireBody(b'{"slos":[]}' + b' ' * (2 * 1024 * 1024))
    wire(monkeypatch, lambda req: (200, {}, oversized))
    credentials = {"obs-hub": {"token": "synthetic-token"}}
    result = slo.probe_all(ReadOnlyClient(max_attempts=1), [STACK], credentials)
    assert not result["obs-hub"]["available"]
    now = [0.0]
    def tick():
        now[0] += 0.4
    slow = WireBody(b'{"slos":[]}', tick=tick)
    wire(monkeypatch, lambda req: (200, {}, slow))
    result = slo.probe_all(ReadOnlyClient(max_attempts=1, timeout=0.3, clock=lambda: now[0]),
                           [STACK], credentials)
    assert not result["obs-hub"]["available"]


@pytest.mark.parametrize("body", [
    {"slos": [{"nested": [{}] * 100_001}]},
    {"slos": [{"nested": float("nan")}]},
    {"slos": [{"x" * 257: "synthetic"}]},
])
def test_structurally_unbounded_or_malformed_resource_defers(body):
    result = slo.probe_all(client_for(body), [STACK],
                           {"obs-hub": {"token": "synthetic-token"}})
    assert result == {"obs-hub": {"available": False, "reason": "unsafe_schema"}}


def test_deep_schema_is_deferred_without_inspecting_text():
    nested = {}
    for _ in range(34):
        nested = {"nested": nested}
    result = slo.probe_all(client_for({"slos": [nested]}), [STACK],
                           {"obs-hub": {"token": "synthetic-token"}})
    assert result["obs-hub"]["reason"] == "unsafe_schema"
    result = slo.fetch_slo_inventory(client_for({"slos": [
        {"query": "apiKey password authorization", "body": "clientSecret"}]}),
        STACK, "synthetic-token")
    assert result["available"] and result["count"] == 1


@pytest.mark.parametrize("payload,step,timeout,expected_available", [
    (b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n{"slos":[]}', 0, 1, True),
    (b'HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\n{"slos":[]}', 0, 1, False),
    (b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n{"slos":[]}', 0.01, 0.2, False),
    (b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n{"slos":[]}', 0.01, 0.5, False),
])
def test_real_http_parser_socket_receives_obey_total_deadline(
        monkeypatch, payload, step, timeout, expected_available):
    """Real opener, HTTPSConnection and HTTPResponse; replace only socket/TLS connect."""
    now = [0.0]
    waits = []
    class Raw(io.BytesIO):
        def readinto(self, buffer):
            now[0] += step
            data = self.read(min(len(buffer), 1))
            buffer[:len(data)] = data
            return len(data)
    class Socket:
        def settimeout(self, wait):
            waits.append(wait)
        def sendall(self, data):
            pass
        def makefile(self, mode, buffering=None):
            return Raw(payload)
        def close(self):
            pass
    monkeypatch.setattr(http.client.HTTPSConnection, "connect",
                        lambda conn: setattr(conn, "sock", Socket()))
    client = ReadOnlyClient(max_attempts=1, timeout=timeout, clock=lambda: now[0])
    result = slo.probe_all(client, [STACK], {"obs-hub": {"token": "synthetic-token"}})
    assert result["obs-hub"]["available"] is expected_available
    assert waits and all(0 < wait <= timeout for wait in waits)
    if step:
        assert waits[-1] < waits[0]
        assert now[0] <= timeout + step


def test_transport_exception_cannot_persist_response_content():
    def transport(request, timeout):
        raise RuntimeError("synthetic-sensitive body, token, expression")
    result = slo.probe_all(ReadOnlyClient(transport=transport, max_attempts=1), [STACK],
                           {"obs-hub": {"token": "synthetic-token"}})
    assert result == {"obs-hub": {"available": False, "reason": "transport_error"}}
