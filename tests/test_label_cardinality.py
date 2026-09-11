"""Key-only unbounded-cardinality classification and Pillar E composition."""

from __future__ import annotations

import json
import unittest

from collector import label_cardinality
from collector.coverage import Coverage
from collector.pillars import risk


class PatternArtifactTest(unittest.TestCase):
    def test_artifact_is_versioned_generic_content_with_exact_tiers(self):
        raw = json.loads(label_cardinality.PATTERN_PATH.read_text())
        self.assertIsInstance(raw["version"], int)
        self.assertGreaterEqual(raw["version"], 1)
        self.assertEqual(set(raw), {"version", "unbounded"})
        self.assertEqual(set(raw["unbounded"]), {"high", "possible"})

        high = set(raw["unbounded"]["high"])
        possible = set(raw["unbounded"]["possible"])
        self.assertEqual(high & possible, set())
        self.assertEqual(high | possible, label_cardinality.PATTERNS.patterns)
        self.assertEqual(label_cardinality.PATTERN_VERSION, raw["version"])
        for pattern in high | possible:
            self.assertNotRegex(pattern, r"^.$", "a bare single-letter pattern is too broad")
            self.assertNotRegex(pattern, r"(?:alpha|beta|left-estate)")

    def test_shipped_pattern_set_is_exact_and_possible_is_separate(self):
        expected_high = {
            "uuid", "guid", "id", "trace_id", "traceid", "span_id", "spanid",
            "request_id", "requestid", "correlation_id", "run_id", "job_id", "build_id",
            "task_id", "container_id", "pod_template_hash", "pid", "timestamp", "epoch",
            "time", "datetime", "url", "full_path", "query", "querystring", "uri",
        }
        self.assertEqual(label_cardinality.PATTERNS.high, frozenset(expected_high))
        self.assertEqual(label_cardinality.PATTERNS.possible,
                         frozenset({"path", "endpoint", "route"}))


class ClassifierTest(unittest.TestCase):
    def test_matching_is_exact_and_confidence_tiers_do_not_merge(self):
        self.assertEqual(label_cardinality.classify("trace_id"), ("unbounded", "high"))
        self.assertEqual(label_cardinality.classify("endpoint"), ("unbounded", "possible"))
        self.assertIsNone(label_cardinality.classify("trace_id_extra"))
        self.assertIsNone(label_cardinality.classify("Trace_id"))
        self.assertIsNone(label_cardinality.classify("not_endpoint"))

    def test_rows_read_only_the_key_and_numeric_cardinality_count(self):
        class NameOnlyRow(dict[str, object]):
            def get(self, key, default=None):
                if key in {"label_value", "sample", "raw_value"}:
                    raise AssertionError(f"raw label value must not be read: {key}")
                return super().get(key, default)

        rows = label_cardinality.classify_rows([
            NameOnlyRow({"label": "trace_id", "values": 120}),
            NameOnlyRow({"label": "endpoint", "values": 80}),
            NameOnlyRow({"label": "trace_id_extra", "values": 999}),
        ])
        self.assertEqual(rows, [
            {"label": "trace_id", "values": 120, "class": "unbounded", "confidence": "high"},
            {"label": "endpoint", "values": 80, "class": "unbounded", "confidence": "possible"},
        ])

    def test_malformed_matched_row_is_refused(self):
        with self.assertRaises(label_cardinality.PatternError):
            label_cardinality.classify_rows([{"label": "trace_id", "values": None}])


def _coverage(stacks: list[dict[str, object]]) -> Coverage:
    coverage = Coverage(tier="t3", total=len(stacks))
    for stack in stacks:
        coverage.record_ok(str(stack["slug"]))
    return coverage


class RiskPillarTest(unittest.TestCase):
    STACKS = [
        {"slug": "alpha", "status": "active"},
        {"slug": "beta", "status": "active"},
        {"slug": "gamma", "status": "active"},
    ]

    def test_view_schema_and_rows_disclose_mimir_top_n_and_confidence(self):
        metrics, views = risk.build(
            self.STACKS,
            _coverage(self.STACKS),
            dataplane={
                "alpha": {"cardinality": {"available": True, "top_labels": [
                    {"label": "trace_id", "values": 120},
                    {"label": "endpoint", "values": 80},
                    {"label": "service_name", "values": 999},
                ]}},
                "beta": {"cardinality": {"available": True, "top_labels": [
                    {"label": "uuid", "values": 60},
                    {"label": "route", "values": 40},
                ]}},
                "gamma": {"cardinality": {"available": False, "top_labels": [
                    {"label": "trace_id", "values": 1000},
                ]}},
                "departed": {"cardinality": {"available": True, "top_labels": [
                    {"label": "trace_id", "values": 5000},
                ]}},
            },
        )

        self.assertEqual(
            risk.VIEW_SCHEMAS["risk_label_cardinality"],
            (
                (" Stack", "string"), ("Label name", "string"), ("Label values", "number"),
                ("Class", "string"), ("Confidence", "string"), ("Signal", "string"),
                ("Top-N window", "number"),
            ),
        )
        rows = views["risk_label_cardinality"]
        self.assertEqual({row[" Stack"] for row in rows}, {"alpha", "beta"})
        self.assertEqual(
            {(row["Label name"], row["Class"], row["Confidence"]) for row in rows},
            {
                ("trace_id", "unbounded", "high"),
                ("uuid", "unbounded", "high"),
                ("endpoint", "unbounded", "possible"),
                ("route", "unbounded", "possible"),
            },
        )
        for row in rows:
            self.assertEqual(row["Signal"], "metrics")
            self.assertEqual(row["Top-N window"], label_cardinality.TOP_N)
        self.assertFalse(any(row["Label name"] == "service_name" for row in rows))
        self.assertNotIn("departed", repr(rows))
        by_metric = {(name, tuple(sorted(labels.items()))): value
                     for name, labels, value in metrics}
        self.assertEqual(
            by_metric[("gcinsight_risk_label_cardinality_stacks_measured", ())], 2.0
        )
        self.assertEqual(
            by_metric[("gcinsight_stack_label_cardinality_findings",
                       (("kind", "high_confidence"), ("stack", "alpha")))], 1.0
        )
        self.assertEqual(
            by_metric[("gcinsight_stack_label_cardinality_findings",
                       (("kind", "possible"), ("stack", "alpha")))], 1.0
        )
        self.assertEqual(
            by_metric[("gcinsight_stack_label_cardinality_findings",
                       (("kind", "high_confidence"), ("stack", "beta")))], 1.0
        )
        self.assertEqual(
            by_metric[("gcinsight_stack_label_cardinality_findings",
                       (("kind", "possible"), ("stack", "beta")))], 1.0
        )

        summary = next(
            row for row in views["risk_summary"]
            if row[" Metric"] == "Stacks measured for unbounded label cardinality"
        )
        self.assertIn("2 of 3 scannable", summary["Value"])
        self.assertIn("Mimir top 20 label names per stack", summary["Value"])

    def test_failed_reads_are_excluded_from_measured_and_do_not_clear_detail(self):
        stacks = self.STACKS[:2]
        metrics, views = risk.build(
            stacks,
            _coverage(stacks),
            dataplane={
                "alpha": {"cardinality": {"available": False}},
                "beta": {"cardinality": {"available": True, "top_labels": []}},
            },
        )
        self.assertEqual(views["risk_label_cardinality"], [])
        self.assertEqual(
            {(name, tuple(sorted(labels.items()))): value for name, labels, value in metrics}
            [("gcinsight_stack_label_cardinality_findings",
              (("kind", "high_confidence"), ("stack", "beta")))],
            0.0,
        )
        self.assertEqual(
            {(name, tuple(sorted(labels.items()))): value for name, labels, value in metrics}
            [("gcinsight_stack_label_cardinality_findings",
              (("kind", "possible"), ("stack", "beta")))],
            0.0,
        )
        summary = next(
            row for row in views["risk_summary"]
            if row[" Metric"] == "Stacks measured for unbounded label cardinality"
        )
        self.assertIn("1 of 2 scannable", summary["Value"])

    def test_no_successful_cardinality_read_withholds_the_view(self):
        _metrics, views = risk.build(
            self.STACKS[:2], _coverage(self.STACKS[:2]),
            dataplane={"alpha": {"cardinality": {"available": False}}},
        )
        self.assertNotIn("risk_label_cardinality", views)
        summary = next(
            row for row in views["risk_summary"]
            if row[" Metric"] == "Stacks measured for unbounded label cardinality"
        )
        self.assertEqual(summary["Value"], "not measured - needs a T3 cardinality scan")


if __name__ == "__main__":
    unittest.main()
