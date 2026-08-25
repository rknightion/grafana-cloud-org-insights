"""Per-stack alert-rule routing inventory."""

from __future__ import annotations

import json
import unittest

from collector.httpclient import Response
from collector.sources import alert_routing as ar

STACK = {"slug": "alpha", "url": "https://authoritative.example"}


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        status, body = self.replies.pop(0)
        if isinstance(body, Exception):
            raise body
        return Response(status=status, body=json.dumps(body).encode(), url=url)


def rule(uid, *, paused=False, receiver=None, title=None, labels=None):
    return {
        "uid": uid,
        "title": title or f"Rule {uid}",
        "folderUID": "folder-1",
        "ruleGroup": "group-1",
        "isPaused": paused,
        "notification_settings": {"receiver": receiver} if receiver else None,
        "data": [{"model": {"secret": "DO-NOT-STORE"}}],
        "annotations": {"private": "DO-NOT-STORE"},
        "labels": labels or {},
    }


def contact(name):
    return {
        "uid": f"cp-{name}",
        "name": name,
        "type": "email",
        "settings": {"addresses": "private@example.test"},
        "secureFields": {"password": True},
    }


class HealthyInventoryTest(unittest.TestCase):
    def test_classifies_the_rules_with_two_read_only_requests(self):
        client = FakeClient([
            (200, [
                rule("direct", receiver="platform"),
                rule("inherited"),
                rule("paused", paused=True, receiver="platform"),
                rule("missing", receiver="deleted-contact"),
                rule("builtin", receiver=ar.BUILTIN_DEFAULT_RECEIVER),
            ]),
            (200, [contact("platform")]),
        ])

        out = ar.probe_stack(client, {"slug": "alpha", "url": "https://odd.example"}, "tok")

        self.assertEqual(out["state"], ar.OK)
        self.assertEqual(out["rules_total"], 5)
        self.assertEqual(out["rules_active"], 4)
        self.assertEqual(out["rules_paused"], 1)
        self.assertEqual(out["rules_direct_receiver"], 4)
        self.assertEqual(out["rules_inherited"], 1)
        self.assertEqual(out["rules_active_direct_receiver"], 3)
        self.assertEqual(out["rules_paused_direct_receiver"], 1)
        self.assertEqual(out["rules_active_inherited"], 1)
        self.assertEqual(out["rules_paused_inherited"], 0)
        self.assertEqual(out["rules_missing_receiver"], 1)
        self.assertEqual(out["rules_active_missing_receiver"], 1)
        self.assertEqual(out["rules_paused_missing_receiver"], 0)
        self.assertEqual(out["rules_unverified_builtin"], 1)
        self.assertEqual(out["contact_point_integrations"], 1)
        self.assertEqual(out["contact_point_names"], 1)
        self.assertEqual(out["completeness"], ar.API_HAS_NO_TOTAL)
        self.assertEqual([url for url, _kw in client.calls], [
            "https://odd.example/api/v1/provisioning/alert-rules",
            "https://odd.example/api/v1/provisioning/contact-points",
        ])
        self.assertTrue(all(kw["bearer"] == "tok" for _url, kw in client.calls))

    def test_actionable_rows_are_allow_listed_and_never_carry_rule_or_contact_secrets(self):
        client = FakeClient([
            (200, [
                rule("inherited"),
                rule("missing", paused=True, receiver="deleted-contact"),
                rule("builtin", receiver=ar.BUILTIN_DEFAULT_RECEIVER),
                rule("healthy", receiver="platform"),
            ]),
            (200, [contact("platform")]),
        ])

        out = ar.probe_stack(client, STACK, "tok")

        self.assertEqual(out["findings_total"], 3)
        self.assertEqual(out["findings_retained"], 3)
        self.assertFalse(out["findings_truncated"])
        self.assertEqual(
            {row["receiver_state"] for row in out["findings"]},
            {ar.NOT_APPLICABLE, ar.MISSING, ar.UNVERIFIED_BUILTIN},
        )
        self.assertEqual(set(out["findings"][0]), {
            "rule_uid", "title", "folder_uid", "rule_group", "paused",
            "routing", "receiver", "receiver_state",
        })
        self.assertNotIn("DO-NOT-STORE", repr(out))
        self.assertNotIn("private@example.test", repr(out))

    def test_explicit_service_labels_create_service_routes_without_title_inference(self):
        client = FakeClient([
            (200, [
                rule("labelled", receiver="platform", labels={"service_name": "checkout"}),
                rule("legacy", labels={"service": "legacy-api"}),
                rule("title-only", title="checkout latency"),
            ]),
            (200, [contact("platform")]),
        ])

        out = ar.probe_stack(client, STACK, "tok")

        self.assertEqual(out["service_routes"], [
            {"service_name": "checkout", "identity_label": "service_name", "paused": False,
             "routing": "direct", "receiver_state": ar.PROVISIONED},
        ])
        self.assertNotIn("title-only", repr(out["service_routes"]))
        self.assertNotIn("legacy-api", repr(out["service_routes"]))

    def test_bounded_detail_keeps_broken_direct_receivers_ahead_of_inherited_rules(self):
        rules = [rule(f"inherited-{i}") for i in range(ar.MAX_FINDINGS)]
        rules.append(rule("missing", receiver="deleted-contact"))
        client = FakeClient([(200, rules), (200, [contact("platform")])])

        out = ar.probe_stack(client, STACK, "tok")

        self.assertEqual(out["findings_total"], ar.MAX_FINDINGS + 1)
        self.assertEqual(out["findings_retained"], ar.MAX_FINDINGS)
        self.assertTrue(out["findings_truncated"])
        self.assertIn("missing", {row["rule_uid"] for row in out["findings"]})


class FailureStateTest(unittest.TestCase):
    def test_missing_authoritative_url_is_invalid_without_a_request(self):
        client = FakeClient([])

        out = ar.probe_stack(client, {"slug": "alpha"}, "tok")

        self.assertEqual(out["state"], ar.INVALID_RESPONSE)
        self.assertFalse(out["available"])
        self.assertIn("url", out["detail"])
        self.assertEqual(client.calls, [])

    def test_invalid_authoritative_url_is_invalid_without_a_request(self):
        for url in (
            "alpha.example",
            "http://alpha.example",
            "https:///missing-host",
            "https://user@alpha.example",
            "https://alpha.example/base",
            "https://alpha.example?query=1",
            "https://alpha.example#fragment",
            "https://alpha.example:not-a-port",
            "https://alpha example",
        ):
            with self.subTest(url=url):
                client = FakeClient([])

                out = ar.probe_stack(client, {"slug": "alpha", "url": url}, "tok")

                self.assertEqual(out["state"], ar.INVALID_RESPONSE)
                self.assertFalse(out["available"])
                self.assertIn("url", out["detail"])
                self.assertEqual(client.calls, [])

    def test_no_credential_is_not_a_zero_and_makes_no_request(self):
        client = FakeClient([])

        out = ar.probe_stack(client, STACK, "")

        self.assertEqual(out["state"], ar.NO_CREDENTIAL)
        self.assertFalse(out["available"])
        self.assertNotIn("rules_total", out)
        self.assertEqual(client.calls, [])

    def test_http_failures_are_explicit_and_never_carry_partial_counts(self):
        expected = {
            401: ar.UNAUTHORISED,
            403: ar.FORBIDDEN,
            404: ar.NOT_PROVISIONED,
            500: ar.HTTP_ERROR,
        }
        for status, state in expected.items():
            with self.subTest(status=status):
                out = ar.probe_stack(FakeClient([(status, {})]), STACK, "tok")
                self.assertEqual(out["state"], state)
                self.assertFalse(out["available"])
                self.assertNotIn("rules_total", out)

    def test_successful_but_malformed_collections_are_not_measured(self):
        cases = [
            ({"rules": []}, "alert rules"),
            ([rule("valid"), "not-an-object"], "alert rules"),
        ]
        for payload, detail in cases:
            with self.subTest(payload=payload):
                out = ar.probe_stack(FakeClient([(200, payload)]), STACK, "tok")
                self.assertEqual(out["state"], ar.INVALID_RESPONSE)
                self.assertIn(detail, out["detail"])
                self.assertNotIn("rules_total", out)

    def test_duplicate_rule_uids_fail_the_completeness_check(self):
        out = ar.probe_stack(
            FakeClient([(200, [rule("same"), rule("same")]), (200, [contact("platform")])]),
            STACK,
            "tok",
        )
        self.assertEqual(out["state"], ar.INVALID_RESPONSE)
        self.assertIn("duplicate", out["detail"])
        self.assertNotIn("rules_total", out)

    def test_required_classification_fields_are_not_defaulted(self):
        broken = rule("broken")
        broken.pop("isPaused")
        out = ar.probe_stack(
            FakeClient([(200, [broken]), (200, [contact("platform")])]),
            STACK,
            "tok",
        )
        self.assertEqual(out["state"], ar.INVALID_RESPONSE)
        self.assertIn("isPaused", out["detail"])

    def test_transport_failure_is_neither_an_empty_stack_nor_an_http_refusal(self):
        out = ar.probe_stack(
            FakeClient([(200, TimeoutError("private transport detail"))]),
            STACK,
            "tok",
        )
        self.assertEqual(out["state"], ar.TRANSPORT_ERROR)
        self.assertNotIn("rules_total", out)


class ProbeAllTest(unittest.TestCase):
    STACKS = [
        {"slug": "alpha", "url": "https://odd.example", "status": "active"},
        {"slug": "beta", "url": "https://beta.example", "status": "active"},
        {"slug": "paused", "url": "https://paused.example", "status": "paused"},
    ]

    def test_live_inventory_drives_the_sweep_and_credentials_are_a_left_join(self):
        client = FakeClient([(200, []), (200, [])])

        out = ar.probe_all(
            client,
            self.STACKS,
            {"alpha": {"token": "tok"}, "gone": {"token": "tok"}},
        )

        self.assertEqual(set(out), {"alpha", "beta"})
        self.assertEqual(out["alpha"]["state"], ar.OK)
        self.assertEqual(out["beta"]["state"], ar.NO_CREDENTIAL)
        self.assertNotIn("paused", out)
        self.assertNotIn("gone", out)


if __name__ == "__main__":
    unittest.main()
