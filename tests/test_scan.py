"""Scan orchestration contracts that span the individual collectors.

The per-source collectors already preserve their own unavailable states.  This module pins the seam
above them: a healthy gcom detail sweep must not make a T2 run look healthy when every stack-local
source failed.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import bin.make_compose_fixture as compose_fixture
import scan
from collector import config
from collector.emit import hydrate


def cfg_for(tier: str = "t2") -> config.Config:
    return config.Config(
        cap="read", write_token="write", org_id="1", tier=tier, dry_run=True,
        limit=None, stack=None, concurrency=1, deadline_seconds=900, write_stack="target",
        mimir_url="https://mimir.invalid", mimir_tenant="1",
        loki_url="https://loki.invalid", loki_tenant="2",
    )


class FakeClient:
    class Attempts:
        requests = 0
        retries = 0

    attempts = Attempts()


class LabelDomainPublicationTest(unittest.TestCase):
    """Real T3 runner/source accounting/compose and shared publication, with offline I/O."""

    def exercise(self, seed=()):
        from collector.httpclient import DeadlineExceeded, MethodNotAllowed, ReadOnlyClient, Response

        categories = {
            "Learn (web)": 2, "Errors (lodestone)": 3,
            "person-id-canary (tenant-path-canary)": 5,
            "new-category (new-surface)": 7, "other (other)": 11,
            "Investigate": 13, "Other (cli)": 17,
        }
        def transport(request, timeout):
            path = request.full_url.split("?")[0]
            if path.endswith("hero-stats"):
                body = {"data": {"totalUserMessages": sum(categories.values())}}
            elif path.endswith("chat-categories"):
                body = {"data": {"schema": {"fields": [
                    {"name": name, "type": "number"} for name in categories]},
                    "data": {"values": [[count] for count in categories.values()]}}}
            else:
                body = {"data": {}}
            return Response(200, json.dumps(body).encode(), request.full_url)

        client = ReadOnlyClient(transport=transport, max_attempts=1)
        # Exercise the public source parser: names are open even when a metric domain is fixed.
        assistant = scan.assistant_src.probe_stack(client, "s0", "synthetic")
        inventory = [{"slug": f"s{i}", "status": "active"} for i in range(100)]
        errors = [type("NovelError_one", (Exception,), {})("synthetic"),
                  type("NovelError_two", (Exception,), {})("synthetic"),
                  type("person@example.test", (Exception,), {})("synthetic"),
                  RuntimeError("synthetic"), ValueError("synthetic"), KeyError("synthetic"),
                  MethodNotAllowed("synthetic"), DeadlineExceeded("synthetic"),
                  json.JSONDecodeError("synthetic", "", 0)]
        def probe(client, stack, cap):
            index = int(stack["slug"][1:])
            if index < len(errors):
                raise errors[index]
            return {}

        def hydrated(tier, gathered, **kwargs):
            return {**gathered, "assistant": {"s0": assistant}}, {}

        saved, published, wire = [], [], []
        real_push, real_runner = scan.mimir.RemoteWriter.push, scan.run_t3
        def runner(client, cfg):
            result = real_runner(client, cfg)
            result["_emit"]["metrics"].extend(seed)
            return result
        def post(request, timeout):
            self.assertEqual(request.full_url, "https://mimir.invalid/api/prom/push")
            self.assertEqual(request.method, "POST")
            wire.append(scan.mimir.snappy_decompress(request.data))
            response = mock.MagicMock()
            response.__enter__.return_value.status = 204
            return response
        def save(metrics, *args, **kwargs):
            saved.extend(metrics)
            return "offline carry sink"
        def push(writer, metrics):
            published.extend(metrics)
            # Real writer validation, externalization, protobuf and snappy; fake only its HTTP sink.
            return real_push(writer, metrics)

        from dataclasses import replace
        cfg = replace(cfg_for("t3"), dry_run=False)
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t3", side_effect=runner),
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=inventory),
            mock.patch.object(scan.dataplane, "probe_stack", side_effect=probe),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=hydrated),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan.carry, "save_state", side_effect=save),
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir.RemoteWriter, "push", autospec=True, side_effect=push),
            mock.patch.object(scan.loki.LokiWriter, "push", return_value=0),
            mock.patch("urllib.request.urlopen", side_effect=post),
            mock.patch("socket.socket.connect", side_effect=AssertionError("no network")),
            mock.patch.object(subprocess, "run", side_effect=AssertionError("no subprocess")),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(scan.run(client, cfg, SimpleNamespace(out=None)), 0)
        self.assertEqual(len(wire), 1, "exercise actual native remote_write transport")
        for canary in (b"person-id-canary", b"tenant-path-canary", b"NovelError", b"person@example.test"):
            self.assertNotIn(canary, wire[0])
        self.assertEqual(assistant["categories"], categories, "projection must not mutate source input")
        return saved, published, sum(categories.values())

    def assert_sinks(self, saved, published, *, other_messages=23, other_failures=3):
        from collector.emit import guard
        expected = {
            ("Learn", "web"): 2, ("Errors", "lodestone"): 3,
            ("other", "other"): other_messages, ("Investigate", "unknown"): 13, ("Other", "cli"): 17,
        }
        for sink in (saved, published):
            self.assertTrue(sink, "both carry and push must actually receive samples")
            guard.check_no_duplicates(sink)
            ai = {(labels["category"], labels["surface"]): value for name, labels, value in sink
                  if name == "gcinsight_ai_estate_messages"}
            self.assertEqual(ai, expected)
            failed = {labels["reason"]: value for name, labels, value in sink
                      if name == "gcinsight_scan_stacks_failed"}
            self.assertEqual(failed, {"RuntimeError": 1, "ValueError": 1, "KeyError": 1,
                                      "MethodNotAllowed": 1, "DeadlineExceeded": 1,
                                      "JSONDecodeError": 1, "other": other_failures})
            self.assertEqual(sum(ai.values()), sum(expected.values()))
            self.assertNotIn("person-id-canary", json.dumps([labels for _, labels, _ in sink]))
            self.assertNotIn("NovelError", json.dumps([labels for _, labels, _ in sink]))

    def test_open_inputs_are_projected_and_collisions_summed_before_every_metric_sink(self):
        saved, published, total = self.exercise()
        self.assert_sinks(saved, published)
        self.assertEqual(sum(v for n, _, v in published if n == "gcinsight_ai_estate_messages"), total)

    def test_gcom_open_exception_names_are_bounded_at_the_common_publication_boundary(self):
        # Use the original public Coverage interface and real gcom exception catcher so this
        # also proves the common boundary, independently of ScanCoverage's early projection.
        from collector.coverage import Coverage
        inventory = [{"slug": f"s{i}"} for i in range(30)]
        coverage = Coverage("t2", len(inventory))
        errors = [type("NovelFailure_one", (Exception,), {}),
                  type("NovelFailure_two", (Exception,), {})]
        def detail(client, cfg, slug):
            index = int(slug[1:])
            if index < len(errors):
                raise errors[index]("synthetic")
            return {}
        with mock.patch.object(scan.gcom, "fetch_stack_detail", side_effect=detail):
            records = scan.gcom.fetch_all_stack_detail(FakeClient(), cfg_for(), inventory, coverage)
        result = {"meta": {"tier": "t2", **coverage.as_meta()}, "data": {"stack_detail": records},
                  "_emit": {"metrics": coverage.as_metrics(), "views": {}, "view_coverage": {}}}
        published = []
        def push(metrics):
            published.extend(metrics)
            return len(metrics)
        with (
            mock.patch.object(scan, "run_t2", return_value=result),
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir.RemoteWriter, "push", side_effect=push),
            mock.patch.object(scan.loki.LokiWriter, "push", return_value=0),
            mock.patch("socket.socket.connect", side_effect=AssertionError("no network")),
            mock.patch.object(subprocess, "run", side_effect=AssertionError("no subprocess")),
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(scan.run(FakeClient(), cfg_for(), SimpleNamespace(out=None)), 0)
        failed = [(labels, value) for name, labels, value in published
                  if name == "gcinsight_scan_stacks_failed"]
        self.assertEqual(failed, [({"tier": "t2", "reason": "other"}, 2)])
        self.assertEqual(result["meta"]["failures_by_reason"],
                         {"NovelFailure_one": 1, "NovelFailure_two": 1},
                         "raw diagnostics are not the metric domain")

    def test_unrelated_duplicate_series_are_still_refused_at_publication(self):
        from collector.emit import guard
        with self.assertRaises(guard.DuplicateSeries):
            self.exercise([("gcinsight_estate_stacks", {"status": "total"}, 999)])

    def test_t1_live_hydration_deduplicates_legacy_carry_before_native_publication(self):
        import copy
        import datetime as dt
        from dataclasses import replace

        live = [{"slug": "live", "status": "active"}]
        assistant = scan.assistant_src.summarise_stack(
            "live", {"totalUserMessages": 7}, {"NovelCategory (NovelSurface)": 7},
            {}, 1, {}, [])
        legacy = {"tier": "t3", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "metrics": [["gcinsight_ai_estate_messages",
                               {"category": "NovelCategory", "surface": "NovelSurface"}, 7]]}
        original = copy.deepcopy(legacy)
        published, wire = [], []
        real_push = scan.mimir.RemoteWriter.push

        def push(writer, metrics):
            published.extend(metrics)
            return real_push(writer, metrics)

        def post(request, timeout):
            self.assertEqual(request.full_url, "https://mimir.invalid/api/prom/push")
            wire.append(scan.mimir.snappy_decompress(request.data))
            response = mock.MagicMock()
            response.__enter__.return_value.status = 204
            return response

        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=live),
            mock.patch.object(scan.gcom, "fetch_access_policies", return_value=[]),
            mock.patch.object(scan.gcom, "fetch_org_members", return_value={"state": "ok", "members": []}),
            mock.patch.object(scan, "gather_fleet", return_value=({}, [])),
            mock.patch.object(scan.hydrate, "hydrate", return_value=({"assistant": {"live": assistant}}, {})),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan.carry, "load_state", return_value=legacy),
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir.RemoteWriter, "push", autospec=True, side_effect=push),
            mock.patch.object(scan.loki.LokiWriter, "push", return_value=0),
            mock.patch("urllib.request.urlopen", side_effect=post),
            mock.patch("socket.socket.connect", side_effect=AssertionError("no network")),
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(scan.run(FakeClient(), replace(cfg_for("t1"), dry_run=False),
                                      SimpleNamespace(out=None)), 0)
        self.assertEqual(len(wire), 1, "exercise native remote_write with real T1 runner/compose/carry")
        messages = [(labels, value) for name, labels, value in published
                    if name == "gcinsight_ai_estate_messages"]
        self.assertEqual(messages, [({"category": "other", "surface": "other"}, 7)])
        self.assertNotIn(b"NovelCategory", wire[0])
        self.assertEqual(legacy, original, "projection must not rewrite the retained source state")

    def test_common_boundary_projects_legacy_runner_batches_before_carry_save_and_push(self):
        # Seed AFTER real source accounting and compose, so early producer/helper projection
        # cannot make this pass. Old carry state and later producers are fenced by run itself.
        seed = [
            ("gcinsight_ai_estate_messages", {"category": "one@example.test", "surface": "path/one"}, 4),
            ("gcinsight_ai_estate_messages", {"category": "two@example.test", "surface": "path/two"}, 6),
            ("gcinsight_ai_estate_messages", {"category": "other", "surface": "other"}, 8),
            ("gcinsight_scan_stacks_failed", {"tier": "t3", "reason": "NovelError_legacy_one"}, 10),
            ("gcinsight_scan_stacks_failed", {"tier": "t3", "reason": "NovelError_legacy_two"}, 12),
            ("gcinsight_scan_stacks_failed", {"tier": "t3", "reason": "other"}, 14),
        ]
        saved, published, total = self.exercise(seed)
        self.assert_sinks(saved, published, other_messages=41, other_failures=39)
        self.assertEqual(sum(v for n, _, v in published if n == "gcinsight_ai_estate_messages"), total + 18)
        self.assertEqual(seed[0][1]["category"], "one@example.test", "do not mutate the legacy batch")


class EnterpriseProcessEdgeTest(unittest.TestCase):
    def test_anonymous_catalogue_once_from_fresh_inventory_attaches_only_live_successes(self):
        from collector.httpclient import ReadOnlyClient, Response
        stacks = [
            {"slug": "ok", "datasourceCnts": {"grafana-aurora-datasource": 2}},
            {"slug": "failed", "datasourceCnts": {"yesoreyeram-infinity-datasource": 1}},
            {"slug": "paused", "datasourceCnts": {"grafana-aurora-datasource": 1}},
        ]
        detail = {"ok": {"users": []}, "departed": {"users": []}}
        requests = []
        fixtures = pathlib.Path(__file__).parent / "fixtures"

        def transport(request, timeout):
            requests.append(request)
            name = request.full_url.rsplit("/", 1)[-1]
            path = fixtures / ("plugin_catalog." + name + ".json")
            return Response(200, json.dumps(json.loads(path.read_text())["body"]).encode(),
                            request.full_url)

        client = ReadOnlyClient(transport=transport, max_attempts=1)
        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.label_risk_src, "probe_all", return_value={}),
            mock.patch.object(scan.gcom, "fetch_all_stack_detail", return_value=detail),
            mock.patch.object(scan, "gather_service_accounts", side_effect=RuntimeError("stop seam")),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop seam"):
                scan.run_t2(client, cfg_for())
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(not r.has_header("Authorization") for r in requests))
        self.assertEqual(set(detail), {"ok", "departed"})
        self.assertNotIn("plugin_catalogue", detail["departed"])
        self.assertEqual(set(detail["ok"]["plugin_catalogue"]), {"grafana-aurora-datasource"})
        self.assertIs(detail["ok"]["plugin_catalogue"]["grafana-aurora-datasource"]["enterprise"], True)
        self.assertNotIn("author", json.dumps(detail))


class LabelInventoryDiagnosticBoundaryTest(unittest.TestCase):
    def test_real_cli_out_excludes_private_input_and_future_label_register(self):
        name = "ordinary_NAME_canary_7d0de1a4"
        result = {
            "meta": {"tier": "t2", "coverage_ratio": 1.0, "stacks_total": 1,
                     "stacks_failed": 0, "stacks_scannable": 1},
            "data": {"label_inventory": {"alpha": {"name": name}}},
            # A later pillar may attach the private register to the scan for diagnostic purposes.
            "views": {"labelling_label_register": [{"Label name": name}]},
            "_emit": {"metrics": [], "views": {}, "view_coverage": {}},
        }
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "diagnostic.json"
            with (
                mock.patch.object(scan.config, "load", return_value=cfg_for()),
                mock.patch.object(scan, "run_t2", return_value=result),
                mock.patch.object(scan.s3emit, "write_views", return_value=[]),
                mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
                mock.patch.object(scan.mimir.RemoteWriter, "push", return_value=0),
                mock.patch.object(scan.loki.LokiWriter, "push", return_value=0),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(scan.main(["--tier", "t2", "--dry-run", "--out", str(output)]), 0)
            self.assertNotIn(name, output.read_text())
        self.assertIn(name, json.dumps(result), "filtering must not mutate the private S3 scan")


class LabelInventoryProcessEdgeTest(unittest.TestCase):
    """Drive actual CLI/config/inventory/source/compose/publication seams, no live calls."""

    def exercise(self, enabled=True, mode="valid", extra_args=()):
        from collector.httpclient import Response
        from tests.test_label_inventory import STACK
        from collector.sources import label_inventory as source
        import urllib.parse

        value = "VALUE_canary_eb6d5cca"
        suppressed = "NAME_canary_9c708f2a@example.test"
        ordinary = "ordinary_NAME_canary_5571e2a"
        requests, raw_source, scans, views, metrics, events = [], [], [], [], [], []
        env = {name: "synthetic" for name, _ in config.REQUIRED_ENV}
        env.update({"GCINSIGHT_READ_TOKEN": "synthetic-read", "GCINSIGHT_LABEL_INVENTORY_ENABLED": str(enabled).lower(),
                    "GCINSIGHT_MIMIR_URL": "https://mimir.invalid", "GCINSIGHT_LOKI_URL": "https://loki.invalid"})
        fixtures = json.loads((pathlib.Path(__file__).parent / "fixtures/label_inventory/contracts.json").read_text())

        def body(req):
            requests.append(req)
            parts = urllib.parse.urlsplit(req.full_url)
            if parts.hostname == "grafana.com":
                if parts.path == "/api/instances":
                    return json.dumps({"items": [STACK]}).encode()
                return b'{"items":[]}'  # actual gcom detail user/plugin reads
            signal = parts.hostname.split(".")[0]
            names = parts.path.endswith(("/label_names", "/labels", "/tags", "/LabelNames"))
            if mode == "exception":
                raise RuntimeError(value + suppressed)
            if signal == "metrics":
                if names:
                    names_list = [ordinary, suppressed, "job"]
                    doc = {"label_names_count": 3, "label_values_count_total": 3,
                           "cardinality": [{"label_name": n, "label_values_count": 1} for n in names_list],
                           "untrusted_extra": value}
                else:
                    label = urllib.parse.parse_qs(parts.query)["label_names[]"][0]
                    doc = {"series_count_total": 1, "labels": [{"label_name": label,
                           "label_values_count": 1, "series_count": 1,
                           "cardinality": [{"label_value": value, "series_count": 1}]}]}
            elif parts.path == "/loki/api/v1/series":
                if mode == "overflow":
                    return (value + suppressed).encode() + b"x" * (2 * 1024 * 1024)
                if mode == "malformed":
                    return (value + suppressed).encode()
                doc = {"status": "success", "data": [
                    {ordinary: value, suppressed: value, "service_name": value}]}
            elif names:
                names_list = [ordinary, suppressed, "service_name"]
                doc = ({"scopes": [{"name": "resource", "tags": names_list}]} if signal == "traces" else
                       {"names" if signal == "profiles" else "data": names_list,
                        **({"status": "success"} if signal == "logs" else {})})
            elif mode == "overflow":
                return (value + suppressed).encode() + b"x" * (2 * 1024 * 1024)
            elif mode == "malformed":
                return (value + suppressed).encode()
            else:
                if parts.path == "/tempo/api/v2/search/tag/name/values":
                    doc = json.loads((pathlib.Path(__file__).parent / "fixtures/label_inventory/c4_span_names.json").read_text())["values"]
                else:
                    doc = fixtures[f"{signal}_values"]
                if signal == "traces":
                    doc = {"tagValues": doc["tagValues"] + [{"type": "string", "value": value}]}
                else:
                    key = "names" if signal == "profiles" else "data"
                    doc = {**doc, key: doc[key] + [value]}
            return json.dumps(doc).encode()

        class Body(io.BytesIO):
            status = 200
            headers = {}

        opener = mock.Mock()
        def opened(req, timeout):
            raw_body = body(req)
            if mode not in {"incomplete", "duplicate_conflicting", "duplicate_repeated"}:
                return Body(raw_body)
            import http.client

            class Socket:
                def makefile(self, mode):
                    return io.BytesIO(wire)

            is_metrics = "/cardinality/label_names" in req.full_url
            declared = len(raw_body) + (100 if mode == "incomplete" and is_metrics else 0)
            duplicate = b""
            if mode.startswith("duplicate_") and is_metrics:
                second = len(raw_body) + (100 if mode == "duplicate_conflicting" else 0)
                duplicate = b"Content-Length: " + str(second).encode() + b"\r\n"
            wire = (b"HTTP/1.1 200 OK\r\nContent-Length: " + str(declared).encode()
                    + b"\r\n" + duplicate + b"\r\n" + raw_body)
            response = http.client.HTTPResponse(Socket())
            response.begin()
            return response

        opener.open.side_effect = opened
        real_probe = source.probe_all
        real_runner = scan.run_t2
        real_hydrate = hydrate.hydrate

        def capture_source(*args, **kwargs):
            records = real_probe(*args, **kwargs)
            raw_source.append(json.loads(json.dumps(records)))
            return records

        def capture_runner(*args):
            result = real_runner(*args)
            scans.append(json.loads(json.dumps(result)))
            return result

        healthy = {STACK["slug"]: {"available": True}}
        compose_contract = json.loads((pathlib.Path(__file__).parent / "fixtures/compose_inputs.json").read_text())
        def related_input(name):
            records = compose_contract.get(name) or {}
            row = next((r for r in records.values() if isinstance(r, dict) and r.get("available")), None)
            return {STACK["slug"]: row} if row else healthy
        gather_names = ["gather_assistant", "gather_insights", "gather_dashboard_inventory",
            "gather_datasource_query_cost", "gather_adaptive_logs", "gather_adaptive_traces",
            "gather_public_dashboards", "gather_alert_routing", "gather_slo_inventory",
            "gather_synthetic_inventory", "gather_irm_integrations", "gather_irm_alert_groups",
            "gather_ml_jobs", "gather_reports_inventory", "gather_playlists_inventory",
            "gather_library_panels_inventory", "gather_cloud_accounts", "gather_faro_apps", "gather_signal_inventory"]
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as patches:
            output = pathlib.Path(directory) / "out.json"
            stdout, stderr = io.StringIO(), io.StringIO()
            patches.enter_context(mock.patch.dict(os.environ, env, clear=True))
            patches.enter_context(mock.patch("collector.httpclient._urllib_transport", side_effect=lambda req, timeout: Response(200, body(req), "")))
            # Real bounded read/byte-cap/redirect handler, fake process-edge opener only.
            patches.enter_context(mock.patch("urllib.request.build_opener", return_value=opener))
            patches.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value=healthy))
            patches.enter_context(mock.patch.object(source, "probe_all", side_effect=capture_source))
            patches.enter_context(mock.patch.object(scan, "run_t2", side_effect=capture_runner))
            patches.enter_context(mock.patch.object(scan.plugin_catalog, "fetch_catalogue", return_value={}))
            for name in gather_names:
                patches.enter_context(mock.patch.object(scan, name, return_value=(related_input(name.removeprefix("gather_")), [])))
            patches.enter_context(mock.patch.object(scan, "gather_pdc_networks", return_value=(related_input("pdc_networks"), [])))
            patches.enter_context(mock.patch.object(scan, "gather_service_accounts", return_value=({STACK["slug"]: {"state": scan.sa_src.OK, "accounts": []}}, [])))
            patches.enter_context(mock.patch.object(scan, "gather_capability_adoption", return_value=(compose_contract["capability_adoption"], [])))
            patches.enter_context(mock.patch.object(scan, "gather_loki_config", return_value=({STACK["slug"]: {"limits": {"available": True}, "change_requests": {"available": True}}}, [])))
            patches.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
            patches.enter_context(mock.patch.object(scan, "assistant_gaps", return_value={}))
            patches.enter_context(mock.patch.object(hydrate, "hydrate", side_effect=lambda *a, **kw: real_hydrate(*a, loader=lambda *_: None, **kw)))
            patches.enter_context(mock.patch.object(scan.s3emit, "write_views", side_effect=lambda v, *a, **kw: views.append(v) or []))
            patches.enter_context(mock.patch.object(scan.s3emit, "write_scan", side_effect=lambda s, **kw: scans.append(json.loads(json.dumps(s))) or []))
            patches.enter_context(mock.patch.object(scan.mimir.RemoteWriter, "push", side_effect=lambda m: metrics.extend(m) or len(m)))
            patches.enter_context(mock.patch.object(scan.loki.LokiWriter, "push", side_effect=lambda e: events.extend(e) or len(e)))
            patches.enter_context(contextlib.redirect_stdout(stdout))
            patches.enter_context(contextlib.redirect_stderr(stderr))
            code = scan.main(["--tier", "t2", "--dry-run", "--out", str(output), *extra_args])
            diagnostic = output.read_text() if output.exists() else ""
        return {"code": code, "source": raw_source, "scans": scans, "views": views, "metrics": metrics,
                "events": events, "stdout": stdout.getvalue(), "stderr": stderr.getvalue(),
                "out": diagnostic, "requests": requests, "value": value, "suppressed": suppressed,
                "ordinary": ordinary}

    def test_incomplete_http_body_withholds_private_input_but_allows_other_publication(self):
        from collector import label_rules

        evidence = self.exercise(mode="incomplete")
        private = evidence["source"][0]
        self.assertNotIn("label_inventory", evidence["scans"][0]["data"],
                         "unavailable owner input must be withheld, not persisted as complete")
        payload = private["synthetic"]["signals"]["metrics"]
        self.assertEqual(payload["state"], "unavailable")
        self.assertEqual(payload["data"], "unknown")
        result = next(r for r in label_rules.evaluate(private)["results"] if r["rule"] == "M_identity")
        self.assertEqual((result["result"], result["reason"]), ("not_evaluated", "missing_input"))
        self.assertEqual(evidence["code"], 0)
        self.assertFalse(evidence["scans"][0]["meta"]["scan_healthy"])
        self.assertTrue(evidence["views"], "D-LBL12 preserves other T2 publication")
        self.assertTrue(all(not any(name.startswith("labelling_") for name in views)
                            for views in evidence["views"]))

    def test_duplicate_http_lengths_withhold_private_input_but_allow_other_publication(self):
        from collector import label_rules

        for mode in ("duplicate_conflicting", "duplicate_repeated"):
            with self.subTest(mode=mode):
                evidence = self.exercise(mode=mode)
                private = evidence["source"][0]
                payload = private["synthetic"]["signals"]["metrics"]
                self.assertEqual((payload["state"], payload["data"], payload["reason"]),
                                 ("unavailable", "unknown", "missing_input"))
                self.assertNotIn("label_inventory", evidence["scans"][0]["data"],
                                 "ambiguous owner input must be withheld")
                result = next(r for r in label_rules.evaluate(private)["results"] if r["rule"] == "M_identity")
                self.assertEqual((result["result"], result["reason"]), ("not_evaluated", "missing_input"))
                self.assertEqual(evidence["code"], 0)
                self.assertFalse(evidence["scans"][0]["meta"]["scan_healthy"])
                for boundary in ("views", "metrics", "events"):
                    self.assertTrue(evidence[boundary], "D-LBL12 must not refuse unrelated writes")
                self.assertTrue(all(not any(name.startswith("labelling_") for name in views)
                                    for views in evidence["views"]))
                self.assertTrue(evidence["out"])
                for boundary in ("source", "scans", "views", "metrics", "events", "stdout", "stderr", "out"):
                    self.assertNotIn(evidence["value"], json.dumps(evidence[boundary]), boundary)
                    self.assertNotIn(evidence["suppressed"], json.dumps(evidence[boundary]), boundary)
                for boundary in ("views", "metrics", "events", "stdout", "stderr", "out"):
                    self.assertNotIn(evidence["ordinary"], json.dumps(evidence[boundary]), boundary)

    def test_cli_default_off_performs_no_label_source_calls(self):
        evidence = self.exercise(enabled=False)
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        self.assertEqual(evidence["source"], [{}])
        self.assertTrue(all("grafana.com" in r.full_url for r in evidence["requests"]))
        # Disabled inputs retain an empty persisted key, not a measured-empty payload.
        self.assertEqual(evidence["scans"][0]["data"]["label_inventory"], {})
        self.assertEqual(evidence["scans"][0]["data"]["library_panels_inventory"], {})
        self.assertEqual(evidence["scans"][0]["meta"]["sources"]["label_inventory"]["reason"], "not_selected")
        self.assertEqual(evidence["scans"][0]["meta"]["sources"]["label_inventory"]["state"], "disabled")
        for name in ("label_inventory", "library_panels_inventory"):
            self.assertEqual(evidence["scans"][0]["meta"]["inputs"][name]["state"], "disabled")
            self.assertFalse(evidence["scans"][0]["meta"]["inputs"][name]["available"])
            self.assertFalse(any(labels.get("input") == name for _, labels, _ in evidence["metrics"]))
        self.assertTrue(all("library_panels_inventory" not in views for views in evidence["views"]))
        diagnostic = json.loads(evidence["out"])
        self.assertEqual(diagnostic["meta"]["inputs"]["library_panels_inventory"]["state"], "disabled")

    def test_unique_values_and_minimized_names_absent_at_every_real_cli_public_boundary(self):
        for mode in ("valid", "malformed", "overflow", "exception"):
            with self.subTest(mode=mode):
                evidence = self.exercise(mode=mode)
                self.assertEqual(evidence["code"], 0, evidence["stderr"])
                self.assertTrue(any("/cardinality/label_names" in r.full_url for r in evidence["requests"]))
                for boundary in ("source", "scans", "views", "metrics", "events", "stdout", "stderr", "out"):
                    serialized = json.dumps(evidence[boundary])
                    self.assertNotIn(evidence["value"], serialized, boundary)
                    self.assertNotIn(evidence["suppressed"], serialized, boundary)
                # Ordinary names ARE permitted privately, but never public logs/diagnostics/metrics.
                if mode in {"valid", "overflow"}:
                    self.assertIn(evidence["ordinary"], json.dumps(evidence["source"]))
                    self.assertIn(evidence["ordinary"], json.dumps(evidence["scans"][0]["data"]["label_inventory"]))
                # Shipping permits ordinary names only in the private S3 register, never other views.
                if mode in {"valid", "overflow"}:
                    self.assertTrue(evidence["views"], "successful CLI must observe S3 view publication")
                for view_map in evidence["views"]:
                    private_register = view_map.get("labelling_label_register", [])
                    other_views = {name: rows for name, rows in view_map.items()
                                   if name != "labelling_label_register"}
                    self.assertNotIn(evidence["ordinary"], json.dumps(other_views), "non-register views")
                    if mode in {"valid", "overflow"}:
                        self.assertIn(evidence["ordinary"], json.dumps(private_register))
                for boundary in ("metrics", "events", "stdout", "stderr", "out"):
                    self.assertNotIn(evidence["ordinary"], json.dumps(evidence[boundary]), boundary)
                self.assertTrue(evidence["out"])
                self.assertEqual(evidence["scans"][0]["meta"]["inputs"]["label_inventory"]["schema_version"], 1)
                if mode not in {"valid", "overflow"}:
                    self.assertNotIn("label_inventory", evidence["scans"][0]["data"])
                    self.assertFalse(evidence["scans"][0]["meta"]["inputs"]["label_inventory"]["available"])
                    self.assertTrue(all(not any(name.startswith("labelling_") for name in views)
                                        for views in evidence["views"]))
                    self.assertTrue(evidence["events"])
                    self.assertTrue(evidence["metrics"])
                self.assertNotIn("REFUSING all S3", evidence["stderr"])

    def test_enabled_source_keeps_limited_publication_refusal_at_every_write(self):
        from dataclasses import replace
        evidence = self.exercise(extra_args=("--limit", "1"))
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        candidate = evidence["scans"][0]
        self.assertIn("label_inventory", candidate["data"])
        cfg = replace(cfg_for(), dry_run=False, limit=1, label_inventory_enabled=True)
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t2", return_value=candidate),
            mock.patch.object(scan.s3emit, "write_views") as views,
            mock.patch.object(scan.s3emit, "write_scan") as envelope,
            mock.patch.object(scan.mimir, "RemoteWriter") as mimir,
            mock.patch.object(scan.loki, "LokiWriter") as loki,
            mock.patch.object(scan.carry, "save_state") as carry,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(scan.run(FakeClient(), cfg, SimpleNamespace(out=None)), 2)
        self.assertIn("REFUSING all S3, Mimir and Loki writes", stderr.getvalue())
        for writer in (views, envelope, mimir, loki, carry):
            writer.assert_not_called()

    def test_source_report_left_joins_signal_coverage_not_any_stack_success(self):
        payload = {"active": {"signals": {"metrics": {"state": "complete", "reason": "none"},
            "logs": {"state": "partial", "reason": "truncated"},
            "traces": {"state": "partial", "reason": "deadline"},
            "profiles": {"state": "unavailable", "reason": "missing_input"}}},
            "departed": {"signals": {s: {"state": "complete", "reason": "none"} for s in scan.label_inventory_src.SIGNALS}}}
        report = scan.label_inventory_source_report([{"slug": "active"}, {"slug": "paused", "status": "paused"}], payload)
        self.assertEqual((report["expected"], report["available"], report["unit"]), (4, 2, "stack-signals"))
        self.assertFalse(report["healthy"])
        self.assertEqual(report["signals"]["logs"]["partial"], 1)
        self.assertEqual(report["signals"]["traces"]["available"], 0)


class LabelInventoryFloorPublicationTest(unittest.TestCase):
    """Real CLI, source, compose and S3 serialization against an offline upstream/store."""

    def exercise(self, measured, *, peer_measured=5, limit=None, stack=None,
                 primary_unhealthy=False, dry_run=False):
        from dataclasses import replace
        from collector.httpclient import Response
        from tests.test_label_inventory import SourceContracts, STACK

        contract = SourceContracts()
        contract.setUp()
        stacks = []
        for i in range(5):
            record = {**STACK, "slug": f"floor-{i}"}
            for host, tenant, _ in scan.label_inventory_src.SIGNALS.values():
                record[host] = record[host].replace(".example.test", f".floor-{i}.example.test")
                record[tenant] += i
            stacks.append(record)
        cfg = replace(cfg_for(), dry_run=dry_run, label_inventory_enabled=True, limit=limit, stack=stack)
        fixture = json.loads((pathlib.Path(__file__).parent / "fixtures/compose_inputs.json").read_text())
        healthy = {s["slug"]: {"available": True} for s in stacks}
        stored = {"views/" + name + ".json": {"meta": {"generated_at": "last-good"}, "rows": ["last-good"]}
                  for name in hydrate.VIEW_INPUTS if name.startswith("labelling_")}
        stored["scans/t2/last-good.json"] = {"data": {"label_inventory": "last-good-private-input"}}
        last_good = json.loads(json.dumps(stored))
        observations, composed, metrics, events, written = [], [], [], [], []
        real_compose = scan.compose.build_all
        real_hydrate = hydrate.hydrate
        real_probe = scan.label_inventory_src.probe_all
        real_detail = scan.gcom.fetch_all_stack_detail
        real_gap_update = scan.gapstate.update
        real_gap_load = scan.gapstate.load
        gap_before = {"floor-4": "2026-10-01T00:00:00+00:00"}
        gap_store = {"first_seen": dict(gap_before)}
        gap_updates, gap_writes = [], []

        def gap_runner(command, **kwargs):
            # The real helper/update/read/merge/write all execute, with only the AWS process
            # replaced. A non-dry-run side update is an observable persistent write here.
            if command[3] == f"s3://{scan.s3emit.BUCKET}/{scan.gapstate.KEY}":
                return SimpleNamespace(returncode=0, stdout=json.dumps(gap_store))
            payload = json.loads(pathlib.Path(command[3]).read_text())
            gap_writes.append(payload)
            gap_store.clear()
            gap_store.update(payload)
            return SimpleNamespace(returncode=0, stdout="")

        def update_gaps(*args, **kwargs):
            gap_updates.append(kwargs)
            return real_gap_update(*args, runner=gap_runner, **kwargs)

        def detail_with_primary_fault(client, cfg, selected, coverage, **kwargs):
            result = real_detail(client, cfg, selected, coverage, **kwargs)
            if primary_unhealthy:
                # Inject an independent primary Coverage refusal while keeping the returned
                # detail source healthy, so a peer source failure cannot mask this guard.
                coverage.record_failure(selected[0]["slug"], "http_503")
            return result

        def source_response(req, timeout):
            # Fail whole stack-signals in a deterministic signal-major order. Remaining
            # signals are real bounded reads. No fake health-report override.
            signal = req.full_url.split("//", 1)[1].split(".", 1)[0]
            index = next(i for i in range(5) if f".floor-{i}." in req.full_url)
            if list(scan.label_inventory_src.SIGNALS).index(signal) * 5 + index < 20 - measured:
                return Response(503, b"VALUE_canary_floor_secret", req.full_url)
            return contract.send(req, timeout)

        class Body(io.BytesIO):
            headers = {}

        def opened(req, timeout):
            response = source_response(req, timeout)
            body = Body(response.body)
            body.status = response.status
            return body

        def upstream(req, timeout):
            path = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(req.full_url).path
            payload = {"items": stacks} if path == "/api/instances" else {"items": []}
            return Response(200, json.dumps(payload).encode(), req.full_url)

        def capture_source(*args, **kwargs):
            payload = real_probe(*args, **kwargs)
            observations.append(payload)
            return payload

        def capture_compose(*args, **kwargs):
            composed.append(kwargs)
            return real_compose(*args, **kwargs)

        def put(path, key, bucket, dry_run):
            if dry_run:
                return "DRY-RUN " + key
            written.append(key)
            stored[key] = json.loads(path.read_text())
            return key

        def related(name):
            row = next((r for r in (fixture.get(name) or {}).values()
                        if isinstance(r, dict) and r.get("available")), None)
            return {s["slug"]: {**(row or {"available": True}), "slug": s["slug"]} for s in stacks}

        gather_names = ("assistant", "insights", "dashboard_inventory", "datasource_query_cost",
                        "adaptive_logs", "adaptive_traces", "public_dashboards", "alert_routing",
                        "slo_inventory", "synthetic_inventory", "irm_integrations", "irm_alert_groups",
                        "ml_jobs", "reports_inventory", "playlists_inventory", "library_panels_inventory",
                        "cloud_accounts", "faro_apps", "signal_inventory", "pdc_networks")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as patches:
            patches.enter_context(mock.patch.object(scan.config, "load", return_value=cfg))
            patches.enter_context(mock.patch.object(scan, "_verified_ecs_runtime", return_value=True))
            patches.enter_context(mock.patch.object(scan.scanlock, "ScanLock"))
            patches.enter_context(mock.patch("collector.httpclient._urllib_transport", side_effect=upstream))
            patches.enter_context(mock.patch("urllib.request.build_opener", return_value=SimpleNamespace(open=opened)))
            patches.enter_context(mock.patch.object(scan.label_inventory_src, "probe_all", side_effect=capture_source))
            patches.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value=healthy))
            patches.enter_context(mock.patch.object(scan.plugin_catalog, "fetch_catalogue", return_value={}))
            patches.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail_with_primary_fault))
            for name in gather_names:
                patches.enter_context(mock.patch.object(scan, "gather_" + name, return_value=(related(name), [])))
            patches.enter_context(mock.patch.object(scan, "gather_service_accounts", return_value=(
                {s["slug"]: {"state": scan.sa_src.OK, "accounts": []} for s in stacks}, [])))
            patches.enter_context(mock.patch.object(scan, "gather_capability_adoption", return_value=(fixture["capability_adoption"], [])))
            patches.enter_context(mock.patch.object(scan, "gather_loki_config", return_value=(
                {s["slug"]: {"limits": {"available": True}, "change_requests": {"available": True}} for s in stacks}, [])))
            patches.enter_context(mock.patch.object(scan, "gather_insights", return_value=(
                {s["slug"]: {**related("insights")[s["slug"]], "available": i < peer_measured}
                 for i, s in enumerate(stacks)}, [])))
            patches.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
            patches.enter_context(mock.patch.object(scan.gapstate, "update", side_effect=update_gaps))
            patches.enter_context(mock.patch.object(scan.gapstate, "load", side_effect=lambda **kw:
                real_gap_load(runner=gap_runner, **kw)))
            patches.enter_context(mock.patch.object(hydrate, "hydrate", side_effect=lambda *a, **kw:
                real_hydrate(*a, loader=lambda *_: None, **kw)))
            patches.enter_context(mock.patch.object(scan.compose, "build_all", side_effect=capture_compose))
            patches.enter_context(mock.patch.object(scan.s3emit, "_put", side_effect=put))
            patches.enter_context(mock.patch.object(scan.mimir.RemoteWriter, "push", side_effect=lambda m: metrics.extend(m) or len(m)))
            patches.enter_context(mock.patch.object(scan.loki.LokiWriter, "push", side_effect=lambda e: events.extend(e) or len(e)))
            patches.enter_context(contextlib.redirect_stdout(stdout))
            patches.enter_context(contextlib.redirect_stderr(stderr))
            args = ["--tier", "t2"] + (["--dry-run"] if dry_run else [])
            if limit:
                args += ["--limit", str(limit)]
            if stack:
                args += ["--stack", stack]
            code = scan.main(args)
        return {"code": code, "stored": stored, "last_good": last_good, "written": written,
                "source": observations, "compose": composed, "metrics": metrics, "events": events,
                "gap_updates": gap_updates, "gap_writes": gap_writes,
                "gap_before": gap_before, "gap_after": gap_store["first_seen"],
                "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}

    def test_17_of_20_publishes_healthy_label_input_at_real_cli_boundary(self):
        evidence = self.exercise(17)
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        owner = evidence["stored"]["scans/t2/latest.json"]
        report = owner["meta"]["sources"]["label_inventory"]
        self.assertEqual((report["available"], report["expected"]), (17, 20))
        self.assertTrue(report["healthy"])
        self.assertTrue(owner["meta"]["inputs"]["label_inventory"]["available"])
        self.assertEqual(owner["data"]["label_inventory"], evidence["source"][0])
        self.assertIn("label_inventory", evidence["compose"][0])
        self.assertIn("views/labelling_stack_summary.json", evidence["written"])
        self.assertEqual(report["error_count"], 3, "classified unavailable signals, not hidden exceptions")
        self.assertEqual(report["signals"]["metrics"]["unavailable_reasons"], {"missing_input": 3})
        self.assertIn('"unavailable_reasons":{"missing_input":3}', evidence["stderr"])
        self.assertNotIn("VALUE_canary_floor_secret", json.dumps(evidence))

    def test_15_of_20_withholds_only_labelling_and_publishes_other_t2_inputs(self):
        evidence = self.exercise(15)
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        owner = evidence["stored"]["scans/t2/latest.json"]
        report = owner["meta"]["sources"]["label_inventory"]
        self.assertFalse(report["healthy"])
        self.assertEqual(report["state"], "partial")
        self.assertEqual(report["error_count"], 5)
        self.assertEqual(owner["meta"]["inputs"]["label_inventory"]["state"], "partial")
        self.assertFalse(owner["meta"]["inputs"]["label_inventory"]["available"])
        self.assertNotIn("label_inventory", owner["data"])
        self.assertNotIn("label_inventory", evidence["compose"][0])
        self.assertIn("insights", owner["data"])
        self.assertIn("views/insights_summary.json", evidence["written"])
        self.assertTrue(evidence["metrics"])
        self.assertTrue(evidence["events"])
        self.assertIn(("gcinsight_input_available", {"tier": "t2", "input": "label_inventory"}, 0.0), evidence["metrics"])
        self.assertFalse(any(n == "gcinsight_input_age_seconds" and l.get("input") == "label_inventory"
                             for n, l, _ in evidence["metrics"]))
        for key, old in evidence["last_good"].items():
            self.assertEqual(evidence["stored"][key], old, key)
            self.assertNotIn(key, evidence["written"], key)
        self.assertNotIn("REFUSING all S3", evidence["stderr"])
        self.assertNotIn("VALUE_canary_floor_secret", json.dumps(evidence))

    def test_exact_80_percent_is_accepted_and_other_source_floor_still_blocks(self):
        evidence = self.exercise(16)
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        self.assertTrue(evidence["stored"]["scans/t2/latest.json"]["meta"]["sources"]["label_inventory"]["healthy"])
        evidence = self.exercise(15, peer_measured=4)
        self.assertEqual(evidence["code"], 1)
        self.assertEqual(evidence["written"], [])
        self.assertEqual(evidence["metrics"], [])
        self.assertEqual(evidence["events"], [])
        self.assertIn("REFUSING all S3", evidence["stderr"])
        self.assertNotIn("insights", evidence["compose"][0])

    def test_zero_of_20_is_unavailable_without_refusing_other_writes(self):
        evidence = self.exercise(0)
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        owner = evidence["stored"]["scans/t2/latest.json"]
        report = owner["meta"]["sources"]["label_inventory"]
        self.assertEqual((report["available"], report["error_count"], report["state"]), (0, 20, "unavailable"))
        self.assertFalse(report["healthy"])
        self.assertFalse(owner["meta"]["sources_healthy"], "non-blocking is not source health")
        self.assertFalse(owner["meta"]["scan_healthy"], "keep the degraded scan honest")
        self.assertNotIn("label_inventory", owner["data"])
        self.assertNotIn("label_inventory", evidence["compose"][0])
        self.assertIn("views/insights_summary.json", evidence["written"])
        self.assertEqual(owner["meta"]["inputs"]["label_inventory"]["state"], "unavailable")
        for key, old in evidence["last_good"].items():
            self.assertEqual(evidence["stored"][key], old)

    def test_below_floor_label_cannot_allow_subset_or_primary_refused_gap_state_writes(self):
        for options, expected_exit in (({"limit": 1}, 2), ({"stack": "floor-0"}, 2),
                                       ({"primary_unhealthy": True}, 1)):
            with self.subTest(options=options):
                evidence = self.exercise(15, **options)
                self.assertEqual(evidence["code"], expected_exit, evidence["stderr"])
                self.assertNotIn("label_inventory", evidence["compose"][0], "labels must be below floor")
                self.assertIn("assistant", evidence["compose"][0], "healthy Assistant is not a peer blocker")
                self.assertEqual(evidence["gap_updates"], [],
                                 "refused runs must stop before the real gapstate.update seam")
                self.assertEqual(evidence["gap_writes"], [], "no persistent side write before refusal")
                self.assertEqual(evidence["gap_after"], evidence["gap_before"])
                self.assertEqual(evidence["written"], [])
                self.assertEqual(evidence["metrics"], [])
                self.assertEqual(evidence["events"], [])
                self.assertIn("REFUSING all S3", evidence["stderr"])

    def test_below_floor_label_still_allows_full_gap_update_and_subset_dry_run_computation(self):
        evidence = self.exercise(15)
        self.assertEqual(evidence["code"], 0, evidence["stderr"])
        self.assertEqual(len(evidence["gap_updates"]), 1)
        self.assertFalse(evidence["gap_updates"][0]["dry_run"])
        self.assertEqual(len(evidence["gap_writes"]), 1, "full healthy publication retains its gap update")
        for options in ({"limit": 1}, {"stack": "floor-0"}):
            with self.subTest(options=options):
                evidence = self.exercise(15, dry_run=True, **options)
                self.assertEqual(evidence["code"], 0, evidence["stderr"])
                self.assertEqual(len(evidence["gap_updates"]), 1)
                self.assertTrue(evidence["gap_updates"][0]["dry_run"])
                self.assertEqual(evidence["gap_writes"], [])
                self.assertEqual(evidence["gap_after"], evidence["gap_before"])
                self.assertEqual(evidence["written"], [])

    def test_wrapper_counts_live_unavailable_observations_and_logs_only_closed_classes(self):
        name, value, text = "NAME_canary_floor", "VALUE_canary_floor", "EXCEPTION_canary_floor"
        payload = {"live": {"signals": {
            "metrics": {"state": "complete", "reason": "none", "register": [name, value]},
            "logs": {"state": "partial", "reason": "deadline", "detail": text},
            "traces": {"state": "unavailable", "reason": "missing_input"},
            "profiles": {"state": "unavailable", "reason": name + value + text},
        }}, "departed": {"signals": {s: {"state": "unavailable", "reason": "deadline"}
                                      for s in scan.label_inventory_src.SIGNALS}}}
        stacks = [{"slug": "live"}, {"slug": "paused", "status": "PAUSED"}]
        from dataclasses import replace
        stderr = io.StringIO()
        with (mock.patch.object(scan.label_inventory_src, "probe_all", return_value=payload),
              contextlib.redirect_stderr(stderr)):
            data, errors = scan.gather_label_inventory(FakeClient(), replace(cfg_for(), label_inventory_enabled=True), stacks)
        self.assertIs(data, payload)
        self.assertEqual(errors, ["logs: deadline", "traces: missing_input", "profiles: missing_input"])
        report = scan.label_inventory_source_report(stacks, payload, errors)
        self.assertEqual(report["error_count"], 3)
        self.assertEqual(report["error_count_unit"], "classified unavailable stack-signal observations")
        self.assertEqual((report["expected"], report["available"]), (4, 1))
        records = [json.loads(line) for line in stderr.getvalue().splitlines()]
        self.assertEqual({r["signal"]: r["unavailable_reasons"] for r in records},
                         {"metrics": {}, "logs": {"deadline": 1}, "traces": {"missing_input": 1},
                          "profiles": {"missing_input": 1}})
        for canary in (name, value, text):
            self.assertNotIn(canary, json.dumps(report) + stderr.getvalue() + json.dumps(errors))
        # Even an externally supplied error sample cannot export arbitrary exception text.
        safe_report = scan.label_inventory_source_report(stacks, payload, [text])
        self.assertEqual(safe_report["error_count"], 1)
        self.assertNotIn(text, json.dumps(safe_report))

    def test_shared_source_floor_remains_exactly_ten_percent_failure(self):
        from collector.coverage import FAILURE_ABORT_RATIO, Coverage
        self.assertEqual(FAILURE_ABORT_RATIO, 0.10)
        self.assertEqual(scan.LABEL_INVENTORY_FLOOR, 0.80)
        for missing in (2, 3):
            rows = {str(i): True for i in range(20 - missing)}
            self.assertEqual(scan.source_report(20, rows, available=bool)["healthy"], missing == 2)
            cov = Coverage(tier="t2", total=20)
            for i in range(20):
                if i < missing:
                    cov.record_failure(str(i), "missing_input")
                else:
                    cov.record_ok(str(i))
            self.assertEqual(cov.should_abort, missing == 3)


class ConsoleLoggingTest(unittest.TestCase):
    def test_console_log_is_one_json_line_with_explicit_level_and_message(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            scan.console_log("warn", "first line\nsecond line", source="assistant")

        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertEqual(
            json.loads(stderr.getvalue()),
            {
                "level": "warn",
                "message": "first line\nsecond line",
                "source": "assistant",
            },
        )

    def test_all_stderr_records_go_through_the_structured_helper(self):
        source = pathlib.Path(scan.__file__).read_text()
        tree = ast.parse(source)
        stderr_prints = []
        direct_writes = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                for keyword in node.keywords:
                    target = keyword.value
                    if (
                        keyword.arg == "file"
                        and isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "sys"
                        and target.attr == "stderr"
                    ):
                        stderr_prints.append(node.lineno)
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"write", "writelines"}
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "sys"
                and node.func.value.attr == "stderr"
            ):
                direct_writes.append(node.lineno)

        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "console_log"
        )
        self.assertEqual(len(stderr_prints), 1, "only console_log may print to stderr")
        self.assertTrue(helper.lineno <= stderr_prints[0] <= helper.end_lineno)
        self.assertEqual(direct_writes, [])

    def test_console_log_rejects_unknown_levels(self):
        with self.assertRaisesRegex(ValueError, "invalid console log level"):
            scan.console_log("warning", "not in the contract")

    def test_invalid_cli_is_one_structured_error_record(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            scan.main(["--tier", "t1", "--not-a-real-option"])

        self.assertEqual(ctx.exception.code, 2)
        lines = stderr.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["level"], "error")
        self.assertIn("unrecognized arguments: --not-a-real-option", record["message"])

    def test_partial_completion_is_warn_but_t4_zero_of_zero_is_info(self):
        self.assertEqual(
            scan.scan_completion_level({
                "scan_healthy": True, "stacks_scannable": 10, "coverage_ratio": 0.9,
            }),
            "warn",
        )
        self.assertEqual(
            scan.scan_completion_level({
                "scan_healthy": True, "stacks_scannable": 0, "coverage_ratio": 0.0,
            }),
            "info",
        )

    def test_unexpected_top_level_exception_is_logged_once_then_reraised(self):
        stderr = io.StringIO()
        with (
            mock.patch.object(scan, "main", side_effect=RuntimeError("unexpected boom")),
            contextlib.redirect_stderr(stderr),
            self.assertRaisesRegex(RuntimeError, "unexpected boom"),
        ):
            scan.entrypoint()

        lines = stderr.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["level"], "error")
        self.assertIn("unexpected boom", record["message"])


class ConfigurationExitTest(unittest.TestCase):
    def test_missing_identifier_cli_exits_2_with_one_diagnostic(self):
        proc = subprocess.run(
            [sys.executable, str(pathlib.Path(scan.__file__)), "--tier", "t1", "--dry-run"],
            env={"GCINSIGHT_READ_TOKEN": "synthetic-read-token"},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(proc.stdout, "")
        lines = proc.stderr.splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["level"], "error")
        self.assertIn("GCINSIGHT_ORG_ID is not set", record["message"])

    def test_all_configuration_errors_stop_before_source_or_publication(self):
        for error_type, dry_run in (
            (error_type, dry_run)
            for error_type in (config.IncompleteConfig, config.MissingConfig, config.MissingCredential)
            for dry_run in (True, False)
        ):
            with self.subTest(error=error_type.__name__, dry_run=dry_run):
                stderr = io.StringIO()
                with (
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(config, "load", side_effect=error_type("invalid configuration")),
                    mock.patch.object(scan, "ReadOnlyClient") as client,
                    mock.patch.object(scan.gcom, "fetch_inventory") as inventory,
                    mock.patch.object(scan, "run") as run,
                    mock.patch.object(scan, "_verified_ecs_runtime") as ecs,
                    contextlib.redirect_stderr(stderr),
                ):
                    argv = ["--tier", "t1"] + (["--dry-run"] if dry_run else [])
                    self.assertEqual(scan.main(argv), 2)
                client.assert_not_called()
                inventory.assert_not_called()
                run.assert_not_called()
                ecs.assert_not_called()
                self.assertEqual(len(stderr.getvalue().splitlines()), 1)
                self.assertEqual(json.loads(stderr.getvalue())["message"], "error: invalid configuration")

    def test_unexpected_configuration_error_propagates_unchanged(self):
        error = RuntimeError("unexpected configuration bug")
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(config, "load", side_effect=error),
            mock.patch.object(scan, "ReadOnlyClient") as client,
            contextlib.redirect_stderr(stderr),
            self.assertRaises(RuntimeError) as caught,
        ):
            scan.main(["--tier", "t1", "--dry-run"])
        self.assertIs(caught.exception, error)
        client.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")


class T3CarryPublicationOrderTest(unittest.TestCase):
    def test_a_limited_nondry_run_refuses_every_publication_seam(self):
        result = {
            "meta": {
                "tier": "t1", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_scannable": 1,
                "stacks_total": 1, "source_failures": [], "inputs": {},
            },
            "data": {"stacks": [{"slug": "alpha"}]},
            "_emit": {
                "metrics": [("gcinsight_estate_stacks", {}, 1.0)],
                "views": {"estate": [{"Stacks": 1}]},
            },
        }
        base = cfg_for("t1")
        cfg = config.Config(**{**base.__dict__, "dry_run": False, "limit": 1})
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t1", return_value=result),
            mock.patch.object(scan.s3emit, "write_views") as write_views,
            mock.patch.object(scan.s3emit, "write_scan") as write_scan,
            mock.patch.object(scan.mimir, "RemoteWriter") as remote_writer,
            mock.patch.object(scan.loki, "LokiWriter") as loki_writer,
        ):
            rc = scan.run(FakeClient(), cfg, SimpleNamespace(out=None))

        self.assertEqual(rc, 2)
        write_views.assert_not_called()
        write_scan.assert_not_called()
        remote_writer.assert_not_called()
        loki_writer.assert_not_called()

    def test_t3_runner_never_saves_carry_state_before_the_common_health_gate(self):
        """A rejected partial T3 must not become the state that healthy T1 republishes hourly."""
        stacks = [{"slug": "alpha", "status": "active"}]
        client = SimpleNamespace(
            attempts=SimpleNamespace(requests=1, retries=0, by_status={503: 1})
        )
        cfg = cfg_for("t3")
        cfg = config.Config(**{**cfg.__dict__, "dry_run": False})

        def failed_dataplane(_client, _cap, selected, coverage, **_kwargs):
            self.assertEqual(selected, stacks)
            coverage.record_failure("alpha", "http_503")
            return {"alpha": {"available": False, "reason": "http_503"}}

        provenance = hydrate.Provenance({
            "dataplane": {"available": True, "source": "own", "tier": "t3",
                          "age_seconds": 0.0, "stale": False},
        })
        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.dataplane, "probe_all", side_effect=failed_dataplane),
            mock.patch.object(scan.hydrate, "hydrate", return_value=(
                {"dataplane": {"alpha": {"available": False}}}, provenance,
            )),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan.compose, "build_all", return_value=(
                [("gcinsight_cost_active_series", {"stack": "alpha"}, 1.0)], {}, {},
            )),
            mock.patch.object(scan.carry, "save_state") as save_state,
        ):
            result = scan.run_t3(client, cfg)

        self.assertTrue(result["meta"]["stacks_failed"])
        save_state.assert_not_called()

    def test_common_health_gate_saves_an_accepted_t3_batch_before_publication(self):
        metrics = [("gcinsight_cost_active_series", {"stack": "alpha"}, 1.0)]
        view_coverage = {"cost_adaptive_headroom": {
            "measured": 2, "in_scope": 3, "complete": False,
        }}
        result = {
            "meta": {
                "tier": "t3", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_scannable": 1,
                "stacks_total": 1, "source_failures": [], "inputs": {},
            },
            "data": {},
            "_emit": {"metrics": metrics, "views": {"cost_adaptive_headroom": []},
                      "view_coverage": view_coverage},
        }
        args = SimpleNamespace(out=None)
        cfg = cfg_for("t3")
        cfg = config.Config(**{**cfg.__dict__, "dry_run": False})
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t3", return_value=result),
            mock.patch.object(scan.carry, "save_state", return_value="s3://bucket/state/t3.json")
            as save_state,
            mock.patch.object(scan.s3emit, "write_views", return_value=[]) as write_views,
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir, "RemoteWriter") as remote_writer,
            mock.patch.object(scan.loki, "LokiWriter") as loki_writer,
        ):
            remote_writer.return_value.push.return_value = 3
            loki_writer.return_value.push.return_value = 1
            rc = scan.run(FakeClient(), cfg, args)

        self.assertEqual(rc, 0)
        save_state.assert_called_once_with(metrics, "t3", bucket=scan.s3emit.BUCKET)
        self.assertEqual(write_views.call_args.kwargs["view_coverage"], view_coverage)
        self.assertNotIn(("gcinsight_findings", {"kind": "adaptive_headroom"}, 0.0),
                         remote_writer.return_value.push.call_args.args[0])

    def test_retention_change_rows_are_forwarded_to_loki_after_view_withholding(self):
        row = {
            " Stack": "alpha",
            "Status": "pending",
            "Requested": "requested-at",
            "Processed": None,
            "Author": "operator",
            "Message": "retain synthetic logs",
            "PR": 7,
            "Limit": '{"period":"14d"}',
            "Opaque keys": '{}',
        }
        result = {
            "meta": {
                "tier": "t2", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_scannable": 1,
                "stacks_total": 1, "source_failures": [], "inputs": {},
            },
            "data": {},
            "_emit": {
                "metrics": [],
                "views": {"risk_retention_change_requests": [row]},
            },
        }
        with (
            mock.patch.object(scan, "run_t2", return_value=result),
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir.RemoteWriter, "push", return_value=0),
            mock.patch.object(scan.loki.LokiWriter, "push", return_value=2) as push,
        ):
            rc = scan.run(FakeClient(), cfg_for("t2"), SimpleNamespace(out=None))

        self.assertEqual(rc, 0)
        events = push.call_args.args[0]
        change = [line for labels, line in events if labels.get("event") == "change"]
        self.assertEqual(change, [{
            "stack": "alpha", "status": "pending", "requested": "requested-at",
            "processed": None, "author": "operator", "message": "retain synthetic logs",
            "pr": 7, "limit": '{"period":"14d"}', "opaque": '{}',
        }])

    def test_production_stdout_is_a_compact_summary_not_the_scan_envelope(self):
        result = {
            "meta": {
                "tier": "t3", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_scanned": 1,
                "stacks_scannable": 1, "stacks_total": 1, "stacks_skipped": 0,
                "requests": 3, "retries": 0, "series_emitted": 1,
                "duration_seconds": 2.5, "source_failures": [], "inputs": {},
            },
            "data": {"dataplane": {"alpha": {"secret_sentinel": "never-log-envelope"}}},
            "_emit": {"metrics": [], "views": {}},
        }
        cfg = config.Config(**{**cfg_for("t3").__dict__, "dry_run": False})
        stdout = io.StringIO()
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t3", return_value=result),
            mock.patch.object(scan.carry, "save_state", return_value=None),
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]) as write_scan,
            mock.patch.object(scan.mimir.RemoteWriter, "push", return_value=0),
            mock.patch.object(scan.loki.LokiWriter, "push", return_value=0),
            mock.patch("sys.stdout", stdout),
        ):
            rc = scan.run(FakeClient(), cfg, SimpleNamespace(out=None))

        self.assertEqual(rc, 0)
        self.assertNotIn("never-log-envelope", stdout.getvalue())
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["event"], "scan_complete")
        self.assertEqual(summary["tier"], "t3")
        self.assertEqual(summary["level"], "info")
        self.assertEqual(summary["stacks_scanned"], 1)
        self.assertEqual(summary["series_emitted"], 2)
        self.assertTrue(summary["scan_healthy"])
        self.assertTrue(summary["sources_healthy"])
        persisted = write_scan.call_args.args[0]
        self.assertTrue(persisted["meta"]["scan_healthy"])
        self.assertTrue(persisted["meta"]["sources_healthy"])
        self.assertEqual(persisted["meta"]["series_emitted"], 2)

    def test_writer_failure_marks_the_persisted_scan_and_summary_unhealthy(self):
        for failed_writer in ("mimir", "loki"):
            with self.subTest(failed_writer=failed_writer):
                result = {
                    "meta": {
                        "tier": "t3", "generated_at": "2026-08-21T00:00:00+00:00",
                        "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_scanned": 1,
                        "stacks_scannable": 1, "stacks_total": 1, "stacks_skipped": 0,
                        "requests": 3, "retries": 0, "source_failures": [], "inputs": {},
                    },
                    "data": {},
                    "_emit": {"metrics": [], "views": {}},
                }
                cfg = config.Config(**{**cfg_for("t3").__dict__, "dry_run": False})
                stdout = io.StringIO()
                mimir_result = (
                    scan.mimir.RemoteWriteFailed("mimir failed")
                    if failed_writer == "mimir" else 0
                )
                loki_result = (
                    scan.loki.LokiPushFailed("loki failed")
                    if failed_writer == "loki" else 0
                )
                with (
                    mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
                    mock.patch.object(scan, "run_t3", return_value=result),
                    mock.patch.object(scan.carry, "save_state", return_value=None),
                    mock.patch.object(scan.s3emit, "write_views", return_value=[]),
                    mock.patch.object(scan.s3emit, "write_scan", return_value=[]) as write_scan,
                    mock.patch.object(
                        scan.mimir.RemoteWriter, "push",
                        side_effect=mimir_result if isinstance(mimir_result, Exception) else None,
                        return_value=mimir_result if not isinstance(mimir_result, Exception) else None,
                    ),
                    mock.patch.object(
                        scan.loki.LokiWriter, "push",
                        side_effect=loki_result if isinstance(loki_result, Exception) else None,
                        return_value=loki_result if not isinstance(loki_result, Exception) else None,
                    ),
                    mock.patch("sys.stdout", stdout),
                ):
                    rc = scan.run(FakeClient(), cfg, SimpleNamespace(out=None))

                self.assertEqual(rc, 3)
                summary = json.loads(stdout.getvalue())
                self.assertEqual(summary["level"], "error")
                self.assertFalse(summary["scan_healthy"])
                self.assertIsNotNone(summary[f"{failed_writer}_push_failed"])
                persisted = write_scan.call_args.args[0]
                self.assertFalse(persisted["meta"]["scan_healthy"])

    def test_dry_run_stdout_is_one_levelled_completion_record(self):
        result = {
            "meta": {
                "tier": "t4", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 0.0, "stacks_failed": 0, "stacks_scanned": 0,
                "stacks_scannable": 0, "stacks_total": 0, "stacks_skipped": 0,
                "requests": 0, "retries": 0, "source_failures": [], "inputs": {},
            },
            "data": {},
            "_emit": {"metrics": [], "views": {}},
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(scan, "run_t4", return_value=result),
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir.RemoteWriter, "push", return_value=0),
            mock.patch.object(scan.loki.LokiWriter, "push", return_value=0),
            mock.patch("sys.stdout", stdout),
        ):
            rc = scan.run(FakeClient(), cfg_for("t4"), SimpleNamespace(out=None))

        self.assertEqual(rc, 0)
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["event"], "scan_complete")
        self.assertEqual(summary["level"], "info", "T4's intentional 0/0 coverage is healthy")

    def test_production_out_is_refused_before_the_tier_runs(self):
        cfg = config.Config(**{**cfg_for("t3").__dict__, "dry_run": False})
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t3") as runner,
        ):
            rc = scan.run(FakeClient(), cfg, SimpleNamespace(out="/dev/stdout"))

        self.assertEqual(rc, 2)
        runner.assert_not_called()


class T2SourceHealthTest(unittest.TestCase):
    def test_loki_retention_uses_org_cap_and_stack_reader_store_independently(self):
        client = object()
        stacks = [{"slug": "alpha", "status": "active"}]
        cfg = SimpleNamespace(concurrency=3, cap="org-cap")
        creds = {"alpha": {"token": "reader"}}
        result = {
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            }
        }
        with (
            mock.patch.object(scan.credentials, "load_all", return_value=creds),
            mock.patch.object(scan.loki_config_src, "probe_all", return_value=result) as probe,
        ):
            data, errors = scan.gather_loki_config(client, cfg, stacks)

        self.assertIs(data, result)
        self.assertEqual(errors, [])
        self.assertEqual(probe.call_args.args, (client, stacks, "org-cap", creds))
        self.assertEqual(probe.call_args.kwargs["concurrency"], 3)

    def test_usage_insights_receives_the_shared_deadline_aware_client(self):
        client = object()
        stacks = [{"slug": "alpha", "status": "active"}]
        with (
            mock.patch.object(scan.credentials, "load_all", return_value={"alpha": {"token": "x"}}),
            mock.patch.object(scan.usage_insights, "probe_all", return_value={
                "alpha": {"available": True},
            }) as probe,
        ):
            data, errors = scan.gather_insights(
                client, SimpleNamespace(concurrency=2), stacks,
            )

        self.assertEqual(data, {"alpha": {"available": True}})
        self.assertEqual(errors, [])
        self.assertIs(probe.call_args.kwargs["client"], client)

    def test_signal_inventory_uses_the_org_cap_and_shared_client(self):
        client = object()
        stacks = [{"slug": "alpha", "status": "active"}]
        cfg = SimpleNamespace(concurrency=2, cap="org-cap")
        with mock.patch.object(scan.signal_inventory_src, "probe_all", return_value={
            "alpha": {"available": True, "metric_names": [], "log_services": [],
                      "trace_services": [], "profile_services": []},
        }) as probe:
            data, errors = scan.gather_signal_inventory(client, cfg, stacks)

        self.assertTrue(data["alpha"]["available"])
        self.assertEqual(errors, [])
        self.assertEqual(probe.call_args.args, (client, stacks, "org-cap"))
        self.assertEqual(probe.call_args.kwargs["concurrency"], 2)

    def test_every_secondary_source_failing_marks_the_scan_unhealthy(self):
        stacks = [{"slug": "alpha", "status": "active"}]

        def detail(_client, _cfg, selected, coverage, *, on_error):
            coverage.record_ok("alpha")
            return {"alpha": {"slug": "alpha", "users": [], "plugins": []}}

        def hydrate_own(_tier, own, *, unavailable, enabled, bucket):
            prov = hydrate.Provenance({
                name: {"available": bool(value), "source": "own", "tier": "t2",
                       "age_seconds": 0.0, "stale": not bool(value)}
                for name, value in own.items()
            })
            prov.update({
                name: {"available": False, "source": "own", "tier": "t2",
                       "age_seconds": None, "stale": False, **detail}
                for name, detail in unavailable.items()
            })
            return dict(own), prov

        unavailable = ({}, ["credential store: denied"])
        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail),
            mock.patch.object(scan, "gather_service_accounts", return_value=unavailable),
            mock.patch.object(scan, "gather_assistant", return_value=unavailable),
            mock.patch.object(scan, "gather_insights", return_value=unavailable),
            mock.patch.object(scan, "gather_dashboard_inventory", return_value=unavailable),
            mock.patch.object(scan, "gather_datasource_query_cost", return_value=unavailable),
            mock.patch.object(scan, "gather_adaptive_logs", return_value=unavailable),
            mock.patch.object(scan, "gather_adaptive_traces", return_value=unavailable),
            mock.patch.object(scan, "gather_public_dashboards", return_value=unavailable),
            mock.patch.object(scan, "gather_alert_routing", return_value=unavailable),
            mock.patch.multiple(scan,
                gather_slo_inventory=mock.Mock(return_value=unavailable),
                slo_reads_enabled=mock.Mock(return_value=True),
                gather_synthetic_inventory=mock.Mock(return_value=unavailable),
                synthetic_reads_enabled=mock.Mock(return_value=True)),
            mock.patch.object(scan, "gather_signal_inventory", return_value=unavailable),
            mock.patch.object(scan, "gather_capability_adoption", return_value=unavailable),
            mock.patch.object(scan, "gather_loki_config", return_value=unavailable),
            mock.patch.object(scan.label_risk_src, "probe_all", return_value={}),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=hydrate_own),
            mock.patch.object(scan.compose, "build_all", return_value=([], {}, {})),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
        ):
            result = scan.run_t2(FakeClient(), cfg_for())

        self.assertEqual(result["meta"]["coverage_ratio"], 1.0,
                         "gcom detail coverage is still independently healthy")
        self.assertFalse(result["meta"]["sources_healthy"])
        self.assertFalse(result["meta"]["scan_healthy"])
        self.assertEqual(
            set(result["meta"]["source_failures"]),
            {"service_accounts", "assistant", "insights", "adaptive_logs", "adaptive_traces", "public_dashboards",
             "alert_routing", "dashboard_inventory", "datasource_query_cost", "signal_inventory",
             "capability_adoption", "label_risk", "loki_config_limits",
             "loki_config_change_requests", "slo_inventory", "synthetic_inventory"},
        )
        for name in result["meta"]["source_failures"]:
            with self.subTest(source=name):
                self.assertEqual(result["meta"]["sources"][name]["available"], 0)
                self.assertEqual(result["meta"]["sources"][name]["expected"], 1)

    def test_an_unhealthy_source_makes_the_tier_exit_nonzero(self):
        result = {
            "meta": {
                "tier": "t2", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_total": 1,
                "source_failures": ["assistant"], "sources_healthy": False,
                "scan_healthy": False,
            },
            "data": {},
            "_emit": {"metrics": [], "views": {}},
        }
        args = type("Args", (), {"out": None})()
        with (
            mock.patch.object(scan, "run_t2", return_value=result),
            mock.patch.object(scan.s3emit, "write_views") as write_views,
            mock.patch.object(scan.s3emit, "write_scan") as write_scan,
            mock.patch.object(scan.mimir, "RemoteWriter") as remote_writer,
            mock.patch.object(scan.loki, "LokiWriter") as loki_writer,
        ):
            rc = scan.run(FakeClient(), cfg_for(), args)
        self.assertEqual(rc, 1)
        write_views.assert_not_called()
        write_scan.assert_not_called()
        remote_writer.assert_not_called()
        loki_writer.assert_not_called()

    def test_primary_coverage_below_the_floor_cannot_publish_before_exiting(self):
        """Returning 1 after the writes is too late: the thin estate has already replaced the truth."""
        result = {
            "meta": {
                "tier": "t1", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 0.5, "stacks_failed": 1, "stacks_scannable": 2,
                "stacks_total": 2,
            },
            "data": {},
            "_emit": {"metrics": [], "views": {"estate": [{"Stacks": 1}]}},
        }
        args = type("Args", (), {"out": None})()
        with (
            mock.patch.object(scan, "run_t1", return_value=result),
            mock.patch.object(scan.s3emit, "write_views") as write_views,
            mock.patch.object(scan.s3emit, "write_scan") as write_scan,
            mock.patch.object(scan.mimir, "RemoteWriter") as remote_writer,
            mock.patch.object(scan.loki, "LokiWriter") as loki_writer,
        ):
            rc = scan.run(FakeClient(), cfg_for("t1"), args)
        self.assertEqual(rc, 1)
        write_views.assert_not_called()
        write_scan.assert_not_called()
        remote_writer.assert_not_called()
        loki_writer.assert_not_called()

    def test_one_success_and_268_failures_cannot_reach_estate_composition_or_envelope(self):
        stacks = [{"slug": f"stack-{i}", "status": "active"} for i in range(269)]

        def detail(_client, _cfg, selected, coverage, *, on_error):
            for stack in selected:
                coverage.record_ok(stack["slug"])
            return {s["slug"]: {"slug": s["slug"], "users": [], "plugins": []} for s in selected}

        healthy = {s["slug"]: {"available": True} for s in stacks}
        loki_healthy = {
            s["slug"]: {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            }
            for s in stacks
        }
        service_accounts = {
            s["slug"]: {"state": scan.sa_src.OK, "accounts": []} for s in stacks
        }
        partial_insights = {
            s["slug"]: ({"available": True, "views": 99}
                        if i == 0 else {"available": False, "reason": "forbidden_403"})
            for i, s in enumerate(stacks)
        }
        seen: dict[str, object] = {}
        real_hydrate = hydrate.hydrate

        def local_hydrate(tier, own, **kwargs):
            return real_hydrate(
                tier, own, unavailable=kwargs.get("unavailable"), enabled=kwargs.get("enabled", ()),
                loader=lambda _tier, _bucket: None,
            )

        def compose(_stacks, _coverage, **kwargs):
            seen.update(kwargs)
            # This models the dangerous output seam: if the partial input reaches composition, an
            # estate total and summary view are produced from the one successful stack.
            if "insights" in kwargs:
                return ([('gcinsight_dashboards_estate_views', {"version": "2"}, 99.0)],
                        {"insights_summary": [{"Value": 99}]}, {})
            return [], {}, {}

        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail),
            mock.patch.object(scan, "gather_service_accounts", return_value=(service_accounts, [])),
            mock.patch.object(scan, "gather_assistant", return_value=(healthy, [])),
            mock.patch.object(scan, "gather_insights", return_value=(partial_insights, [])),
            mock.patch.object(scan, "gather_dashboard_inventory", return_value=(healthy, [])),
            mock.patch.object(scan, "gather_datasource_query_cost", return_value=(healthy, [])),
            mock.patch.object(scan, "gather_adaptive_logs", return_value=(healthy, [])),
            mock.patch.object(scan, "gather_public_dashboards", return_value=(healthy, [])),
            mock.patch.object(scan, "gather_alert_routing", return_value=(healthy, [])),
            mock.patch.multiple(scan,
                gather_slo_inventory=mock.Mock(return_value=(healthy, [])),
                slo_reads_enabled=mock.Mock(return_value=True),
                gather_synthetic_inventory=mock.Mock(return_value=(healthy, [])),
                synthetic_reads_enabled=mock.Mock(return_value=True)),
            mock.patch.object(scan, "gather_signal_inventory", return_value=(healthy, [])),
            mock.patch.object(
                scan, "gather_capability_adoption",
                return_value=({"available": True, "values": {}}, []),
            ),
            mock.patch.object(scan, "gather_loki_config", return_value=(loki_healthy, [])),
            mock.patch.object(scan.label_risk_src, "probe_all", return_value=healthy),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=local_hydrate),
            mock.patch.object(scan.compose, "build_all", side_effect=compose),
            mock.patch.object(scan, "assistant_gaps", return_value={}) as assistant_gaps,
            mock.patch.object(scan, "load_ratecard", return_value=None),
        ):
            result = scan.run_t2(FakeClient(), cfg_for())

        self.assertNotIn("insights", seen, "partial source must not reach estate composition")
        self.assertNotIn("insights", result["data"], "partial source must not become latest owner input")
        self.assertEqual(result["_emit"], {"metrics": [], "views": {}, "view_coverage": {}})
        self.assertEqual(result["meta"]["sources"]["insights"]["available"], 1)
        self.assertFalse(result["meta"]["sources"]["insights"]["healthy"])
        self.assertEqual(result["meta"]["inputs"]["insights"]["state"], "partial")
        self.assertFalse(result["meta"]["inputs"]["insights"]["available"])
        self.assertFalse(
            assistant_gaps.call_args.kwargs["gathered"],
            "a rejected peer source must suppress Assistant's S3 gap-state update too",
        )


class T1FleetSourceHealthTest(unittest.TestCase):
    def test_one_fleet_success_and_many_failures_is_withheld_and_marks_t1_unhealthy(self):
        stacks = [
            {
                "slug": f"stack-{i}", "status": "active", "agentManagementInstanceUrl": "https://fm",
            }
            for i in range(100)
        ]
        fleet_data = {
            stack["slug"]: ({"available": True, "collectors": 7, "pipelines": 2}
                            if i == 0 else {"available": False, "reason": "http_error"})
            for i, stack in enumerate(stacks)
        }
        seen: dict[str, object] = {}

        def local_hydrate(_tier, own, *, unavailable, enabled, bucket):
            seen["own"] = own
            seen["unavailable"] = unavailable
            prov = hydrate.Provenance({
                "fleet": {"available": False, "source": "own", "tier": "t1",
                          "age_seconds": None, "stale": False, **unavailable["fleet"]},
            })
            return dict(own), prov

        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_access_policies", return_value=[]),
            mock.patch.object(scan.gcom, "fetch_org_members",
                              return_value={"state": "ok", "members": []}),
            mock.patch.object(scan, "gather_fleet", return_value=(fleet_data, [])),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=local_hydrate),
            mock.patch.object(scan.compose, "build_all", return_value=([], {}, {})),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan.carry, "load_state", side_effect=scan.carry.StateUnavailable("none")),
        ):
            result = scan.run_t1(FakeClient(), cfg_for("t1"))

        self.assertNotIn("fleet", seen["own"])
        self.assertEqual(seen["unavailable"]["fleet"]["state"], "partial")
        self.assertNotIn("fleet", result["data"])
        self.assertEqual(result["meta"]["source_failures"], ["fleet"])
        self.assertFalse(result["meta"]["sources_healthy"])
        self.assertFalse(result["meta"]["scan_healthy"])
        self.assertEqual(result["meta"]["sources"]["fleet"]["expected"], 100)
        self.assertEqual(result["meta"]["sources"]["fleet"]["available"], 1)

    def test_stacks_without_a_fleet_endpoint_are_not_failures(self):
        stacks = [
            {"slug": "fm", "status": "active", "agentManagementInstanceUrl": "https://fm"},
            {"slug": "none", "status": "active"},
            {"slug": "paused", "status": "paused", "agentManagementInstanceUrl": "https://fm"},
        ]
        fleet_data = {
            "fm": {"available": True, "collectors": 0, "pipelines": 0},
            "none": {"available": False, "reason": "no_fm_url"},
        }

        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_access_policies", return_value=[]),
            mock.patch.object(scan.gcom, "fetch_org_members",
                              return_value={"state": "ok", "members": []}),
            mock.patch.object(scan, "gather_fleet", return_value=(fleet_data, [])),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=lambda _t, own, **_kw: (
                own, hydrate.Provenance()
            )),
            mock.patch.object(scan.compose, "build_all", return_value=([], {}, {})),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan.carry, "load_state", side_effect=scan.carry.StateUnavailable("none")),
        ):
            result = scan.run_t1(FakeClient(), cfg_for("t1"))

        self.assertEqual(result["meta"]["sources"]["fleet"]["expected"], 1)
        self.assertEqual(result["meta"]["sources"]["fleet"]["available"], 1)
        self.assertTrue(result["meta"]["sources_healthy"])


class T1OrgMembershipSourceHealthTest(unittest.TestCase):
    def test_a_complete_membership_read_reaches_composition_and_the_owner_envelope(self):
        stacks = [{"slug": "alpha", "status": "active"}]
        org_members = {"state": "ok", "members": []}
        seen: dict[str, object] = {}

        def local_hydrate(_tier, own, *, unavailable, enabled, bucket):
            seen["own"] = own
            seen["unavailable"] = unavailable
            return dict(own), hydrate.Provenance()

        def compose(_stacks, _coverage, **kwargs):
            seen["compose"] = kwargs
            return [], {}, {}

        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_access_policies", return_value=[]),
            mock.patch.object(scan.gcom, "fetch_org_members", return_value=org_members),
            mock.patch.object(scan, "gather_fleet", return_value=({}, [])),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=local_hydrate),
            mock.patch.object(scan.compose, "build_all", side_effect=compose),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan.carry, "load_state", side_effect=scan.carry.StateUnavailable("none")),
        ):
            result = scan.run_t1(FakeClient(), cfg_for("t1"))

        self.assertEqual(seen["own"]["org_members"], org_members)
        self.assertEqual(seen["compose"]["org_members"], org_members)
        self.assertEqual(result["data"]["org_members"], org_members)
        self.assertNotIn("org_members", seen["unavailable"])
        self.assertTrue(result["meta"]["sources"]["org_members"]["healthy"])

    def test_a_failed_membership_read_is_withheld_and_marks_t1_unhealthy(self):
        stacks = [{"slug": "alpha", "status": "active"}]
        seen: dict[str, object] = {}

        def local_hydrate(_tier, own, *, unavailable, enabled, bucket):
            seen["own"] = own
            seen["unavailable"] = unavailable
            return dict(own), hydrate.Provenance()

        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_access_policies", return_value=[]),
            mock.patch.object(scan.gcom, "fetch_org_members", side_effect=RuntimeError("HTTP 500")),
            mock.patch.object(scan, "gather_fleet", return_value=({}, [])),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=local_hydrate),
            mock.patch.object(scan.compose, "build_all", return_value=([], {}, {})),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=None),
            mock.patch.object(scan.carry, "load_state", side_effect=scan.carry.StateUnavailable("none")),
        ):
            result = scan.run_t1(FakeClient(), cfg_for("t1"))

        self.assertNotIn("org_members", seen["own"])
        self.assertEqual(seen["unavailable"]["org_members"]["state"], "unavailable")
        self.assertIn("org response", seen["unavailable"]["org_members"]["reason"])
        self.assertNotIn("stacks available", seen["unavailable"]["org_members"]["reason"])
        self.assertNotIn("org_members", result["data"])
        self.assertIn("org_members", result["meta"]["source_failures"])
        self.assertEqual(result["meta"]["sources"]["org_members"]["expected"], 1)
        self.assertEqual(result["meta"]["sources"]["org_members"]["available"], 0)
        self.assertFalse(result["meta"]["scan_healthy"])


class RateCardLoadingTest(unittest.TestCase):
    def test_rate_card_existence_process_failure_is_a_domain_error(self):
        def runner(_cmd, **_kwargs):
            raise OSError("aws executable unavailable")

        with self.assertRaisesRegex(
            scan.RateCardReadFailed,
            r"s3://deployment-bucket/config/ratecard.csv:.*aws executable unavailable",
        ):
            scan.load_ratecard(bucket="deployment-bucket", runner=runner)

    def test_rate_card_download_process_failure_is_a_domain_error(self):
        calls = 0

        def runner(_cmd, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return SimpleNamespace(returncode=0, stdout="{}", stderr="")
            raise OSError("aws process could not start")

        with self.assertRaisesRegex(
            scan.RateCardReadFailed,
            r"s3://deployment-bucket/config/ratecard.csv:.*aws process could not start",
        ):
            scan.load_ratecard(bucket="deployment-bucket", runner=runner)

    def test_rate_card_existence_check_has_a_finite_timeout(self):
        def runner(_cmd, **kwargs):
            raise subprocess.TimeoutExpired("aws", kwargs.get("timeout"))

        with self.assertRaisesRegex(scan.RateCardReadFailed, "head-object timed out"):
            scan.load_ratecard(bucket="deployment-bucket", runner=runner)

    def test_rate_card_download_has_a_finite_timeout(self):
        calls = 0

        def runner(_cmd, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return SimpleNamespace(returncode=0, stdout="{}", stderr="")
            raise subprocess.TimeoutExpired("aws", kwargs.get("timeout"))

        with self.assertRaisesRegex(scan.RateCardReadFailed, "read timed out"):
            scan.load_ratecard(bucket="deployment-bucket", runner=runner)

    def test_an_absent_optional_card_loads_as_none(self):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(
                returncode=255, stdout="",
                stderr="An error occurred (404) when calling the HeadObject operation: Not Found",
            )

        self.assertIsNone(scan.load_ratecard(bucket="deployment-bucket", runner=runner))
        self.assertIn("deployment-bucket", calls[0])
        self.assertIn("config/ratecard.csv", calls[0])

    def test_a_present_card_is_parsed_by_the_strict_loader(self):
        responses = iter([
            SimpleNamespace(returncode=0, stdout="{}", stderr=""),
            SimpleNamespace(
                returncode=0,
                stdout=("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                        "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,test\n"),
                stderr="",
            ),
        ])

        card = scan.load_ratecard(bucket="deployment-bucket", runner=lambda *_a, **_kw: next(responses))

        self.assertEqual(card.currency, "USD")
        self.assertEqual(card.price("metrics_series", 2000), 6.74)

    def test_t2_passes_the_loaded_card_to_composition(self):
        stacks = [{"slug": "alpha", "status": "active"}]
        card = object()
        seen = {}

        def detail(_client, _cfg, selected, coverage, *, on_error):
            coverage.record_ok("alpha")
            return {"alpha": {"slug": "alpha", "users": [], "plugins": []}}

        def compose(*args, **kwargs):
            seen.update(kwargs)
            return [], {}, {}

        available = ({"alpha": {"available": True}}, [])
        loki_available = ({
            "alpha": {
                "limits": {"available": True, "retention_stream": []},
                "change_requests": {"available": True, "items": []},
            },
        }, [])
        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail),
            mock.patch.object(
                scan, "gather_service_accounts",
                return_value=({"alpha": {"state": scan.sa_src.OK, "accounts": []}}, []),
            ),
            mock.patch.object(scan, "gather_assistant", return_value=available),
            mock.patch.object(scan, "gather_insights", return_value=available),
            mock.patch.object(scan, "gather_dashboard_inventory", return_value=available),
            mock.patch.object(scan, "gather_datasource_query_cost", return_value=available),
            mock.patch.object(scan, "gather_adaptive_logs", return_value=available),
            mock.patch.object(scan, "gather_public_dashboards", return_value=available),
            mock.patch.object(scan, "gather_alert_routing", return_value=available),
            mock.patch.multiple(scan,
                gather_slo_inventory=mock.Mock(return_value=available),
                slo_reads_enabled=mock.Mock(return_value=True),
                gather_synthetic_inventory=mock.Mock(return_value=available),
                synthetic_reads_enabled=mock.Mock(return_value=True)),
            mock.patch.object(scan, "gather_signal_inventory", return_value=available),
            mock.patch.object(
                scan, "gather_capability_adoption",
                return_value=({"available": True, "values": {}}, []),
            ),
            mock.patch.object(scan, "gather_loki_config", return_value=loki_available),
            mock.patch.object(scan.label_risk_src, "probe_all", return_value=available[0]),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=lambda _t, own, **_kw: (own, hydrate.Provenance())),
            mock.patch.object(scan.compose, "build_all", side_effect=compose),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=card),
        ):
            result = scan.run_t2(FakeClient(), cfg_for())

        self.assertIs(seen.get("ratecard"), card)
        self.assertIs(seen.get("signal_inventory"), available[0])
        self.assertIs(seen.get("loki_config"), loki_available[0])
        self.assertIs(seen.get("label_risk"), available[0])
        self.assertIs(result["data"].get("label_risk"), available[0])
        self.assertIs(result["data"].get("signal_inventory"), available[0])

    def test_a_malformed_present_card_is_an_honest_configuration_error(self):
        args = type("Args", (), {"out": None})()
        failure = scan.ratecard.InvalidRateCard(
            "s3://deployment-bucket/config/ratecard.csv: line 2: bad unit"
        )
        with (
            mock.patch.object(scan, "run_t2", side_effect=failure),
            mock.patch("sys.stderr") as stderr,
        ):
            rc = scan.run(FakeClient(), cfg_for(), args)

        self.assertEqual(rc, 2)
        message = " ".join(str(call) for call in stderr.write.call_args_list)
        self.assertIn("invalid rate card", message)
        self.assertIn("config/ratecard.csv", message)


class LocalPublicationGuardTest(unittest.TestCase):
    def test_local_publication_is_refused_after_configuration_is_validated(self):
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(scan.config, "load", return_value=cfg_for()) as load,
            mock.patch.object(scan, "ReadOnlyClient") as client,
        ):
            rc = scan.main(["--tier", "t1"])

        self.assertEqual(rc, 2)
        load.assert_called_once()
        client.assert_not_called()

    def test_local_dry_run_still_reaches_configuration_loading(self):
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(
                scan.config, "load", side_effect=config.MissingCredential("test stop")
            ) as load,
        ):
            rc = scan.main(["--tier", "t1", "--dry-run"])

        self.assertEqual(rc, 2)
        load.assert_called_once()

    def test_ecs_publication_still_reaches_configuration_loading(self):
        metadata = io.BytesIO(json.dumps({
            "ContainerARN": "arn:aws:ecs:eu-west-1:123456789012:container/cluster/id",
        }).encode())
        with (
            mock.patch.dict(
                "os.environ", {
                    "ECS_CONTAINER_METADATA_URI_V4": "http://169.254.170.2/v4/container-id",
                },
                clear=True,
            ),
            mock.patch.object(scan.urllib.request, "urlopen", return_value=metadata),
            mock.patch.object(
                scan.config, "load", side_effect=config.MissingCredential("test stop")
            ) as load,
        ):
            rc = scan.main(["--tier", "t1"])

        self.assertEqual(rc, 2)
        load.assert_called_once()

    def test_a_spoofed_metadata_environment_does_not_authorise_publication(self):
        with (
            mock.patch.dict(
                "os.environ", {"ECS_CONTAINER_METADATA_URI_V4": "http://metadata.invalid"},
                clear=True,
            ),
            mock.patch.object(scan.urllib.request, "urlopen") as urlopen,
            mock.patch.object(scan.config, "load", return_value=cfg_for()) as load,
            mock.patch.object(scan, "ReadOnlyClient") as client,
        ):
            rc = scan.main(["--tier", "t1"])

        self.assertEqual(rc, 2)
        urlopen.assert_not_called()
        load.assert_called_once()
        client.assert_not_called()

    def test_the_publication_seam_rechecks_the_verified_ecs_runtime(self):
        cfg = SimpleNamespace(tier="t1", dry_run=False)
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=False),
            mock.patch.object(scan, "run_t1") as runner,
        ):
            rc = scan.run(object(), cfg, SimpleNamespace())

        self.assertEqual(rc, 2)
        runner.assert_not_called()


class ComposeFixtureOrgMembersTest(unittest.TestCase):
    @staticmethod
    def scans(*, include_org_members: bool) -> dict[str, dict]:
        t1_data = {"access_policies": [], "fleet": {}}
        if include_org_members:
            t1_data["org_members"] = {
                "state": "ok",
                "members": [{"id": 1, "role": "Admin"}],
            }
        return {
            "t1": {"data": t1_data},
            "t2": {"data": {
                "stack_detail": {"alpha": {}},
                "assistant": {},
                "insights": {},
                "dashboard_inventory": {},
                "datasource_query_cost": {},
            }},
            "t3": {"data": {
                "stacks": [{"slug": "alpha"}],
                "dataplane": {"alpha": {}},
            }},
        }

    def test_fixture_preserves_the_t1_org_members_payload(self):
        scans = self.scans(include_org_members=True)
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "compose_inputs.json"
            with (
                mock.patch.object(
                    compose_fixture, "fetch", side_effect=lambda tier: scans[tier]
                ),
                contextlib.redirect_stderr(stderr),
            ):
                rc = compose_fixture.main(["--stacks", "1", "--output", str(out)])

            payload = json.loads(out.read_text())

        self.assertEqual(rc, 0)
        self.assertEqual(payload["org_members"], scans["t1"]["data"]["org_members"])
        # This minimal exporter fixture intentionally has no Pillar J observations.
        self.assertIn("no `insights` payload", stderr.getvalue())

    def test_fixture_warns_when_t1_has_no_org_members_payload(self):
        scans = self.scans(include_org_members=False)
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "compose_inputs.json"
            with (
                mock.patch.object(
                    compose_fixture, "fetch", side_effect=lambda tier: scans[tier]
                ),
                contextlib.redirect_stderr(stderr),
            ):
                rc = compose_fixture.main(["--stacks", "1", "--output", str(out)])

        self.assertEqual(rc, 0)
        self.assertIn("no `org_members` payload", stderr.getvalue())
        self.assertIn("no `insights` payload", stderr.getvalue())

    def test_fixture_treats_a_malformed_org_members_payload_as_absent(self):
        scans = self.scans(include_org_members=False)
        scans["t1"]["data"]["org_members"] = ["not", "a", "mapping"]
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "compose_inputs.json"
            with (
                mock.patch.object(
                    compose_fixture, "fetch", side_effect=lambda tier: scans[tier]
                ),
                contextlib.redirect_stderr(stderr),
            ):
                rc = compose_fixture.main(["--stacks", "1", "--output", str(out)])
            payload = json.loads(out.read_text())

        self.assertEqual(rc, 0)
        self.assertEqual(payload["org_members"], {})
        self.assertIn("no `org_members` payload", stderr.getvalue())
        self.assertIn("no `insights` payload", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
