"""Recorded synthetic response contracts and minimized source -> strict consumer seam."""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path
import unittest
from unittest import mock
import urllib.parse

from collector import config, label_rules
from collector.httpclient import ReadOnlyClient, Response
from collector.sources import label_inventory as source

FIXTURE = json.loads((Path(__file__).parent / "fixtures/label_inventory/contracts.json").read_text())
NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)
STACK = {"slug": "synthetic", "status": "active"}
for signal, (host, tenant, _) in source.SIGNALS.items():
    STACK.update({host: f"https://{signal}.example.test", tenant: 5_000_001})


class SourceContracts(unittest.TestCase):
    def setUp(self):
        self.requests = []

    def send(self, req, timeout):
        self.requests.append(req)
        signal = urllib.parse.urlsplit(req.full_url).hostname.split(".")[0]
        names = urllib.parse.urlsplit(req.full_url).path.endswith(("/label_names", "/labels", "/tags", "/LabelNames"))
        return Response(200, json.dumps(FIXTURE[f"{signal}_{'names' if names else 'values'}"]).encode(), "")

    def probe(self, **kw):
        return source.probe_stack(ReadOnlyClient(transport=self.send, deadline=60, max_attempts=1),
                                 STACK, "synthetic-cap", now=NOW, rpc_transport=self.send, **kw)

    def test_four_shapes_windows_scopes_units_and_no_unapproved_routes(self):
        record = self.probe()
        self.assertEqual(label_rules.validate_inventory(record), record)
        self.assertEqual(set(record["signals"]), set(source.SIGNALS))
        metrics = record["signals"]["metrics"]
        self.assertEqual((metrics["window"], metrics["data"], metrics["state"]), ("head", "present", "complete"))
        counts = {r["name"]: r["distinct_count"] for r in metrics["register"]}
        self.assertEqual(counts, {"request_id": 200, "cluster": 3, "job": 2})
        samples = metrics["inputs"]["distinct_values"]["samples"]
        self.assertEqual([s["value"] for s in samples], [200, 3, 2])
        self.assertTrue(all(s["population"] is None for s in samples))
        self.assertEqual(samples[1]["label_kind"], "static")
        self.assertNotIn("shape_count", metrics["inputs"], "24h values cannot masquerade as head measurements")
        self.assertFalse(any(k in p["inputs"] for p in record["signals"].values()
                             for k in ("service_gap", "span_names", "metric_series", "labels_per_stream", "drilldown_missing")))
        trace = record["signals"]["traces"]
        self.assertEqual({r["scope"] for r in trace["register"]}, {"resource", "span"})
        for signal in ("logs", "traces", "profiles"):
            payload = record["signals"][signal]
            self.assertEqual((payload["window"], payload["state"], payload["reason"]), ("24h", "partial", "truncated"))
            self.assertTrue(all(r["count_semantics"] == "at_least" for r in payload["register"]))
        self.assertNotIn("orders", json.dumps(record))
        evaluated = label_rules.evaluate({"synthetic": record})
        self.assertNotIn("request_id", json.dumps(evaluated))
        m4 = next(r for r in evaluated["results"] if r["rule"] == "M4")
        self.assertEqual((m4["result"], m4["reason"]), ("not_evaluated", "missing_input"))
        for req in self.requests:
            parts = urllib.parse.urlsplit(req.full_url)
            signal = parts.hostname.split(".")[0]
            query = urllib.parse.parse_qs(parts.query)
            if signal == "metrics":
                self.assertEqual(parts.path, "/api/prom/api/v1/cardinality/label_names")
                self.assertEqual(query, {"limit": ["500"], "count_method": ["inmemory"]})
            elif signal == "profiles":
                self.assertEqual(req.get_method(), "POST")
                self.assertIn(parts.path, source.label_risk.PROFILE_PATHS)
                self.assertIn("allow-utf8-labelnames=true", req.get_header("Accept"))
                body = json.loads(req.data)
                self.assertEqual(body["end"] - body["start"], 86_400_000)
            else:
                self.assertEqual(req.get_method(), "GET")
                factor = 1_000_000_000 if signal == "logs" else 1
                self.assertEqual(int(query["end"][0]) - int(query["start"][0]), 86400 * factor)
        self.assertEqual(sum("/cardinality/label_names" in r.full_url for r in self.requests), 1)

    def test_disabled_zero_calls_and_no_isolated_client_construction(self):
        with mock.patch.object(source, "ReadOnlyClient") as client, mock.patch.object(source, "bounded_transport") as transport:
            self.assertEqual(source.probe_all(object(), [STACK], "cap"), {})
        client.assert_not_called()
        transport.assert_not_called()

    def test_deadline_slice_isolated_request_accounting_and_only_live_scannable_stacks(self):
        caller = ReadOnlyClient(deadline=400)
        real_client = ReadOnlyClient
        seen = []
        def factory(**kw):
            seen.append(kw)
            return real_client(**kw)
        with mock.patch.object(source, "bounded_transport", return_value=self.send), mock.patch.object(source, "ReadOnlyClient", side_effect=factory):
            records = source.probe_all(caller, [STACK, {"slug": "paused", "status": "paused"}], "cap", enabled=True)
        self.assertEqual(set(records), {"synthetic"})
        self.assertEqual(len(seen), 1)
        self.assertLessEqual(seen[0]["deadline"], 100)
        self.assertEqual(seen[0]["timeout"], 10)
        self.assertEqual(seen[0]["max_attempts"], 1)
        self.assertEqual(caller.attempts.requests, len(self.requests))
        self.assertEqual(caller.attempts.by_status, {200: len(self.requests)})
        self.requests.clear()
        caller = ReadOnlyClient(deadline=0)
        with mock.patch.object(source, "bounded_transport", return_value=self.send):
            records = source.probe_all(caller, [STACK], "cap", enabled=True)
        self.assertEqual(self.requests, [])
        self.assertTrue(all(p["state"] == "partial" and p["reason"] == "deadline" and p["data"] == "unknown"
                            for p in records["synthetic"]["signals"].values()))
        for value in (0, -1, 901, float("inf"), float("nan"), True):
            with self.assertRaisesRegex(ValueError, "invalid label inventory deadline"):
                source.probe_all(caller, [STACK], "cap", enabled=True, max_seconds=value)

    def test_minimization_bytes_pii_names_shapes_and_whole_row_caps(self):
        names = ["ordinary", "a" * 513, "é" * 257, "person_NAME_canary_8ef418@example.test", "user_email"]
        original = self.send
        def send(req, timeout):
            signal = urllib.parse.urlsplit(req.full_url).hostname.split(".")[0]
            if signal == "metrics":
                doc = {"label_names_count": len(names), "label_values_count_total": len(names),
                       "cardinality": [{"label_name": n, "label_values_count": 1} for n in names]}
            elif req.full_url.split("?")[0].endswith(("/labels", "/tags", "/LabelNames")):
                doc = ({"scopes": [{"name": "resource", "tags": names}]} if signal == "traces" else
                       {"names" if signal == "profiles" else "data": names, **({"status": "success"} if signal == "logs" else {})})
            else:
                values = ["VALUE_canary_773b536e", "reader@example.test", "+1 202 555 0199", "4242 4242 4242 4242", "x" * 300]
                doc = ({"tagValues": [{"type": "string", "value": v} for v in values]} if signal == "traces" else
                       {"names" if signal == "profiles" else "data": values, **({"status": "success"} if signal == "logs" else {})})
            return Response(200, json.dumps(doc).encode(), "")
        self.send = send
        record = self.probe()
        serialized = json.dumps(record)
        for sentinel in (names[1], names[2], names[3], names[4], "VALUE_canary_773b536e", "reader@example.test"):
            self.assertNotIn(sentinel, serialized)
        for p in record["signals"].values():
            for row in p["register"]:
                self.assertTrue(set(row["shape_counts"]) <= label_rules.SHAPES)
                if row["name_class"] != "ordinary":
                    self.assertIsNone(row["name"])
                    self.assertIsNone(row["distinct_count"])
                    self.assertEqual(row["shape_counts"], {})
            self.assertEqual(sum(r["name_count"] for r in p["register"] if r["name_class"] == "oversize"), 2)
        self.send = original
        capped = self.probe(bounds=source.Bounds(keys=1, values=1, rows=1))
        self.assertTrue(all(p["register_truncated"] == 1 and len(p["register"]) == 1 for p in capped["signals"].values()))
        self.assertTrue(all(p["inputs"]["missing_identity"]["names_truncated"] == 1 for p in capped["signals"].values()))
        self.assertEqual(capped["signals"]["logs"]["register"][0]["distinct_count"], 1)

    def test_exact200_malformed_numeric_contract_empty_and_error_sanitization(self):
        original = self.send
        for body, status in [(b'raw_VALUE_canary_bad', 200), (b'raw_NAME_canary_bad', 403),
                             (json.dumps(FIXTURE["metrics_names"]).encode(), 206),
                             (b'{"cardinality":[],"label_names_count":true,"label_values_count_total":0}', 200)]:
            with self.subTest(body=body, status=status):
                self.send = lambda *_: Response(status, body, "")
                record = self.probe()
                self.assertTrue(all(p["data"] == "unknown" and p["reason"] == "missing_input" for p in record["signals"].values()))
                self.assertNotIn("canary", json.dumps(record))
        def raises(*_):
            raise RuntimeError("VALUE_canary_in_exception NAME_canary_in_exception")
        self.send = raises
        self.assertNotIn("canary", json.dumps(self.probe()))
        self.send = original
        def empty(req, timeout):
            signal = urllib.parse.urlsplit(req.full_url).hostname.split(".")[0]
            doc = {"metrics": {"cardinality": [], "label_names_count": 0, "label_values_count_total": 0},
                   "logs": {"status": "success", "data": None}, "traces": {"scopes": []}, "profiles": {}}[signal]
            return Response(200, json.dumps(doc).encode(), "")
        self.send = empty
        record = self.probe()
        self.assertEqual(record["signals"]["metrics"]["data"], "empty")
        for signal in ("logs", "traces", "profiles"):
            self.assertEqual((record["signals"][signal]["data"], record["signals"][signal]["state"]), ("unknown", "partial"))

    def test_value_overflow_is_not_zero_or_pass_and_name_overflow_is_not_value_finding(self):
        original = self.send
        def overflowing(req, timeout):
            names = req.full_url.split("?")[0].endswith(("/label_names", "/labels", "/tags", "/LabelNames"))
            return original(req, timeout) if names else Response(200, b"VALUE_canary_overflow" * 200, "")
        self.send = overflowing
        record = self.probe(bounds=source.Bounds(response_bytes=1024))
        for signal in ("logs", "traces", "profiles"):
            self.assertEqual(record["signals"][signal]["inputs"]["shape_count"]["values_overflow"], 1)
        evaluated = label_rules.evaluate({"synthetic": record})
        shapes = [r for r in evaluated["results"] if r["rule"] in {"L_shape", "T_shape", "P_shape"}]
        self.assertTrue(all(r["result"] == "fail" and r["evidence"]["condition"] == "overflow" for r in shapes))
        self.assertNotIn("canary", json.dumps(record))
        self.send = original
        record = self.probe(bounds=source.Bounds(response_bytes=1))
        self.assertTrue(all(p["state"] == "partial" and p["reason"] == "truncated" and not p["inputs"] for p in record["signals"].values()))

    def test_bound_upper_envelope_and_priority_are_deterministic(self):
        def many(req, timeout):
            return Response(200, json.dumps({"label_names_count": 500, "label_values_count_total": 125250,
                "cardinality": [{"label_name": ("request_id" if n == 1 else "a" * 500 + str(n)), "label_values_count": n}
                                for n in range(1, 501)]}).encode(), "")
        self.send = many
        record = self.probe()
        p = record["signals"]["metrics"]
        self.assertEqual(p["register"][0]["name"], "request_id")
        self.assertEqual(p["register"][1]["distinct_count"], 500)
        self.assertEqual(len(p["register"]), 256)
        self.assertLessEqual(len(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode()), label_rules.MAX_SIGNAL_BYTES)
        self.assertEqual(p["reason"], "truncated")

    def test_escaped_name_serialization_drops_whole_rows_before_strict_validator(self):
        names = [str(n) + chr(34) * 508 for n in range(256)]
        self.send = lambda *_: Response(200, json.dumps({"label_names_count": 256,
            "label_values_count_total": 256,
            "cardinality": [{"label_name": n, "label_values_count": 1} for n in names]}).encode(), "")
        payload = self.probe()["signals"]["metrics"]
        self.assertEqual(payload["register_truncated"], 1)
        self.assertEqual((payload["state"], payload["reason"]), ("partial", "truncated"))
        self.assertLess(len(payload["register"]), 256)
        self.assertTrue(all(r["name"] in names for r in payload["register"]))
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()), label_rules.MAX_SIGNAL_BYTES)
        self.assertTrue(all(i["names_truncated"] for i in payload["inputs"].values()))

    def test_bounded_transport_keeps_overflow_status_and_existing_post_fences(self):
        class Body(io.BytesIO):
            status = 200
            headers = {}
        opener = mock.Mock()
        opener.open.return_value = Body(b"NAME_VALUE_canary_oversize")
        with mock.patch("urllib.request.build_opener", return_value=opener) as build:
            response = source.bounded_transport(4)(mock.Mock(), 2)
        self.assertEqual(response.status, 200)
        self.assertEqual(len(response.body), 5, "cap+1 bytes prove overflow without an unbounded read")
        for status in (206, 302, 401, 403, 500):
            opener.open.return_value = Body(b"secret-canary")
            opener.open.return_value.status = status
            with mock.patch("urllib.request.build_opener", return_value=opener):
                response = source.bounded_transport(4)(mock.Mock(), 2)
            self.assertEqual((response.status, response.body), (status, b""))
        self.assertIsNone(build.call_args.args[0].redirect_request(None, None, 302, "", {}, "https://evil.test"))
        with self.assertRaisesRegex(ValueError, "unlisted_label_read"):
            source.label_risk.profile_read(STACK, "cap", "/querier.v1.QuerierService/SelectSeries",
                                          {"start": 1, "end": 2}, transport=self.send)
        self.assertEqual(self.requests, [])

        # Exercise actual HTTPResponse.read1 framing, not an echoing transport.
        import http.client

        class Socket:
            def makefile(self, mode):
                return io.BytesIO(wire)

        raw_body = b'{"names":[]}'
        for length, transfer, error in ((str(len(raw_body)), b"", None),
                                        (str(len(raw_body) + 5), b"", "incomplete_response_body"),
                                        ("invalid", b"", "invalid_response_framing"),
                                        (str(len(raw_body)), b"Transfer-Encoding: chunked\r\n", "invalid_response_framing")):
            with self.subTest(length=length, transfer=bool(transfer)):
                wire = (b"HTTP/1.1 200 OK\r\nContent-Length: " + length.encode()
                        + b"\r\n" + transfer + b"\r\n" + raw_body)
                framed = http.client.HTTPResponse(Socket())
                framed.begin()
                opener.open.return_value = framed
                with mock.patch("urllib.request.build_opener", return_value=opener):
                    transport = source.bounded_transport(1024)
                    if error:
                        with self.assertRaisesRegex(ValueError, error):
                            transport(mock.Mock(), 2)
                    else:
                        self.assertEqual(transport(mock.Mock(), 2).body, raw_body)

    def test_actual_http_response_rejects_all_duplicate_content_lengths_before_reading(self):
        import http.client

        class Socket:
            def makefile(self, mode):
                return io.BytesIO(wire)

        raw_body = b'{"names":[]}'
        first = str(len(raw_body))
        for second in (str(len(raw_body) + 100), first, "invalid"):
            with self.subTest(second=second):
                wire = (b"HTTP/1.1 200 OK\r\nContent-Length: " + first.encode()
                        + b"\r\ncontent-length: " + second.encode() + b"\r\n\r\n" + raw_body)
                framed = http.client.HTTPResponse(Socket())
                framed.begin()
                self.assertEqual(framed.headers.get_all("Content-Length"), [first, second])
                opener = mock.Mock()
                opener.open.return_value = framed
                with (mock.patch("urllib.request.build_opener", return_value=opener),
                      mock.patch.object(framed, "read1", wraps=framed.read1) as read):
                    with self.assertRaisesRegex(ValueError, "invalid_response_framing"):
                        source.bounded_transport(1024)(mock.Mock(), 2)
                    read.assert_not_called()


class CompositionPlumbingContract(unittest.TestCase):
    def test_optional_private_argument_preserves_the_complete_old_return(self):
        from collector.coverage import Coverage
        from collector.pillars import compose
        contract = SourceContracts()
        contract.setUp()
        private = {STACK["slug"]: contract.probe()}
        coverage = Coverage(tier="t2", total=1)
        coverage.record_ok(STACK["slug"])
        before = compose.build_all([STACK], coverage, now=NOW)
        self.assertEqual(len(before), 3)
        for payload in (None, {}, private):
            with self.subTest(payload_present=bool(payload)):
                after = compose.build_all([STACK], coverage, now=NOW, label_inventory=payload)
                self.assertEqual(after, before, "additive source plumbing must not add or change pillar output")


class ConfigurationContract(unittest.TestCase):
    def test_own_default_off_enable_flag_and_redacted_count_only_projection(self):
        env = {name: "synthetic" for name, _ in config.REQUIRED_ENV}
        env["GCINSIGHT_READ_TOKEN"] = "synthetic-read"
        for raw, enabled in [(None, False), ("false", False), ("true", True), ("1", True), ("0", False)]:
            with self.subTest(raw=raw), mock.patch.dict("os.environ", env, clear=True):
                if raw is not None:
                    import os
                    os.environ[config.LABEL_INVENTORY_ENV] = raw
                cfg = config.load(tier="t2", dry_run=True)
                self.assertIs(cfg.label_inventory_enabled, enabled)
                self.assertIs(cfg.redacted["label_inventory_enabled"], enabled)
        with mock.patch.dict("os.environ", env | {config.LABEL_INVENTORY_ENV: "maybe"}, clear=True):
            with self.assertRaisesRegex(config.MissingConfig, "must be one of"):
                config.load(tier="t2", dry_run=True)
