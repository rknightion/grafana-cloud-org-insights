"""Synthetic-only probes through the real GET client; no live estate data."""
import base64
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from collector.httpclient import ReadOnlyClient, Response
from collector.sources import loki_volume

STACK = {"slug": "synthetic", "hlInstanceUrl": "https://logs.example.test",
         "hlInstanceId": 123}


def payload(rows=()):
    return {"status": "success", "data": {"resultType": "vector", "result": [
        {"metric": {"service_name": name}, "value": [123456, str(count)]}
        for name, count in rows], "stats": {"summary": {"totalBytesProcessed": 999999}}}}


def run(body, status=200, stacks=None, enabled=True):
    calls = []

    def transport(request, timeout):
        calls.append(request)
        return Response(status, json.dumps(body).encode(), request.full_url)

    client = ReadOnlyClient(transport=transport, max_attempts=1)
    result = loki_volume.probe_all(client, [STACK] if stacks is None else stacks,
                                   "synthetic-cap", enabled=enabled)
    return result["stacks"], calls


def test_default_off_and_inventory_join():
    rows, calls = run(payload(), stacks=[STACK, {"slug": "new"}], enabled=False)
    assert set(rows) == {"synthetic", "new"}
    assert all(r["reason"] == "disabled" for r in rows.values())
    assert not calls
    rows, calls = run(payload(), stacks=[])
    assert rows == {} and calls == []
    client = ReadOnlyClient(transport=lambda *_: pytest.fail("disabled request"))
    assert loki_volume.probe_all(client, [STACK], "cap")["stacks"]["synthetic"]["reason"] == "disabled"


def test_exact_request_sorted_private_rows(monkeypatch, capsys):
    monkeypatch.setattr(loki_volume.time, "time_ns", lambda: 200000 * 10**9)
    rows, calls = run(payload([("private-b", 4), ("private-a", 9)]))
    row = rows["synthetic"]
    assert row == {"state": "complete", "reason": "none", "window_seconds": 86400,
                   "rows": [{"service_name": "private-a", "bytes": 9},
                            {"service_name": "private-b", "bytes": 4}],
                   "other_bytes": None, "total_bytes": None, "truncated": False}
    req = calls[0]
    assert req.get_method() == "GET"
    assert urlsplit(req.full_url).path == loki_volume.PATH
    assert parse_qs(urlsplit(req.full_url).query) == {
        "query": ['{service_name=~".+"}'], "targetLabels": ["service_name"], "limit": ["100"],
        "start": [str((200000 - 86400) * 10**9)], "end": [str(200000 * 10**9)]}
    assert req.get_header("Authorization") == "Basic " + base64.b64encode(b"123:synthetic-cap").decode()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("status", [206, 204, 401, 403, 500])
def test_non_200_unavailable(status):
    rows, _ = run(payload([("secret", 3)]), status=status)
    assert rows["synthetic"] == loki_volume._unavailable("http_error")


def test_empty_and_limit_do_not_invent_remainder():
    for count in (0, 99, 100):
        rows, _ = run(payload([(f"synthetic-{i}", i) for i in range(count)]))
        row = rows["synthetic"]
        assert row["state"] == "complete"
        assert len(row["rows"]) == count
        assert row["truncated"] is (count == 100)
        assert row["other_bytes"] is None and row["total_bytes"] is None


@pytest.mark.parametrize("body", [None, {}, {"status": "error"},
    {"status": "success", "data": {"resultType": "matrix", "result": []}},
    payload([("duplicate", 1), ("duplicate", 2)]), payload([("", 3)]),
    payload([("bad", -1)]), payload([("bad", "NaN")]), payload([("bad", "1.5")]),
    payload([(str(i), i) for i in range(101)])])
def test_malformed(body):
    rows, _ = run(body)
    assert rows["synthetic"] == loki_volume._unavailable("invalid_response")


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(warnings=["private-warning"]),
    lambda b: b["data"]["result"][0]["metric"].update(other="private"),
    lambda b: b["data"]["result"][0].update(value=[True, "1"]),
    lambda b: b["data"]["result"][0].update(value=[float("inf"), "1"]),
])
def test_partial_or_invalid_vector(mutation):
    body = payload([("private", 1)])
    mutation(body)
    rows, _ = run(body)
    assert rows["synthetic"]["reason"] == "invalid_response"


def test_stack_failure_isolated_and_errors_values_free(capsys):
    rows, calls = run(payload(), stacks=[STACK, {"slug": "missing"}])
    assert len(calls) == 1
    assert rows["synthetic"]["state"] == "complete"
    assert rows["missing"] == loki_volume._unavailable("missing_endpoint")
    def failing(*args, **kwargs):
        raise RuntimeError("private-service-name")
    client = ReadOnlyClient(transport=failing, max_attempts=1)
    result = loki_volume.probe_all(client, [STACK], "cap", enabled=True)
    assert result["stacks"]["synthetic"] == loki_volume._unavailable("transport_error")
    assert "private-service-name" not in json.dumps(result)
    assert capsys.readouterr() == ("", "")
    assert loki_volume.probe_all(client, [STACK], "", enabled=True)["stacks"]["synthetic"]["reason"] == "no_credential"


def test_composition_inputs_shallow_copy():
    inputs = {"loki_volume": {"stacks": {}}}
    result = loki_volume.composition_inputs(inputs)
    assert result == inputs and result is not inputs
