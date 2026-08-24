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
import pathlib
import subprocess
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
                [("gcinsight_cost_active_series", {"stack": "alpha"}, 1.0)], {},
            )),
            mock.patch.object(scan.carry, "save_state") as save_state,
        ):
            result = scan.run_t3(client, cfg)

        self.assertTrue(result["meta"]["stacks_failed"])
        save_state.assert_not_called()

    def test_common_health_gate_saves_an_accepted_t3_batch_before_publication(self):
        metrics = [("gcinsight_cost_active_series", {"stack": "alpha"}, 1.0)]
        result = {
            "meta": {
                "tier": "t3", "generated_at": "2026-08-21T00:00:00+00:00",
                "coverage_ratio": 1.0, "stacks_failed": 0, "stacks_scannable": 1,
                "stacks_total": 1, "source_failures": [], "inputs": {},
            },
            "data": {},
            "_emit": {"metrics": metrics, "views": {}},
        }
        args = SimpleNamespace(out=None)
        cfg = cfg_for("t3")
        cfg = config.Config(**{**cfg.__dict__, "dry_run": False})
        with (
            mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
            mock.patch.object(scan, "run_t3", return_value=result),
            mock.patch.object(scan.carry, "save_state", return_value="s3://bucket/state/t3.json")
            as save_state,
            mock.patch.object(scan.s3emit, "write_views", return_value=[]),
            mock.patch.object(scan.s3emit, "write_scan", return_value=[]),
            mock.patch.object(scan.mimir, "RemoteWriter") as remote_writer,
            mock.patch.object(scan.loki, "LokiWriter") as loki_writer,
        ):
            remote_writer.return_value.push.return_value = 3
            loki_writer.return_value.push.return_value = 1
            rc = scan.run(FakeClient(), cfg, args)

        self.assertEqual(rc, 0)
        save_state.assert_called_once_with(metrics, "t3", bucket=scan.s3emit.BUCKET)

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

        def hydrate_own(_tier, own, *, unavailable, bucket):
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
            mock.patch.object(scan, "gather_public_dashboards", return_value=unavailable),
            mock.patch.object(scan, "gather_alert_routing", return_value=unavailable),
            mock.patch.object(scan, "gather_signal_inventory", return_value=unavailable),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=hydrate_own),
            mock.patch.object(scan.compose, "build_all", return_value=([], {})),
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
            {"service_accounts", "assistant", "insights", "adaptive_logs", "public_dashboards",
             "alert_routing", "dashboard_inventory", "datasource_query_cost", "signal_inventory"},
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
                tier, own, unavailable=kwargs.get("unavailable"),
                loader=lambda _tier, _bucket: None,
            )

        def compose(_stacks, _coverage, **kwargs):
            seen.update(kwargs)
            # This models the dangerous output seam: if the partial input reaches composition, an
            # estate total and summary view are produced from the one successful stack.
            if "insights" in kwargs:
                return ([('gcinsight_dashboards_estate_views', {"version": "2"}, 99.0)],
                        {"insights_summary": [{"Value": 99}]})
            return [], {}

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
            mock.patch.object(scan, "gather_signal_inventory", return_value=(healthy, [])),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=local_hydrate),
            mock.patch.object(scan.compose, "build_all", side_effect=compose),
            mock.patch.object(scan, "assistant_gaps", return_value={}) as assistant_gaps,
            mock.patch.object(scan, "load_ratecard", return_value=None),
        ):
            result = scan.run_t2(FakeClient(), cfg_for())

        self.assertNotIn("insights", seen, "partial source must not reach estate composition")
        self.assertNotIn("insights", result["data"], "partial source must not become latest owner input")
        self.assertEqual(result["_emit"], {"metrics": [], "views": {}})
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

        def local_hydrate(_tier, own, *, unavailable, bucket):
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
            mock.patch.object(scan.compose, "build_all", return_value=([], {})),
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
            mock.patch.object(scan.compose, "build_all", return_value=([], {})),
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

        def local_hydrate(_tier, own, *, unavailable, bucket):
            seen["own"] = own
            seen["unavailable"] = unavailable
            return dict(own), hydrate.Provenance()

        def compose(_stacks, _coverage, **kwargs):
            seen["compose"] = kwargs
            return [], {}

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

        def local_hydrate(_tier, own, *, unavailable, bucket):
            seen["own"] = own
            seen["unavailable"] = unavailable
            return dict(own), hydrate.Provenance()

        with (
            mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks),
            mock.patch.object(scan.gcom, "fetch_access_policies", return_value=[]),
            mock.patch.object(scan.gcom, "fetch_org_members", side_effect=RuntimeError("HTTP 500")),
            mock.patch.object(scan, "gather_fleet", return_value=({}, [])),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=local_hydrate),
            mock.patch.object(scan.compose, "build_all", return_value=([], {})),
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
            return [], {}

        available = ({"alpha": {"available": True}}, [])
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
            mock.patch.object(scan, "gather_signal_inventory", return_value=available),
            mock.patch.object(scan.hydrate, "hydrate", side_effect=lambda _t, own, **_kw: (own, hydrate.Provenance())),
            mock.patch.object(scan.compose, "build_all", side_effect=compose),
            mock.patch.object(scan, "assistant_gaps", return_value={}),
            mock.patch.object(scan, "load_ratecard", return_value=card),
        ):
            result = scan.run_t2(FakeClient(), cfg_for())

        self.assertIs(seen.get("ratecard"), card)
        self.assertIs(seen.get("signal_inventory"), available[0])
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
    def test_local_publication_is_refused_before_configuration_is_loaded(self):
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(scan.config, "load") as load,
        ):
            rc = scan.main(["--tier", "t1"])

        self.assertEqual(rc, 2)
        load.assert_not_called()

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
            mock.patch.object(scan.config, "load") as load,
        ):
            rc = scan.main(["--tier", "t1"])

        self.assertEqual(rc, 2)
        urlopen.assert_not_called()
        load.assert_not_called()

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
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "compose_inputs.json"
            with (
                mock.patch.object(
                    compose_fixture, "fetch", side_effect=lambda tier: scans[tier]
                ),
            ):
                rc = compose_fixture.main(["--stacks", "1", "--output", str(out)])

            payload = json.loads(out.read_text())

        self.assertEqual(rc, 0)
        self.assertEqual(payload["org_members"], scans["t1"]["data"]["org_members"])

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


if __name__ == "__main__":
    unittest.main()
