"""Pillar K coverage depth, identity joins, and absent-versus-zero contracts."""

from __future__ import annotations

import unittest

from collector import observability_score
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
        "slo_services": ["checkout"],
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
        "rules_total": 2,
        "service_routes": [
            {"service_name": "checkout", "identity_label": "service_name", "paused": False,
             "routing": "direct", "receiver_state": "provisioned"},
            {"service_name": "inventory", "identity_label": "service_name", "paused": True,
             "routing": "direct", "receiver_state": "provisioned"},
        ],
    },
}


class CoverageBuildTest(unittest.TestCase):
    def test_structurally_absent_products_are_unscored_with_the_reason(self):
        """Product absence is an adoption opportunity, not failed service coverage."""
        record = dict(SIGNALS["alpha"])
        record.update({
            "metric_services": ["app"],
            "log_services": ["app"],
            "trace_services": ["app"],
            "profile_services": [],
            "slo_services": [],
            "metric_names": ["application_metric"],
        })
        metrics, views = coverage.build(
            [{"slug": "alpha"}], {"alpha": record},
            dashboard_inventory={"alpha": {"available": False}},
            alert_routing={"alpha": {"available": True, "rules_total": 0}},
        )

        row = views[coverage.SERVICE_VIEW][0]
        self.assertEqual(row["Metrics"], "yes")
        self.assertEqual(row["Logs"], "yes")
        self.assertEqual(row["Traces"], "yes")
        self.assertEqual(row["Profiles"], "unscored: signal_not_in_use")
        self.assertEqual(row["Has SLO"], "unscored: product_not_in_use")
        self.assertEqual(row["Has alert"], "unscored: product_not_in_use")
        self.assertEqual(row["Has dashboard"], "unscored: inventory_unavailable")
        self.assertEqual(row["Applicable components"], 3)
        self.assertIsNone(row["Observability completeness %"])

        unscored = {
            (labels["component"], labels["reason"]): value
            for name, labels, value in metrics
            if name == "gcinsight_coverage_unscored"
        }
        self.assertEqual(unscored[("profiles", "signal_not_in_use")], 1)
        self.assertEqual(unscored[("slo", "product_not_in_use")], 1)
        self.assertEqual(unscored[("alert", "product_not_in_use")], 1)
        self.assertEqual(unscored[("dashboard", "inventory_unavailable")], 1)

    def test_zero_dashboards_is_scored_no_when_the_inventory_succeeded(self):
        """An empty successful dashboard inventory is evidence, not an unavailable input."""
        _metrics, views = coverage.build(
            STACKS, SIGNALS,
            dashboard_inventory={"alpha": {"available": True, "dashboards": []}},
            alert_routing=ALERTS,
        )
        row = next(row for row in views[coverage.SERVICE_VIEW] if row["Service"] == "checkout")
        self.assertEqual(row["Has dashboard"], "no")
        self.assertEqual(row["Applicable components"], 7)

    def test_unavailable_alert_inventory_and_dashboard_evidence_are_not_zero(self):
        """A failed evidence read must not be converted into an evaluated component with value no."""
        _metrics, views = coverage.build(
            STACKS, SIGNALS,
            dashboard_inventory={
                "alpha": {"available": True, "detail_available": False, "dashboards": []},
            },
            alert_routing={"alpha": {"available": False}},
        )
        row = next(row for row in views[coverage.SERVICE_VIEW] if row["Service"] == "checkout")
        self.assertEqual(row["Has alert"], "unscored: inventory_unavailable")
        self.assertEqual(row["Has dashboard"], "unscored: evidence_unavailable")
        self.assertEqual(row["Applicable components"], 5)

    def test_non_application_populations_stay_visible_but_leave_application_aggregates(self):
        """Named populations make exclusions auditable instead of silently shrinking the denominator."""
        record = dict(SIGNALS["alpha"])
        record.update({
            "metric_services": ["short", "worker.service", "K6-SYNTHETIC-stack"],
            "log_services": [
                "app", "api", "worker.service", "session-12", "batch-12345678",
                "a1b2c3d4-1234-5678-9012-a1b2c3d4e5f6", "K6-SYNTHETIC-stack",
                "load-k6-synthetic-tool",
            ],
            "trace_services": [], "profile_services": [], "slo_services": [],
            "metric_names": ["application_metric"],
        })
        metrics, views = coverage.build(
            [{"slug": "alpha"}], {"alpha": record},
            dashboard_inventory={"alpha": {"available": True, "dashboards": []}},
            alert_routing={"alpha": {"available": True, "rules_total": 0}},
        )
        rows = {row["Service"]: row for row in views[coverage.SERVICE_VIEW]}
        self.assertEqual(rows["k6-synthetic-stack"]["Population"], "platform")
        self.assertEqual(rows["worker.service"]["Population"], "application",
                         "metrics evidence overrides a machine-shaped log identity")
        self.assertEqual(rows["session-12"]["Population"], "infrastructure_unit")
        self.assertEqual(rows["batch-12345678"]["Population"], "infrastructure_unit")
        self.assertEqual(
            rows["a1b2c3d4-1234-5678-9012-a1b2c3d4e5f6"]["Population"],
            "infrastructure_unit",
        )
        self.assertEqual(rows["api"]["Population"], "application",
                         "identity length is never classification evidence")
        self.assertEqual(rows["load-k6-synthetic-tool"]["Population"], "application",
                         "the platform prefix is anchored and never a loose k6 substring")
        self.assertIsNone(rows["k6-synthetic-stack"]["Observability completeness %"])

        values = {
            (name, tuple(sorted(labels.items()))): value for name, labels, value in metrics
        }
        self.assertEqual(values[("gcinsight_coverage_stack_services", (("stack", "alpha"),))], 5)
        self.assertEqual(
            values[("gcinsight_coverage_services_by_depth", (("kind", "1"),))], 4,
        )
        self.assertEqual(
            values[("gcinsight_coverage_unscored", (
                ("component", "row"), ("reason", "platform_identity"),
            ))],
            1,
        )
        populations = {
            labels["kind"]: value for name, labels, value in metrics
            if name == "gcinsight_coverage_service_population"
        }
        self.assertEqual(populations, {
            "application": 5, "platform": 1, "infrastructure_unit": 3,
        })

    def test_service_depth_uses_canonical_exact_normalized_identity(self):
        metrics, views = coverage.build(
            STACKS, SIGNALS, dashboard_inventory=DASHBOARDS, alert_routing=ALERTS,
        )
        rows = {row["Service"]: row for row in views[coverage.SERVICE_VIEW]}
        self.assertEqual(set(rows), {"checkout", "inventory", "log-only"})
        self.assertEqual(rows["checkout"]["Signals present"], 4)
        self.assertEqual(
            [rows["checkout"][field] for field in ("Metrics", "Logs", "Traces", "Profiles")],
            ["yes", "yes", "yes", "yes"],
        )
        self.assertEqual(rows["checkout"]["Has alert"], "yes")
        self.assertEqual(rows["checkout"]["Has dashboard"], "yes")
        self.assertEqual(rows["checkout"]["Has routed active alert"], "yes")
        self.assertEqual(rows["checkout"]["Has SLO"], "yes")
        self.assertEqual(rows["checkout"]["Observability completeness %"], 100.0)
        self.assertEqual(rows["checkout"]["Score numerator"], 7)
        self.assertEqual(rows["checkout"]["Score maximum"], 7)
        self.assertEqual(rows["checkout"]["Score version"], observability_score.VERSION)
        self.assertEqual(rows["inventory"]["Has alert"], "yes")
        self.assertEqual(rows["inventory"]["Has dashboard"], "no",
                         "dashboard titles must never infer a service relationship")
        self.assertEqual(rows["inventory"]["Has routed active alert"], "no")
        self.assertEqual(rows["inventory"]["Observability completeness %"], round(2 / 7 * 100, 1))

        by_metric = {}
        for name, labels, value in metrics:
            by_metric[(name, tuple(sorted(labels.items())))] = value
        depth = "gcinsight_coverage_services_by_depth"
        self.assertEqual(by_metric[(depth, (("kind", "1"),))], 2)
        self.assertEqual(by_metric[(depth, (("kind", "4"),))], 1)
        by_signal = "gcinsight_coverage_services_by_signal"
        self.assertEqual(by_metric[(by_signal, (("kind", "metrics"),))], 2)
        self.assertEqual(by_metric[(by_signal, (("kind", "logs"),))], 2)
        self.assertEqual(by_metric[(by_signal, (("kind", "traces"),))], 1)
        self.assertEqual(by_metric[(by_signal, (("kind", "profiles"),))], 1)

    def test_configurable_weights_change_only_the_score_not_component_evidence(self):
        weights = observability_score.parse_weights(
            '{"metrics": 4, "logs": 0, "traces": 0, "profiles": 0, '
            '"dashboard": 1, "alert": 1, "slo": 1}'
        )
        _metrics, views = coverage.build(
            STACKS, SIGNALS, dashboard_inventory=DASHBOARDS, alert_routing=ALERTS,
            score_weights=weights,
        )
        row = next(row for row in views[coverage.SERVICE_VIEW] if row["Service"] == "inventory")
        self.assertEqual(row["Metrics"], "yes")
        self.assertEqual(row["Logs"], "no")
        self.assertEqual(row["Has alert"], "yes")
        self.assertEqual(row["Observability completeness %"], round(5 / 7 * 100, 1))

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

    def test_technology_presence_distribution_uses_four_closed_buckets(self):
        """The registry detects presence; dividing sentinel matches by every metric name is invalid."""
        sentinels = [
            "kube_pod_info", "node_uname_info", "mysql_up", "redis_up", "rabbitmq_channels",
        ]
        stacks = [{"slug": f"stack-{index}"} for index in range(4)]
        records = {}
        for index, count in enumerate((0, 1, 2, 5)):
            records[f"stack-{index}"] = {
                "available": True,
                "window_end": "2026-08-25T00:00:00+00:00",
                "metric_names": sentinels[:count],
                "metric_services": [], "legacy_metric_services": [], "log_services": [],
                "trace_services": [], "profile_services": [], "slo_services": [], "clusters": [],
            }
        metrics, _views = coverage.build(stacks, records)
        distribution = {
            labels["kind"]: value for name, labels, value in metrics
            if name == "gcinsight_coverage_stacks_by_technology_count"
        }
        self.assertEqual(distribution, {"0": 1, "1": 1, "2-4": 1, "5+": 1})

    def test_summary_keeps_unmatched_count_without_publishing_a_share(self):
        """Unmatched names are a registry backlog, not a classification-confidence denominator."""
        _metrics, views = coverage.build(STACKS, SIGNALS)
        row = views[coverage.SUMMARY_VIEW][0]
        self.assertEqual(row["Unmatched metric names"], 1)
        self.assertNotIn("Unmatched metric share %", row)

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


class ObservabilityScoreConfigTest(unittest.TestCase):
    def test_defaults_weight_all_seven_visible_components_equally(self):
        self.assertEqual(observability_score.parse_weights(""), {
            component: 1.0 for component in observability_score.COMPONENTS
        })

    def test_invalid_weight_configuration_is_rejected(self):
        cases = (
            '{"unknown": 1}',
            '{"metrics": -1}',
            '{"metrics": "heavy"}',
            '{"metrics": 0, "logs": 0, "traces": 0, "profiles": 0, '
            '"dashboard": 0, "alert": 0, "slo": 0}',
            '[]',
            '{',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(observability_score.InvalidWeights):
                    observability_score.parse_weights(raw)

    def test_score_uses_only_applicable_components(self):
        """A product that is not in use must not remain in the score denominator."""
        states = {component: None for component in observability_score.COMPONENTS}
        states.update({"metrics": True, "logs": False, "traces": True, "dashboard": False})
        self.assertEqual(
            observability_score.calculate(states, observability_score.parse_weights("")),
            (2.0, 4.0, 50.0),
        )

    def test_percentage_is_withheld_below_four_applicable_components(self):
        """A thin score looks precise while resting on too little of the declared rubric."""
        states = {component: None for component in observability_score.COMPONENTS}
        states.update({"metrics": True, "logs": False, "traces": True})
        self.assertEqual(
            observability_score.calculate(states, observability_score.parse_weights("")),
            (2.0, 3.0, None),
        )


if __name__ == "__main__":
    unittest.main()
