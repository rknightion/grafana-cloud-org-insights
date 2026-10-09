"""Synthetic-only witnesses through the actual GET client; no live estate data."""
import base64
import copy
import json
from urllib.parse import urlsplit

import pytest

from collector.httpclient import DeadlineExceeded, ReadOnlyClient, Response
from collector.sources import rule_inventory as source

PATHS = ("/api/prom/api/v1/rules", "/api/prom/api/v1/alerts",
         "/prometheus/api/v1/rules", "/alertmanager/api/v2/alerts",
         "/alertmanager/api/v2/silences")
STACK = {"slug": "synthetic", "hmInstancePromUrl": "https://metrics.example",
         "hmInstancePromId": 11, "hlInstanceUrl": "https://logs.example/",
         "hlInstanceId": 22, "amInstanceUrl": "https://alerts.example", "amInstanceId": 33}
SECRET = "synthetic-private-marker"
PRIVATE = {"name": SECRET, "query": SECRET, "expr": SECRET,
           "labels": {"alertname": SECRET}, "annotations": {"summary": SECRET},
           "receivers": [{"name": SECRET}], "matchers": [{"name": SECRET, "value": SECRET}],
           "createdBy": SECRET, "comment": SECRET}


def prom(field, rows):
    return {"status": "success", "data": {field: rows}, "error": "", "errorType": ""}


def fixtures():
    return {
        PATHS[0]: prom("groups", [{**PRIVATE, "rules": [
            {**PRIVATE, "type": "alerting", "state": "inactive"},
            {**PRIVATE, "type": "recording"}]}]),
        PATHS[1]: prom("alerts", [{**PRIVATE, "state": s} for s in ("firing", "pending", "firing")]),
        PATHS[2]: prom("groups", [{**PRIVATE, "rules": [{**PRIVATE, "type": "recording"}]}]),
        PATHS[3]: [{**PRIVATE, "status": {"state": s}} for s in ("active", "suppressed", "unprocessed", "active")],
        PATHS[4]: [{**PRIVATE, "status": {"state": s}} for s in ("active", "pending", "expired", "expired")],
    }


def run(payloads=None, statuses=None, stacks=None, cap="synthetic-cap", enabled=True, error=None):
    payloads = fixtures() if payloads is None else payloads
    calls = []

    def transport(req, timeout):
        calls.append(req)
        if error:
            raise error
        path = urlsplit(req.full_url).path
        raw = payloads[path]
        body = raw if isinstance(raw, bytes) else json.dumps(raw).encode()
        return Response((statuses or {}).get(path, 200), body, req.full_url)

    client = ReadOnlyClient(transport=transport, max_attempts=1, timeout=1, deadline=10)
    return source.probe_all(client, [STACK] if stacks is None else stacks, cap, enabled=enabled), calls


def test_counts_real_get_routes_auth_and_minimization():
    result, calls = run()
    assert result == {"stacks": {"synthetic": {
        "mimir": {"state": "complete", "reason": "none", "rule_groups": 1,
                  "alerting_rules": 1, "recording_rules": 1, "firing": 2, "pending": 1},
        "loki": {"state": "complete", "reason": "none", "rule_groups": 1,
                 "alerting_rules": 0, "recording_rules": 1, "firing": None, "pending": None},
        "alertmanager": {"state": "complete", "reason": "none", "active": 2,
                         "suppressed": 1, "unprocessed": 1, "silences_active": 1,
                         "silences_pending": 1, "silences_expired": 2}}}}
    assert [urlsplit(req.full_url).path for req in calls] == list(PATHS)
    for req, tenant in zip(calls, (11, 11, 22, 33, 33)):
        assert req.get_method() == "GET"
        assert req.get_header("Authorization") == "Basic " + base64.b64encode(f"{tenant}:synthetic-cap".encode()).decode()
        assert not urlsplit(req.full_url).query
    assert SECRET not in json.dumps(result)
    assert source.composition_inputs(result) == result
    assert source.composition_inputs(result) is not result


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("status", (206, 204, 301, 401, 403, 404, 429, 500))
def test_every_route_requires_exact_200(path, status):
    result, _ = run(statuses={path: status})
    family = "mimir" if path in PATHS[:2] else "loki" if path == PATHS[2] else "alertmanager"
    row = result["stacks"]["synthetic"][family]
    assert row["reason"] == "http_error"
    assert row["state"] == ("unavailable" if family == "loki" else "partial")
    fields = (("rule_groups", "alerting_rules", "recording_rules") if path in (PATHS[0], PATHS[2])
              else ("firing", "pending") if path == PATHS[1]
              else ("active", "suppressed", "unprocessed") if path == PATHS[3]
              else ("silences_active", "silences_pending", "silences_expired"))
    assert all(row[field] is None for field in fields)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("bad", (b"not JSON synthetic-private-marker", None, {}, [None], b'"text"'))
def test_every_route_malformed_is_unknown_values_free(path, bad):
    docs = fixtures()
    docs[path] = bad
    result, _ = run(docs)
    family = "mimir" if path in PATHS[:2] else "loki" if path == PATHS[2] else "alertmanager"
    assert result["stacks"]["synthetic"][family]["reason"] == "invalid_response"
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("path,bad", [
    (PATHS[0], prom("groups", [{"rules": [{"type": SECRET}]}])),
    (PATHS[0], prom("groups", [{}])),
    (PATHS[0], {"status": "error", "data": {"groups": []}}),
    (PATHS[0], {**prom("groups", []), "warnings": [SECRET]}),
    (PATHS[1], prom("alerts", [{"state": SECRET}])),
    (PATHS[1], prom("alerts", [{"state": []}])),
    (PATHS[2], prom("groups", [{"rules": None}])),
    (PATHS[3], [{"status": {"state": SECRET}}]),
    (PATHS[3], [{"status": {}}]),
    (PATHS[4], [{"status": {"state": SECRET}}]),
    (PATHS[4], [{"matchers": PRIVATE["matchers"]}]),
])
def test_invalid_inner_shapes_never_become_zero(path, bad):
    docs = fixtures()
    docs[path] = bad
    result, _ = run(docs)
    family = "mimir" if path in PATHS[:2] else "loki" if path == PATHS[2] else "alertmanager"
    assert result["stacks"]["synthetic"][family]["reason"] == "invalid_response"
    assert SECRET not in json.dumps(result)


def test_proven_empty_is_zero_not_missing():
    docs = {path: prom("groups" if path != PATHS[1] else "alerts", [])
            if path in PATHS[:3] else [] for path in PATHS}
    result, _ = run(docs)
    for family, row in result["stacks"]["synthetic"].items():
        assert row["state"] == "complete"
        for field, value in row.items():
            if field not in ("state", "reason"):
                assert value == (None if family == "loki" and field in ("firing", "pending") else 0)


def test_default_off_and_inventory_join():
    client = ReadOnlyClient(transport=lambda *_: pytest.fail("default off made a request"))
    assert source.probe_all(client, [STACK], "cap") == {}
    assert run(stacks=[])[0] == {"stacks": {}}
    result, calls = run(stacks=[{**STACK, "slug": "new"}, {**STACK, "slug": "paused", "status": "Paused"},
                                {"slug": "missing"}])
    assert set(result["stacks"]) == {"new", "missing"}
    assert len(calls) == 5
    assert all(row["reason"] == "missing_endpoint" for row in result["stacks"]["missing"].values())


@pytest.mark.parametrize("base", ("http://example", "https://user:pass@example", "https://example/path",
                                  "https://example?x=1", "https://example#frag", "https://[", None))
def test_endpoint_fence(base):
    stack = copy.deepcopy(STACK)
    stack.update(hmInstancePromUrl=base, hlInstanceUrl=base, amInstanceUrl=base)
    result, calls = run(stacks=[stack])
    assert not calls
    assert all(row["reason"] == "missing_endpoint" for row in result["stacks"]["synthetic"].values())


def test_missing_cap_and_request_failure_are_closed():
    result, calls = run(cap="")
    assert not calls
    assert all(row["reason"] == "missing_credentials" for row in result["stacks"]["synthetic"].values())
    result, _ = run(error=RuntimeError(SECRET))
    assert all(row["reason"] == "request_failed" for row in result["stacks"]["synthetic"].values())
    assert SECRET not in json.dumps(result)
    client = ReadOnlyClient(deadline=0)
    result = source.probe_all(client, [STACK], "cap", enabled=True)
    assert all(row["reason"] == "deadline" for row in result["stacks"]["synthetic"].values())
