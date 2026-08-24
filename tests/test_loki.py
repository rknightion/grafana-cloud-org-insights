"""Loki push (PLAN 5.4).

The one thing that must not happen: an unbounded field becoming a **stream** label. Loki streams are as
cardinality-sensitive as Prometheus series, so `stack` in a stream label means 271 streams per event
type. It goes in the line body, where `| json | stack="x"` still filters on it for free.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import unittest

from collector.emit import loki

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"
NOW = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.timezone.utc)


def _stacks():
    return json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]


def _dataplane():
    return json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())


class StreamLabelTest(unittest.TestCase):
    def test_only_the_four_permitted_stream_labels_are_accepted(self):
        loki.check_stream({"job": "gcinsight", "tier": "t3", "pillar": "B", "event": "finding"})

    def test_stack_as_a_stream_label_is_refused(self):
        """271 stacks x N event types is a stream explosion, and the exact mistake the metric guard
        exists to prevent, one layer down."""
        with self.assertRaises(loki.UnboundedStream):
            loki.check_stream({"job": "j", "stack": "stack084"})

    def test_other_tempting_stream_labels_are_refused(self):
        for key in ("region", "cluster", "metric", "label", "user", "login", "dashboard_uid",
                    "version", "severity"):
            with self.assertRaises(loki.UnboundedStream, msg=key):
                loki.check_stream({"job": "j", key: "x"})

    def test_an_empty_stream_label_value_is_refused(self):
        with self.assertRaises(loki.UnboundedStream):
            loki.check_stream({"job": "j", "tier": ""})

    def test_job_is_injected_so_every_stream_is_attributable(self):
        payload = loki.build_payload(
            [({"tier": "t1", "pillar": "A", "event": "finding"}, {"stack": "x"})], timestamp=NOW
        )
        self.assertEqual(payload["streams"][0]["stream"]["job"], loki.JOB)


class PayloadTest(unittest.TestCase):
    def test_timestamps_are_nanosecond_strings(self):
        payload = loki.build_payload([({"tier": "t1"}, {"a": 1})], timestamp=NOW)
        ts = payload["streams"][0]["values"][0][0]
        self.assertIsInstance(ts, str)
        self.assertEqual(len(ts), 19, "nanoseconds since epoch is 19 digits at this date")
        self.assertEqual(int(ts), int(NOW.timestamp()) * 1_000_000_000)

    def test_lines_are_json_objects(self):
        payload = loki.build_payload([({"tier": "t1"}, {"stack": "x", "series": 5})], timestamp=NOW)
        line = json.loads(payload["streams"][0]["values"][0][1])
        self.assertEqual(line, {"level": "info", "stack": "x", "series": 5})

    def test_level_is_set_explicitly_so_loki_does_not_sniff_it(self):
        """Measured: without an explicit level, Loki stamped all 271 stack_detail lines
        detected_level=error, showing a healthy scan as 271 errors in Explore Logs."""
        payload = loki.build_payload([({"tier": "t3"}, {"stack": "x"})], timestamp=NOW)
        self.assertEqual(json.loads(payload["streams"][0]["values"][0][1])["level"], "info")

    def test_a_caller_supplied_level_wins(self):
        payload = loki.build_payload([({"tier": "t3"}, {"level": "warn", "stack": "x"})],
                                      timestamp=NOW)
        self.assertEqual(json.loads(payload["streams"][0]["values"][0][1])["level"], "warn")

    def test_entries_sharing_labels_are_grouped_into_one_stream(self):
        entries = [({"tier": "t1", "event": "stack_detail"}, {"stack": s}) for s in "abc"]
        payload = loki.build_payload(entries, timestamp=NOW)
        self.assertEqual(len(payload["streams"]), 1)
        self.assertEqual(len(payload["streams"][0]["values"]), 3)

    def test_entries_with_different_labels_get_separate_streams(self):
        entries = [({"tier": "t1", "pillar": "A", "event": "finding"}, {"x": 1}),
                   ({"tier": "t1", "pillar": "B", "event": "finding"}, {"x": 2})]
        self.assertEqual(len(loki.build_payload(entries, timestamp=NOW)["streams"]), 2)

    def test_stream_count_stays_small_for_the_whole_estate(self):
        """271 stacks must not become 271 streams."""
        entries = loki.stack_detail_events("t3", _stacks(), _dataplane())
        payload = loki.build_payload(entries, timestamp=NOW)
        self.assertEqual(len(entries), 271)
        self.assertEqual(len(payload["streams"]), 1, "one stream, 271 lines")
        self.assertEqual(len(payload["streams"][0]["values"]), 271)


class StackDetailEventTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entries = loki.stack_detail_events("t3", _stacks(), _dataplane())
        cls.by_stack = {json.loads(json.dumps(line))["stack"]: line for _labels, line in cls.entries}

    def test_stack_travels_in_the_body_not_the_labels(self):
        for labels, line in self.entries:
            self.assertNotIn("stack", labels)
            self.assertIn("stack", line)

    def test_the_unbounded_fields_banned_from_metric_labels_are_here_instead(self):
        light = self.by_stack["stack084"]
        # Label NAMES - the actionable half of a cardinality finding.
        self.assertIn("top_labels", light)
        self.assertIn("label_values_count_total", light)
        # Version strings churn on every upgrade, so they are banned from labels.
        self.assertIsInstance(light["running_version"], str)
        # Datasource ids are a growing set.
        self.assertIsInstance(light["datasource_types"], list)

    def test_cardinality_and_adaptive_detail_appear_only_where_measured(self):
        entries = loki.stack_detail_events("t1", _stacks(), dataplane=None)
        for _labels, line in entries:
            self.assertNotIn("top_labels", line)
            self.assertNotIn("adaptive_rules_applied", line)
            self.assertNotIn("collectors", line)

    def test_the_worst_cardinality_offender_is_recoverable_from_the_line(self):
        light = self.by_stack["stack084"]
        self.assertEqual(light["label_values_count_total"], 398_773)
        self.assertGreater(light["active_series"], 1_000_000)

    def test_every_event_passes_the_stream_check(self):
        for labels, _line in self.entries:
            loki.check_stream({"job": loki.JOB, **labels})


class IdentityEventTest(unittest.TestCase):
    """T2's identity payload: the densest concentration of label-banned fields in the platform."""

    def _detail(self):
        return {"obs-hub-dev": {
            "slug": "obs-hub-dev",
            "users": [
                {"login": "a.b@example.com", "name": "A B", "email_domain": "example.com",
                 "role": "Admin", "lastSeenAt": "2026-08-01T00:00:00Z"},
                {"login": "c.d@example.com", "name": "C D", "email_domain": "example.com",
                 "role": "Viewer", "lastSeenAt": None},
            ],
            "service_accounts": [
                {"name": "sa.operator", "kind": "custom", "role": "Admin", "tokens": 19,
                 "isDisabled": False},
                {"name": "extsvc-app", "kind": "extsvc", "role": "Viewer", "tokens": 1,
                 "isDisabled": False},
            ],
            "plugins": [
                {"pluginSlug": "yesoreyeram-infinity-datasource", "version": "3.0.0",
                 "latestVersion": "3.2.1"},
                {"pluginSlug": "grafana-gitlab-datasource", "version": "1.1.0",
                 "latestVersion": "1.1.0"},
            ],
        }}

    def test_identities_travel_in_the_body_and_never_in_a_stream_label(self):
        entries = loki.stack_identity_events("t2", self._detail())
        labels, line = entries[0]
        loki.check_stream({"job": loki.JOB, **labels})
        for value in labels.values():
            self.assertNotIn("@", value)
        self.assertEqual(line["users"][0]["login"], "a.b@example.com")
        self.assertEqual(line["stack"], "obs-hub-dev")

    def test_service_account_detail_is_preserved_including_the_token_hoard(self):
        _labels, line = loki.stack_identity_events("t2", self._detail())[0]
        self.assertEqual(line["service_account_tokens"], 20)
        hoard = [a for a in line["service_accounts"] if a["tokens"] == 19][0]
        self.assertEqual(hoard["name"], "sa.operator")
        self.assertEqual(hoard["kind"], "custom")

    def test_plugin_drift_is_precomputed_on_the_line(self):
        _labels, line = loki.stack_identity_events("t2", self._detail())[0]
        drift = {p["slug"]: p["drift"] for p in line["plugins"]}
        self.assertTrue(drift["yesoreyeram-infinity-datasource"])
        self.assertFalse(drift["grafana-gitlab-datasource"])

    def test_admin_count_is_derived(self):
        _labels, line = loki.stack_identity_events("t2", self._detail())[0]
        self.assertEqual(line["user_count"], 2)
        self.assertEqual(line["admin_count"], 1)

    def test_empty_detail_produces_no_events(self):
        self.assertEqual(loki.stack_identity_events("t2", {}), [])

    def test_identity_events_group_into_a_single_stream(self):
        detail = {f"stack{i}": {"users": [], "service_accounts": [], "plugins": []}
                  for i in range(271)}
        entries = loki.stack_identity_events("t2", detail)
        payload = loki.build_payload(entries, timestamp=NOW)
        self.assertEqual(len(entries), 271)
        self.assertEqual(len(payload["streams"]), 1)


class FindingAndSummaryTest(unittest.TestCase):
    def test_pillar_becomes_the_stream_label_and_the_rest_the_body(self):
        entries = loki.finding_events("t3", [
            {"pillar": "E", "stack": "stack094", "kind": "admin_sprawl", "admin_share": 93.8},
        ])
        labels, line = entries[0]
        self.assertEqual(labels["pillar"], "E")
        self.assertEqual(labels["event"], "finding")
        self.assertEqual(line["stack"], "stack094")
        self.assertEqual(line["admin_share"], 93.8)

    def test_a_finding_without_a_pillar_still_produces_a_valid_stream(self):
        labels, _ = loki.finding_events("t1", [{"stack": "x", "kind": "y"}])[0]
        loki.check_stream({"job": loki.JOB, **labels})

    def test_summary_event_carries_the_coverage_meta(self):
        labels, line = loki.summary_event("t3", {"stacks_total": 271, "coverage_ratio": 1.0})
        self.assertEqual(labels["event"], "scan_summary")
        self.assertEqual(line["coverage_ratio"], 1.0)

    def test_unhealthy_summary_event_is_error(self):
        _labels, line = loki.summary_event("t3", {"scan_healthy": False, "level": "info"})
        self.assertEqual(line["level"], "error")

    def test_healthy_summary_event_is_info(self):
        _labels, line = loki.summary_event("t3", {"scan_healthy": True})
        self.assertEqual(line["level"], "info")

    def test_finding_severity_does_not_turn_an_operational_log_into_an_error(self):
        entry = loki.finding_events("t3", [{"pillar": "E", "severity": "critical"}])
        payload = loki.build_payload(entry, timestamp=NOW)
        line = json.loads(payload["streams"][0]["values"][0][1])
        self.assertEqual(line["level"], "info")

    def test_the_event_vocabulary_is_closed(self):
        used = {loki.summary_event("t1", {})[0]["event"],
                loki.stack_detail_events("t1", _stacks()[:1])[0][0]["event"],
                loki.finding_events("t1", [{"pillar": "A"}])[0][0]["event"]}
        self.assertTrue(used <= set(loki.EVENTS), f"{used} outside {loki.EVENTS}")


class WriterTest(unittest.TestCase):
    def test_the_push_path_is_appended_once(self):
        for base in ("https://logs-prod-012.grafana.net",
                     "https://logs-prod-012.grafana.net/",
                     "https://logs-prod-012.grafana.net/loki/api/v1/push"):
            self.assertEqual(
                loki.LokiWriter(base, "000000", "tok", dry_run=True).url,
                "https://logs-prod-012.grafana.net/loki/api/v1/push",
            )

    def test_plain_http_is_refused(self):
        with self.assertRaises(loki.LokiPushRefused):
            loki.LokiWriter("http://example.invalid", "1", "tok")

    def test_dry_run_still_validates_streams(self):
        writer = loki.LokiWriter("https://logs.example.net", "1", "tok", dry_run=True)
        self.assertEqual(writer.push([({"tier": "t1"}, {"stack": "x"})]), 1)
        with self.assertRaises(loki.UnboundedStream):
            writer.push([({"stack": "x"}, {"a": 1})])

    def test_an_empty_batch_is_a_no_op(self):
        writer = loki.LokiWriter("https://logs.example.net", "1", "tok", dry_run=True)
        self.assertEqual(writer.push([]), 0)


if __name__ == "__main__":
    unittest.main()
