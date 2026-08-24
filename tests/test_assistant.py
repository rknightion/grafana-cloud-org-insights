"""`collector/sources/assistant.py` - the per-stack Assistant reads.

Every fixture in here is a real payload shape, trimmed. The API's dataframe envelope and its
epoch-millisecond bound are external contracts, so a test written from the implementation would only
prove the implementation agrees with itself; these were taken from live 200s on obs-hub-dev, stack024,
stack023 and stack152 on 2026-08-20.
"""

from __future__ import annotations

import datetime as dt
import json
import unittest
import urllib.parse
import urllib.request

from collector.httpclient import ReadOnlyClient, Response
from collector.sources import assistant as A

NOW = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.timezone.utc)


def frame(fields, values):
    return {"status": "success",
            "data": {"schema": {"fields": fields}, "data": {"values": values}}}


HERO = {"status": "success", "data": {
    "totalActiveUsers": 5, "totalUserMessages": 49, "totalInvestigationsCreated": 0,
    "totalTokens": 14_677_233, "totalInvestigationTokens": 0, "totalChatTokens": 14_677_233}}

CATEGORIES = frame(
    [{"name": "time", "type": "time"},
     {"name": "Investigate (web)", "type": "number"},
     {"name": "Investigate (cli)", "type": "number"},
     {"name": "Other (lodestone)", "type": "number"}],
    [[1, 2], [3, 0], [2, 3], [0, 1]],
)
# The API's way of saying zero: the time field only. NOT a set of zero-valued fields.
INVESTIGATIONS_EMPTY = frame([{"name": "time", "type": "time"}], [[1, 2]])
INVESTIGATIONS = frame(
    [{"name": "time", "type": "time"},
     {"name": "assistant (created)", "type": "number"},
     {"name": "user (created)", "type": "number"}],
    [[1, 2], [2, 1], [1, 1]],
)
ACTIVE_USERS = frame([{"name": "time", "type": "time"}, {"name": "active_users", "type": "number"}],
                     [[1, 2, 3, 4], [0, 1, 1, 0]])

SKILL = {"id": "u-1", "name": "Onboarding", "scope": "tenant", "createdBy": "sa-17@serviceaccount.grafana",
         "created": "2026-07-31T13:30:52.435Z", "modified": "2026-07-31T13:30:52.435Z",
         "body": "x" * 40_000, "includeInKnowledgebase": True, "version": 1}
MCP = {"id": "u-2", "name": "Corp Confluence", "type": "mcp", "enabled": True, "scope": "tenant",
       "authenticationFailed": False, "createdBy": "sa-17@serviceaccount.grafana",
       "created": "2026-07-31T13:30:52.412Z", "modified": "2026-08-20T09:54:50.559Z",
       "configuration": {"url": "https://confluence.example.com/mcp/"},
       "customHeaders": [{"key": "Authorization", "value": "<redacted>"}]}

BODIES = {
    "api/v1/usage/hero-stats": HERO,
    "api/v1/usage/chat-categories": CATEGORIES,
    "api/v1/usage/investigations": INVESTIGATIONS_EMPTY,
    "api/v1/usage/active-users": ACTIVE_USERS,
    "api/v1/skills": {"status": "success",
                      "data": {"skills": [SKILL], "pagination": {"total": 1, "limit": 200, "offset": 0}}},
    "api/v1/rules": {"status": "success",
                     "data": {"rules": [], "pagination": {"total": 0, "limit": 200, "offset": 0}}},
    # No `pagination` block at all - the length is the only count available here.
    "api/v1/automations": {"status": "success", "data": {"automations": []}},
    "api/v1/integrations": {"status": "success",
                            "data": {"integrations": [MCP],
                                     "pagination": {"total": 1, "limit": 200, "offset": 0}}},
}


def transport(status_for=None, seen=None):
    """Serve BODIES by path. `status_for(path) -> int` overrides the status for one path."""
    seen = seen if seen is not None else []

    def send(req: urllib.request.Request, timeout: float) -> Response:
        parsed = urllib.parse.urlparse(req.full_url)
        path = parsed.path.split("/resources/", 1)[-1]
        seen.append((path, urllib.parse.parse_qs(parsed.query)))
        status = (status_for or (lambda p: 200))(path)
        body = json.dumps(BODIES.get(path, {"status": "success", "data": {}})).encode()
        return Response(status=status, body=body, url=req.full_url)

    send.seen = seen  # type: ignore[attr-defined]
    return send


def client(status_for=None, seen=None) -> ReadOnlyClient:
    return ReadOnlyClient(transport=transport(status_for, seen), max_attempts=1)


class WindowTest(unittest.TestCase):
    """The trap that returns HTTP 200 with every value zero."""

    def test_bounds_are_epoch_milliseconds_not_seconds(self):
        start, end = A.window(NOW)
        self.assertEqual(end, 1787227200000)
        # Thirteen digits, not ten. A seconds-based bound is silently answered with zeros, so the
        # magnitude IS the contract.
        self.assertEqual(len(str(end)), 13)
        self.assertEqual(end - start, A.WINDOW_DAYS * 86400 * 1000)

    def test_the_query_string_actually_carries_milliseconds(self):
        seen: list = []
        A.probe_stack(client(seen=seen), "s", "tok", now=NOW)
        _, params = seen[0]
        self.assertEqual(params["start"], ["1784635200000"])
        self.assertEqual(params["end"], ["1787227200000"])

    def test_window_is_thirty_days(self):
        self.assertEqual(A.WINDOW_DAYS, 30)


class FrameParsingTest(unittest.TestCase):
    def test_time_field_is_never_summed(self):
        self.assertEqual(A.frame_sums(CATEGORIES),
                         {"Investigate (web)": 3.0, "Investigate (cli)": 5.0, "Other (lodestone)": 1.0})

    def test_a_time_only_frame_is_an_absent_breakdown_not_a_set_of_zeros(self):
        """`usage/investigations` returns the time field alone when the count is zero."""
        self.assertEqual(A.frame_sums(INVESTIGATIONS_EMPTY), {})

    def test_investigation_origins_are_parsed_from_dynamic_field_names(self):
        self.assertEqual(A.frame_sums(INVESTIGATIONS),
                         {"assistant (created)": 3.0, "user (created)": 2.0})

    def test_missing_and_malformed_frames_do_not_raise(self):
        for body in (None, {}, {"data": {}}, {"data": {"schema": {}, "data": {}}},
                     {"data": {"schema": {"fields": [{"name": "x", "type": "number"}]},
                               "data": {"values": []}}}):
            self.assertEqual(A.frame_sums(body), {})
            self.assertEqual(A.days_active(body), 0)

    def test_days_active_counts_buckets_not_users(self):
        """`active-users` is a DAILY bucket; summing it would double-count a returning user."""
        self.assertEqual(A.days_active(ACTIVE_USERS), 2)

    def test_non_numeric_values_are_skipped_rather_than_crashing(self):
        body = frame([{"name": "time", "type": "time"}, {"name": "n", "type": "number"}],
                     [[1, 2, 3], [1, None, "x"]])
        self.assertEqual(A.frame_sums(body), {"n": 1.0})


class CategoryParsingTest(unittest.TestCase):
    def test_every_observed_surface_parses(self):
        for name, expected in (
            ("Dashboard (web)", ("Dashboard", "web")),
            ("Investigate (cli)", ("Investigate", "cli")),
            ("Learn (a2a)", ("Learn", "a2a")),
            ("Investigate (automation)", ("Investigate", "automation")),
            ("Other (lodestone)", ("Other", "lodestone")),
            ("Observe (slack)", ("Observe", "slack")),
            ("Errors (lodestone)", ("Errors", "lodestone")),
        ):
            self.assertEqual(A.split_category(name), expected)

    def test_an_unparseable_name_is_visible_rather_than_silent(self):
        """An API change must show up as an odd row, not be quietly dropped."""
        self.assertEqual(A.split_category("weird"), ("weird", "unknown"))
        self.assertEqual(A.split_category("(web)"), ("(web)", "unknown"))

    def test_machine_share_is_over_categorised_messages_only(self):
        # 10 web + 30 non-web. The denominator is 40, NOT total messages, because categorisation
        # covers a minority of traffic on most stacks.
        self.assertEqual(A.machine_share({"Learn (web)": 10, "Learn (cli)": 20, "Learn (a2a)": 10}), 0.75)

    def test_machine_share_is_absent_when_nothing_was_categorised(self):
        """A zero would read as 'all human', which is a different claim from 'unknown'."""
        self.assertIsNone(A.machine_share({}))
        self.assertIsNone(A.machine_share({"Learn (web)": 0}))

    def test_only_web_counts_as_human(self):
        self.assertEqual(A.HUMAN_SURFACES, frozenset({"web"}))


class InventoryTest(unittest.TestCase):
    def test_count_prefers_pagination_total_over_the_page(self):
        body = {"data": {"skills": [SKILL], "pagination": {"total": 42, "limit": 1, "offset": 0}}}
        self.assertEqual(A.object_count(body, "skills"), 42)

    def test_count_falls_back_to_length_where_there_is_no_pagination(self):
        """`/api/v1/automations` returns no pagination block at all."""
        self.assertEqual(A.object_count({"data": {"automations": [1, 2]}}, "automations"), 2)
        self.assertEqual(A.object_count({"data": {}}, "automations"), 0)
        self.assertEqual(A.object_count(None, "automations"), 0)

    def test_prompts_bodies_urls_and_headers_are_dropped(self):
        skill = A.strip_object(SKILL, "skills")
        self.assertNotIn("body", skill)
        mcp = A.strip_object(MCP, "integrations")
        for banned in ("configuration", "customHeaders", "ruleContent", "body"):
            self.assertNotIn(banned, mcp)
        self.assertEqual(mcp["authenticationFailed"], False)

    def test_the_field_set_is_an_allow_list_so_a_new_api_field_is_dropped(self):
        out = A.strip_object({**SKILL, "somethingNew": "secret"}, "skills")
        self.assertNotIn("somethingNew", out)
        self.assertEqual(set(out) - {"kind"}, set(A.OBJECT_FIELDS) & set(SKILL))


class ProbeStackTest(unittest.TestCase):
    def test_all_eight_endpoints_are_called_and_none_of_the_excluded_ones(self):
        seen: list = []
        A.probe_stack(client(seen=seen), "s", "tok", now=NOW)
        paths = [p for p, _ in seen]
        self.assertEqual(len(paths), 8)
        for excluded in ("api/v2/investigations", "api/v1/watcher-agents", "api/v1/usage/tokens"):
            self.assertNotIn(excluded, paths)

    def test_record_shape(self):
        rec = A.probe_stack(client(), "obs-hub-dev", "tok", now=NOW)
        self.assertTrue(rec["available"])
        self.assertEqual(rec["active_users"], 5)
        self.assertEqual(rec["messages"], 49)
        self.assertEqual(rec["days_active"], 2)
        self.assertEqual(rec["messages_categorised"], 9)
        self.assertEqual(rec["messages_uncategorised"], 40)
        self.assertEqual(rec["tenant"], {"skills": 1, "rules": 0, "automations": 0, "integrations": 1})
        self.assertEqual(rec["tenant_objects"], 2)
        self.assertEqual(rec["tokens_per_active_user"], round(14_677_233 / 5, 1))
        self.assertFalse(rec["watchers_measurable"])
        self.assertFalse(rec["investigation_inventory_measurable"])

    def test_investigation_origins_are_absent_rather_than_zero(self):
        rec = A.probe_stack(client(), "s", "tok", now=NOW)
        self.assertEqual(rec["investigations_by_origin"], {})

    def test_a_401_and_a_403_are_distinguished_because_the_repairs_differ(self):
        for status, reason in ((401, A.UNAUTHORISED), (403, A.FORBIDDEN), (404, A.PLUGIN_ABSENT),
                              (500, A.HTTP_ERROR)):
            with self.assertRaises(A.AssistantUnavailable) as ctx:
                A.probe_stack(client(lambda p, s=status: s), "s", "tok", now=NOW, sleep=lambda _: None)
            self.assertEqual(ctx.exception.reason, reason)

    def test_a_refused_first_call_stops_the_stack_rather_than_repeating_seven_times(self):
        seen: list = []
        with self.assertRaises(A.AssistantUnavailable):
            A.probe_stack(client(lambda p: 403, seen), "s", "tok", now=NOW, sleep=lambda _: None)
        # One re-attempt of the FIRST call, then stop. Not the other seven endpoints.
        self.assertEqual(len(seen), 2)

    def test_a_transient_first_call_failure_is_retried_once_and_the_stack_is_kept(self):
        """Measured: `stack143` 403'd mid-sweep and answered 200 four minutes later."""
        for status in (403, 522, 500):
            calls = {"n": 0}

            def status_for(path, s=status):
                if path != "api/v1/usage/hero-stats":
                    return 200
                calls["n"] += 1
                return s if calls["n"] == 1 else 200

            rec = A.probe_stack(client(status_for), "s", "tok", now=NOW, sleep=lambda _: None)
            self.assertTrue(rec["available"], status)
            self.assertEqual(rec["messages"], 49)

    def test_a_dead_token_is_not_retried_because_it_will_still_be_dead(self):
        for status in (401, 404):
            seen: list = []
            with self.assertRaises(A.AssistantUnavailable):
                A.probe_stack(client(lambda p, s=status: s, seen), "s", "tok", now=NOW,
                              sleep=lambda _: None)
            self.assertEqual(len(seen), 1, status)

    def test_one_failed_section_degrades_that_section_not_the_stack(self):
        rec = A.probe_stack(
            client(lambda p: 500 if p == "api/v1/skills" else 200), "s", "tok", now=NOW)
        self.assertTrue(rec["available"])
        self.assertEqual(rec["tenant"]["skills"], 0)
        self.assertEqual(rec["messages"], 49)

    def test_the_uncategorised_remainder_is_clamped_and_the_disagreement_is_flagged(self):
        """Measured live: two stacks reported 0 messages against a non-zero category frame."""
        rec = A.summarise_stack("s", {"totalUserMessages": 0}, {"Learn (web)": 8}, {}, 0, {}, [])
        self.assertEqual(rec["messages_uncategorised"], 0)
        self.assertTrue(rec["categorised_exceeds_total"])

    def test_a_normal_stack_does_not_raise_the_disagreement_flag(self):
        rec = A.probe_stack(client(), "s", "tok", now=NOW)
        self.assertFalse(rec["categorised_exceeds_total"])


class ProbeAllTest(unittest.TestCase):
    """The golden rule: iterate the inventory, look the credential up."""

    def setUp(self):
        self.creds = {"live": {"token": "t1"}, "gone": {"token": "t2"}}
        self.stacks = [{"slug": "live", "status": "active"},
                       {"slug": "fresh", "status": "active"},
                       {"slug": "sleepy", "status": "paused"}]

    def test_a_stack_that_left_the_estate_gets_no_row_however_stale_the_store_is(self):
        out = A.probe_all(client(), self.stacks, self.creds, concurrency=2, now=NOW)
        self.assertNotIn("gone", out)

    def test_a_brand_new_stack_gets_a_row_saying_why(self):
        out = A.probe_all(client(), self.stacks, self.creds, concurrency=2, now=NOW)
        self.assertFalse(out["fresh"]["available"])
        self.assertEqual(out["fresh"]["reason"], A.NO_CREDENTIAL)

    def test_a_paused_stack_is_omitted_entirely_rather_than_reported_as_missing(self):
        out = A.probe_all(client(), self.stacks, self.creds, concurrency=2, now=NOW)
        self.assertNotIn("sleepy", out)

    def test_a_transport_failure_is_one_stack_not_the_sweep(self):
        def boom(req, timeout):
            raise OSError("connection reset")

        bad = ReadOnlyClient(transport=boom, max_attempts=1)
        errors: list[str] = []
        out = A.probe_all(bad, self.stacks, self.creds, concurrency=1, now=NOW,
                          on_error=lambda s, m: errors.append(s))
        self.assertEqual(out["live"]["reason"], A.TRANSPORT_ERROR)
        self.assertEqual(errors, ["live"])

    def test_an_empty_credential_record_counts_as_no_credential(self):
        out = A.probe_all(client(), [{"slug": "live", "status": "active"}], {"live": {"token": ""}},
                          now=NOW)
        self.assertEqual(out["live"]["reason"], A.NO_CREDENTIAL)


if __name__ == "__main__":
    unittest.main()
