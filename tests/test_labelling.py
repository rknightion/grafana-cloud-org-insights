"""Private labelling compose contract, exercised at the real composition boundary."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import unittest

from collector import label_rules
from collector.coverage import Coverage
from collector.emit import carry, hydrate, loki
from collector.pillars import compose, findings
from collector.sources import label_inventory as source


STACKS = [{"slug": "synthetic-live", "status": "active"}]


def sample(value=0, population=1000, semantics="exact"):
    return {"value": value, "semantics": semantics, "population": population,
            "population_semantics": "exact", "label_kind": "dynamic"}


def envelope():
    """Ideal numeric seam fixture, NOT a source observation or completeness claim."""
    signals = {}
    for signal in label_rules.SIGNALS:
        inputs = {key: {"state": "complete", "reason": "none", "names_truncated": 0,
                       "values_overflow": 0, "samples": [sample()]}
                  for key, entry in label_rules.CATALOGUE.inputs.items()
                  if signal in entry["signals"] and entry["route"] == "approved"}
        signals[signal] = {"data": "present", "state": "complete", "reason": "none",
                           "window": "head" if signal == "metrics" else "24h",
                           "register": [], "register_truncated": 0, "inputs": inputs}
    return {"schema_version": 1, "signals": signals}


def register_row(name="synthetic_label_sentinel"):
    return {"name": name, "name_class": "ordinary", "name_count": 1, "scope": "label",
            "distinct_count": 20, "count_semantics": "exact", "shape_counts": {"uuid": 2},
            "series_count": 1000, "stream_count": None}


def composed(payload=None, *, stacks=None, **kwargs):
    stacks = STACKS if stacks is None else stacks
    metrics, views, _ = compose.build_all(stacks, Coverage(tier="t2", total=len(stacks)),
                                         label_inventory=payload, **kwargs)
    return [(n, l, v) for n, l, v in metrics if n.startswith("gcinsight_labelling_")], {
        n: rows for n, rows in views.items() if n.startswith("labelling_")}


class LabellingContractTest(unittest.TestCase):
    def test_private_input_reaches_shipping_compose_and_score(self):
        inputs = source.composition_inputs({"label_inventory": {STACKS[0]["slug"]: envelope()}})
        metrics, views = composed(inputs["label_inventory"])
        self.assertIn("labelling_stack_summary", views)
        score = [(labels, value) for name, labels, value in metrics
                 if name == "gcinsight_labelling_score"]
        self.assertEqual({labels["signal"] for labels, _ in score}, set(label_rules.SIGNALS))
        self.assertTrue(all(value == 100 for _, value in score))

    def test_no_input_is_absent_and_unknown_population_does_not_score(self):
        self.assertEqual(composed(), ([], {}))
        data = envelope()
        for signal in data["signals"].values():
            signal["state"], signal["reason"] = "partial", "truncated"
        data["signals"]["metrics"]["inputs"]["distinct_values"]["samples"] = [sample(99, None)]
        metrics, views = composed({"synthetic-live": data})
        self.assertFalse(any(n == "gcinsight_labelling_score" for n, _, _ in metrics))
        row = next(r for r in views["labelling_stack_summary"] if r["Signal"] == "metrics")
        self.assertIsNone(row["Score"])
        missing = next(r for r in views["labelling_findings"] if r["Rule"] == "M4")
        self.assertEqual((missing["Result"], missing["Reason"]), ("not_evaluated", "missing_input"))

    def test_metric_shapes_and_severity_escalation_keep_uncertainty(self):
        data = envelope()
        data["signals"]["metrics"]["inputs"]["distinct_values"]["samples"] = [sample(10000)]
        metrics, _ = composed({"synthetic-live": data})
        by = {(n, tuple(sorted(l.items()))): v for n, l, v in metrics}
        self.assertEqual(by[("gcinsight_labelling_findings", (("severity", "high"), ("stack", "synthetic-live")))], 1)
        self.assertFalse(any(n == "gcinsight_labelling_findings" and l["severity"] == "low" for n, l, _ in metrics),
                         "no applicable verified low rules means unknown, not a zero")
        data["signals"]["metrics"]["inputs"]["distinct_values"]["samples"] = [sample(99, None)]
        for signal in ("logs", "traces", "profiles"):
            data["signals"][signal]["data"] = "empty"
            for inp in data["signals"][signal]["inputs"].values():
                inp["samples"] = []
        metrics, _ = composed({"synthetic-live": data})
        self.assertFalse(any(n == "gcinsight_labelling_findings" and l["severity"] == "high" for n, l, _ in metrics),
                         "a cardinality rule can escalate to high; its missing evidence stays in high coverage")
        for name, labels, _ in metrics:
            self.assertNotIn("rule", labels)
            self.assertLessEqual(len(labels), 2)
            if "signal" in labels:
                self.assertIn(labels["signal"], label_rules.SIGNALS)
            if name.endswith("catalogue_version"):
                self.assertEqual(labels, {})

    def test_policy_tunables_are_forwarded_and_provenance_is_truthful(self):
        data = envelope()
        data["signals"]["metrics"]["inputs"]["distinct_values"]["samples"] = [sample(150)]
        _, baseline = composed({"synthetic-live": data})
        self.assertEqual(next(r for r in baseline["labelling_findings"] if r["Rule"] == "M4")["Result"], "fail")
        _, tuned = composed({"synthetic-live": data}, label_inventory_tunables={"thresholds": {"M4": {"warn": 200}}})
        row = next(r for r in tuned["labelling_findings"] if r["Rule"] == "M4")
        self.assertEqual(row["Result"], "pass")
        self.assertEqual(json.loads(row["Threshold provenance"])["warn"]["provenance"], "policy")
        data["signals"]["metrics"]["inputs"].pop("shape_count")
        default, _ = composed({"synthetic-live": data})
        strict, _ = composed({"synthetic-live": data}, label_inventory_tunables={"coverage_floor": 1})
        # Across four signals, medium coverage is 18/21: adequate at 0.8, not at 1.
        medium = lambda metrics: [v for n, l, v in metrics
                                  if n == "gcinsight_labelling_findings" and l["severity"] == "medium"]
        self.assertEqual(medium(default), [1])
        self.assertEqual(medium(strict), [])
        with self.assertRaises(label_rules.RuleError):
            composed({"synthetic-live": data}, label_inventory_tunables={"coverage_floor": 0.7})

    def test_missing_signal_emits_no_structural_zero_and_empty_has_schemas(self):
        from collector.pillars import labelling
        data = envelope()
        data["signals"].pop("logs")
        metrics, views = composed({"synthetic-live": data})
        self.assertFalse(any(l.get("signal") == "logs" for _, l, _ in metrics))
        for payload in data["signals"].values():
            payload["data"] = "empty"
            for inp in payload["inputs"].values():
                inp["samples"] = []
        metrics, views = composed({"synthetic-live": data})
        self.assertFalse(any("stack" in l for _, l, _ in metrics))
        self.assertEqual(views["labelling_label_register"], [])
        self.assertEqual(set(labelling.VIEW_SCHEMAS), labelling.S3_ONLY_VIEWS)
        for name, rows in views.items():
            fields = {k for k, _ in labelling.VIEW_SCHEMAS[name]}
            for row in rows:
                self.assertEqual(set(row), fields)
                self.assertEqual(row["Catalogue version"], label_rules.CATALOGUE.version)

    def test_private_register_and_sets_never_reach_events_metrics_or_diagnostics(self):
        data = envelope()
        data["signals"]["metrics"]["register"] = [register_row()]
        inventory = {"synthetic-live": {"available": True, "metric_services": ["private_service_sentinel"],
                     "log_services": [], "trace_services": [], "profile_services": [],
                     "clusters": ["private_cluster_sentinel"]}}
        metrics, views = composed({"synthetic-live": data}, signal_inventory=inventory)
        events, totals = findings.derive(views)
        serialized = json.dumps([loki.finding_events("t2", events), findings.metrics(totals), metrics])
        for sentinel in ("synthetic_label_sentinel", "private_service_sentinel", "private_cluster_sentinel"):
            self.assertNotIn(sentinel, serialized)
        self.assertFalse(any(s.view.startswith("labelling_") for s in findings.SPECS))
        self.assertEqual(events, [])
        diagnostic = source.diagnostic_scan({"data": {"label_inventory": {"synthetic-live": data}}, "views": views,
                                             "_emit": {"views": views}})
        self.assertNotIn("synthetic_label_sentinel", json.dumps(diagnostic))
        self.assertIn("synthetic_label_sentinel", json.dumps(views["labelling_label_register"]))
        self.assertNotIn("private_service_sentinel", json.dumps(views))
        self.assertNotIn("private_cluster_sentinel", json.dumps(views))
        self.assertIn("labelling_label_register", views, "diagnostic filter must not mutate S3 output")

    def test_invalid_envelope_rejected_without_reflecting_raw_input(self):
        data = envelope()
        data["signals"]["metrics"]["register"] = [register_row("sensitive@example.invalid")]
        with self.assertRaises(label_rules.RuleError) as error:
            composed({"synthetic-live": data})
        self.assertNotIn("sensitive", str(error.exception))

    def test_fresh_inventory_is_the_only_join_and_carry_drops_departed_stacks(self):
        data = {"synthetic-live": envelope(), "departed-stack": envelope()}
        data["departed-stack"]["untrusted_raw_sentinel"] = "must-not-validate-departed"
        metrics, views = composed(data)
        self.assertFalse(any(l.get("stack") == "departed-stack" for _, l, _ in metrics))
        self.assertFalse(any(r[" Stack"] == "departed-stack" for rows in views.values() for r in rows))
        self.assertEqual(composed(data, stacks=[]), ([], {}), "empty inventory is unknown, no estate gauge")
        now = dt.datetime(2026, 10, 7, tzinfo=dt.timezone.utc)
        old, _ = composed({"departed-stack": envelope()}, stacks=[{"slug": "departed-stack"}])
        state = {"tier": "t2", "generated_at": now.isoformat(), "metrics": metrics + old}
        thin, _ = composed()
        carried, report = carry.carry_forward(thin, state, now=now, live_stacks={"synthetic-live"})
        self.assertGreater(report["dropped_absent"], 0)
        self.assertFalse(any(l.get("stack") == "departed-stack" for _, l, _ in carried))

    def test_cross_signal_counts_are_set_sizes_only_and_require_both_inputs(self):
        inventory = {"synthetic-live": {"available": True, "metric_services": ["a", "b", "b"],
                     "log_services": ["b", "c"], "trace_services": [], "profile_services": [], "clusters": ["c"]}}
        _, views = composed({"synthetic-live": envelope()}, signal_inventory=inventory)
        row = next(r for r in views["labelling_cross_signal"] if r["Signal A"] == "metrics" and r["Signal B"] == "logs")
        self.assertEqual([row[k] for k in ("Services A", "Services B", "Shared services", "Union services", "Only A", "Only B", "Metric clusters")],
                         [2, 2, 1, 3, 1, 1, 1])
        self.assertNotIn("labelling_cross_signal", composed({"synthetic-live": envelope()})[1])
        self.assertNotIn("labelling_cross_signal", composed(signal_inventory=inventory)[1])

    def test_bounded_register_preserves_minimization_and_truncation(self):
        data = envelope()
        payload = data["signals"]["metrics"]
        payload["state"], payload["reason"], payload["register_truncated"] = "partial", "truncated", 1
        payload["register"] = [register_row(f"synthetic_label_{i}") for i in range(255)] + [{
            "name": None, "name_class": "pii", "name_count": 7, "scope": "label",
            "distinct_count": None, "count_semantics": "at_least", "shape_counts": {},
            "series_count": None, "stream_count": None}]
        _, views = composed({"synthetic-live": data})
        rows = views["labelling_label_register"]
        self.assertEqual(len(rows), 256)
        hidden = next(r for r in rows if r["Name class"] == "pii")
        self.assertIsNone(hidden["Label name"])
        self.assertEqual(hidden["Name count"], 7)
        self.assertIsNone(hidden["Distinct count"])
        self.assertTrue(all(r["Register truncated"] == 1 for r in rows))
        payload["register"].append(register_row("too_many"))
        with self.assertRaises(label_rules.RuleError):
            composed({"synthetic-live": data})

    def test_joint_fixture_is_private_truthful_and_hydration_withholds_missing_input(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "compose_inputs.json").read_text())
        self.assertTrue(fixture["label_inventory"])
        for data in fixture["label_inventory"].values():
            label_rules.validate_inventory(data)
        _, views = composed(fixture["label_inventory"], stacks=fixture["stacks"], signal_inventory=fixture["signal_inventory"])
        for name in views:
            kept, withheld = hydrate.filter_views({name: views[name]}, hydrate.Provenance())
            self.assertNotIn(name, kept)
            self.assertIn(name, withheld)


if __name__ == "__main__":
    unittest.main()
