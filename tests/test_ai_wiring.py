"""Real scanner admission and immutable projection boundaries for aggregate AI history."""
import copy
import json
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import pytest

import scan
from collector import config, identity
from collector.emit import ai_history
from collector.httpclient import Response
from collector.sources import ai_billing
from tests import test_producer_rule_wiring as scanner
from tests.test_ai_billing import fixture_values
from tests.test_ai_history import S3, observation, NOW, STACKS
from tests.test_consumer_manifest import fixture, consumer_manifest


@pytest.mark.parametrize("case", ["healthy", "limited", "peer_failed", "empty"])
def test_actual_cli_ai_history_obeys_every_publication_guard(tmp_path, case):
    stack = dict(scanner.STACK, id=1, url="https://synthetic.example.test")
    original = scanner.client_for
    values = fixture_values()
    values.update(users=[({}, 1)], service_users=[({}, 0)], user_tokens=[({}, 50000000)],
                  service_tokens=[({}, 0)], user_excess=[({}, 10000000)], users_over_allowance=[({}, 1)])
    for name in values:
        if name.startswith("stack_"):
            values[name] = [(labels, value) for labels, value in values[name] if labels["stack_id"] == "1"]
    values.update(stack_user_tokens=[({"stack_id": "1"}, 50000000)],
                  stack_service_users=[({"stack_id": "1"}, 0)],
                  stack_service_tokens=[({"stack_id": "1"}, 0)])
    factory = ai_billing.queries()
    names = {expression: name for name, expression in factory.items()}
    def client_for(**kwargs):
        client, calls = original(**kwargs)
        prior = client._transport
        def transport(request, timeout):
            if "/api/datasources/proxy/" not in request.full_url:
                return prior(request, timeout)
            params = parse_qs(urlsplit(request.full_url).query)
            key = names[params["query"][0]]
            calls.append("ai_" + key)
            body = {"status": "success", "data": {"resultType": "vector", "result": [
                {"metric": labels, "value": [int(params["time"][0]), str(value)]}
                for labels, value in values[key]]}}
            return Response(200, json.dumps(body).encode(), request.full_url)
        client._transport = transport
        return client, calls
    store = S3()
    real_update = ai_history.update
    def update(*args, **kwargs):
        return real_update(*args, **kwargs, runner=store)
    with mock.patch.object(scanner, "STACK", stack), mock.patch.object(scanner, "client_for", client_for), \
         mock.patch.object(scan.credentials, "load_all", return_value={"synthetic": {"token": "synthetic"}}), \
         mock.patch.object(scan.s3emit, "BUCKET", "synthetic-bucket"), \
         mock.patch.object(ai_history, "update", side_effect=update):
        result = scanner.exercise_cli(tmp_path, ai=True, dry_run=False,
             empty_estate=case == "empty", limited=case == "limited",
             failed=("/loki/api/v1/index/volume",) if case == "peer_failed" else ())
    puts = [args for args, _kw in store.calls if args[2] == "put-object"]
    if case == "healthy":
        assert result["code"] == 0, result["stderr"]
        assert len(puts) == 1
        snapshot = result["scans"][0]["data"]["ai_billing"]
        assert snapshot["org"]["users"] == 1
        assert "history" in snapshot
        assert "ai_cost_current" in result["views"][0]
        assert sum(call.startswith("ai_") for call in result["calls"]) == 14
    else:
        assert result["code"] != 0
        assert not puts
        assert not result["scans"]


def test_ai_policy_is_digest_bound_and_legacy_defaults_stay_compatible():
    body = fixture()
    for name in identity.AI_BILLING_DEFAULTS:
        body["runtime"]["scan"].pop(name, None)
    old = consumer_manifest.regenerate(body)
    rendered = dict(consumer_manifest.effective(old)["runtime"]["scan"], **identity.AI_BILLING_DEFAULTS)
    rendered["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] = old["runtime_projection_digests"]["scan"]
    assert identity.verify_runtime_projection("scan", environ=rendered)
    rendered["GCINSIGHT_AI_PERSONAL_ALLOWANCE"] = "1"
    with pytest.raises(identity.InvalidIdentity):
        identity.verify_runtime_projection("scan", environ=rendered)
    bad = copy.deepcopy(old)
    for value in ("-1", "1.5", "NaN", "01", "9007199254740992"):
        bad["runtime"]["scan"]["GCINSIGHT_AI_PERSONAL_ALLOWANCE"] = value
        with pytest.raises(consumer_manifest.ManifestError):
            consumer_manifest.regenerate(bad)


def test_customer_backfill_provenance_is_closed_and_dated():
    item = observation(source="bi_one_time", provenance={
        "start": "2026-10-01T00:00:00+00:00", "end": "2026-10-14T11:00:00+00:00",
        "cutover": NOW.isoformat(), "query_sha256": "a" * 64})
    rows = ai_history.merge([], item, STACKS, now=NOW)
    assert rows[0]["provenance"] == item["provenance"]
    bad = copy.deepcopy(item)
    bad["provenance"]["email"] = "private@example.test"
    with pytest.raises(ai_history.HistoryError):
        ai_history.merge([], bad, STACKS, now=NOW)
