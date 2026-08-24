"""The per-stack service-account inventory (PLAN 18.13).

The defect this replaces: the inventory was fetched through the gcom proxy with the ORG access policy,
which 403s for the deployment credential because no `stack-service-accounts:read` scope exists. So
`risk_service_accounts` published zero rows on every scheduled run, and the only time it looked healthy
was after a hand-run with a wider credential - which then got overwritten empty.

The stack-local `serviceaccounts:read` action was already in the provisioned role the whole time.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from collector.httpclient import Response
from collector.sources import serviceaccounts as sa


class FakeClient:
    """Records every URL asked for, so pagination and the left-join can both be asserted."""

    def __init__(self, pages, *, roles=(200, []), tokens=(200, [])):
        self.pages = pages          # search pages, in call order
        self.roles = roles
        self.tokens = tokens
        self.calls: list[tuple[str, dict]] = []
        self.search_calls = 0

    def get(self, url, *, params=None, headers=None, bearer=None, basic=None):
        self.calls.append((url, dict(params or {})))
        if "/serviceaccounts/search" in url:
            status, body = self.pages[min(self.search_calls, len(self.pages) - 1)]
            self.search_calls += 1
        elif url.endswith("/roles"):
            status, body = self.roles
        else:
            status, body = self.tokens
        if isinstance(body, Exception):
            raise body
        return Response(status=status, body=json.dumps(body).encode(), url=url)


def page(accounts, total=None):
    return 200, {"totalCount": total if total is not None else len(accounts),
                 "serviceAccounts": accounts}


def inventory_stack(slug="alpha", *, url=None):
    return {"slug": slug, "url": url or f"https://{slug}.example"}


ACCOUNT = {"id": 42, "name": "platform-admin", "role": "Admin", "isDisabled": False, "tokens": 19}
EXTSVC = {"id": 7, "name": "extsvc-grafana-assistant-app", "role": "Viewer",
          "isDisabled": False, "tokens": 1}

CUSTOM_ROLE = {"uid": "reader-uid", "name": "custom:estate.reader",
               "displayName": "Estate reader", "global": False,
               "description": "not needed in the view"}
FIXED_ROLE = {"uid": "fixed-uid", "name": "fixed:reports:writer",
              "displayName": "Report writer", "global": False}
PLUGIN_ROLE = {"uid": "plugin-uid", "name": "plugins:example-app:reader",
               "displayName": "Example reader", "global": False}
TOKEN = {"id": 91, "name": "automation", "role": "Admin",
         "created": "2026-01-02T03:04:05Z", "expiration": None,
         "secondsUntilExpiration": 0, "hasExpired": False,
         "lastUsedAt": "2026-08-20T17:00:00Z"}


class RecordShapeTest(unittest.TestCase):
    def test_it_classifies_grafanas_own_accounts(self):
        """`extsvc-*` outnumber real accounts ~9:1, so a combined count buries what matters."""
        self.assertEqual(sa.record(ACCOUNT)["kind"], "custom")
        self.assertEqual(sa.record(EXTSVC)["kind"], "extsvc")

    def test_it_keeps_only_the_fields_the_pillar_consumes(self):
        self.assertEqual(set(sa.record(ACCOUNT)), {
            "name", "kind", "role", "basic_role", "isDisabled", "tokens",
            "assigned_roles", "assigned_roles_total", "roles_state", "token_metadata", "tokens_state",
            "token_hygiene_state", "tokens_non_expiring", "tokens_never_used", "tokens_stale",
            "token_nearest_future_expiry",
        })

    def test_a_nameless_account_does_not_become_the_string_none(self):
        self.assertIsNone(sa.record({})["name"])
        self.assertEqual(sa.record({})["kind"], "custom")


class ProbeStackTest(unittest.TestCase):
    def test_every_request_uses_the_authoritative_inventory_url(self):
        stack = {"slug": "alpha", "url": "https://tenant.example/"}
        c = FakeClient([page([ACCOUNT])], roles=(200, []), tokens=(200, [TOKEN] * 19))

        sa.probe_stack(c, stack, "tok")

        self.assertEqual([url for url, _params in c.calls], [
            "https://tenant.example/api/serviceaccounts/search",
            "https://tenant.example/api/access-control/users/42/roles",
            "https://tenant.example/api/serviceaccounts/42/tokens",
        ])

    def test_missing_or_invalid_inventory_url_is_unavailable_without_a_request(self):
        for stack in (
            {"slug": "missing"},
            {"slug": "blank", "url": "  "},
            {"slug": "relative", "url": "tenant.example"},
            {"slug": "insecure", "url": "http://tenant.example"},
            {"slug": "credentials", "url": "https://user@tenant.example"},
            {"slug": "path", "url": "https://tenant.example/base"},
            {"slug": "query", "url": "https://tenant.example?x=1"},
            {"slug": "fragment", "url": "https://tenant.example#x"},
            {"slug": "port", "url": "https://tenant.example:not-a-port"},
            {"slug": "whitespace", "url": " https://tenant.example"},
        ):
            with self.subTest(stack=stack["slug"]):
                c = FakeClient([page([ACCOUNT])])
                out = sa.probe_stack(c, stack, "tok")
                self.assertEqual(out["state"], "invalid_url")
                self.assertEqual(out["accounts"], [])
                self.assertEqual(c.calls, [])

    def test_complete_token_metadata_is_folded_into_decision_ready_hygiene(self):
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        tokens = [
            {**TOKEN, "id": 1, "expiration": None, "lastUsedAt": None,
             "created": "2026-01-01T00:00:00Z"},
            {**TOKEN, "id": 2, "expiration": "2026-08-28T12:00:00Z",
             "secondsUntilExpiration": 604800, "lastUsedAt": "2026-01-01T00:00:00Z"},
            {**TOKEN, "id": 3, "expiration": "2026-09-21T12:00:00Z",
             "secondsUntilExpiration": 2678400, "lastUsedAt": "2026-08-20T00:00:00Z"},
        ]
        summary = sa.summarise_token_hygiene(tokens, now=now)

        self.assertEqual(summary, {
            "token_hygiene_state": sa.OK,
            "tokens_non_expiring": 1,
            "tokens_never_used": 1,
            "tokens_stale": 2,
            "token_nearest_future_expiry": "2026-08-28T12:00:00Z",
        })

    def test_never_used_token_is_stale_only_after_the_fixed_threshold(self):
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        fresh = {**TOKEN, "created": "2026-08-20T12:00:00Z", "lastUsedAt": None}
        old = {**TOKEN, "id": 92, "created": "2026-01-01T00:00:00Z", "lastUsedAt": None}

        summary = sa.summarise_token_hygiene([fresh, old], now=now)

        self.assertEqual(sa.TOKEN_STALE_AFTER_DAYS, 90)
        self.assertEqual(summary["tokens_never_used"], 2)
        self.assertEqual(summary["tokens_stale"], 1)

    def test_incomplete_token_metadata_is_unknown_never_a_confident_zero(self):
        summary = sa.summarise_token_hygiene([{"id": 1, "name": "shape drift"}])

        self.assertEqual(summary["token_hygiene_state"], sa.PARTIAL_METADATA)
        for field in (
            "tokens_non_expiring", "tokens_never_used", "tokens_stale",
            "token_nearest_future_expiry",
        ):
            self.assertIsNone(summary[field])

    def test_custom_accounts_include_basic_role_and_every_direct_assignment(self):
        roles = [CUSTOM_ROLE, FIXED_ROLE, PLUGIN_ROLE]
        c = FakeClient([page([ACCOUNT])], roles=(200, roles), tokens=(200, [TOKEN] * 19))
        out = sa.probe_stack(c, inventory_stack(), "tok")
        account = out["accounts"][0]
        self.assertEqual(account["basic_role"], "Admin")
        self.assertEqual(account["assigned_roles"], [
            {key: role[key] for key in ("uid", "name", "displayName", "global")}
            for role in roles
        ])
        self.assertEqual(account["roles_state"], sa.OK)
        self.assertEqual(c.calls[1][1], {"includeHidden": "true"})
        self.assertEqual([u for u, _p in c.calls], [
            "https://alpha.example" + sa.SEARCH_PATH,
            "https://alpha.example" + sa.ROLES_PATH.format(account_id=42),
            "https://alpha.example" + sa.TOKENS_PATH.format(account_id=42),
        ])

    def test_token_hygiene_keeps_metadata_but_never_a_secret(self):
        unsafe = {**TOKEN, "key": "LIVE-SECRET", "secret": "LIVE-SECRET",
                  "token": "LIVE-SECRET", "accessToken": "LIVE-SECRET"}
        one_token = {**ACCOUNT, "tokens": 1}
        c = FakeClient([page([one_token])], tokens=(200, [unsafe]))
        account = sa.probe_stack(c, inventory_stack(), "tok")["accounts"][0]
        self.assertEqual(account["tokens_state"], sa.OK)
        self.assertEqual(account["token_metadata"], [TOKEN])
        self.assertNotIn("LIVE-SECRET", repr(account))

    def test_a_short_token_listing_is_flagged_not_reported_as_complete(self):
        account_with_two = {**ACCOUNT, "tokens": 2}
        c = FakeClient([page([account_with_two])], tokens=(200, [TOKEN]))
        account = sa.probe_stack(c, inventory_stack(), "tok")["accounts"][0]
        self.assertEqual(account["tokens_state"], sa.TRUNCATED)
        self.assertIn("1 of 2", account["tokens_detail"])
        self.assertEqual(account["token_hygiene_state"], sa.TRUNCATED)
        self.assertIsNone(account["tokens_non_expiring"])

    def test_a_refused_token_listing_has_no_hygiene_zeroes(self):
        c = FakeClient([page([ACCOUNT])], tokens=(403, {}))
        account = sa.probe_stack(c, inventory_stack(), "tok")["accounts"][0]

        self.assertEqual(account["tokens_state"], sa.FORBIDDEN)
        self.assertEqual(account["token_hygiene_state"], sa.FORBIDDEN)
        self.assertIsNone(account["tokens_never_used"])
        self.assertIsNone(account["tokens_stale"])

    def test_assigned_role_detail_is_bounded_and_flagged(self):
        roles = [{**CUSTOM_ROLE, "uid": f"uid-{i}", "name": f"custom:role-{i}"}
                 for i in range(sa.MAX_ASSIGNED_ROLES_PER_ACCOUNT + 1)]
        c = FakeClient([page([ACCOUNT])], roles=(200, roles),
                       tokens=(200, [TOKEN] * ACCOUNT["tokens"]))
        account = sa.probe_stack(c, inventory_stack(), "tok")["accounts"][0]
        self.assertEqual(account["roles_state"], sa.TRUNCATED)
        self.assertEqual(account["assigned_roles_total"], sa.MAX_ASSIGNED_ROLES_PER_ACCOUNT + 1)
        self.assertEqual(len(account["assigned_roles"]), sa.MAX_ASSIGNED_ROLES_PER_ACCOUNT)

    def test_a_single_page_makes_one_inventory_call(self):
        c = FakeClient([page([ACCOUNT, EXTSVC])])
        out = sa.probe_stack(c, inventory_stack(), "tok")
        self.assertEqual(out["state"], sa.OK)
        self.assertEqual(len(out["accounts"]), 2)
        self.assertEqual(c.search_calls, 1, "no second inventory page when the first is complete")

    def test_it_pages_until_totalcount_is_satisfied(self):
        """Undercounting an inventory reads as good hygiene, which is the worst way to be wrong."""
        c = FakeClient([page([ACCOUNT], total=3), page([EXTSVC], total=3), page([ACCOUNT], total=3)])
        out = sa.probe_stack(c, inventory_stack(), "tok")
        self.assertEqual(out["state"], sa.OK)
        self.assertEqual(len(out["accounts"]), 3)
        self.assertEqual([p["page"] for u, p in c.calls if "/serviceaccounts/search" in u], [1, 2, 3])

    def test_an_empty_final_page_before_totalcount_is_truncated(self):
        """A short inventory reads as good hygiene, so it must never be published as successful."""
        c = FakeClient([page([ACCOUNT], total=99), page([], total=99)])
        out = sa.probe_stack(c, inventory_stack(), "tok")
        self.assertEqual(out["state"], sa.TRUNCATED)
        self.assertEqual(out["accounts"], [])
        self.assertEqual(c.search_calls, 2)

    def test_running_out_of_pages_is_reported_as_truncated_not_as_success(self):
        c = FakeClient([page([ACCOUNT], total=10_000)])
        out = sa.probe_stack(c, inventory_stack(), "tok")
        self.assertEqual(out["state"], sa.TRUNCATED)
        self.assertEqual(out["accounts"], [], "a consumer must not sum a known-short inventory")
        self.assertEqual(c.search_calls, sa.MAX_PAGES)

    def test_no_credential_is_its_own_state_and_makes_no_call(self):
        """A stack awaiting provisioning is not a stack with no service accounts."""
        c = FakeClient([page([ACCOUNT])])
        out = sa.probe_stack(c, inventory_stack(), "")
        self.assertEqual(out["state"], sa.NO_CREDENTIAL)
        self.assertEqual(c.calls, [])

    def test_401_and_403_are_distinguished(self):
        """They need different repairs: re-mint the token versus re-patch the role."""
        self.assertEqual(sa.probe_stack(FakeClient([(401, {})]), inventory_stack("a"), "t")["state"],
                         sa.UNAUTHORISED)
        self.assertEqual(sa.probe_stack(FakeClient([(403, {})]), inventory_stack("a"), "t")["state"],
                         sa.FORBIDDEN)

    def test_other_http_and_transport_failures_are_neither_of_those(self):
        self.assertEqual(sa.probe_stack(FakeClient([(500, {})]), inventory_stack("a"), "t")["state"],
                         sa.HTTP_ERROR)
        c = FakeClient([(200, TimeoutError("boom"))])
        self.assertEqual(sa.probe_stack(c, inventory_stack("a"), "t")["state"], sa.TRANSPORT_ERROR)

    def test_a_200_with_no_totalcount_is_not_a_complete_inventory(self):
        c = FakeClient([(200, {"serviceAccounts": [ACCOUNT]})])
        out = sa.probe_stack(c, inventory_stack("a"), "t")
        self.assertEqual(out["state"], sa.HTTP_ERROR)
        self.assertEqual(out["accounts"], [])

    def test_extsvc_accounts_are_explicitly_skipped_without_extra_requests(self):
        c = FakeClient([page([EXTSVC])])
        account = sa.probe_stack(c, inventory_stack("a"), "t")["accounts"][0]
        self.assertEqual(account["roles_state"], sa.SKIPPED_EXTSVC)
        self.assertEqual(account["tokens_state"], sa.SKIPPED_EXTSVC)
        self.assertEqual(len(c.calls), 1)

    def test_failed_role_enrichment_is_not_an_empty_role_set_and_does_not_suppress_tokens(self):
        c = FakeClient([page([ACCOUNT])], roles=(403, {}), tokens=(200, [TOKEN] * 19))
        account = sa.probe_stack(c, inventory_stack("a"), "t")["accounts"][0]
        self.assertEqual(account["roles_state"], sa.FORBIDDEN)
        self.assertEqual(account["assigned_roles"], [])
        self.assertEqual(account["tokens_state"], sa.OK)
        self.assertEqual(len(account["token_metadata"]), 19)

    def test_no_failure_state_ever_carries_accounts(self):
        """A partial list beside a failure state would be summed by a consumer reading only accounts."""
        for status in (401, 403, 500):
            with self.subTest(status=status):
                self.assertEqual(
                    sa.probe_stack(FakeClient([(status, {})]), inventory_stack("a"), "t")["accounts"],
                    [],
                )


class ProbeAllTest(unittest.TestCase):
    """The golden rule: the LIVE inventory drives the sweep, the credential store is a left join."""

    STACKS = [{"slug": "alpha", "url": "https://alpha.example", "status": "active"},
              {"slug": "beta", "url": "https://beta.example", "status": "active"},
              {"slug": "paused-one", "url": "https://paused.example", "status": "paused"}]

    def test_a_stack_with_no_stored_credential_still_gets_a_row(self):
        c = FakeClient([page([ACCOUNT])])
        out = sa.probe_all(c, self.STACKS, {"alpha": {"token": "t"}})
        self.assertEqual(out["beta"]["state"], sa.NO_CREDENTIAL)
        self.assertEqual(out["alpha"]["state"], sa.OK)

    def test_a_credential_for_a_departed_stack_produces_no_row(self):
        """Iterating the store would keep a decommissioned stack alive until its parameter was deleted."""
        c = FakeClient([page([ACCOUNT])])
        out = sa.probe_all(c, self.STACKS, {"alpha": {"token": "t"}, "gone": {"token": "t"}})
        self.assertNotIn("gone", out)

    def test_paused_stacks_are_skipped_rather_than_recorded_as_broken(self):
        """A paused stack answers 403 here, which would read as a role that needs repairing."""
        c = FakeClient([page([ACCOUNT])])
        out = sa.probe_all(c, self.STACKS, {s["slug"]: {"token": "t"} for s in self.STACKS})
        self.assertNotIn("paused-one", out)

    def test_only_real_failures_reach_on_error(self):
        """`no_credential` is a provisioning state that self-heals; reporting it as an error is noise."""
        seen: list[tuple[str, str]] = []
        c = FakeClient([(403, {})])
        sa.probe_all(c, self.STACKS, {"alpha": {"token": "t"}}, on_error=lambda s, m: seen.append((s, m)))
        self.assertEqual([s for s, _m in seen], ["alpha"])


if __name__ == "__main__":
    unittest.main()
