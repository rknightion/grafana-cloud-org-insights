"""Opt-in Synthetic Monitoring public-boundary and privacy contract."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector.coverage import Coverage
from collector.httpclient import ReadOnlyClient, Response

STACK = {"slug": "obs-hub", "url": "https://inventory.example.test"}
KEY = "GCINSIGHT_READER_PRODUCT_READS"
SELECTED = "synthetic-monitoring,synthetic-monitoring-query"


def test_absent_query_token_makes_no_http_or_credential_calls():
    for policy in ("", "slo", "synthetic-monitoring", "slo,synthetic-monitoring"):
        with mock.patch.dict("os.environ", {KEY: policy}), mock.patch.object(
            scan.credentials, "load_all"
        ) as credentials:
            calls = []
            client = ReadOnlyClient(transport=lambda *args: calls.append(args), max_attempts=1)
            assert scan.gather_synthetic_inventory(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
            assert calls == []
            credentials.assert_not_called()


def fixture_client(*, overrides=None, exception=False):
    from collector.sources import synthetic
    body = json.loads((Path(__file__).parent / "fixtures/synthetic_lists.json").read_text())
    canary = "synthetic-sensitive"
    for item in body["checks"] + body["probes"]:
        item.update({"id": canary, "tenantId": canary, "name": canary, "target": canary,
                     "url": canary, "job": canary, "labels": [{"name": canary, "value": canary}],
                     "headers": {"Authorization": canary}, "script": canary})
    paths = {"/api/datasources": body["datasources"],
             "/api/datasources/proxy/uid/synthetic-sm/sm/check/list": body["checks"],
             "/api/datasources/proxy/uid/synthetic-sm/sm/probe/list": body["probes"]}
    calls = []
    def transport(request, timeout):
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        path = request.full_url.removeprefix(STACK["url"])
        assert path in paths
        calls.append(path)
        if exception:
            raise RuntimeError(canary)
        status, data = (overrides or {}).get(path, (200, paths[path]))
        return Response(status, json.dumps(data).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1), calls


def test_minimized_counts_cross_gather_compose_and_hydrate(capsys):
    from collector.emit import hydrate
    from collector.pillars import compose, synthetic as pillar
    client, calls = fixture_client()
    with mock.patch.dict("os.environ", {KEY: SELECTED}), mock.patch.object(
        scan.credentials, "load_all", return_value={"obs-hub": {"token": "synthetic-token"}}
    ):
        data, errors = scan.gather_synthetic_inventory(client, SimpleNamespace(concurrency=1), [STACK])
    assert not errors and len(calls) == 3
    record = data["obs-hub"]
    assert record["check_count"] == 4 and record["enabled_count"] == 3
    assert record["check_type_counts"]["http"] == 3 and record["check_type_counts"]["ping"] == 1
    assert record["probe_counts"] == {"public": 2, "private": 1}
    result = compose.build_all([STACK], Coverage(tier="t2", total=1), synthetic_inventory=data)
    metrics, views = result[:2]
    assert not any("synthetic_inventory" in name for name, _, _ in metrics)
    row = views[pillar.VIEW][0]
    assert row["Checks"] == 4 and row["Enabled checks"] == 3
    assert row["Public probes"] == 2 and row["Private probes"] == 1
    encoded = json.dumps({"input": data, "view": row, "errors": errors}) + capsys.readouterr().out
    assert "synthetic-sensitive" not in encoded
    for field in ("target", "url", "script", "headers", "labels", "name", "id", "tenantId"):
        assert f'"{field}"' not in encoded
    # A fresh other-tier scan really hydrates this input, never an owner's old failed scan.
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    envelope = {"meta": {"generated_at": now.isoformat()}, "data": {"synthetic_inventory": data}}
    hydrated, provenance = hydrate.hydrate("t1", {}, bucket="offline", now=now,
                                           loader=lambda tier, bucket: envelope if tier == "t2" else None)
    assert hydrated["synthetic_inventory"] == data
    assert provenance.satisfied("synthetic_inventory")
    assert hydrate.filter_views(views, provenance)[0][pillar.VIEW] == views[pillar.VIEW]
    own, _ = hydrate.hydrate("t2", {}, bucket="offline", now=now, loader=lambda *args: envelope)
    assert not own.get("synthetic_inventory")
    _, left_join = pillar.build([STACK], {**data, "departed": record})
    assert len(left_join[pillar.VIEW]) == 1


@pytest.mark.parametrize("overrides,reason", [
    ({"/api/datasources": (200, [])}, "no_datasource"),
    ({"/api/datasources": (200, [{"type": "synthetic-monitoring-datasource", "uid": "synthetic-sm"}] * 2)}, "ambiguous"),
    ({"/api/datasources": (200, [{"type": "synthetic-monitoring-datasource", "uid": "bad:*"}])}, "invalid_uid"),
    ({"/api/datasources/proxy/uid/synthetic-sm/sm/check/list": (403, {"error": "synthetic-sensitive"})}, "checks_unreadable"),
    ({"/api/datasources/proxy/uid/synthetic-sm/sm/probe/list": (403, {"error": "synthetic-sensitive"})}, "probes_unreadable"),
    ({"/api/datasources/proxy/uid/synthetic-sm/sm/check/list": (200, {"items": []})}, "invalid_schema"),
    ({"/api/datasources/proxy/uid/synthetic-sm/sm/probe/list": (200, [{}])}, "invalid_schema"),
])
def test_unavailable_never_becomes_zero_and_errors_are_private(overrides, reason, capsys):
    from collector.sources import synthetic
    from collector.pillars import synthetic as pillar
    client, calls = fixture_client(overrides=overrides)
    errors = []
    data = synthetic.probe_all(client, [STACK], {"obs-hub": {"token": "synthetic-token"}},
                               on_error=lambda slug, msg: errors.append(msg))
    assert data == {"obs-hub": {"available": False, "reason": reason}}
    assert errors == [f"synthetic_inventory: {reason}"]
    assert pillar.build([STACK], data) == ([], {})
    assert "synthetic-sensitive" not in json.dumps(data) + str(errors) + capsys.readouterr().out
    if reason in {"no_datasource", "ambiguous", "invalid_uid"}:
        assert calls == ["/api/datasources"]


def test_known_absence_is_not_failure_but_unknown_coverage_still_is():
    """A proven missing optional datasource must not suppress another stack's measured rows."""
    no_ds = {"available": False, "reason": "no_datasource"}
    good = {"available": True}
    report = scan.synthetic_source_report(2, {"a": no_ds, "b": good}, [])
    assert report["expected"] == 1 and report["available"] == 1
    assert report["not_applicable"] == 1 and report["healthy"]
    failed = {"available": False, "reason": "unreadable"}
    report = scan.synthetic_source_report(2, {"a": no_ds, "b": failed}, [])
    assert report["expected"] == 1 and report["available"] == 0
    assert not report["healthy"]
    for reason in ("no_credential", "ambiguous", "invalid_uid", "transport_error"):
        report = scan.synthetic_source_report(1, {"a": {"available": False, "reason": reason}}, [])
        assert report["expected"] == 1 and not report["healthy"]
    report = scan.synthetic_source_report(2, {"a": no_ds}, [])
    assert report["expected"] == 1 and not report["healthy"]  # missing record is unknown
    with mock.patch.dict("os.environ", {KEY: "synthetic-monitoring"}):
        assert not scan.synthetic_reads_enabled()


@pytest.mark.parametrize("path,size", [
    ("/api/datasources", 6_281_868),
    ("/api/datasources", 11_027_145),
    ("/api/datasources/proxy/uid/synthetic-sm/sm/check/list", 32 * 1024 * 1024),
    ("/api/datasources/proxy/uid/synthetic-sm/sm/probe/list", 32 * 1024 * 1024),
])
def test_oversized_synthetic_lists_use_real_guarded_transport(path, size):
    """Synthetic bytes at the observed sizes and cap, never a live customer body."""
    from collector.sources import synthetic
    payloads = {
        "/api/datasources": [{"type": "synthetic-monitoring-datasource", "uid": "synthetic-sm"}],
        "/api/datasources/proxy/uid/synthetic-sm/sm/check/list": [
            {"enabled": True, "settings": {"http": {}}}],
        "/api/datasources/proxy/uid/synthetic-sm/sm/probe/list": [{"public": True}],
    }
    def open_response(req, timeout):
        route = req.full_url.removeprefix(STACK["url"])
        raw = json.dumps(payloads[route]).encode()
        if route == path:
            raw += b" " * (size - len(raw))
        import io
        fh = io.BytesIO(raw)
        fh.code, fh.headers = 200, {"Content-Length": str(len(raw))}
        fh.read1 = fh.read
        return fh
    with mock.patch("collector.httpclient.urllib.request.build_opener") as opener:
        opener.return_value.open.side_effect = open_response
        record = synthetic.probe_stack(ReadOnlyClient(), STACK, "synthetic-token")
    assert record["available"], record
    assert record["check_count"] == 1
    assert record["probe_counts"] == {"public": 1, "private": 0}


@pytest.mark.parametrize("failed_path", [
    "/api/datasources",
    "/api/datasources/proxy/uid/synthetic-sm/sm/check/list",
    "/api/datasources/proxy/uid/synthetic-sm/sm/probe/list",
])
def test_over_cap_stays_transport_error_and_withholds_publication(failed_path, capsys):
    from collector.httpclient import MAX_SYNTHETIC_BYTES
    from collector.pillars import synthetic as pillar
    from collector.sources import synthetic
    payloads = {
        "/api/datasources": [{"type": "synthetic-monitoring-datasource", "uid": "synthetic-sm"}],
        "/api/datasources/proxy/uid/synthetic-sm/sm/check/list": [],
        "/api/datasources/proxy/uid/synthetic-sm/sm/probe/list": [],
    }
    def open_response(req, timeout):
        import io
        path = req.full_url.removeprefix(STACK["url"])
        fh = io.BytesIO(json.dumps(payloads[path]).encode())
        fh.code = 200
        fh.headers = {"Content-Length": str(MAX_SYNTHETIC_BYTES + 1)} if path == failed_path else {}
        fh.read1 = fh.read
        return fh
    errors = []
    with mock.patch("collector.httpclient.urllib.request.build_opener") as opener:
        opener.return_value.open.side_effect = open_response
        data = synthetic.probe_all(ReadOnlyClient(), [STACK], {"obs-hub": {"token": "synthetic-token"}},
                                   on_error=lambda slug, msg: errors.append(msg))
    assert data == {"obs-hub": {"available": False, "reason": "transport_error"}}
    assert errors == ["synthetic_inventory: transport_error"]
    assert pillar.build([STACK], data) == ([], {})
    report = scan.synthetic_source_report(1, data, errors)
    assert report["expected"] == 1 and report["not_applicable"] == 0
    assert not report["healthy"]
    assert capsys.readouterr().out == ""


def test_transport_failures_empty_lists_and_unknown_type():
    from collector.sources import synthetic
    client, _ = fixture_client(exception=True)
    assert synthetic.probe_stack(client, STACK, "synthetic-token") == {
        "available": False, "reason": "transport_error"}
    client, _ = fixture_client(overrides={
        "/api/datasources/proxy/uid/synthetic-sm/sm/check/list": (200, []),
        "/api/datasources/proxy/uid/synthetic-sm/sm/probe/list": (200, [])})
    result = synthetic.probe_stack(client, STACK, "synthetic-token")
    assert result["available"] and result["check_count"] == 0
    client, _ = fixture_client(overrides={
        "/api/datasources/proxy/uid/synthetic-sm/sm/check/list":
            (200, [{"enabled": False, "settings": {"synthetic-sensitive": {}}}])})
    result = synthetic.probe_stack(client, STACK, "synthetic-token")
    assert result["check_type_counts"]["unknown"] == 1
    assert "synthetic-sensitive" not in json.dumps(result)
