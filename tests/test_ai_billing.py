"""AI aggregate boundary: identities stay upstream and missing gauges stay unknown."""
from __future__ import annotations

import datetime as dt
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import ai_cost
from collector.sources import ai_billing

NOW = dt.datetime(2026, 10, 14, 12, tzinfo=dt.timezone.utc)
STACKS = [
    {"id": 1, "slug": "hub", "regionSlug": "r1", "url": "https://hub.example.test"},
    {"id": 2, "slug": "peer", "regionSlug": "r2", "url": "https://peer.example.test"},
]


def vector(rows, instant=NOW):
    return {"status": "success", "data": {"resultType": "vector", "result": [
        {"metric": labels, "value": [instant.timestamp(), str(value)]} for labels, value in rows
    ]}}


def fixture_values():
    # One person uses 30M on each stack: allowance is deducted once, leaving 20M.
    return {
        "users": [({}, 1)], "service_users": [({}, 1)],
        "user_tokens": [({}, 60_000_000)], "service_tokens": [({}, 600_000_000)],
        "user_excess": [({}, 20_000_000)], "users_over_allowance": [({}, 1)],
        "stack_users": [({"stack_id": "1"}, 1), ({"stack_id": "2"}, 1)],
        "stack_service_users": [({"stack_id": "1"}, 1)],
        "stack_user_tokens": [({"stack_id": "1"}, 30_000_000), ({"stack_id": "2"}, 30_000_000)],
        "stack_service_tokens": [({"stack_id": "1"}, 600_000_000)],
        "stack_user_excess": [({"stack_id": "1"}, 10_000_000), ({"stack_id": "2"}, 10_000_000)],
        "reconciliation": [({}, 0)], "billed_overage": [({}, 240)],
        "stack_billed_overage": [({"stack_id": "1"}, 220), ({"stack_id": "2"}, 20)],
    }


def probe(values=None, *, now=NOW, alter=None):
    queries = ai_billing.queries(40_000_000)
    values = values if values is not None else fixture_values()
    requests = []

    def transport(request, timeout):
        requests.append(request)
        params = parse_qs(urlsplit(request.full_url).query)
        assert params["time"] == [str(int(now.timestamp()))]
        expression = params["query"][0]
        key = next(key for key, query in queries.items() if query == expression)
        body = vector(values.get(key, []), now)
        code = 200
        if alter:
            body, code = alter(key, body)
        return Response(code, json.dumps(body).encode(), request.full_url)

    result = ai_billing.probe(ReadOnlyClient(transport=transport), STACKS,
                              {"hub": {"token": "existing-reader"}},
                              write_stack="hub", now=now)
    return result, requests


def test_real_get_boundary_dedup_and_shared_allowance_projection():
    result, requests = probe()
    assert result["available"] is True
    assert result["org"]["users"] == 1
    assert result["org"]["system_excess"] == 100_000_000
    assert sum(row["user_excess"] for row in result["stacks"].values()) == 20_000_000
    assert result["stacks"]["2"]["service_tokens"] is None
    assert len(requests) == 14
    assert all(request.get_method() == "GET" for request in requests)
    assert all(urlsplit(request.full_url).path ==
               "/api/datasources/proxy/uid/grafanacloud-usage/api/v1/query" for request in requests)
    assert all(request.get_header("Authorization") == "Bearer existing-reader" for request in requests)
    expressions = list(ai_billing.queries(40_000_000).values())
    allocation = ai_billing.queries(40_000_000)["stack_user_excess"]
    assert "sum by(email)" in allocation and "on(email) group_left()" in allocation
    assert "sum by(stack_id,email)" in allocation
    import re
    for expression in expressions:
        selectors = re.findall(r"grafanacloud_[A-Za-z0-9_]+\{([^}]*)\}", expression)
        assert selectors and all('__ignore_usage__=""' in selector for selector in selectors)
    assert 'email' not in json.dumps(result)
    _, views = ai_cost.build(STACKS, result)
    assert views["ai_cost_current"][0]["Model total USD"] == 260
    assert len(views["ai_cost_stacks"]) == 2
    assert "email" not in json.dumps(views)
    assert not any("USD" in key for row in views["ai_cost_stacks"] for key in row)


@pytest.mark.parametrize("case", ["email", "warning", "nonfinite", "fractional_count", "duplicate", "206"])
def test_malformed_or_identity_bearing_response_is_unavailable(case):
    def alter(key, body):
        if key != "users":
            return body, 200
        row = body["data"]["result"][0]
        if case == "email":
            row["metric"]["email"] = "private@example.test"
        elif case == "warning":
            body["warnings"] = ["private@example.test"]
        elif case == "nonfinite":
            row["value"][1] = "NaN"
        elif case == "fractional_count":
            row["value"][1] = "1.5"
        elif case == "duplicate":
            body["data"]["result"].append(dict(row))
        return body, 206 if case == "206" else 200
    result, _ = probe(alter=alter)
    assert result["available"] is False
    assert "private" not in json.dumps(result)
    assert ai_cost.build(STACKS, result) == ([], {})


def test_zero_excess_and_missing_billing_are_distinct_from_missing_source():
    values = fixture_values()
    values["user_excess"] = [({}, 0)]
    values["users_over_allowance"] = [({}, 0)]
    values["stack_user_excess"] = [({"stack_id": "1"}, 0), ({"stack_id": "2"}, 0)]
    values["billed_overage"] = []
    values["stack_billed_overage"] = []
    result, _ = probe(values)
    assert result["available"] is True
    assert result["org"]["user_excess"] == 0
    assert result["org"]["users_over_allowance"] == 0
    assert result["org"]["billed_overage"] is None
    values["user_tokens"] = []
    missing, _ = probe(values)
    assert missing["available"] is False


def test_reconciliation_and_rollover_block_false_history_and_departed_stacks():
    values = fixture_values()
    values["reconciliation"] = [({}, 1)]
    result, _ = probe(values)
    assert result["available"] is False
    first = NOW.replace(day=1)
    result, _ = probe(now=first)
    assert result["period_status"] == "rollover_unverified"
    result["stacks"]["999"] = dict(result["stacks"]["1"])
    result["history"] = [dict(result, history=[])]
    _, views = ai_cost.build(STACKS, result)
    assert all(row[" Stack"] != "999" for row in views["ai_cost_stacks"])
    assert views["ai_cost_monthly"] == []


def test_fresh_inventory_is_required_for_org_population_and_no_calls_without_reader():
    values = fixture_values()
    values["stack_user_tokens"].append(({"stack_id": "999"}, 1))
    result, _ = probe(values)
    assert result == {"available": False, "reason": "inventory_mismatch"}
    client = ReadOnlyClient(transport=lambda *_: pytest.fail("must not call absent reader"))
    assert not ai_billing.probe(client, STACKS, {}, write_stack="hub")["available"]
    assert not ai_billing.probe(client, [], {}, write_stack="hub")["available"]


def test_history_preserves_distinct_sources_and_captured_allowance_basis():
    result, _ = probe()
    bootstrap = dict(result, source="bi_one_time", query_time="2026-10-14T10:00:00+00:00")
    prior = dict(result, query_time="2026-10-14T11:00:00+00:00")
    result["history"] = [bootstrap, prior]
    _, views = ai_cost.build(STACKS, result)
    months = views["ai_cost_monthly"]
    assert len(months) == 2
    native = next(row for row in months if row["Source"] == "billing_observation")
    assert native["Observed at"] == result["query_time"]
    assert native["Personal allowance"] == 40_000_000
    assert native["Model total USD"] == 260
    result["org"]["users"] = 10**1000
    assert ai_cost.build(STACKS, result) == ([], {})
