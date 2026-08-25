"""Pillar K coverage depth, identity joins, and absent-versus-zero contracts."""

from __future__ import annotations

import unittest

from collector.pillars import coverage
from collector.emit import hydrate
from collector.coverage import Coverage, rollup


class CoverageTest(unittest.TestCase):
    def test_full_coverage(self):
        cov = Coverage(tier="t1", total=3)
        for stack in ("a", "b", "c"):
            cov.record_ok(stack)
        self.assertEqual(cov.ratio, 1.0)
        self.assertFalse(cov.should_abort)
        self.assertEqual(cov.failed, 0)

    def test_failures_are_recorded_by_reason_and_named(self):
        cov = Coverage(tier="t2", total=4)
        cov.record_ok("a")
        cov.record_failure("b", "http_429")
        cov.record_failure("c", "http_429")
        cov.record_failure("d", "timeout")
        self.assertEqual(cov.failed, 3)
        meta = cov.as_meta()
        self.assertEqual(meta["failures_by_reason"], {"http_429": 2, "timeout": 1})
        self.assertEqual(meta["failed_stacks"], {"b": "http_429", "c": "http_429", "d": "timeout"})

    def test_a_retried_stack_stops_being_a_failure(self):
        cov = Coverage(tier="t1", total=1)
        cov.record_failure("a", "timeout")
        cov.record_ok("a")
        self.assertEqual(cov.failed, 0)
        self.assertEqual(cov.as_meta()["failures_by_reason"], {})

    def test_abort_threshold_is_ten_percent(self):
        cov = Coverage(tier="t1", total=100)
        for i in range(10):
            cov.record_failure(f"s{i}", "http_500")
        self.assertFalse(cov.should_abort, "exactly 10% must not abort")
        cov.record_failure("s10", "http_500")
        self.assertTrue(cov.should_abort)

    def test_metrics_labels_stay_bounded(self):
        """Cardinality guard: only `tier` and a closed `reason` vocabulary may appear."""
        cov = Coverage(tier="t3", total=2)
        cov.record_ok("a")
        cov.record_failure("b", "http_429")
        names = {name for name, _, _ in cov.as_metrics()}
        self.assertEqual(
            names,
            {
                "gcinsight_scan_stacks_total",
                "gcinsight_scan_stacks_scannable",
                "gcinsight_scan_stacks_scanned",
                "gcinsight_scan_coverage_ratio",
                "gcinsight_scan_stacks_failed",
            },
        )
        for _, labels, _ in cov.as_metrics():
            self.assertLessEqual(set(labels), {"tier", "reason"})

    def test_paused_stacks_are_skipped_not_failed(self):
        """The estate's 4 paused stacks answer HTTP 409. Counting them as failures would cap coverage
        at 98.5% forever; counting them as scanned would be the opposite lie."""
        cov = Coverage(tier="t2", total=271)
        for i in range(267):
            cov.record_ok(f"s{i}")
        for slug in ("testsrobot002", "teststack004", "teststack017", "teststack018"):
            cov.record_skipped(slug, "paused")

        self.assertEqual(cov.failed, 0)
        self.assertEqual(cov.scannable, 267)
        self.assertEqual(cov.ratio, 1.0, "a fully-scanned estate must read 100% despite paused stacks")
        self.assertFalse(cov.should_abort)
        meta = cov.as_meta()
        self.assertEqual(meta["stacks_skipped"], 4)
        self.assertEqual(meta["skipped_by_reason"], {"paused": 4})
        self.assertFalse(rollup("x", 1, cov)["partial"])

    def test_skipped_stacks_do_not_mask_real_failures(self):
        cov = Coverage(tier="t2", total=100)
        for i in range(4):
            cov.record_skipped(f"p{i}", "paused")
        for i in range(11):
            cov.record_failure(f"f{i}", "http_500")
        for i in range(85):
            cov.record_ok(f"s{i}")
        self.assertEqual(cov.scannable, 96)
        self.assertTrue(cov.should_abort, "11 of 96 scannable is over the 10% threshold")

    def test_rollup_carries_its_denominator(self):
        """The fix for the flagship silent-wrongness path: a partial scan is visibly partial."""
        cov = Coverage(tier="t1", total=271)
        for i in range(244):
            cov.record_ok(f"s{i}")
        for i in range(27):
            cov.record_failure(f"f{i}", "http_500")

        got = rollup("dashboards_total", 6700, cov)
        self.assertEqual(got["stacks_counted"], 244)
        self.assertEqual(got["stacks_total"], 271)
        self.assertTrue(got["partial"])
        self.assertEqual(got["coverage_ratio"], 0.9004)

    def test_rollup_is_not_partial_at_full_coverage(self):
        cov = Coverage(tier="t1", total=2)
        cov.record_ok("a")
        cov.record_ok("b")
        self.assertFalse(rollup("x", 1, cov)["partial"])

    def test_empty_estate_does_not_divide_by_zero(self):
        cov = Coverage(tier="t1", total=0)
        self.assertEqual(cov.ratio, 0.0)
        self.assertFalse(cov.should_abort)


STACKS = [{"slug": "alpha"}, {"slug": "failed"}, {"slug": "departed-never-iterate"}]
SIGNALS = {
    "alpha": {
        "available": True,
        "window_end": "2026-08-25T00:00:00+00:00",
        "metric_names": ["kube_pod_info", "unknown_metric"],
        "metric_services": [" Checkout ", "inventory"],
        "legacy_metric_services": ["legacy-api"],
        "log_services": ["checkout", "log-only"],
        "trace_services": ["CHECKOUT"],
        "profile_services": ["checkout"],
        "clusters": ["compute-a"],
    },
    "failed": {"available": False, "reason": "auth"},
    "payload-only": {"available": True, "metric_names": ["kube_pod_info"]},
}
DASHBOARDS = {
    "alpha": {
        "available": True,
        "dashboards": [
            {"uid": "explicit", "title": "Unrelated title", "service_tags": ["service:checkout"]},
            {"uid": "title-only", "title": "inventory dashboard", "service_tags": []},
        ],
    },
}
ALERTS = {
    "alpha": {
        "available": True,
        "service_routes": [
            {"service_name": "checkout", "identity_label": "service_name", "paused": False,
             "routing": "direct", "receiver_state": "provisioned"},
            {"service_name": "inventory", "identity_label": "service_name", "paused": True,
             "routing": "direct", "receiver_state": "provisioned"},
        ],
    },
}


class CoverageBuildTest(unittest.TestCase):
    def test_service_depth_uses_canonical_exact_normalized_identity(self):
        metrics, views = coverage.build(
            STACKS, SIGNALS, dashboard_inventory=DASHBOARDS, alert_routing=ALERTS,
        )
        rows = {row["Service"]: row for row in views[coverage.SERVICE_VIEW]}
        self.assertEqual(set(rows), {"checkout", "inventory", "log-only"})
        self.assertEqual(rows["checkout"]["Signals present"], 4)
        self.assertEqual(rows["checkout"]["Signals"], "metrics, logs, traces, profiles")
        self.assertEqual(rows["checkout"]["Has alert"], "yes")
        self.assertEqual(rows["checkout"]["Has dashboard"], "yes")
        self.assertEqual(rows["checkout"]["Has routed active alert"], "yes")
        self.assertEqual(rows["inventory"]["Has alert"], "yes")
        self.assertEqual(rows["inventory"]["Has dashboard"], "no",
                         "dashboard titles must never infer a service relationship")
        self.assertEqual(rows["inventory"]["Has routed active alert"], "no")

        by_metric = {}
        for name, labels, value in metrics:
            by_metric[(name, tuple(sorted(labels.items())))] = value
        depth = "gcinsight_coverage_services_by_depth"
        self.assertEqual(by_metric[(depth, (("kind", "1"),))], 2)
        self.assertEqual(by_metric[(depth, (("kind", "4"),))], 1)

    def test_failed_stack_and_departed_payload_produce_no_rows_or_zero_metrics(self):
        metrics, views = coverage.build(STACKS, SIGNALS)
        self.assertNotIn("failed", {row[" Stack"] for rows in views.values() for row in rows})
        self.assertNotIn("payload-only", {row[" Stack"] for rows in views.values() for row in rows})
        per_stack = [(labels.get("stack"), value) for _name, labels, value in metrics if "stack" in labels]
        self.assertTrue(per_stack)
        self.assertEqual({stack for stack, _value in per_stack}, {"alpha"})

    def test_legacy_service_is_reported_separately_not_promoted_into_coverage(self):
        metrics, views = coverage.build(STACKS, SIGNALS)
        services = {row["Service"] for row in views[coverage.SERVICE_VIEW]}
        self.assertNotIn("legacy-api", services)
        self.assertEqual(views[coverage.LEGACY_SERVICE_VIEW], [{
            " Stack": "alpha", "Legacy service": "legacy-api", "Also canonical": "no",
            "Last seen": "2026-08-25T00:00:00+00:00",
        }])
        identity = {
            labels["kind"]: value for name, labels, value in metrics
            if name == "gcinsight_coverage_service_identity"
        }
        self.assertEqual(identity, {"canonical": 3, "legacy_only": 1, "overlap": 0})

    def test_technology_classification_publishes_names_and_unmatched_share_inputs(self):
        metrics, views = coverage.build(STACKS, SIGNALS)
        tech = views[coverage.TECHNOLOGY_VIEW]
        self.assertEqual(tech[0]["Technology"], "Kubernetes")
        metric_rows = {row["Metric name"]: row for row in views[coverage.METRIC_VIEW]}
        self.assertEqual(metric_rows["kube_pod_info"]["Technology"], "Kubernetes")
        self.assertEqual(metric_rows["unknown_metric"]["Technology"], "(unmatched)")
        classified = {
            labels["kind"]: value for name, labels, value in metrics
            if name == "gcinsight_coverage_metric_names"
        }
        self.assertEqual(classified, {"matched": 1, "unmatched": 1})

    def test_no_signal_input_emits_nothing(self):
        self.assertEqual(coverage.build(STACKS, None), ([], {}))

    def test_named_service_view_is_withheld_when_explicit_metadata_inputs_are_unsatisfied(self):
        provenance = hydrate.Provenance({
            "signal_inventory": {"available": True, "stale": False},
            "dashboard_inventory": {"available": False, "stale": False},
            "alert_routing": {"available": True, "stale": False},
        })
        views = {
            coverage.SERVICE_VIEW: [{"Service": "checkout"}],
            coverage.TECHNOLOGY_VIEW: [{"Technology": "Kubernetes"}],
        }
        kept, withheld = hydrate.filter_views(views, provenance)
        self.assertNotIn(coverage.SERVICE_VIEW, kept)
        self.assertIn(coverage.SERVICE_VIEW, withheld)
        self.assertIn(coverage.TECHNOLOGY_VIEW, kept)

    def test_service_view_is_top_n_bounded_per_stack(self):
        record = dict(SIGNALS["alpha"])
        record["log_services"] = [f"service-{index:03d}" for index in range(coverage.MAX_SERVICES + 1)]
        _metrics, views = coverage.build([{"slug": "alpha"}], {"alpha": record})
        self.assertEqual(len(views[coverage.SERVICE_VIEW]), coverage.MAX_SERVICES)
        self.assertEqual(views[coverage.SUMMARY_VIEW][0]["Services retained"], coverage.MAX_SERVICES)
        self.assertGreater(views[coverage.SUMMARY_VIEW][0]["Services discovered"], coverage.MAX_SERVICES)

    def test_declared_view_schemas_are_derived_from_real_rows(self):
        _metrics, views = coverage.build(
            STACKS, SIGNALS, dashboard_inventory=DASHBOARDS, alert_routing=ALERTS,
        )
        self.assertEqual(set(views), set(coverage.VIEW_SCHEMAS))
        for name, schema in coverage.VIEW_SCHEMAS.items():
            with self.subTest(view=name):
                self.assertTrue(views[name], "fixture must exercise the schema instead of asserting it")
                self.assertEqual(tuple(views[name][0]), tuple(column for column, _kind in schema))


if __name__ == "__main__":
    unittest.main()
