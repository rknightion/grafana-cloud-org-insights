"""Anonymous public catalogue contract, not signature or installed entitlement inference."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from collector.httpclient import ReadOnlyClient, Response
from collector.sources import plugin_catalog as source

FIXTURES = Path(__file__).parent / "fixtures"
SLUGS = ("grafana-aurora-datasource", "yesoreyeram-infinity-datasource")
PRIVATE = "private-author-credential-canary"


def fixture(slug):
    return json.loads((FIXTURES / f"plugin_catalog.{slug}.json").read_text())


def inventory(*slugs):
    return [{"slug": "fresh", "datasourceCnts": {slug: 1 for slug in slugs}}]


def client_for(bodies, calls=None):
    def transport(request, timeout):
        assert request.method == "GET"
        assert request.get_header("Authorization") is None
        assert not request.headers
        assert 0 < timeout <= 1
        slug = request.full_url.removeprefix("https://grafana.com/api/plugins/")
        assert request.full_url == "https://grafana.com/api/plugins/" + slug
        if calls is not None:
            calls.append(slug)
        body, status = bodies[slug]
        if isinstance(body, Exception):
            raise body
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        return Response(status, data, request.full_url)
    return ReadOnlyClient(transport=transport, timeout=1, deadline=30, max_attempts=1)


def record(body):
    return {"available": True, "enterprise": body["status"] == "enterprise",
            "status": body["status"], "version": body["version"],
            "basis": "current_public_catalogue"}


def test_real_two_plugin_contract_and_fixture_integrity():
    witnessed = {slug: fixture(slug) for slug in SLUGS}
    for slug, evidence in witnessed.items():
        assert evidence["sourceURL"] == "https://grafana.com/api/plugins/" + slug
        assert evidence["httpStatus"] == 200
        assert evidence["observedAt"]
        assert evidence["contractRevision"] == "6e5fb9d9729c94b2a0f51b66ee92949684af9824"
        assert len(bytes.fromhex(evidence["rawBodySha256"])) == 32
        digest = hashlib.sha256(json.dumps(evidence["body"], sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
        assert digest == evidence["projectionSha256"]
        assert evidence["body"]["slug"] == slug
        assert evidence["body"]["typeCode"] == "datasource"
        assert evidence["body"]["signatureType"] == "grafana"
    assert witnessed[SLUGS[0]]["body"]["status"] == "enterprise"
    assert witnessed[SLUGS[1]]["body"]["status"] == "active"
    client = client_for({slug: (e["body"], 200) for slug, e in witnessed.items()})
    assert source.fetch_catalogue(client, inventory(*SLUGS)) == {
        slug: record(e["body"]) for slug, e in witnessed.items()}


def test_discovery_uses_fresh_inventory_keys_and_deduplicates_not_configuration():
    body = {"slug": "new-vendor-datasource", "typeCode": "datasource", "status": "enterprise",
            "version": "1.2.3"}
    other = {**body, "slug": "another", "status": "active"}
    calls = []
    client = client_for({body["slug"]: (body, 200), "another": (other, 200)}, calls)
    stacks = inventory(body["slug"], "another") + inventory(body["slug"])
    # Discovery is by keys, including configured zero-count keys, never a literal plugin list.
    stacks[0]["datasourceCnts"]["another"] = 0
    assert source.fetch_catalogue(client, stacks) == {body["slug"]: record(body), "another": record(other)}
    assert calls == sorted({body["slug"], "another"})
    calls.clear()
    assert source.fetch_catalogue(client, inventory("another")) == {"another": record(other)}
    assert calls == ["another"]
    calls.clear()
    assert source.fetch_catalogue(client, [{"slug": "empty"}, {"datasourceCnts": None}]) == {}
    assert source.fetch_catalogue(client, []) == {}
    assert calls == []


@pytest.mark.parametrize("slug", ["", "../escape", "https://evil.test", "a?token=x", "a#fragment",
                                   "a%2fb", "a/b", "a b", "a\n", "a" * 129])
def test_invalid_ids_never_enter_public_requests(slug):
    calls = []
    assert source.fetch_catalogue(client_for({}, calls), inventory(slug)) == {}
    assert calls == []


@pytest.mark.parametrize("status", [206, 201, 204, 301, 401, 403, 404, 429, 500])
def test_only_exact_200_is_complete_metadata(status):
    slug = SLUGS[0]
    result = source.fetch_catalogue(client_for({slug: (fixture(slug)["body"], status)}), inventory(slug))
    assert result == {slug: {"available": False, "reason": "unreadable"}}


@pytest.mark.parametrize("status", [None, "", "unknown", "deleted", "pending", "deprecated", "Enterprise",
                                     False, [], {}])
def test_missing_unknown_other_status_never_means_not_enterprise(status):
    slug = SLUGS[0]
    body = {**fixture(slug)["body"], "status": status}
    result = source.fetch_catalogue(client_for({slug: (body, 200)}), inventory(slug))
    assert result == {slug: {"available": False, "reason": "unknown_status"}}
    del body["status"]
    assert source.fetch_catalogue(client_for({slug: (body, 200)}), inventory(slug)) == result


@pytest.mark.parametrize("body", [None, [], {}, b"not-json", {"slug": "other", "typeCode": "datasource"},
                                   {"slug": SLUGS[0], "typeCode": "panel"},
                                   {"slug": SLUGS[0], "typeCode": None}])
def test_invalid_shape_or_identity_never_classifies(body):
    slug = SLUGS[0]
    result = source.fetch_catalogue(client_for({slug: (body, 200)}), inventory(slug))[slug]
    assert result["available"] is False
    assert result["reason"] in {"invalid_response", "metadata_mismatch"}
    assert "enterprise" not in result


def test_transport_failure_is_closed_and_independent_of_other_plugin(capsys, caplog, tmp_path):
    good = fixture(SLUGS[1])["body"]
    result = source.fetch_catalogue(client_for({SLUGS[0]: (RuntimeError(PRIVATE), 200),
                                                SLUGS[1]: (good, 200)}), inventory(*SLUGS))
    assert result[SLUGS[0]] == {"available": False, "reason": "transport_error"}
    assert result[SLUGS[1]] == record(good)
    output = tmp_path / "output.json"
    output.write_text(json.dumps(result))
    assert PRIVATE not in output.read_text() + caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("status", ["enterprise", "active"])
def test_only_minimized_metadata_crosses_boundary_and_signature_is_not_classification(status):
    slug = "novel-plugin"
    body = {"slug": slug, "typeCode": "datasource", "status": status, "version": "2.3.4-beta.1",
            "signatureType": "community", "orgName": PRIVATE, "author": {"email": PRIVATE},
            "url": "https://" + PRIVATE, "readme": PRIVATE, "installedVersion": "0.0.1"}
    original = copy.deepcopy(body)
    result = source.fetch_catalogue(client_for({slug: (body, 200)}), inventory(slug))
    assert result == {slug: record(body)}
    assert body == original
    assert PRIVATE not in json.dumps(result)


def test_catalogue_version_is_optional_not_an_installed_version_claim():
    slug = SLUGS[0]
    body = fixture(slug)["body"]
    for version in [None, {}, PRIVATE, "https://secret.test", "x" * 1000]:
        changed = {**body, "version": version}
        result = source.fetch_catalogue(client_for({slug: (changed, 200)}), inventory(slug))[slug]
        assert result == {k: v for k, v in record(body).items() if k != "version"}


def test_discovery_read_budget_withholds_excess_without_network():
    slugs = [f"plugin-{number}" for number in range(source.MAX_PLUGINS + 1)]
    calls = []
    result = source.fetch_catalogue(client_for({}, calls), inventory(*slugs))
    assert result == {slug: {"available": False, "reason": "discovery_limit"} for slug in slugs}
    assert calls == []
