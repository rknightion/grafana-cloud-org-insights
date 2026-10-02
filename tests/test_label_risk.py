"""Public source -> compose -> hydration/dashboard privacy boundary using captured API shapes."""
from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
import unittest
from unittest import mock
import urllib.parse

from collector import pii
from collector.coverage import Coverage
from collector.emit import hydrate, loki
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose, findings, label_risk as pillar
from collector.sources import label_risk as source

FIXTURE = json.loads(pathlib.Path(__file__).with_name("fixtures").joinpath(
    "label_risk_contracts.json").read_text())
NOW = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)
STACK = {"slug": "obs-hub", "status": "active"}
for signal, (host, tenant, _prefix) in source.SIGNALS.items():
    STACK.update({host: f"https://{signal}.example.test", tenant: 123})


class LabelRiskContracts(unittest.TestCase):
    def setUp(self):
        self.requests = []

    def send(self, request, timeout):
        self.requests.append(request)
        signal = urllib.parse.urlsplit(request.full_url).hostname.split(".")[0]
        names = request.full_url.split("?")[0].endswith(("/labels", "/tags", "/LabelNames"))
        doc = FIXTURE[f"{signal}_{'names' if names else 'values'}"]
        return Response(200, json.dumps(doc).encode(), request.full_url)

    def probe(self, **kw):
        return source.probe_stack(ReadOnlyClient(transport=self.send, max_attempts=1, deadline=60),
                                  STACK, "synthetic-cap", now=NOW, rpc_transport=self.send, **kw)

    def test_all_four_captured_shapes_and_exact_windows(self):
        record = self.probe()
        self.assertTrue(record["available"])
        self.assertEqual(set(record["signals"]), set(source.SIGNALS))
        self.assertTrue(all(s["state"] == "partial" for s in record["signals"].values()))
        retained = [v for r in record["findings"] for v in r["values"]]
        self.assertEqual(set(retained), {"reader@example.test"})
        self.assertNotIn("orders", json.dumps(record))
        trace_keys = {(r["scope"], r["key"]) for r in record["findings"] if r["signal"] == "traces"}
        self.assertEqual(trace_keys, {("resource", "user_email"), ("span", "user_email")})
        for req in self.requests:
            signal = urllib.parse.urlsplit(req.full_url).hostname.split(".")[0]
            if signal == "profiles":
                self.assertEqual(req.get_method(), "POST")
                self.assertIn("allow-utf8-labelnames=true", req.get_header("Accept"))
                self.assertEqual(req.get_header("Content-type"), "application/json")
                body = json.loads(req.data)
                self.assertIs(type(body["start"]), int)
                self.assertEqual(body["end"] - body["start"], 86_400_000)
                self.assertEqual(body["end"], int(NOW.timestamp()) * 1000)
            else:
                self.assertEqual(req.get_method(), "GET")
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
                factor = 1_000_000_000 if signal == "logs" else 1
                self.assertEqual(int(query["end"][0]), int(NOW.timestamp()) * factor)
                self.assertEqual(int(query["end"][0]) - int(query["start"][0]), 86400 * factor)

    def test_production_bounded_transport_path_uses_only_live_scannable_stacks(self):
        caller = ReadOnlyClient(deadline=60)
        with mock.patch.object(source, "bounded_transport", return_value=self.send):
            result = source.probe_all(caller,
                [STACK, {"slug": "paused-stack", "status": "paused"}], "cap", concurrency=2)
        self.assertEqual(set(result), {"obs-hub"})
        self.assertTrue(result["obs-hub"]["available"])
        self.assertEqual(len(self.requests), 12)
        self.assertEqual(caller.attempts.requests, 12)
        self.assertEqual(caller.attempts.by_status, {200: 12})

    def test_native_post_rejects_all_other_paths_methods_and_shapes(self):
        for path, method in [("/querier.v1.QuerierService/SelectSeries", "POST"),
                             ("/querier.v1.QuerierService/LabelNames?x=1", "POST"),
                             ("/querier.v1.QuerierService/LabelNames", "GET")]:
            with self.assertRaises(ValueError):
                source.profile_read(STACK, "cap", path, {"start": 1, "end": 2},
                                    method=method, transport=self.send)
        for stack, body in [({**STACK, "hpInstanceUrl": "https://evil.test/path"}, {"start": 1, "end": 2}),
                            (STACK, {"start": "1", "end": 2}),
                            (STACK, {"start": 1, "end": 2, "limit": 1})]:
            with self.assertRaises(ValueError):
                source.profile_read(stack, "cap", next(iter(source.PROFILE_PATHS)), body,
                                    transport=self.send)
        self.assertEqual(self.requests, [])

    def test_caps_keep_counts_and_never_shorten_raw_values(self):
        record = self.probe(bounds=source.Bounds(keys=1, values=2, matches=1, retained_bytes=1))
        self.assertTrue(all(s["local_key_cap"] for s in record["signals"].values()))
        matched = [r for r in record["findings"] if r["evidence"] == "value_format"]
        self.assertTrue(matched)
        self.assertTrue(all(r["sampled_count"] == 2 and r["matched_count"] == 1
                            and r["retained_count"] == 0 and r["values"] == [] for r in matched))
        record = self.probe(bounds=source.Bounds(keys=1, values=1))
        self.assertTrue(all(s["local_value_cap"] for s in record["signals"].values()))

    def test_default_match_bound_retains_64_full_values_and_total_count(self):
        values = [f"person{i:03d}@example.test" for i in range(70)]
        def many(req, timeout):
            is_names = req.full_url.split("?")[0].endswith(("/labels", "/tags", "/LabelNames"))
            signal = urllib.parse.urlsplit(req.full_url).hostname.split(".")[0]
            if signal == "traces":
                doc = ({"scopes": [{"name": "resource", "tags": ["user_email"]}]} if is_names else
                       {"tagValues": [{"type": "string", "value": v} for v in values]})
            else:
                doc = {"names" if signal == "profiles" else "data": ["user_email"] if is_names else values}
                if signal != "profiles":
                    doc["status"] = "success"
            return Response(200, json.dumps(doc).encode(), "")
        self.send = many
        record = self.probe()
        for row in record["findings"]:
            if row["evidence"] == "value_format":
                self.assertEqual(row["sampled_count"], 70)
                self.assertEqual(row["matched_count"], 70)
                self.assertEqual(row["retained_count"], 64)
                self.assertEqual(row["values"], values[:64])
        self.assertTrue(all(r["local_match_cap"] for r in record["signals"].values()))

    def test_truncated_failed_and_empty_shapes_are_not_clean(self):
        original = self.send
        def altered(req, timeout):
            if req.full_url.startswith("https://metrics"):
                return Response(200, json.dumps(FIXTURE["metrics_truncated"]).encode(), "")
            if req.full_url.startswith("https://logs"):
                return Response(200, json.dumps(FIXTURE["logs_empty"]).encode(), "")
            if req.full_url.startswith("https://profiles"):
                return Response(200, b"{}", "")
            return Response(403, b'raw-secret-from-error', "")
        self.send = altered
        record = self.probe()
        self.assertTrue(record["signals"]["metrics"]["server_cap"])
        self.assertEqual(record["signals"]["logs"]["keys_returned"], 0)
        self.assertEqual(record["signals"]["profiles"]["keys_returned"], 0)
        self.assertEqual(record["signals"]["traces"]["state"], "unavailable")
        self.assertEqual(record["signals"]["traces"]["reason"], "auth")
        self.assertIsNone(record["signals"]["traces"]["keys_returned"])
        self.assertNotIn("raw-secret", json.dumps(record))
        self.send = original
        record = self.probe(bounds=source.Bounds(response_bytes=1))
        self.assertFalse(record["available"])
        self.assertTrue(all(s["reason"] == "response_byte_cap" for s in record["signals"].values()))
        expired = ReadOnlyClient(transport=self.send, deadline=0)
        self.requests.clear()
        record = source.probe_stack(expired, STACK, "cap", now=NOW, rpc_transport=self.send)
        self.assertFalse(record["available"])
        self.assertEqual(self.requests, [])
        self.assertTrue(all(s["reason"] == "deadline" for s in record["signals"].values()))
        def fails(req, timeout):
            raise ValueError("secret-value-in-upstream-error")
        self.send = fails
        record = self.probe()
        self.assertNotIn("secret-value", json.dumps(record))
        self.assertTrue(all(s["reason"] == "read_failed" for s in record["signals"].values()))

    def test_actual_transport_bounds_read_and_does_not_follow_redirects(self):
        class Body(io.BytesIO):
            status = 200
            headers = {}
        opener = mock.Mock()
        opener.open.return_value = Body(b"12345")
        with mock.patch("urllib.request.build_opener", return_value=opener) as build:
            with self.assertRaisesRegex(ValueError, "response_byte_cap"):
                source.bounded_transport(4)(mock.Mock(), 2)
        self.assertIsInstance(build.call_args.args[0], source._NoRedirect)
        self.assertIsNone(build.call_args.args[0].redirect_request(None, None, 302, "", {}, "https://evil.test"))

    def test_compose_hydration_denominators_and_no_raw_loki_metrics_diagnostics(self):
        record = self.probe()
        payload = {"obs-hub": record, "departed-stack": record}
        cov = Coverage(tier="t2", total=2)
        cov.record_ok("obs-hub")
        cov.record_ok("missing-stack")
        stacks = [STACK, {"slug": "missing-stack"}]
        metrics, views, _ = compose.build_all(stacks, cov, label_risk=payload, now=NOW)
        rows = views["risk_label_hygiene"]
        self.assertTrue(rows)
        self.assertEqual({r[" Stack"] for r in rows}, {"obs-hub"})
        self.assertTrue(all(r["Scannable stacks"] == 2 and r["Measured stacks (names)"] == 1 and r["Value-read stacks"] == 1
                            for r in views["risk_label_hygiene_coverage"]))
        self.assertNotIn("reader@example.test", json.dumps(metrics))
        self.assertEqual(metrics, compose.build_all(stacks, cov, now=NOW)[0])
        # Even a future accidental registration of an unrestricted finding spec is refused.
        spec = findings.FindingSpec("risk_label_hygiene", "E", "privacy", "high", "test")
        with mock.patch.object(findings, "SPECS", (spec,)):
            detail, totals = findings.derive(views)
        self.assertEqual((detail, totals), ([], {}))
        self.assertNotIn("reader@example.test", json.dumps(loki.build_payload(loki.finding_events("t2", detail))))
        scan = {"meta": {}, "data": {"label_risk": payload, "stacks": stacks}}
        self.assertNotIn("reader@example.test", json.dumps(pillar.diagnostic_scan(scan)))
        self.assertIn("reader@example.test", json.dumps(scan))
        inputs, prov = hydrate.hydrate("t1", {}, now=NOW, loader=lambda *_: {
            "meta": {"generated_at": NOW.isoformat()}, "data": {"label_risk": payload}})
        self.assertEqual(inputs["label_risk"], payload)
        self.assertTrue(prov.satisfied("label_risk"))
        _, own = hydrate.hydrate("t2", {}, now=NOW, loader=lambda *_: scan)
        self.assertFalse(own.satisfied("label_risk"))
        kept, withheld = hydrate.filter_views(views, own)
        self.assertNotIn("risk_label_hygiene", kept)
        self.assertIn("risk_label_hygiene", withheld)


class GenericClassifier(unittest.TestCase):
    def test_generic_versioned_patterns_and_false_positive_controls(self):
        self.assertRegex(pii.VERSION, r"^\d+\.\d+\.\d+$")
        for names in pii.KEYS.values():
            for name in names:
                self.assertGreater(len(name), 1)
                self.assertRegex(name, r"^[a-z_]+$")
        self.assertEqual(pii.value_classes("service_name", "Order Processor"), [])
        self.assertEqual(pii.value_classes("build_version", "1.2.3"), [])
        self.assertEqual(pii.value_classes("trace_id", "0123456789abcdef0123456789abcdef"), [])
        self.assertEqual(pii.value_classes("full_name", "Example Person"), [("person_name", "possible")])
        self.assertIn(("ip_address", "possible"), pii.value_classes("client_ip", "2001:db8::1"))
        self.assertIn(("card_like", "possible"), pii.value_classes("card", "4242 4242 4242 4242"))
        self.assertEqual(pii.value_classes("card", "4242 4242 4242 4241"), [])
        self.assertIn(("phone", "high"), pii.value_classes("phone", "+1 202 555 0199"))
        self.assertIn(("secret", "possible"), pii.value_classes("api_key", "abcdefghijk1234567890ABCDE"))
        self.assertIn(("jwt", "high"), pii.value_classes("session", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c2ln"))
        self.assertNotIn("jwt", [c for c, _ in pii.value_classes("session", "aaa.bbb.ccc")])
        self.assertIn(("email", "high"), pii.value_classes("anything", "reader@example.test"))
