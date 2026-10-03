"""Playlist count boundary: only a complete witnessed collection response survives."""
import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector.coverage import Coverage
from collector.emit import hydrate, s3
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose
from collector.provision import desired_permissions, parse_product_reads, product_read_pairs
from collector.sources import playlists

STACK = {"slug": "obs-hub", "url": "https://inventory.example.test"}
PRIVATE = "playlist-private-canary"
PLAYLIST = {"interval": "5m", "name": PRIVATE, "uid": PRIVATE}
ROW = {"Stack": "obs-hub", "Configured playlists": 1}


def client_for(body, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + "/api/playlists"
        assert request.get_header("Authorization") == "Bearer synthetic"
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


def test_default_off_exact_grant_and_zero_http_calls():
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), \
            mock.patch.object(scan.credentials, "load_all") as store:
        client = mock.Mock()
        assert scan.gather_playlists_inventory(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        store.assert_not_called()
        client.get.assert_not_called()
    pair = ("playlists:read", "")
    assert product_read_pairs({"playlists"}) == frozenset({pair})
    baseline = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False)}
    selected = {(p["action"], p.get("scope", "")) for p in desired_permissions(
        write_stack=False, product_reads={"playlists"})}
    assert selected - baseline == {pair}
    assert parse_product_reads("playlists") == frozenset({"playlists"})
    with pytest.raises(ValueError):
        parse_product_reads("playlists,playlist-items")


def test_complete_empty_and_positive_records_left_join_live_inventory():
    positive = playlists.fetch_playlists(client_for([PLAYLIST]), STACK, "synthetic")
    empty = playlists.fetch_playlists(client_for([]), STACK, "synthetic")
    assert positive == {"available": True, "playlist_count": 1}
    assert empty == {"available": True, "playlist_count": 0}
    stacks = [STACK, {"slug": "new-stack"}]
    rows = compose.build_all(stacks, Coverage(tier="t2", total=2),
                             playlists_inventory={"obs-hub": positive, "departed": positive})[1]
    assert rows["playlists_inventory"] == [ROW]
    assert "playlists_inventory" not in compose.build_all(
        [], Coverage(tier="t2", total=0), playlists_inventory={"departed": positive})[1]
    calls = []
    records = playlists.probe_all(client_for([PLAYLIST], calls=calls), [STACK],
                                  {"obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}})
    assert set(records) == {"obs-hub"}
    assert calls == [STACK["url"] + "/api/playlists"]


@pytest.mark.parametrize("body,status", [
    ([PLAYLIST], 206), ({"items": [PLAYLIST]}, 200), ({"playlists": [PLAYLIST]}, 200),
    ([{"interval": "5m", "name": PRIVATE, "uid": PRIVATE, "items": []}], 200),
    ([{"interval": "5m", "name": PRIVATE, "uid": PRIVATE, "api_key": PRIVATE}], 200),
    ([{"interval": 5, "name": PRIVATE, "uid": PRIVATE}], 200),
    ({"error": PRIVATE}, 403),
])
def test_partial_malformed_and_error_responses_are_absent_without_private_content(body, status, caplog, capsys):
    errors = []
    record = playlists.probe_all(client_for(body, status), [STACK],
                                 {"obs-hub": {"token": "synthetic"}},
                                 on_error=lambda slug, reason: errors.append(reason))["obs-hub"]
    assert record["available"] is False
    rows = compose.build_all([STACK], Coverage(tier="t2", total=1),
                             playlists_inventory={"obs-hub": record})[1]
    assert "playlists_inventory" not in rows
    assert PRIVATE not in json.dumps([record, errors]) + caplog.text + capsys.readouterr().out


def test_unsafe_url_bound_response_and_exception_are_sanitized():
    calls = []
    for url in ("http://host.test", "https://u:p@host.test", "https://host.test/?x=y",
                "https://host.test/#x", "https://host.test/%61pi"):
        record = playlists.fetch_playlists(client_for([PLAYLIST], calls=calls), {**STACK, "url": url}, "synthetic")
        assert not record["available"]
    assert calls == []
    with mock.patch.object(playlists, "MAX_PLAYLISTS", 0):
        assert not playlists.fetch_playlists(client_for([PLAYLIST]), STACK, "synthetic")["available"]
    client = mock.Mock()
    client.get.side_effect = RuntimeError(PRIVATE)
    assert playlists.fetch_playlists(client, STACK, "synthetic") == {
        "available": False, "reason": "transport_error"}
    assert playlists.fetch_playlists(client, STACK, "") == {
        "available": False, "reason": "no_credential"}


@pytest.mark.parametrize("body,status,measured", [([PLAYLIST], 200, True), ([], 200, True),
                                                    ([PLAYLIST], 206, False), ({"error": PRIVATE}, 403, False)])
def test_selected_t2_scan_to_view_envelope_and_dashboard(body, status, measured, capsys, caplog, tmp_path):
    from tests.test_scan import cfg_for

    def detail(_client, _cfg, _selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}

    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "playlists"}))
        edges.enter_context(mock.patch.object(scan.credentials, "load_all", return_value={
            "obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}}))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_inventory", return_value=[STACK]))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail))
        for name in ("service_accounts", "assistant", "insights", "dashboard_inventory", "datasource_query_cost",
                     "adaptive_logs", "adaptive_traces", "public_dashboards", "alert_routing", "slo_inventory",
                     "signal_inventory", "capability_adoption", "loki_config"):
            edges.enter_context(mock.patch.object(scan, "gather_" + name, return_value=({}, [])))
        edges.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value={}))
        edges.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        edges.enter_context(mock.patch.object(hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1)))
        result = scan.run_t2(client_for(body, status), cfg_for())

    if measured:
        count = len(body)
        assert result["data"]["playlists_inventory"] == {
            "obs-hub": {"available": True, "playlist_count": count}}
        assert result["meta"]["sources"]["playlists_inventory"]["healthy"]
        assert result["_emit"]["views"]["playlists_inventory"] == (
            [{"Stack": "obs-hub", "Configured playlists": count}])
    else:
        assert "playlists_inventory" not in result["data"]
        assert not result["meta"]["sources"]["playlists_inventory"]["healthy"]
        assert "playlists_inventory" not in result["_emit"]["views"]

    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
        s3.write_views(views, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    if measured:
        envelope = json.loads(writes["views/playlists_inventory.json"])
        assert envelope["rows"] == [{"Stack": "obs-hub", "Configured playlists": len(body)}]
        assert envelope["meta"]["inputs"]["playlists_inventory"]["source"] == "own"
        assert envelope["meta"]["inputs"]["playlists_inventory"]["tier"] == "t2"
    else:
        assert "views/playlists_inventory.json" not in writes
    from bin import dashboards
    _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "playlists_inventory.json" in json.dumps(assembled)
    output = tmp_path / "diagnostic.json"
    output.write_text(json.dumps(result, default=str))
    assert PRIVATE not in output.read_text() + json.dumps(writes) + caplog.text + capsys.readouterr().out


def test_unsatisfied_view_is_withheld():
    provenance = hydrate.Provenance()
    views, withheld = hydrate.filter_views({"playlists_inventory": [ROW]}, provenance)
    assert "playlists_inventory" not in views
    assert "playlists_inventory" in withheld
