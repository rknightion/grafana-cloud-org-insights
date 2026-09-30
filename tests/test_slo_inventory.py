"""Captured SLO list contracts through the real GET client and compose boundary."""
import json
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


def test_transport_exception_cannot_persist_response_content():
    def transport(request, timeout):
        raise RuntimeError("synthetic-sensitive body, token, expression")
    result = slo.probe_all(ReadOnlyClient(transport=transport, max_attempts=1), [STACK],
                           {"obs-hub": {"token": "synthetic-token"}})
    assert result == {"obs-hub": {"available": False, "reason": "transport_error"}}
