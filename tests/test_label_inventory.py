"""Recorded synthetic response contracts and minimized source -> strict consumer seam."""
from __future__ import annotations

import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.parse

from collector import config, label_rules
from collector.httpclient import ReadOnlyClient, Response
from collector.sources import label_inventory as source

FIXTURE = json.loads((Path(__file__).parent / "fixtures/label_inventory/contracts.json").read_text())
C1 = json.loads((Path(__file__).parent / "fixtures/label_inventory/c1_series.json").read_text())
C2 = json.loads((Path(__file__).parent / "fixtures/label_inventory/c2_streams.json").read_text())
NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)
STACK = {"slug": "synthetic", "status": "active"}
for signal, (host, tenant, _) in source.SIGNALS.items():
    STACK.update({host: f"https://{signal}.example.test", tenant: 5_000_001})


def mimir_values(name, count, *, limit=256):
    """Synthetic body with the frozen C1 label/value row fields, not live data."""
    return {"series_count_total": count * 10, "labels": [{"label_name": name,
            "label_values_count": count, "series_count": count * 10,
            "cardinality": [{"label_value": f"VALUE_canary_{i}", "series_count": 10}
                            for i in range(min(count, limit))]}]}


class SourceContracts(unittest.TestCase):
    def setUp(self):
        self.requests = []

    def send(self, req, timeout):
        self.requests.append(req)
        signal = urllib.parse.urlsplit(req.full_url).hostname.split(".")[0]
        names = urllib.parse.urlsplit(req.full_url).path.endswith(("/label_names", "/labels", "/tags", "/LabelNames"))
        if urllib.parse.urlsplit(req.full_url).path == "/loki/api/v1/series":
            body = C2["series"]
        elif signal == "metrics" and not names:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            name = query["label_names[]"][0]
            count = next(r["label_values_count"] for r in FIXTURE["metrics_names"]["cardinality"] if r["label_name"] == name)
            body = mimir_values(name, count, limit=int(query["limit"][0]))
        else:
            body = FIXTURE[f"{signal}_{'names' if names else 'values'}"]
        return Response(200, json.dumps(body).encode(), "")

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
        self.assertEqual([s["population"] for s in samples], [2000, 30, 20])
        self.assertEqual(samples[1]["label_kind"], "static")
        self.assertEqual(metrics["inputs"]["shape_count"]["samples"][0]["value"], 0)
        self.assertEqual(metrics["inputs"]["metric_series"]["state"], "unavailable", "__name__ was not observed")
        # E2 now ships the witnessed stream consumer; the other routes remain unsupported.
        self.assertIn("labels_per_stream", record["signals"]["logs"]["inputs"])
        self.assertFalse(any(k in p["inputs"] for p in record["signals"].values()
                             for k in ("service_gap", "span_names", "drilldown_missing")))
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
        self.assertEqual((m4["result"], m4["reason"]), ("fail", None))
        for req in self.requests:
            parts = urllib.parse.urlsplit(req.full_url)
            signal = parts.hostname.split(".")[0]
            query = urllib.parse.parse_qs(parts.query)
            if signal == "metrics":
                if parts.path.endswith("/label_names"):
                    self.assertEqual(query, {"limit": ["500"], "count_method": ["inmemory"]})
                else:
                    self.assertEqual(parts.path, "/api/prom/api/v1/cardinality/label_values")
                    self.assertEqual(set(query), {"limit", "count_method", "label_names[]"})
                    self.assertEqual(query["limit"], ["256"])
                    self.assertEqual(query["count_method"], ["inmemory"])
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

    def test_c1_series_reductions_activate_verified_rules_without_values(self):
        names, values = C1["names"], C1["values"]
        self.assertEqual(sorted(values), C1["witness_top_keys"])
        self.assertEqual(sorted(values["labels"][0]), C1["witness_label_row_keys"])
        self.assertEqual(sorted(values["labels"][0]["cardinality"][0]), C1["witness_value_row_keys"])
        original = self.send
        def send(req, timeout):
            parts = urllib.parse.urlsplit(req.full_url)
            if parts.hostname != "metrics.example.test":
                return original(req, timeout)
            self.requests.append(req)
            if parts.path.endswith("/label_names"):
                body = names
            else:
                self.assertTrue(parts.path.endswith("/cardinality/label_values"))
                query = urllib.parse.parse_qs(parts.query)
                self.assertEqual(query["limit"], ["256"])
                self.assertEqual(query["count_method"], ["inmemory"])
                self.assertNotIn("start", query)
                body = json.loads(json.dumps(values))
                body["labels"][0]["label_name"] = query["label_names[]"][0]
            return Response(200, json.dumps(body).encode(), "")
        self.send = send
        record = self.probe()
        p = record["signals"]["metrics"]
        self.assertEqual(p["state"], "complete")
        self.assertEqual([s["value"] for s in p["inputs"]["metric_series"]["samples"]], [1200, 300])
        self.assertTrue(all(s["population"] == 1500 for s in p["inputs"]["distinct_values"]["samples"]))
        self.assertTrue(all(r["series_count"] == 1500 for r in p["register"]))
        results = {r["rule"]: r for r in label_rules.evaluate({"synthetic": record})["results"]}
        self.assertEqual((results["M5"]["result"], results["M5"]["evidence"]["offending_labels"]), ("fail", 1))
        self.assertEqual(results["M4"]["result"], "pass")
        self.assertGreater(label_rules.CATALOGUE.version, 1)
        self.assertNotIn("METRIC_canary", json.dumps(record))
        requests = [urllib.parse.parse_qs(urllib.parse.urlsplit(r.full_url).query)
                    for r in self.requests if "/cardinality/label_values" in r.full_url]
        self.assertEqual([q["label_names[]"][0] for q in requests], ["__name__", "job"])

    def c1_probe(self, transform=None, **kw):
        original = self.send
        def send(req, timeout):
            parts = urllib.parse.urlsplit(req.full_url)
            if parts.hostname != "metrics.example.test":
                return original(req, timeout)
            self.requests.append(req)
            if parts.path.endswith("/label_names"):
                return Response(200, json.dumps(C1["names"]).encode(), "")
            doc = copy.deepcopy(C1["values"])
            doc["labels"][0]["label_name"] = urllib.parse.parse_qs(parts.query)["label_names[]"][0]
            if transform is not None:
                return transform(doc)
            return Response(200, json.dumps(doc).encode(), "")
        self.send = send
        try:
            return self.probe(**kw)
        finally:
            self.send = original

    def test_c1_capped_priority_partial_missing_and_overflow_never_false_pass(self):
        record = self.c1_probe(bounds=source.Bounds(keys=1))
        self.assertEqual(record["signals"]["metrics"]["state"], "partial")
        calls = [r for r in self.requests if "/cardinality/label_values" in r.full_url]
        self.assertEqual(len(calls), 1)
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0].full_url).query)["label_names[]"], ["__name__"])
        def results(record):
            return {r["rule"]: r for r in label_rules.evaluate({"synthetic": record})["results"]}
        self.assertEqual(results(record)["M4"]["result"], "not_evaluated")
        self.assertEqual(results(record)["M5"]["result"], "fail")
        def partial(doc):
            doc["labels"][0]["label_values_count"] = 3
            doc["labels"][0]["series_count"] = doc["series_count_total"] = 2000
            doc["labels"][0]["cardinality"][0]["series_count"] = 800
            return Response(200, json.dumps(doc).encode(), "")
        bounded = results(self.c1_probe(partial))
        self.assertEqual((bounded["M5"]["result"], bounded["M5"]["reason"]), ("not_evaluated", "truncated"))
        for status in (206, 302, 403, 500):
            with self.subTest(status=status):
                unavailable = results(self.c1_probe(lambda doc: Response(status, json.dumps(doc).encode(), "")))
                self.assertEqual(unavailable["M5"]["result"], "not_evaluated")
                self.assertEqual(unavailable["M4"]["result"], "not_evaluated")
        overflow = results(self.c1_probe(lambda _: Response(200, b"raw_canary" * 1000, ""),
                                        bounds=source.Bounds(response_bytes=1024)))
        self.assertEqual((overflow["M5"]["result"], overflow["M5"]["evidence"]["condition"]), ("fail", "overflow"))

    def test_c1_value_shapes_are_closed_unweighted_and_pii_values_are_transient(self):
        def shapes(doc):
            if doc["labels"][0]["label_name"] != "__name__":
                doc["series_count_total"] = 600
                doc["labels"][0].update(label_values_count=3, series_count=600, cardinality=[
                    {"label_value": "550e8400-e29b-41d4-a716-446655440000", "series_count": 300},
                    {"label_value": "PII_VALUE_canary@example.test", "series_count": 200},
                    {"label_value": "long_VALUE_canary" * 20, "series_count": 100}])
            return Response(200, json.dumps(doc).encode(), "")
        record = self.c1_probe(shapes)
        p = record["signals"]["metrics"]
        row = next(r for r in p["register"] if r["name"] == "job")
        self.assertEqual(row["shape_counts"], {"uuid": 1, "long_value": 1})
        self.assertEqual(row["series_count"], 600)
        self.assertEqual(p["inputs"]["shape_count"]["samples"][0]["value"], 2)
        self.assertNotIn("canary", json.dumps(record))
        self.assertNotIn("550e8400", json.dumps(record))

    def test_c1_rejects_inconsistent_numeric_duplicate_missing_and_identity_shapes(self):
        mutations = [lambda d: d.update(series_count_total=True),
                     lambda d: d.update(series_count_total=label_rules.MAX_COUNT + 1),
                     lambda d: d.update(labels=[]),
                     lambda d: d["labels"].append(copy.deepcopy(d["labels"][0])),
                     lambda d: d["labels"][0].update(label_name="WRONG_NAME_canary"),
                     lambda d: d["labels"][0].update(series_count=100),
                     lambda d: d["labels"][0].update(series_count=1400),
                     lambda d: d["labels"][0].update(label_values_count=1),
                     lambda d: d["labels"][0]["cardinality"][0].update(series_count=-1),
                     lambda d: d["labels"][0]["cardinality"][0].update(label_value=chr(0xD800)),
                     lambda d: d["labels"][0]["cardinality"][1].update(label_value="METRIC_canary_853121")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                def invalid(doc):
                    mutation(doc)
                    return Response(200, json.dumps(doc).encode(), "")
                record = self.c1_probe(invalid)
                result = next(r for r in label_rules.evaluate({"synthetic": record})["results"] if r["rule"] == "M5")
                self.assertEqual((result["result"], result["reason"]), ("not_evaluated", "missing_input"))
                self.assertNotIn("canary", json.dumps(record))

    def test_c1_source_to_real_offline_cli_and_all_publication_fences(self):
        from collector.coverage import Coverage
        from collector.emit import loki
        from collector.pillars import compose, findings
        record = self.c1_probe()
        metrics, views, _ = compose.build_all([STACK], Coverage(tier="t2", total=1),
                                             label_inventory={STACK["slug"]: record})
        events, totals = findings.derive(views)
        public = [metrics, loki.finding_events("t2", events), findings.metrics(totals),
                  source.diagnostic_scan({"data": {"label_inventory": {STACK["slug"]: record}}, "views": views})]
        self.assertNotIn("canary", json.dumps([record, views, public]))
        self.assertTrue(any(r["Rule"] == "M5" and r["Result"] == "fail" for r in views["labelling_findings"]))
        with tempfile.TemporaryDirectory(prefix="label-mimir-cli-") as directory:
            scan, out = Path(directory) / "scan.json", Path(directory) / "views"
            scan.write_text(json.dumps({"stacks": [STACK], "label_inventory": {STACK["slug"]: record}}))
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "bin/make_local_views.py"),
                       "--scan", str(scan), "--out", str(out)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            serialized = run.stdout + run.stderr + "".join(p.read_text() for p in out.glob("*.json"))
            self.assertNotIn("canary", serialized)
            output = json.loads((out / "labelling_findings.json").read_text())
            self.assertTrue(any(r["Rule"] == "M5" and r["Result"] == "fail" and r["Catalogue version"] == 3
                                for r in output["rows"]))

    def c2_probe(self, transform=None, **kw):
        original = self.send
        def send(req, timeout):
            parts = urllib.parse.urlsplit(req.full_url)
            if parts.path != "/loki/api/v1/series":
                return original(req, timeout)
            self.requests.append(req)
            self.assertEqual(req.get_method(), "GET")
            query = urllib.parse.parse_qs(parts.query)
            self.assertEqual(query, {"match[]": [C2["selector"]],
                "start": [str(int(NOW.timestamp() - C2["window_seconds"]) * 1_000_000_000)],
                "end": [str(int(NOW.timestamp()) * 1_000_000_000)]})
            doc = copy.deepcopy(C2["series"])
            return transform(doc) if transform else Response(200, json.dumps(doc).encode(), "")
        self.send = send
        try:
            return self.probe(**kw)
        finally:
            self.send = original

    def test_c2_witnessed_stream_shape_true_label_population_and_no_ratio_policy(self):
        record = self.c2_probe()
        logs = record["signals"]["logs"]
        self.assertEqual((logs["window"], logs["state"], logs["reason"]), ("24h", "partial", "truncated"))
        sizes = logs["inputs"]["labels_per_stream"]
        self.assertEqual(sorted(s["value"] for s in sizes["samples"]), [2, 3, 16])
        self.assertTrue(all(s["semantics"] == "at_least" for s in sizes["samples"]))
        rows = {r["name"]: r for r in logs["register"]}
        self.assertEqual((rows["request_id"]["distinct_count"], rows["request_id"]["stream_count"]), (1, 2))
        self.assertEqual((rows["service_name"]["distinct_count"], rows["service_name"]["stream_count"]), (2, 3))
        self.assertEqual(rows["request_id"]["count_semantics"], "at_least")
        # Selected populations are real lower bounds, NOT whole-label denominators.
        self.assertTrue(all(s["population"] is None for s in logs["inputs"]["distinct_values"]["samples"]))
        results = {r["rule"]: r for r in label_rules.evaluate({"synthetic": record})["results"]}
        self.assertEqual((results["L1"]["result"], results["L1"]["evidence"]["offending_labels"]), ("fail", 1))
        self.assertEqual(results["L1"]["evidence"]["at_least"], 1)
        self.assertEqual((results["L3"]["result"], results["L3"]["reason"]), ("not_evaluated", "missing_input"))
        self.assertEqual(label_rules.CATALOGUE.version, 3)
        self.assertNotIn("STREAM_VALUE_canary", json.dumps(record))
        self.assertEqual(sum("/loki/api/v1/series" in r.full_url for r in self.requests), 1)
        self.assertFalse(any("ratio" in k for k in label_rules.CATALOGUE.inputs))

    def test_c2_selected_below_threshold_or_empty_never_whole_signal_pass(self):
        for data in ([], C2["series"]["data"][1:]):
            for warnings in ([], ["untrusted_warning_VALUE_canary"]):
                with self.subTest(empty=not data, warning=bool(warnings)):
                    def selected(doc):
                        doc.update(data=data, warnings=warnings)
                        return Response(200, json.dumps(doc).encode(), "")
                    record = self.c2_probe(selected)
                    logs = record["signals"]["logs"]
                    self.assertNotEqual(logs["data"], "empty")
                    self.assertEqual(logs["state"], "partial")
                    results = {r["rule"]: r for r in label_rules.evaluate({"synthetic": record})["results"]}
                    self.assertEqual(results["L1"]["result"], "not_evaluated")
                    self.assertEqual(results["L3"]["result"], "not_evaluated")
                    self.assertNotIn("canary", json.dumps(results))
        # Even many selected streams do not supply a whole-label denominator to L3.
        def many(doc):
            doc["data"] = [{"service_name": "VALUE_canary", "request_id": str(i)} for i in range(300)]
            return Response(200, json.dumps(doc).encode(), "")
        record = self.c2_probe(many)
        row = next(r for r in record["signals"]["logs"]["register"] if r["name"] == "request_id")
        self.assertEqual((row["distinct_count"], row["stream_count"], row["count_semantics"]), (256, 300, "at_least"))
        l3 = next(r for r in label_rules.evaluate({"synthetic": record})["results"] if r["rule"] == "L3")
        self.assertEqual((l3["result"], l3["reason"]), ("not_evaluated", "missing_input"))

    def test_c2_caps_prioritize_positive_sizes_and_deduplicate_streams_not_add_samples(self):
        def capped(doc):
            offender = doc["data"][0]
            doc["data"] = [{"service_name": "VALUE_canary", "cluster": str(i)} for i in range(300)]
            doc["data"].extend([offender, copy.deepcopy(offender)])
            return Response(200, json.dumps(doc).encode(), "")
        record = self.c2_probe(capped, bounds=source.Bounds(keys=1, values=1))
        logs = record["signals"]["logs"]
        self.assertEqual(len(logs["inputs"]["labels_per_stream"]["samples"]), 256)
        self.assertEqual(logs["inputs"]["labels_per_stream"]["samples"][0]["value"], 16)
        request = next(r for r in logs["register"] if r["name"] == "request_id")
        self.assertEqual((request["stream_count"], request["distinct_count"]), (1, 1))
        self.assertTrue(all(r["stream_count"] is None for r in logs["register"] if r["name"] != "request_id"))
        l1 = next(r for r in label_rules.evaluate({"synthetic": record})["results"] if r["rule"] == "L1")
        self.assertEqual((l1["result"], l1["evidence"]["offending_labels"]), ("fail", 1))
        self.assertNotIn("VALUE_canary", json.dumps(record))

    def test_c2_missing_partial_malformed_deadline_and_byte_cap_do_not_invent_violations(self):
        responses = [Response(status, json.dumps(C2["series"]).encode(), "") for status in (206, 302, 401, 403, 500)]
        responses.extend(Response(200, json.dumps(doc).encode(), "") for doc in (
            {"status": "error", "data": C2["series"]["data"]},
            {"status": "success", "data": None}, {"status": "success", "data": ["VALUE_canary"]},
            {"status": "success", "data": [{}]}, {"status": "success", "data": [{"service_name": True}]},
            {"status": "success", "data": [{"service_name": chr(0xD800)}]},
            {"status": "success", "data": [{chr(0xD800): "VALUE_canary"}]}))
        responses.extend([Response(200, b"VALUE_canary_malformed", ""),
                          Response(200, b"VALUE_canary" + b"x" * C2["byte_cap"], "")])
        for response in responses:
            with self.subTest(status=response.status, bytes=len(response.body)):
                record = self.c2_probe(lambda _: response)
                l1 = next(r for r in label_rules.evaluate({"synthetic": record})["results"] if r["rule"] == "L1")
                self.assertEqual(l1["result"], "not_evaluated")
                self.assertEqual(l1["evidence"]["condition"], "none")
                self.assertNotIn("canary", json.dumps(record))
        # Exercise expiry of the actual source caller budget. The existing GET
        # client wraps a transport-only TimeoutError as missing_input; that is
        # not evidence that the tier's deadline has expired, and is not repaired here.
        clock = [0.0]
        original = self.send
        def expired(req, timeout):
            if urllib.parse.urlsplit(req.full_url).path == "/loki/api/v1/series":
                clock[0] = 2.0
                return Response(200, json.dumps(C2["series"]).encode(), "")
            return original(req, timeout)
        client = ReadOnlyClient(transport=expired, deadline=1, max_attempts=1, clock=lambda: clock[0])
        record = source.probe_stack(client, STACK, "synthetic-cap", now=NOW, rpc_transport=expired)
        l1 = next(r for r in label_rules.evaluate({"synthetic": record})["results"] if r["rule"] == "L1")
        self.assertEqual((l1["result"], l1["reason"]), ("not_evaluated", "deadline"))
        self.assertNotIn("canary", json.dumps(record))

    def test_c2_stream_values_pii_names_and_oversize_keys_are_transient(self):
        def private(doc):
            doc["data"] = [{"service_name": "reader_VALUE_canary@example.test",
                "person_NAME_canary@example.test": "VALUE_canary", "user_email": "VALUE_canary",
                "x" * 513: "VALUE_canary", "request_id": "VALUE_canary"}]
            return Response(200, json.dumps(doc).encode(), "")
        record = self.c2_probe(private)
        serialized = json.dumps(record)
        self.assertNotIn("canary", serialized)
        self.assertNotIn("user_email", serialized)
        self.assertNotIn("x" * 513, serialized)
        self.assertTrue(all(r["stream_count"] is None for r in record["signals"]["logs"]["register"]
                            if r["name_class"] != "ordinary"))
        self.assertEqual(record["signals"]["logs"]["inputs"]["labels_per_stream"]["samples"][0]["value"], 5)

    def test_c2_actual_scan_cli_uses_new_get_without_leaking_values_or_names(self):
        from tests.test_scan import LabelInventoryProcessEdgeTest
        evidence = LabelInventoryProcessEdgeTest().exercise()
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        requests = [r for r in evidence["requests"] if "/loki/api/v1/series" in r.full_url]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].get_method(), "GET")
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(requests[0].full_url).query)["match[]"], [C2["selector"]])
        logs = evidence["source"][0]["synthetic"]["signals"]["logs"]
        self.assertEqual(logs["inputs"]["labels_per_stream"]["samples"][0]["value"], 3)
        for boundary in ("source", "scans", "views", "metrics", "events", "stdout", "stderr", "out"):
            for sentinel in (evidence["value"], evidence["suppressed"]):
                self.assertNotIn(sentinel, json.dumps(evidence[boundary]), boundary)
        for boundary in ("metrics", "events", "stdout", "stderr", "out"):
            self.assertNotIn(evidence["ordinary"], json.dumps(evidence[boundary]), boundary)

    def test_c2_positive_violation_survives_real_offline_view_cli_and_only_private_counts(self):
        record = self.c2_probe()
        with tempfile.TemporaryDirectory(prefix="label-loki-cli-") as directory:
            scan, out = Path(directory) / "scan.json", Path(directory) / "views"
            scan.write_text(json.dumps({"stacks": [STACK], "label_inventory": {STACK["slug"]: record}}))
            run = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "bin/make_local_views.py"),
                                  "--scan", str(scan), "--out", str(out)],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            serialized = run.stdout + run.stderr + "".join(p.read_text() for p in out.glob("*.json"))
            self.assertNotIn("STREAM_VALUE_canary", serialized)
            rows = json.loads((out / "labelling_findings.json").read_text())["rows"]
            l1 = next(r for r in rows if r["Rule"] == "L1")
            self.assertEqual((l1["Result"], l1["Offending objects"], l1["Catalogue version"]), ("fail", 1, 3))
            l3 = next(r for r in rows if r["Rule"] == "L3")
            self.assertEqual((l3["Result"], l3["Reason"]), ("not_evaluated", "missing_input"))

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
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            if "label_names[]" in query:
                name = query["label_names[]"][0]
                count = 1 if name == "request_id" else int(name[500:])
                return Response(200, json.dumps(mimir_values(name, count)).encode(), "")
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
        def escaped(req, timeout):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            doc = (mimir_values(query["label_names[]"][0], 1) if "label_names[]" in query else
                   {"label_names_count": 256, "label_values_count_total": 256,
                    "cardinality": [{"label_name": n, "label_values_count": 1} for n in names]})
            return Response(200, json.dumps(doc).encode(), "")
        self.send = escaped
        payload = self.probe()["signals"]["metrics"]
        self.assertEqual(payload["register_truncated"], 1)
        self.assertEqual((payload["state"], payload["reason"]), ("partial", "truncated"))
        self.assertLess(len(payload["register"]), 256)
        self.assertTrue(all(r["name"] in names for r in payload["register"]))
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()), label_rules.MAX_SIGNAL_BYTES)
        self.assertTrue(all(i["names_truncated"] for i in payload["inputs"].values() if i["state"] != "unavailable"))

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
    def test_shipping_private_consumer_preserves_existing_pillar_outputs(self):
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
                existing_metrics = [m for m in after[0] if not m[0].startswith("gcinsight_labelling_")]
                existing_views = {name: rows for name, rows in after[1].items()
                                  if not name.startswith("labelling_")}
                self.assertEqual((existing_metrics, existing_views, after[2]), before,
                                 "shipping labelling must preserve every existing pillar output")
                if payload:
                    self.assertIn("labelling_label_register", after[1])
                    self.assertIn("labelling_stack_summary", after[1])


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
