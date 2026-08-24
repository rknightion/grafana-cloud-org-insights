"""Findings derivation (the missing producer for `loki.finding_events`).

The load-bearing test here is `test_a_view_the_tier_could_not_compute_is_absent_not_zero`. That defect
has already been shipped once in this project at the pillar layer - T1 emitted structural zeros for
metrics only T3 could compute, and the hourly timestamp overwrote the real weekly values. This module
introduces exactly the same hazard one layer up.
"""

from __future__ import annotations

import unittest

from collector.emit import loki
from collector.pillars import findings


def view(n: int, prefix: str = "stack") -> list[dict]:
    """Rows for an already-filtered view (most of them). No filter fields needed."""
    return [{" Stack": f"{prefix}{i}", "Active series": i * 1000, "Admins": i} for i in range(1, n + 1)]


def cardinality_view(n: int, worst: int = 9_999) -> list[dict]:
    """`cost_cardinality_outliers` is an unfiltered table, so its rows must clear the threshold."""
    return [{" Stack": f"s{i}", "Worst label": "pod", "Worst label values": worst,
             "Active series": 500_000} for i in range(1, n + 1)]


def sa_view(flagged: int, unflagged: int) -> list[dict]:
    """`risk_service_accounts` is the whole inventory; only `Flag` rows are findings."""
    rows = [{" Stack": "s", "Service account": f"svc{i}", "Kind": "custom", "Role": "Admin",
             "Tokens": 19, "Flag": "admin with many tokens"} for i in range(flagged)]
    rows += [{" Stack": "s", "Service account": f"extsvc-{i}", "Kind": "extsvc", "Role": "Viewer",
              "Tokens": 1, "Flag": None} for i in range(unflagged)]
    return rows


class TestAbsenceVersusZero(unittest.TestCase):
    def test_a_view_the_tier_could_not_compute_is_absent_not_zero(self):
        """T1 has no data plane, so it cannot compute cardinality outliers. It must say NOTHING rather
        than emit 0, which would overwrite the real weekly value every hour."""
        found, totals = findings.derive({"risk_admin_sprawl": view(3)})

        self.assertIn("admin_sprawl", totals)
        self.assertNotIn("cardinality_outlier", totals)
        emitted = {labels["kind"] for _, labels, _ in findings.metrics(totals)}
        self.assertNotIn("cardinality_outlier", emitted)

    def test_a_view_present_but_empty_is_a_real_zero(self):
        """Distinct from absence, and it must be reported. `risk_plugin_drift` legitimately has 0 rows -
        that is a measured 'no drift', not a gap, and the trend line should show it."""
        _, totals = findings.derive({"risk_plugin_drift": []})
        self.assertEqual(totals["plugin_drift"], 0)
        self.assertEqual(findings.metrics(totals), [("gcinsight_findings", {"kind": "plugin_drift"}, 0.0)])

    def test_no_views_yields_no_metrics_at_all(self):
        found, totals = findings.derive({})
        self.assertEqual(found, [])
        self.assertEqual(findings.metrics(totals), [])


class TestCapping(unittest.TestCase):
    def test_lines_are_capped_but_the_metric_carries_the_true_total(self):
        """A cap that also reduced the number would silently understate the estate's problems."""
        found, totals = findings.derive({"cost_cardinality_outliers": cardinality_view(230)})

        self.assertEqual(len(found), findings.MAX_LINES_PER_KIND)
        self.assertEqual(totals["cardinality_outlier"], 230)
        self.assertEqual(findings.metrics(totals)[0][2], 230.0)

    def test_capped_findings_are_marked_and_ranked(self):
        found, _ = findings.derive({"cost_cardinality_outliers": cardinality_view(230)})
        self.assertTrue(all(f["truncated"] for f in found))
        self.assertEqual([f["rank"] for f in found], list(range(1, findings.MAX_LINES_PER_KIND + 1)))
        self.assertTrue(all(f["of_total"] == 230 for f in found))

    def test_an_uncapped_kind_is_not_marked_truncated(self):
        found, _ = findings.derive({"risk_admin_sprawl": view(5)})
        self.assertFalse(any(f["truncated"] for f in found))

    def test_summary_names_the_capped_kinds_rather_than_hiding_them(self):
        _, totals = findings.derive({"cost_cardinality_outliers": cardinality_view(230), "risk_admin_sprawl": view(2)})
        msg = findings.summarise([], totals)
        self.assertIn("cardinality_outlier", msg)
        self.assertIn("capped", msg)
        self.assertNotIn("admin_sprawl", msg.split("capped")[1])


class TestRowExtraction(unittest.TestCase):
    def test_the_leading_space_stack_key_is_found(self):
        """Views key the stack as ' Stack' to force Infinity's alphabetical column order. A naive
        row['Stack'] finds nothing and every finding would be stackless."""
        found, _ = findings.derive({"risk_admin_sprawl": [{" Stack": "stack084", "Admins": 9}]})
        self.assertEqual(found[0]["stack"], "stack084")

    def test_a_row_with_no_stack_column_still_produces_a_finding(self):
        found, _ = findings.derive({"risk_admin_sprawl": [{"Admins": 9}]})
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0]["stack"])

    def test_detail_carries_the_named_fields_and_omits_the_stack(self):
        found, _ = findings.derive(
            {"cost_cardinality_outliers": [
                {" Stack": "s", "Worst label": "pod", "Worst label values": 88000,
                 "Active series": 1, "Ignored": "x"}]}
        )
        d = found[0]["detail"]
        self.assertEqual(d["Worst label"], "pod")
        self.assertEqual(d["Worst label values"], 88000)
        self.assertNotIn("Ignored", d)      # not in the spec's fields
        self.assertNotIn(" Stack", d)       # already a top-level key


class TestRowFilters(unittest.TestCase):
    """The signal-to-noise guard. Two views are the FULL table rather than a finding set, and reporting
    every row made the feature useless in its first version: 4,964 "service account risks" against an
    estate that has 2, and 230 "cardinality outliers" including a stack with 2 active series."""

    def test_only_flagged_service_accounts_count(self):
        _, totals = findings.derive({"risk_service_accounts": sa_view(flagged=2, unflagged=4962)})
        self.assertEqual(totals["service_account_risk"], 2)

    def test_an_all_extsvc_inventory_yields_no_findings(self):
        """4,458 of the estate's service accounts are Grafana's own auto-provisioned accounts."""
        _, totals = findings.derive({"risk_service_accounts": sa_view(flagged=0, unflagged=100)})
        self.assertEqual(totals["service_account_risk"], 0)

    def test_cardinality_below_the_threshold_is_not_a_finding(self):
        """p50 of that view's worst-label values is 33. Without a floor, nearly every stack is an
        'outlier'."""
        _, totals = findings.derive({"cost_cardinality_outliers": cardinality_view(50, worst=33)})
        self.assertEqual(totals["cardinality_outlier"], 0)

    def test_cardinality_at_or_above_the_threshold_is_a_finding(self):
        _, low = findings.derive({"cost_cardinality_outliers": cardinality_view(3, worst=4_999)})
        _, at = findings.derive({"cost_cardinality_outliers": cardinality_view(3, worst=5_000)})
        self.assertEqual(low["cardinality_outlier"], 0)
        self.assertEqual(at["cardinality_outlier"], 3)

    def test_a_missing_or_non_numeric_threshold_field_does_not_match(self):
        """A view that changes shape must under-report rather than crash or over-report."""
        _, totals = findings.derive({"cost_cardinality_outliers": [
            {" Stack": "a"}, {" Stack": "b", "Worst label values": None},
            {" Stack": "c", "Worst label values": "lots"}]})
        self.assertEqual(totals["cardinality_outlier"], 0)

    def test_filtered_kinds_still_report_zero_rather_than_vanishing(self):
        """Filtered to nothing is a measured zero - the view WAS computable. Absence is reserved for a
        view the tier could not produce at all."""
        _, totals = findings.derive({"risk_service_accounts": sa_view(0, 10)})
        self.assertIn("service_account_risk", totals)

    def test_already_filtered_views_are_left_alone(self):
        """`risk_fleet_dead` is filtered upstream - every row has FM dead=True. A filter here would be a
        second, divergent definition."""
        for kind in ("fleet_dead_collector", "admin_sprawl", "adaptive_headroom", "plugin_drift"):
            spec = next(s for s in findings.SPECS if s.kind == kind)
            with self.subTest(kind=kind):
                self.assertEqual(spec.require, ())
                self.assertEqual(spec.at_least, ())


class TestContract(unittest.TestCase):
    def test_kinds_are_unique(self):
        """The metric is keyed on kind, so a duplicate would make one finding overwrite another."""
        self.assertEqual(len(findings.KINDS), len(set(findings.KINDS)))

    def test_every_spec_has_a_known_severity(self):
        for spec in findings.SPECS:
            with self.subTest(kind=spec.kind):
                self.assertIn(spec.severity, findings.SEVERITIES)

    def test_every_spec_explains_why_it_matters(self):
        """A finding a reader cannot act on is noise. The summary is what makes it actionable."""
        for spec in findings.SPECS:
            with self.subTest(kind=spec.kind):
                self.assertGreater(len(spec.summary), 40)

    def test_the_idle_leftover_finding_still_says_it_is_worth_nothing(self):
        """This exact finding was once briefed as a saving. It is a governance finding worth £0 and the
        correction must travel with the data, not just live in a document."""
        spec = next(s for s in findings.SPECS if s.kind == "leftover_stack_idle")
        self.assertIn("£0", spec.summary)
        self.assertIn("aving", spec.summary)  # "saving" / "Never present it as a saving"


class TestLokiIntegration(unittest.TestCase):
    def test_findings_pass_the_loki_stream_label_guard(self):
        """`pillar` becomes a stream label; `stack` must stay in the body. Putting stack in a stream would
        create 271 streams per event type - the same mistake the metric guard exists to prevent."""
        found, _ = findings.derive({"risk_admin_sprawl": view(3)})
        events = loki.finding_events("t2", found)

        self.assertEqual(len(events), 3)
        for labels, body in events:
            self.assertLessEqual(set(labels), loki.STREAM_LABELS)
            self.assertNotIn("stack", labels)
            self.assertIn("stack", body)
            self.assertEqual(labels["event"], "finding")

    def test_every_derived_pillar_is_a_valid_stream_value(self):
        payload = {}
        for spec in findings.SPECS:
            if spec.view == "cost_cardinality_outliers":
                payload[spec.view] = cardinality_view(1)
            elif spec.view == "risk_service_accounts":
                payload[spec.view] = sa_view(1, 0)
            else:
                payload[spec.view] = view(1)
        found, _ = findings.derive(payload)
        pillars = {f["pillar"] for f in found}
        self.assertTrue(pillars <= set("ABCDEFI"), pillars)


class TestBudget(unittest.TestCase):
    def test_the_findings_metric_is_declared_in_the_catalogue(self):
        """Every emitted metric must be declared or the budget stops meaning anything."""
        from collector.emit import budget
        names = {s.name for s in budget.CATALOGUE}
        self.assertIn("gcinsight_findings", names)

    def test_the_declared_cardinality_covers_every_kind(self):
        from collector.emit import budget
        spec = next(s for s in budget.CATALOGUE if s.name == "gcinsight_findings")
        self.assertGreaterEqual(spec.labels["kind"], len(findings.KINDS))


if __name__ == "__main__":
    unittest.main()
