"""Public dashboard ENUMERATION (PLAN 18.17).

The two tests that matter most here guard against the two ways this check can lie:

- `accessToken` is the live public URL, so storing it would publish the customer's exposure through our
  own S3 views.
- the endpoint answers **200 with a permission-filtered list**, never 403, so an unreadable stack must
  never be reported as a compliant zero. On a zero-tolerance policy that is the worst possible defect.
"""

from __future__ import annotations

import unittest

from collector.sources import public_dashboards as pd


def item(title="Ops overview", uid="abc123", enabled=True, token="LIVE-PUBLIC-URL-TOKEN",
         public_uid=None):
    return {"title": title, "dashboardUid": uid, "isEnabled": enabled,
            "accessToken": token, "uid": public_uid or f"pd-{uid}", "slug": "ops-overview"}


def body(items, total=None):
    return {"publicDashboards": items, "totalCount": total if total is not None else len(items),
            "page": 1, "perPage": 1000}


class Client:
    def __init__(self, status=200, payload=None):
        self.status, self.payload, self.urls = status, payload, []

    def get(self, url, **kw):
        self.urls.append(url)
        outer = self

        class R:
            status = outer.status

            @property
            def ok(self):
                return 200 <= self.status < 300

            def json(self):
                return outer.payload
        return R()


class PagingClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        payload = self.payloads[len(self.calls) - 1]

        class R:
            status = 200
            ok = True

            def json(self):
                return payload
        return R()


class NeverStoreAccessTokenTest(unittest.TestCase):
    def test_strip_removes_the_access_token(self):
        self.assertNotIn("accessToken", pd.strip(item()))

    def test_no_access_token_survives_a_probe(self):
        """Asserted on the whole record's text, not on a key name - a future field carrying the same
        value would slip past a key check, and this value is a working public URL."""
        out = pd.probe_stack(Client(200, body([item()])), {"slug": "s", "url": "https://s.example"}, "t")
        self.assertNotIn("LIVE-PUBLIC-URL-TOKEN", repr(out))

    def test_the_dashboard_uid_IS_kept_because_it_is_how_you_fix_it(self):
        out = pd.probe_stack(Client(200, body([item(uid="wanted")])),
                             {"slug": "s", "url": "https://s.example"}, "t")
        self.assertEqual(out["dashboards"][0]["dashboard_uid"], "wanted")


class CountingTest(unittest.TestCase):
    def test_it_pages_until_the_api_total_is_satisfied(self):
        c = PagingClient([
            {"publicDashboards": [item(uid="one")], "totalCount": 2, "page": 1, "perPage": 1},
            {"publicDashboards": [item(uid="two", enabled=False)],
             "totalCount": 2, "page": 2, "perPage": 1},
        ])
        out = pd.probe_stack(c, {"slug": "s", "url": "https://s.example"}, "t")
        self.assertEqual(out["state"], pd.OK)
        self.assertEqual(out["listed"], 2)
        self.assertEqual([call[1]["params"]["page"] for call in c.calls], [1, 2])

    def test_enabled_is_counted_separately_from_existing(self):
        """A disabled public dashboard is still a configured share - it is one click from live - so it
        counts towards the policy breach while `enabled` says what is exposed right now."""
        out = pd.probe_stack(
            Client(200, body([item(uid="one", enabled=True), item(uid="two", enabled=False),
                              item(uid="three", enabled=True)])),
            {"slug": "s", "url": "https://s.example"}, "t")
        self.assertEqual(out["total"], 3)
        self.assertEqual(out["enabled"], 2)

    def test_enabled_is_counted_from_the_full_response_not_the_detail_sample(self):
        rows = [item(uid=f"disabled-{n}", enabled=False) for n in range(pd.MAX_DETAIL)]
        rows += [item(uid="enabled-after-sample", enabled=True)]
        out = pd.probe_stack(Client(200, body(rows)),
                             {"slug": "s", "url": "https://s.example"}, "t")
        self.assertEqual(len(out["dashboards"]), pd.MAX_DETAIL)
        self.assertEqual(out["enabled"], 1)

    def test_an_api_total_that_cannot_be_satisfied_is_truncated_not_ok(self):
        """A short list is not a successful compliance measurement, even when every page was 200."""
        c = PagingClient([
            {"publicDashboards": [item()], "totalCount": 9, "page": 1, "perPage": 1000},
            {"publicDashboards": [], "totalCount": 9, "page": 2, "perPage": 1000},
        ])
        out = pd.probe_stack(c, {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], "truncated")
        self.assertNotIn("total", out)

    def test_a_total_that_changes_between_pages_is_not_ok(self):
        c = PagingClient([
            {"publicDashboards": [item(uid="one")], "totalCount": 2, "page": 1, "perPage": 1},
            {"publicDashboards": [item(uid="two")], "totalCount": 3, "page": 2, "perPage": 1},
        ])
        out = pd.probe_stack(c, {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], "truncated")

    def test_a_server_that_repeats_page_one_is_not_ok(self):
        c = PagingClient([
            {"publicDashboards": [item(uid="one")], "totalCount": 2, "page": 1, "perPage": 1},
            {"publicDashboards": [item(uid="one")], "totalCount": 2, "page": 1, "perPage": 1},
        ])
        out = pd.probe_stack(c, {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], "truncated")

    def test_a_duplicate_public_uid_across_pages_is_not_ok(self):
        c = PagingClient([
            {"publicDashboards": [item(uid="one", public_uid="same")],
             "totalCount": 2, "page": 1, "perPage": 1},
            {"publicDashboards": [item(uid="two", public_uid="same")],
             "totalCount": 2, "page": 2, "perPage": 1},
        ])
        out = pd.probe_stack(c, {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], "truncated")

    def test_a_genuinely_empty_stack_is_ok_and_zero(self):
        out = pd.probe_stack(Client(200, body([])), {"slug": "s", "url": "https://s.example"}, "t")
        self.assertTrue(out["available"])
        self.assertEqual(out["state"], pd.OK)
        self.assertEqual(out["total"], 0)

    def test_the_detail_list_is_bounded(self):
        out = pd.probe_stack(Client(200, body([item(uid=f"dash-{n}") for n in range(60)])),
                             {"slug": "s", "url": "https://s.example"}, "t")
        self.assertEqual(len(out["dashboards"]), pd.MAX_DETAIL)
        self.assertEqual(out["total"], 60, "the COUNT must stay honest when the list is truncated")


class NotMeasuredIsNotZeroTest(unittest.TestCase):
    def test_no_credential_is_not_a_successful_zero_at_the_source(self):
        c = Client(200, body([]))
        out = pd.probe_stack(c, {"slug": "s", "url": "https://s.example"}, "")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], pd.NO_CREDENTIAL)
        self.assertNotIn("total", out)
        self.assertEqual(c.urls, [])

    def test_a_403_is_UNAVAILABLE_never_a_compliant_zero(self):
        """This endpoint answers 200-with-a-filtered-list rather than 403 when the ROLE is missing, so
        a 403 here means the token itself is refused. Either way it is not evidence of compliance."""
        out = pd.probe_stack(Client(403, {}), {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], pd.FORBIDDEN)
        self.assertNotIn("total", out)

    def test_a_401_is_UNAVAILABLE(self):
        out = pd.probe_stack(Client(401, {}), {"slug": "s", "url": "https://s.example"}, "t")
        self.assertEqual(out["state"], pd.UNAUTHORISED)

    def test_only_ok_counts_as_readable(self):
        """The whole state vocabulary exists so a rollup can refuse to add up unreadable stacks."""
        self.assertEqual(pd.READABLE, frozenset({pd.OK}))
        for state in (pd.NO_CREDENTIAL, pd.UNAUTHORISED, pd.FORBIDDEN, pd.HTTP_ERROR,
                      pd.TRANSPORT_ERROR, pd.TRUNCATED):
            self.assertNotIn(state, pd.READABLE)

    def test_a_200_that_is_not_an_object_is_an_error(self):
        out = pd.probe_stack(Client(200, []), {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])

    def test_a_200_with_a_non_list_dashboard_collection_is_an_error(self):
        payload = {"publicDashboards": {"uid": "not-a-list"}, "totalCount": 1,
                   "page": 1, "perPage": 1000}
        out = pd.probe_stack(Client(200, payload),
                             {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], pd.HTTP_ERROR)

    def test_a_200_with_an_invalid_total_is_an_error(self):
        payload = {"publicDashboards": [], "totalCount": "unknown", "page": 1, "perPage": 1000}
        out = pd.probe_stack(Client(200, payload),
                             {"slug": "s", "url": "https://s.example"}, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["state"], pd.HTTP_ERROR)


class ProbeAllTest(unittest.TestCase):
    STACKS = [{"slug": "a", "url": "https://a.example"},
              {"slug": "p", "url": "https://p.example", "status": "paused"},
              {"slug": "n", "url": "https://n.example"}]

    def test_paused_skipped_missing_credential_is_its_own_state(self):
        out = pd.probe_all(Client(200, body([])), self.STACKS, {"a": {"token": "t"}})
        self.assertEqual(set(out), {"a", "n"})
        self.assertEqual(out["n"]["state"], pd.NO_CREDENTIAL)

    def test_a_departed_stack_gets_no_row(self):
        out = pd.probe_all(Client(200, body([])), self.STACKS,
                           {"a": {"token": "t"}, "gone": {"token": "t"}})
        self.assertNotIn("gone", out)

    def test_the_stacks_own_url_is_used(self):
        c = Client(200, body([]))
        pd.probe_all(c, [{"slug": "x", "url": "https://odd.example"}], {"x": {"token": "t"}})
        self.assertTrue(c.urls[0].startswith("https://odd.example/"))


if __name__ == "__main__":
    unittest.main()
