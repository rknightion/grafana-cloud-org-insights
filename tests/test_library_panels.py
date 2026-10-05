"""Count-only library-panel boundary, using synthetic private-field sentinels."""
import copy
import json
from unittest import mock

import pytest

from collector.httpclient import ReadOnlyClient, Response
from collector.sources import library_panels as source

STACK = {"slug": "current", "url": "https://inventory.example.test"}
PRIVATE = "library-private-canary"
PERMISSIONS = {"library.panels:read": ["folders:*"], "folders:read": ["folders:*", "folders:uid:sharedwithme"]}


def element(identity):
    return {"id": identity, "kind": 1, "uid": PRIVATE, "name": PRIVATE,
            "description": PRIVATE, "folderUid": PRIVATE, "model": {"targets": [PRIVATE]},
            "meta": {"createdBy": {"email": PRIVATE}}, "private": PRIVATE}


def page(ids, number=1, total=None):
    return {"result": {"elements": [element(i) for i in ids], "page": number,
                       "perPage": 100, "totalCount": len(ids) if total is None else total}}


def client_for(responses, calls=None, *, permissions=None, permission_status=200):
    responses = iter(responses)
    permissions = PERMISSIONS if permissions is None else permissions
    def transport(request, timeout):
        assert request.method == "GET"
        assert request.get_header("Authorization") == "Bearer synthetic"
        if calls is not None:
            calls.append(request.full_url)
        if request.full_url == STACK["url"] + "/api/access-control/user/permissions":
            assert not seen
            return Response(permission_status, json.dumps(permissions).encode(), request.full_url)
        assert request.full_url == STACK["url"] + source.PATH + f"?kind=1&perPage=100&page={len(seen) + 1}"
        seen.append(request.full_url)
        body, status = next(responses)
        return Response(status, json.dumps(body).encode(), request.full_url)
    seen = []
    return ReadOnlyClient(transport=transport, max_attempts=1)


def test_positive_count_and_private_fields_do_not_cross_public_boundary(tmp_path, caplog, capsys):
    errors = []
    records = source.probe_all(client_for([(page([1, 2]), 200)]), [STACK],
                               {"current": {"token": "synthetic"}},
                               on_error=lambda slug, reason: errors.append(reason))
    assert records == {"current": {"available": True, "library_panel_count": 2}}
    # The public reader result is the payload root can persist; inspect it after serialization too.
    output = tmp_path / "diagnostic.json"
    output.write_text(json.dumps(records))
    assert PRIVATE not in output.read_text() + json.dumps(errors) + caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("ids", [[], [1], list(range(1, 101))])
def test_complete_empty_positive_and_exact_page_size(ids):
    calls = []
    assert source.fetch_library_panels(client_for([(page(ids), 200)], calls), STACK, "synthetic") == {
        "available": True, "library_panel_count": len(ids)}
    assert len(calls) == 2
    assert calls[0] == STACK["url"] + "/api/access-control/user/permissions"


def test_complete_pagination_and_inventory_left_join():
    calls = []
    result = source.probe_all(client_for([(page(range(1, 101), total=101), 200),
                                         (page([101], 2, 101), 200)], calls),
                              [STACK, {**STACK, "slug": "paused", "status": "paused"}],
                              {"current": {"token": "synthetic"}, "departed": {"token": "synthetic"}})
    assert result == {"current": {"available": True, "library_panel_count": 101}}
    assert len(calls) == 3
    client = mock.Mock()
    assert source.probe_all(client, [], {"departed": {"token": "synthetic"}}) == {}
    client.get.assert_not_called()


@pytest.mark.parametrize("second,status", [
    (page([101], 2, 101), 206), (page([101], 2, 102), 200),
    (page([100], 2, 101), 200), (page([], 2, 101), 200),
    (page([101], 1, 101), 200), (page([101, 102], 2, 101), 200),
    ({"error": PRIVATE}, 403),
])
def test_incomplete_later_page_discards_partial_count(second, status, capsys, caplog):
    errors = []
    record = source.probe_all(client_for([(page(range(1, 101), total=101), 200), (second, status)]),
                              [STACK], {"current": {"token": "synthetic"}},
                              on_error=lambda slug, reason: errors.append(reason))["current"]
    assert not record["available"]
    assert "library_panel_count" not in record
    assert PRIVATE not in json.dumps([record, errors]) + caplog.text + capsys.readouterr().out


def malformed_bodies():
    bodies = [[], {}, {"result": []}, page([1, 1]), page([True]), page([0]), page(["1"]),
              page([1], total=100001), page([1], total=2)]
    for field, value in [("page", True), ("page", 2), ("perPage", 99), ("perPage", True),
                         ("totalCount", True), ("totalCount", -1), ("totalCount", "1")]:
        body = page([1])
        body["result"][field] = value
        bodies.append(body)
    for field in ("elements", "page", "perPage", "totalCount"):
        body = page([1])
        del body["result"][field]
        bodies.append(body)
    for value in (None, {}, [None], [{"id": 1, "kind": 2}], [{"id": 1, "kind": True}], [{"kind": 1}]):
        body = page([1])
        body["result"]["elements"] = value
        bodies.append(body)
    return bodies


@pytest.mark.parametrize("body", malformed_bodies())
def test_malformed_and_bounded_responses_are_unavailable(body):
    assert not source.fetch_library_panels(client_for([(body, 200)]), STACK, "synthetic")["available"]


@pytest.mark.parametrize("status", [201, 204, 206, 301, 401, 403, 404, 500])
def test_exact_200_required(status):
    assert source.fetch_library_panels(client_for([(page([1]), status)]), STACK, "synthetic") == {
        "available": False, "reason": "unreadable"}


def test_safe_preconditions_and_exception_sanitization(caplog, capsys):
    client = mock.Mock()
    for url in ("http://host.test", "https://user:pass@host.test", "https://host.test/?x=y",
                "https://host.test/#fragment", "https://host.test/api"):
        assert source.fetch_library_panels(client, {**STACK, "url": url}, "synthetic") == {
            "available": False, "reason": "invalid_url"}
    assert source.fetch_library_panels(client, STACK, "") == {"available": False, "reason": "no_credential"}
    client.get.assert_not_called()
    client.get.side_effect = RuntimeError(PRIVATE)
    result = source.fetch_library_panels(client, STACK, "synthetic")
    assert result == {"available": False, "reason": "transport_error"}
    assert PRIVATE not in json.dumps(result) + caplog.text + capsys.readouterr().out
    with mock.patch.object(source, "MAX_PAGES", 1):
        assert not source.fetch_library_panels(
            client_for([(page(range(1, 101), total=101), 200)]), STACK, "synthetic")["available"]


@pytest.mark.parametrize("permissions", [
    {}, {"library.panels:read": ["folders:*"]}, {"folders:read": ["folders:*"]},
    {"library.panels:read": ["folders:uid:sharedwithme"], "folders:read": ["folders:*"]},
    {"library.panels:read": ["folders:*"], "folders:read": ["folders:uid:sharedwithme"]},
    {"library.panels:read": ["*"], "folders:read": ["folders:*"]},
])
def test_filtered_200_zero_without_either_exact_grant_is_absent(permissions, tmp_path, caplog, capsys):
    errors, calls = [], []
    records = source.probe_all(client_for([(page([]), 200)], calls, permissions=permissions),
                              [STACK], {"current": {"token": "synthetic"}},
                              on_error=lambda slug, reason: errors.append(reason))
    output = tmp_path / "diagnostic.json"
    output.write_text(json.dumps(records))
    assert records["current"]["available"] is False
    assert "library_panel_count" not in output.read_text()
    assert calls == [STACK["url"] + "/api/access-control/user/permissions"]
    assert PRIVATE not in output.read_text() + json.dumps(errors) + caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("permissions,status", [
    (PERMISSIONS, 206), (PERMISSIONS, 403), (PERMISSIONS, 500),
    ([], 200), (PRIVATE, 200),
    ({**PERMISSIONS, "folders:read": "folders:*"}, 200),
    ({**PERMISSIONS, "folders:read": ["folders:*", None]}, 200),
    ({**PERMISSIONS, "folders:read": {"folders:*": True}}, 200),
    ({**PERMISSIONS, "unknown": [True]}, 200),
])
def test_unreadable_or_malformed_permissions_never_publish(permissions, status):
    calls = []
    result = source.fetch_library_panels(client_for([(page([]), 200)], calls,
                                         permissions=permissions, permission_status=status), STACK, "synthetic")
    assert result == {"available": False, "reason": "coverage_unavailable"}
    assert len(calls) == 1


def test_permission_exception_is_sanitized_and_prevents_collection():
    client = mock.Mock()
    client.get.return_value.status = 200
    client.get.return_value.json.side_effect = ValueError(PRIVATE)
    result = source.fetch_library_panels(client, STACK, "synthetic")
    assert result == {"available": False, "reason": "transport_error"}
    assert PRIVATE not in json.dumps(result)
    client.get.assert_called_once_with(STACK["url"] + "/api/access-control/user/permissions",
                                       bearer="synthetic", guarded=True)


def test_input_response_not_mutated():
    body = page([1])
    before = copy.deepcopy(body)
    client = mock.Mock()
    client.get.return_value.status = 200
    client.get.side_effect = [mock.Mock(status=200, json=lambda: PERMISSIONS),
                              mock.Mock(status=200, json=lambda: body)]
    assert source.fetch_library_panels(client, STACK, "synthetic")["library_panel_count"] == 1
    assert body == before
