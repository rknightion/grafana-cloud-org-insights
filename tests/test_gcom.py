"""gcom source contracts that are unsafe to undercount silently."""

from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from collector.config import GCOM
from collector.httpclient import Response
from collector.sources import gcom


def policy(policy_id: str, name: str) -> dict:
    return {
        "id": policy_id,
        "name": name,
        "realms": [{"type": "org", "identifier": "example"}],
        "scopes": ["stacks:read"],
        "createdAt": "2026-01-01T00:00:00Z",
        "status": "active",
    }


def page(items, next_page=None) -> dict:
    return {
        "items": items,
        "metadata": {"pagination": {
            "pageSize": 500,
            "pageCursor": None,
            "nextPage": next_page,
        }},
    }


class Client:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        payload = self.payloads.pop(0)
        return Response(status=200, body=json.dumps(payload).encode(), url=url)


class FailingSecondPageClient(Client):
    def get(self, url, **kwargs):
        if self.calls:
            self.calls.append((url, kwargs))
            return Response(status=500, body=b"{}", url=url)
        return super().get(url, **kwargs)


CFG = SimpleNamespace(cap="read-token")


class OrgMembersTest(unittest.TestCase):
    def test_it_preserves_identity_role_and_staff_access_metadata(self):
        payload = {
            "direction": "asc",
            "items": [
                {
                    "id": 101,
                    "userId": 201,
                    "userName": "Ada Lovelace",
                    "userEmail": "ada@example.test",
                    "userUsername": "ada",
                    "role": "Admin",
                    "createdAt": "2026-01-02T03:04:05.000Z",
                    "mfaEnabled": True,
                    "grafanaStaffAccess": {
                        "accessExpiresAt": "2027-01-02T03:04:05.000Z",
                        "publicReason": "Support engagement",
                        "ticketId": "SUP-123",
                    },
                },
            ],
            "links": [{"rel": "self", "href": "/orgs/123456/members"}],
            "orderBy": "userUsername",
        }
        fetch = getattr(gcom, "fetch_org_members", None)
        self.assertIsNotNone(fetch, "the org-members source is not implemented")

        out = fetch(Client([payload]), SimpleNamespace(cap="read-token", org_id="123456"))

        self.assertEqual(out, {
            "state": "ok",
            "members": [{
                "id": 101,
                "user_id": 201,
                "name": "Ada Lovelace",
                "email": "ada@example.test",
                "login": "ada",
                "role": "Admin",
                "created_at": "2026-01-02T03:04:05.000Z",
                "mfa_enabled": True,
                "staff_access": {
                    "expires_at": "2027-01-02T03:04:05.000Z",
                    "reason": "Support engagement",
                    "ticket_id": "SUP-123",
                },
            }],
        })

    def test_it_refuses_a_response_without_the_member_list(self):
        with self.assertRaisesRegex(RuntimeError, "missing items"):
            gcom.fetch_org_members(
                Client([{"direction": "asc", "links": []}]),
                SimpleNamespace(cap="read-token", org_id="123456"),
            )

    def test_it_refuses_a_non_object_response(self):
        with self.assertRaisesRegex(RuntimeError, "missing items"):
            gcom.fetch_org_members(
                Client([42]), SimpleNamespace(cap="read-token", org_id="123456")
            )

    def test_it_refuses_a_member_without_a_stable_id_or_role(self):
        payload = {"items": [{"id": 101, "userId": 201, "userName": "Unknown role"}]}
        with self.assertRaisesRegex(RuntimeError, "missing role"):
            gcom.fetch_org_members(
                Client([payload]), SimpleNamespace(cap="read-token", org_id="123456")
            )

    def test_a_malformed_staff_window_is_not_collapsed_into_no_access(self):
        payload = {"items": [{
            "id": 101, "userId": 201, "userName": "Ada", "role": "Admin",
            "grafanaStaffAccess": "unexpected",
        }]}
        out = gcom.fetch_org_members(
            Client([payload]), SimpleNamespace(cap="read-token", org_id="123456")
        )
        self.assertEqual(out["members"][0]["staff_access"], {
            "expires_at": None, "reason": None, "ticket_id": None,
        })


class AccessPolicyPaginationTest(unittest.TestCase):
    def test_it_follows_the_live_nextpage_shape(self):
        next_page = "/v1/accesspolicies?region=us&pageSize=1&pageCursor=cursor-1"
        c = Client([
            page([policy("one", "first")], next_page),
            page([policy("two", "second")]),
            page([]),
            page([]),
        ])
        out = gcom.fetch_access_policies(c, CFG)
        self.assertEqual([p["name"] for p in out], ["first", "second"])
        self.assertEqual(c.calls[1][0], f"{GCOM}/v1/accesspolicies?pageSize=1&pageCursor=cursor-1")
        self.assertTrue(all(call[1].get("params", {}).get("region") for call in c.calls))

    def test_it_accepts_an_absolute_same_origin_nextpage_and_retains_region(self):
        next_page = f"{GCOM}/v1/accesspolicies?pageCursor=cursor-1"
        c = Client([
            page([policy("one", "first")], next_page),
            page([policy("two", "second")]),
            page([]),
            page([]),
        ])
        out = gcom.fetch_access_policies(c, CFG)
        self.assertEqual([p["name"] for p in out], ["first", "second"])
        self.assertEqual(c.calls[1][1]["params"]["region"], "us")

    def test_it_refuses_a_cross_origin_nextpage_before_sending_the_token(self):
        c = Client([page([policy("one", "first")], "https://attacker.example/steal")])
        with self.assertRaisesRegex(RuntimeError, "unsafe nextPage"):
            gcom.fetch_access_policies(c, CFG)
        self.assertEqual(len(c.calls), 1)

    def test_it_deduplicates_a_policy_repeated_across_pages(self):
        next_page = "/v1/accesspolicies?region=us&pageCursor=cursor-1"
        c = Client([
            page([policy("same-id", "first copy")], next_page),
            page([policy("same-id", "second copy")]),
            page([]),
            page([]),
        ])
        out = gcom.fetch_access_policies(c, CFG)
        self.assertEqual([p["name"] for p in out], ["first copy"])

    def test_it_refuses_a_repeated_nextpage_cursor(self):
        repeated = "/v1/accesspolicies?region=us&pageCursor=same"
        c = Client([
            page([policy("one", "first")], repeated),
            page([policy("two", "second")], repeated),
        ])
        with self.assertRaisesRegex(RuntimeError, "repeated nextPage"):
            gcom.fetch_access_policies(c, CFG)
        self.assertEqual(len(c.calls), 2)

    def test_it_refuses_a_policy_without_the_live_stable_id(self):
        malformed = policy("ignored", "nameless identity")
        malformed.pop("id")
        c = Client([page([malformed])])
        with self.assertRaisesRegex(RuntimeError, "missing id"):
            gcom.fetch_access_policies(c, CFG)

    def test_a_failed_next_page_cannot_return_a_partial_success(self):
        next_page = "/v1/accesspolicies?region=us&pageCursor=cursor-1"
        c = FailingSecondPageClient([page([policy("one", "first")], next_page)])
        with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
            gcom.fetch_access_policies(c, CFG)


if __name__ == "__main__":
    unittest.main()
