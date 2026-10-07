"""The series budget is only worth having if it cannot drift from what the pillars emit (PLAN 0.12)."""

from __future__ import annotations

import ast
import contextlib
import copy
import datetime as dt
import io
import json
import os
import socket
import subprocess
import pathlib
import unittest
from unittest import mock
from types import SimpleNamespace

from collector.coverage import Coverage
from collector.emit import budget
from collector.emit.budget import (
    CATALOGUE,
    CEILING,
    MAX_PER_STACK_FANOUT,
    BadShape,
    MetricSpec,
    check_budget,
    check_shape,
    total,
)
from collector.emit.guard import ALLOWED_LABELS
from collector.pillars import compose, estate

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


class BudgetShapeTest(unittest.TestCase):
    def test_declared_catalogue_fits_the_ceiling(self):
        self.assertLessEqual(check_budget(), CEILING)

    def test_every_catalogue_label_is_in_the_guards_allow_list(self):
        """The guard is the runtime gate; the budget is the design-time one. They must agree."""
        for spec in CATALOGUE:
            for key in spec.labels:
                self.assertIn(key, ALLOWED_LABELS, f"{spec.name} declares {key!r}")

    def test_no_duplicate_name_and_label_set(self):
        seen = set()
        for spec in CATALOGUE:
            key = (spec.name, tuple(sorted(spec.labels)))
            self.assertNotIn(key, seen, f"{spec.name} declared twice with the same labels")
            seen.add(key)

    def test_per_stack_metric_may_not_carry_two_extra_labels(self):
        with self.assertRaises(BadShape):
            check_shape(MetricSpec("x", "A", {"stack": 271, "role": 3, "signal": 6}))

    def test_per_stack_fan_out_above_the_cap_is_refused(self):
        """`stack` x `kind`(10) is 2,710 series  -  half the target stack. That is a table."""
        with self.assertRaises(BadShape):
            check_shape(MetricSpec("x", "D", {"stack": 271, "kind": 10}))

    def test_the_same_fan_out_is_allowed_as_a_view(self):
        check_shape(MetricSpec("x", "D", {"stack": 271, "kind": 10}, store="view"))

    def test_a_view_contributes_nothing_to_the_series_budget(self):
        self.assertEqual(MetricSpec("x", "D", {"stack": 271, "kind": 10}, store="view").series, 0)

    def test_fan_out_cap_is_actually_binding_on_the_catalogue(self):
        """Guards against the cap being quietly raised until nothing fails."""
        self.assertLessEqual(MAX_PER_STACK_FANOUT, 4)

    def test_input_label_cardinality_tracks_the_hydration_catalogue(self):
        """Adding an input must not silently under-budget both provenance metrics."""
        from collector.emit import hydrate
        self.assertEqual(budget.INPUT, len(hydrate.INPUT_OWNER))

    def test_capability_gap_adds_only_four_estate_series_and_tracks_the_enum(self):
        from collector.pillars.coverage import ADOPTION_CAPABILITIES
        spec = next(s for s in CATALOGUE if s.name == "gcinsight_coverage_capability_gap")
        self.assertEqual(spec.labels, {"kind": 14})
        self.assertEqual(spec.series - 10, 4, "owner allowance is about five estate series")
        self.assertEqual(spec.labels["kind"], len(ADOPTION_CAPABILITIES))
        self.assertEqual(len(ADOPTION_CAPABILITIES), len(set(ADOPTION_CAPABILITIES)))
        self.assertEqual(spec.store, "mimir")

    def test_labelling_shape_is_fifteen_per_stack_plus_one_estate_version(self):
        from collector.pillars import labelling
        specs = [s for s in CATALOGUE if s.pillar == labelling.PILLAR and s.store == "mimir"]
        expected = {
            "gcinsight_labelling_findings": {"stack": budget.STACK, "severity": len(labelling.SEVERITIES)},
            "gcinsight_labelling_score": {"stack": budget.STACK, "signal": len(labelling.SIGNALS)},
            "gcinsight_labelling_rules_evaluated": {"stack": budget.STACK, "signal": len(labelling.SIGNALS)},
            "gcinsight_labelling_rules_passed": {"stack": budget.STACK, "signal": len(labelling.SIGNALS)},
            "gcinsight_labelling_catalogue_version": {},
        }
        self.assertEqual({s.name: s.labels for s in specs}, expected)
        self.assertEqual(sum(s.series for s in specs), 15 * budget.STACK + 1)
        for spec in specs:
            check_shape(spec)
        self.assertEqual({s.name for s in CATALOGUE if s.pillar == labelling.PILLAR and s.store == "view"},
                         set(labelling.VIEW_SCHEMAS))

    def test_technology_cardinality_tracks_the_registry(self):
        from collector import technology_registry
        self.assertEqual(budget.TECHNOLOGY, len(technology_registry.REGISTRY.entries))

    def test_label_cardinality_metrics_use_only_the_bounded_kind_and_stack_dimensions(self):
        declared = {spec.name: spec for spec in CATALOGUE}
        findings = declared["gcinsight_stack_label_cardinality_findings"]
        measured = declared["gcinsight_risk_label_cardinality_stacks_measured"]

        self.assertEqual(findings.labels, {"stack": budget.STACK, "kind": 2})
        self.assertEqual(measured.labels, {})
        self.assertIn("risk_label_cardinality", declared)
        self.assertEqual(declared["risk_label_cardinality"].store, "view")
        self.assertEqual(declared["risk_label_cardinality"].labels, {"stack": budget.STACK})


class BudgetBackstopTest(unittest.TestCase):
    """The budget is static; live denominators belong in a contemporaneous range query."""

    def test_the_ceiling_is_a_runaway_backstop_not_a_design_constraint(self):
        """The ceiling used to be a proportion of the write stack's own series, which made every new
        per-stack metric a negotiation. It is now high enough that only a genuine mistake trips it -
        an unbounded label that slipped the guard, or an unintended cross product.

        The protection that matters is `guard.ALLOWED_LABELS`, which is unchanged and still errors."""
        self.assertGreaterEqual(CEILING, 100_000)
        self.assertLess(total(), CEILING,
                        "the declared catalogue must still sit under the backstop")

    def test_label_discipline_is_still_enforced_even_though_the_ceiling_is_high(self):
        """A high ceiling must not become an excuse for an unbounded label."""
        from collector.emit import guard
        self.assertNotIn("dashboard", guard.ALLOWED_LABELS)
        self.assertNotIn("metric", guard.ALLOWED_LABELS)
        self.assertNotIn("user", guard.ALLOWED_LABELS)
        with self.assertRaises(guard.UnboundedLabel):
            guard.check("gcinsight_x", {"dashboard_uid": "abc"})

    def test_generated_budget_does_not_freeze_a_live_denominator(self):
        rendered = budget.render_table()
        self.assertNotIn("vs org", rendered)
        self.assertNotIn("active series of", rendered)
        self.assertIn("range query", rendered)


class CatalogueMatchesEmissionTest(unittest.TestCase):
    """A pillar that adds a label without updating the budget must fail here, not in production."""

    @classmethod
    def setUpClass(cls) -> None:
        stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
        coverage = Coverage(tier="t1", total=len(stacks))
        for s in stacks:
            if s.get("status") == "paused":
                coverage.record_skipped(str(s["slug"]), "paused")
            else:
                coverage.record_ok(str(s["slug"]))
        cls.metrics, _ = estate.build(
            stacks, coverage, now=dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc)
        )
        cls.declared = {(s.name, tuple(sorted(s.labels))): s for s in CATALOGUE if s.store == "mimir"}

    def test_every_emitted_metric_is_declared_in_the_budget(self):
        for name, labels, _ in self.metrics:
            key = (name, tuple(sorted(labels)))
            self.assertIn(key, self.declared,
                          f"{name}{sorted(labels)} is emitted but not declared in CATALOGUE")

    def test_actual_series_never_exceed_the_declared_cardinality(self):
        actual: dict[tuple, int] = {}
        for name, labels, _ in self.metrics:
            key = (name, tuple(sorted(labels)))
            actual[key] = actual.get(key, 0) + 1
        for key, count in actual.items():
            spec = self.declared[key]
            self.assertLessEqual(count, spec.series,
                                 f"{spec.name} emitted {count} series, budget declares {spec.series}")

    def test_pillar_a_plus_scan_health_is_a_small_share_of_the_whole_budget(self):
        """Phase 1's implemented half should be well inside the ceiling, leaving room for B-F."""
        self.assertLess(len(self.metrics), CEILING * 0.1)


class EveryPillarsEmissionIsDeclaredTest(unittest.TestCase):
    """The same guard as above, but over EVERY pillar rather than Pillar A alone.

    The class above builds only `estate.build`, so a metric name or label shape introduced by any other
    pillar was never checked against `CATALOGUE`  -  the exact class of error the budget guard exists to
    catch, and it would ship silently because an undeclared metric simply never appears in `BUDGET.md`.
    Found while adding Pillar I.

    Uses `tests/fixtures/compose_inputs.json`, which carries real `dataplane`, `stack_detail`,
    `access_policies` and `assistant` payloads, because a synthetic stack does not exercise the branches
    that emit most of these series. Skips if the fixture is absent  -  but then this guard is not running,
    so regenerate it with `bin/make_compose_fixture.py`.
    """

    @classmethod
    def setUpClass(cls) -> None:
        fixture = pathlib.Path(__file__).parent / "fixtures" / "compose_inputs.json"
        if not fixture.exists():
            raise unittest.SkipTest("compose_inputs.json absent; run bin/make_compose_fixture.py")
        data = json.loads(fixture.read_text())
        stacks = cls.stacks = data["stacks"]
        coverage = Coverage(tier="t2", total=len(stacks))
        for i in range(data["scanned"]):
            coverage.record_ok(f"s{i}")
        cls.metrics, cls.views, _ = compose.build_all(
            stacks, coverage,
            dataplane=data.get("dataplane"), stack_detail=data.get("stack_detail"),
            access_policies=data.get("access_policies"), assistant=data.get("assistant"),
            dashboard_inventory=data.get("dashboard_inventory"),
            alert_routing=data.get("alert_routing"),
            signal_inventory=data.get("signal_inventory"),
            now=dt.datetime(2026, 8, 20, tzinfo=dt.timezone.utc),
        )
        cls.declared = {(s.name, tuple(sorted(s.labels))): s for s in CATALOGUE if s.store == "mimir"}

    def test_every_emitted_metric_of_every_pillar_is_declared(self):
        for name, labels, _ in self.metrics:
            key = (name, tuple(sorted(labels)))
            self.assertIn(key, self.declared,
                          f"{name}{sorted(labels)} is emitted but not declared in CATALOGUE")

    def test_composed_samples_conform_without_defining_the_vocabulary(self):
        unresolved = budget.check_runtime_metrics(self.metrics, inventory=self.stacks)
        self.assertEqual(unresolved, {("gcinsight_ai_estate_messages", "category"),
                                      ("gcinsight_ai_estate_messages", "surface")})

    def test_every_pillar_i_view_is_declared(self):
        """Scoped to Pillar I on purpose, and this is a note about the rest.

        `CATALOGUE`'s view half is a DECISION RECORD  -  "this is per-stack detail, here is why it is a
        table rather than a metric"  -  not an inventory of every view. Around twenty older views are
        published without an entry, `estate_drift` among them, and requiring one for all of them is a
        contract this project never adopted. Every Pillar I view carries one because each was a fresh
        decision, and this asserts that rather than quietly widening the rule.
        """
        declared = {s.name for s in CATALOGUE if s.store == "view"}
        published = {n for n in self.views if n.startswith("ai_")}
        self.assertTrue(published)
        self.assertLessEqual(published, declared, sorted(published - declared))

    def test_pillar_i_really_is_exercised_by_this_fixture(self):
        """Otherwise the guard above passes by covering nothing, which is how it read before."""
        names = {n for n, _, _ in self.metrics}
        self.assertIn("gcinsight_ai_messages", names)
        self.assertIn("gcinsight_ai_estate_messages", names)
        self.assertIn("gcinsight_stacks_missing_credential", names)
        self.assertTrue(any(n.startswith("ai_") for n in self.views))


class RenderTest(unittest.TestCase):
    def test_committed_budget_is_generated_from_the_catalogue(self):
        document = pathlib.Path(__file__).resolve().parent.parent / "BUDGET.md"
        with mock.patch.dict("os.environ", {"GCINSIGHT_METRIC_PREFIX": "gcinsight"}):
            self.assertEqual(document.read_text(), budget.render_table() + "\n")

    def test_table_uses_the_configured_external_metric_identity(self):
        with mock.patch.dict("os.environ", {"GCINSIGHT_METRIC_PREFIX": "customer_insight"}):
            table = budget.render_table()
        self.assertIn("`customer_insight_estate_stacks`", table)
        self.assertNotIn("`gcinsight_estate_stacks`", table)

    def test_table_renders_and_names_the_target_stack_denominator_rule(self):
        table = budget.render_table()
        self.assertIn("org total is never the denominator", table)
        self.assertIn(f"{total():,}", table)
        # Every mimir metric appears as a row.
        for spec in CATALOGUE:
            self.assertIn(f"`{spec.name}`", table)


def assert_runtime_reserves_absent(metrics):
    # Project the reserved dimension: adding another bounded label must not hide
    # an emitted reserved tier from the exact-combination contract.
    emitted = {(name, (("tier", str(labels["tier"])),)) for name, labels, _ in metrics
               if "tier" in labels}
    violations = emitted & budget.RUNTIME_RESERVES.keys()
    if violations:
        raise AssertionError(f"reserved selector emitted: {sorted(violations)}")


class RuntimeReserveTest(unittest.TestCase):
    """Observe full transitive output, not merely carry reporter callsite topology.

    Real dispatched runners, composer, hydration, findings, provenance and generic
    label guard stay active. Only existing upstream/destination seams are replaced.
    These synthetic observations complement source contracts; they are not lifetime
    absence or exhaustive input-state proof. No actual destinations are written.
    """

    def exercise(self, tier, baseline=True, seed=None, shared_seed=False):
        import scan
        from collector.emit import hydrate
        from tests.test_scan import cfg_for, LabelInventoryProcessEdgeTest
        with contextlib.ExitStack() as patches:
            patches.enter_context(mock.patch("socket.create_connection", side_effect=AssertionError("network prohibited")))
            patches.enter_context(mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network prohibited")))
            patches.enter_context(mock.patch.object(subprocess, "run", side_effect=AssertionError("AWS/process prohibited")))
            if tier == "t2":
                result = LabelInventoryProcessEdgeTest().exercise(enabled=False)
                self.assertEqual(result["code"], 0, result["stderr"])
                self.assertTrue(result["scans"][0]["_emit"]["metrics"])
                return result["metrics"]
            fixture = json.loads((TESTDATA.parent / "tests/fixtures/compose_inputs.json").read_text())
            now = dt.datetime.now(dt.timezone.utc)
            snapshot = {"meta": {"generated_at": now.isoformat(), "inputs": {
                name: {"schema_version": hydrate.INPUT_SCHEMA_VERSION[name]} for name in hydrate.INPUT_OWNER}},
                "data": fixture}
            cfg = cfg_for(tier)
            client = SimpleNamespace(attempts=SimpleNamespace(requests=0, retries=0, by_status={}))
            captured, runner_metrics, runner_views = [], [], []
            real_hydrate, real_compose = hydrate.hydrate, scan.compose.build_all
            real_report, real_runner = hydrate.report_metrics, getattr(scan, f"run_{tier}")

            def probe(_client, _cap, selected, coverage, **_kwargs):
                for stack in selected:
                    if stack.get("status") == "paused":
                        coverage.record_skipped(str(stack["slug"]), "paused")
                    else:
                        coverage.record_ok(str(stack["slug"]))
                return copy.deepcopy(fixture["dataplane"])

            def compose(*args, **kwargs):
                metrics, views, cov = real_compose(*args, **kwargs)
                if seed and not shared_seed:
                    metrics.append(seed)
                return metrics, views, cov

            def runner(*args):
                result = real_runner(*args)
                runner_metrics.extend(result.get("_emit", {}).get("metrics", []))
                runner_views.extend(result.get("_emit", {}).get("views", {}))
                return result

            def report(*args):
                metrics = real_report(*args)
                if seed and shared_seed:
                    metrics.append(seed)
                return metrics

            def push(metrics):
                captured.extend(metrics)
                return len(metrics)

            histories = [(f"scans/t3/synthetic-{hours}.json", now - dt.timedelta(hours=hours))
                         for hours in ((0, 24, 168) if baseline else (0,))]
            patches.enter_context(mock.patch.dict(os.environ, {"GCINSIGHT_READER_PRODUCT_READS": ""}))
            for obj, name, kwargs in (
                (scan.gcom, "fetch_inventory", {"return_value": copy.deepcopy(fixture["stacks"])}),
                (scan.dataplane, "probe_all", {"side_effect": probe}),
                (hydrate, "hydrate", {"side_effect": lambda *a, **kw: real_hydrate(*a, loader=lambda *_: snapshot, **kw)}),
                (scan, "load_ratecard", {"return_value": None}),
                (scan, "assistant_gaps", {"return_value": {}}),
                (scan.compose, "build_all", {"side_effect": compose}),
                (hydrate, "report_metrics", {"side_effect": report}),
                (scan, f"run_{tier}", {"side_effect": runner}),
                (scan.diff, "list_scans", {"return_value": histories}),
                (scan.diff, "load_scan", {"return_value": snapshot}),
                (scan.s3emit, "write_views", {"return_value": []}),
                (scan.s3emit, "write_scan", {"return_value": []}),
                (scan.mimir.RemoteWriter, "push", {"side_effect": push}),
                (scan.loki.LokiWriter, "push", {"side_effect": lambda events: len(events)}),
            ):
                patches.enter_context(mock.patch.object(obj, name, **kwargs))
            patches.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stderr = patches.enter_context(contextlib.redirect_stderr(io.StringIO()))
            self.assertEqual(scan.run(client, cfg, SimpleNamespace(out=None)), 0, stderr.getvalue())
            if tier == "t4":
                self.assertEqual(runner_metrics, [])
                self.assertEqual(len(runner_views), 2 if baseline else 0)
            else:
                self.assertTrue(runner_metrics)
            self.assertTrue(captured, "must observe final Mimir push, not an empty proxy")
            return captured

    def test_exact_reserves_match_source_backed_dispatch_populations(self):
        expected = {(metric, (("tier", tier),)) for metric in
                    ("gcinsight_carry_forward_series", "gcinsight_carry_forward_age_seconds")
                    for tier in ("t2", "t3", "t4")}
        expected.update({(metric, (("tier", "t4"),)) for metric in
                         ("gcinsight_scan_coverage_ratio", "gcinsight_scan_stacks_total",
                          "gcinsight_scan_stacks_scannable", "gcinsight_scan_stacks_scanned")})
        self.assertEqual(set(budget.RUNTIME_RESERVES), expected)
        for tier, baseline in (("t2", True), ("t3", True), ("t4", True), ("t4", False)):
            with self.subTest(tier=tier, baseline=baseline):
                metrics = self.exercise(tier, baseline)
                assert_runtime_reserves_absent(metrics)
                self.assertIn(("gcinsight_scan_completed_timestamp_seconds", {"tier": tier}),
                              [(name, labels) for name, labels, _ in metrics])
                if tier != "t4":
                    for metric in ("gcinsight_scan_stacks_total", "gcinsight_scan_stacks_scannable",
                                   "gcinsight_scan_stacks_scanned", "gcinsight_scan_coverage_ratio"):
                        self.assertTrue(any(n == metric and labels == {"tier": tier} for n, labels, _ in metrics))
                else:
                    self.assertEqual({n for n, _, _ in metrics},
                                     {"gcinsight_scan_completed_timestamp_seconds", "gcinsight_scan_duration_seconds"})

    def test_reserve_violation_seed_observes_composer_and_shared_publication_output(self):
        for tier, metric, shared in (("t3", "gcinsight_carry_forward_age_seconds", False),
                                     ("t4", "gcinsight_scan_stacks_scanned", True)):
            metrics = self.exercise(tier, seed=(metric, {"tier": tier}, 1.0), shared_seed=shared)
            with self.assertRaisesRegex(AssertionError, metric):
                assert_runtime_reserves_absent(metrics)
        # Every exact key independently rejected, never a family-wide exemption.
        metrics = self.exercise("t3")
        for (name, labels) in budget.RUNTIME_RESERVES:
            for extra in ({}, {"region": "synthetic"}):
                with self.subTest(name=name, labels=labels, extra=extra):
                    with self.assertRaisesRegex(AssertionError, name):
                        assert_runtime_reserves_absent([*metrics, (name, {**dict(labels), **extra}, 1.0)])


class RuntimeDomainTest(unittest.TestCase):
    """Contract checks are offline proof tools, NOT publisher enforcement."""

    def test_fixed_values_and_unused_headroom_do_not_become_runtime_data(self):
        domains = budget.runtime_domains()
        self.assertEqual(domains[("gcinsight_ai_estate_stacks", "kind")].values,
                         ("measured", "with_usage", "with_tenant_config"))
        self.assertEqual(domains[("gcinsight_dashboards_views", "version")].values, ("2",))
        self.assertEqual(domains[("gcinsight_coverage_service_completeness_mean", "version")].values,
                         ("4",))
        for name, labels in (
            ("gcinsight_ai_estate_stacks", {"kind": "spare"}),
            ("gcinsight_dashboards_views", {"stack": "live", "version": "1"}),
            ("gcinsight_cost_usage_by_signal", {"signal": "alerts"}),
        ):
            with self.subTest(name=name, labels=labels):
                with self.assertRaisesRegex(budget.RuntimeDomainError, name):
                    budget.check_runtime_metrics([(name, labels, 0)], inventory=[{"slug": "live"}])

    def test_unknown_domains_preclude_exhaustive_conformance(self):
        unknown = {pair for pair, domain in budget.runtime_domains().items() if domain.kind == "unknown"}
        expected = {("gcinsight_ai_estate_messages", "category"),
                    ("gcinsight_ai_estate_messages", "surface"),
                    ("gcinsight_scan_stacks_failed", "reason")}
        self.assertEqual(unknown, expected)
        unresolved = budget.check_runtime_metrics([
            ("gcinsight_ai_estate_messages", {"category": "NovelCategory", "surface": "NovelSurface"}, 1),
            ("gcinsight_scan_stacks_failed", {"tier": "t2", "reason": "NovelShortError"}, 1),
        ])
        self.assertEqual(unresolved, expected, "passing open values is NOT exhaustive conformance")


    def test_each_fixed_dimension_rejects_unsupported_values_and_shapes(self):
        domains, relations = budget.runtime_domains(), budget.runtime_relations()
        inventory = [{"slug": "live", "regionSlug": "new-region"}]
        for spec in CATALOGUE:
            if spec.store != "mimir":
                continue
            labels = {key: (domain.values[0] if domain.kind == "fixed" else
                            "live" if key == "stack" else "new-region" if key == "region" else "open")
                      for key in spec.labels for domain in (domains[(spec.name, key)],)}
            if spec.name in relations:
                labels.update(dict(relations[spec.name][0]))
            budget.check_runtime_metrics([(spec.name, labels, 1)], inventory=inventory)
            for key in spec.labels:
                if domains[(spec.name, key)].kind != "fixed":
                    continue
                with self.subTest(metric=spec.name, label=key):
                    for seed in ("unsupported_new_value", 1):
                        with self.assertRaisesRegex(budget.RuntimeDomainError, spec.name):
                            budget.check_runtime_metrics([(spec.name, {**labels, key: seed}, 1)], inventory=inventory)
            for seed in ({**labels, "unexpected_dimension": "new"},
                         {key: value for key, value in labels.items() if key != next(iter(labels), None)}):
                if seed == labels:
                    continue
                with self.subTest(metric=spec.name, shape=seed):
                    with self.assertRaisesRegex(budget.RuntimeDomainError, spec.name):
                        budget.check_runtime_metrics([(spec.name, seed, 1)], inventory=inventory)
        with self.assertRaisesRegex(budget.RuntimeDomainError, "undeclared_metric"):
            budget.check_runtime_metrics([("undeclared_metric", {}, 1)])

    def test_restricted_combinations_and_exact_reserves_reject_negative_seeds(self):
        relations = budget.runtime_relations()
        # Generate the rectangular negative population through the resource-bounded
        # proof helper, not an unbounded product inside a data-sized test generator.
        with mock.patch.object(budget, "runtime_relations", return_value={}):
            rectangular, _unknown = budget.runtime_requirements()
        for name, labels in rectangular:
            if name in relations and labels not in relations[name]:
                with self.subTest(metric=name, labels=labels):
                    with self.assertRaisesRegex(budget.RuntimeDomainError, "unsupported runtime relation"):
                        budget.check_runtime_metrics([(name, dict(labels), 1)])
        for name, labels in budget.RUNTIME_RESERVES:
            with self.subTest(metric=name, reserved=labels):
                with self.assertRaisesRegex(budget.RuntimeDomainError, name):
                    budget.check_runtime_metrics([(name, dict(labels), 1)])

    def test_capacity_inflation_does_not_invent_vocabularies_or_obligations(self):
        import dataclasses
        before = budget.runtime_requirements()
        expanded = tuple(dataclasses.replace(s, labels={k: n + 10 for k, n in s.labels.items()}) for s in CATALOGUE)
        with mock.patch.object(budget, "CATALOGUE", expanded):
            self.assertEqual(budget.runtime_requirements(), before)
        for spec in CATALOGUE:
            if spec.store == "mimir":
                for key, capacity in spec.labels.items():
                    domain = budget.runtime_domains()[(spec.name, key)]
                    if domain.kind == "fixed":
                        self.assertLessEqual(len(domain.values), capacity, (spec.name, key))

    def test_new_producer_constant_extends_obligations_and_old_conformance_refuses_it(self):
        from collector.pillars import usage
        before, _ = budget.runtime_requirements()
        old_domains = budget.runtime_domains()
        with mock.patch.dict(usage.SIGNAL_FIELDS, {"new_signal": "new_usage_field"}):
            after, _ = budget.runtime_requirements()
            for name in ("gcinsight_usage_stacks_by_signal", "gcinsight_value_adoption_ratio"):
                self.assertIn((name, (("signal", "new_signal"),)), after - before)
            emitted, _ = usage.build([{"slug": "live", "new_usage_field": 2000}], Coverage("t1", 1))
            new_sample = [m for m in emitted if m[0] == "gcinsight_usage_stacks_by_signal" and m[1]["signal"] == "new_signal"]
            self.assertEqual(len(new_sample), 1, "observe the real emission loop, not a constructed sample")
            self.assertEqual(budget.check_runtime_metrics(new_sample), set())
            with mock.patch.object(budget, "runtime_domains", return_value=old_domains):
                with self.assertRaisesRegex(budget.RuntimeDomainError, "new_signal"):
                    budget.check_runtime_metrics(new_sample)

    def test_live_identity_domains_follow_inventory_changes_not_capacity_rosters(self):
        from collector.pillars import estate
        for slug, region in (("first", "new-one"), ("second", "new-two")):
            inventory = [{"slug": slug, "regionSlug": region}]
            metrics, _ = estate.build(inventory, Coverage("t1", 1))
            self.assertEqual(budget.check_runtime_metrics(metrics, inventory=inventory), set())
            region_sample = next(m for m in metrics if m[0] == "gcinsight_estate_stacks_by_region")
            self.assertEqual(region_sample[1], {"region": region})
            self.assertEqual(budget.check_runtime_metrics([region_sample], inventory=[]),
                             {(region_sample[0], "region")}, "empty discovery remains unknown")
        with self.assertRaisesRegex(budget.RuntimeDomainError, "unsupported region"):
            budget.check_runtime_metrics([region_sample], inventory=[{"slug": "first", "regionSlug": "new-one"}])
        with self.assertRaisesRegex(budget.RuntimeDomainError, "unsupported stack"):
            budget.check_runtime_metrics([("gcinsight_stack_active_series", {"stack": "departed"}, 1)],
                                         inventory=inventory)


class ProducerDomainWitnessTest(unittest.TestCase):
    """Source-site witnesses reject literal drift independently of budget declarations.

    AST reads are scoped to producer build functions/calls, not consumer queries or
    broad string searches. Constant-backed domains also get real emission readbacks.
    """

    def tree(self, path, function="build"):
        module = ast.parse((TESTDATA.parent / path).read_text())
        return next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == function)

    def literal_labels(self, tree, metric, key):
        values = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Tuple) and len(node.elts) == 3 and
                isinstance(node.elts[0], ast.Constant) and node.elts[0].value == metric and
                isinstance(node.elts[1], ast.Dict)):
                for label, value in zip(node.elts[1].keys, node.elts[1].values):
                    if isinstance(label, ast.Constant) and label.value == key and isinstance(value, ast.Constant):
                        values.add(value.value)
        return values

    def loop_keys(self, tree, target):
        loop = next(n for n in ast.walk(tree) if isinstance(n, ast.For) and
                    isinstance(n.target, ast.Tuple) and isinstance(n.target.elts[0], ast.Name) and
                    n.target.elts[0].id == target and isinstance(n.iter, ast.Tuple))
        return {ast.literal_eval(item.elts[0]) for item in loop.iter.elts}

    def test_closed_literal_sites_match_contract_not_fixture_occupancy(self):
        domains = budget.runtime_domains()
        for path, name, key in (
            ("collector/pillars/ai.py", "gcinsight_ai_estate_stacks", "kind"),
            ("collector/pillars/estate.py", "gcinsight_estate_stacks", "status"),
            ("collector/pillars/estate.py", "gcinsight_estate_test_leftover_stacks", "kind"),
            ("collector/pillars/cost.py", "gcinsight_adaptive_recommendations", "status"),
        ):
            with self.subTest(metric=name):
                self.assertEqual(set(domains[(name, key)].values), self.literal_labels(self.tree(path), name, key))
        for path, target, name, key in (
            ("collector/pillars/estate.py", "kind", "gcinsight_estate_feature_stacks", "kind"),
            ("collector/pillars/estate.py", "role", "gcinsight_estate_users_by_role", "role"),
        ):
            self.assertEqual(set(domains[(name, key)].values), self.loop_keys(self.tree(path), target))
        tree = self.tree("collector/pillars/maturity.py")
        self.assertEqual(set(domains[("gcinsight_maturity_percentile", "kind")].values),
                         self.literal_labels(tree, "gcinsight_maturity_percentile", "kind") | self.loop_keys(tree, "kind"))
        tree = self.tree("collector/pillars/insights.py")
        self.assertEqual(set(domains[("gcinsight_dashboards_estate_stacks", "kind")].values),
                         self.literal_labels(tree, "gcinsight_dashboards_estate_stacks", "kind") | self.loop_keys(tree, "kind"))

    def test_coverage_literal_populations_match_real_producer_initializers(self):
        domains = budget.runtime_domains()
        tree = self.tree("collector/pillars/coverage.py")
        for variable, name in (
            ("signal_counts", "gcinsight_coverage_services_by_signal"),
            ("instrumentation_stacks", "gcinsight_coverage_instrumentation_stacks"),
            ("technology_count_distribution", "gcinsight_coverage_stacks_by_technology_count"),
            ("classified_counts", "gcinsight_coverage_metric_names"),
            ("identity_counts", "gcinsight_coverage_service_identity"),
            ("population_counts", "gcinsight_coverage_service_population"),
            ("depth_counts", "gcinsight_coverage_services_by_depth"),
        ):
            assignment = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign) and
                              any(isinstance(t, ast.Name) and t.id == variable for t in n.targets))
            expr = assignment.value
            if isinstance(expr, ast.Dict):
                values = {ast.literal_eval(key) for key in expr.keys}
            else:
                iterable = expr.generators[0].iter
                values = (set(map(str, range(*[ast.literal_eval(a) for a in iterable.args])))
                          if isinstance(iterable, ast.Call) else set(ast.literal_eval(iterable)))
            with self.subTest(variable=variable):
                self.assertEqual(set(domains[(name, "kind")].values), values)

    def test_skip_sources_and_tier_dispatch_witnesses(self):
        import scan
        from collector.sources import gcom, dataplane
        from tests.test_scan import cfg_for
        reasons = {}
        for tier, path, function in (("t1", "scan.py", "run_t1"),
                                     ("t2", "collector/sources/gcom.py", "fetch_all_stack_detail"),
                                     ("t3", "collector/sources/dataplane.py", "probe_all")):
            tree = self.tree(path, function)
            reasons[tier] = {ast.literal_eval(n.args[1]) for n in ast.walk(tree)
                             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                             and n.func.attr == "record_skipped"}
        expected = {(("reason", reason), ("tier", tier)) for tier, values in reasons.items() for reason in values}
        self.assertEqual(set(budget.runtime_relations()["gcinsight_scan_stacks_skipped"]), expected)
        self.assertEqual(scan.TIERS, ("t1", "t2", "t3", "t4"))
        # Inspect real t1 output while replacing only existing upstream/state seams.
        inventory = [{"slug": "paused", "status": "paused"}, {"slug": "active", "status": "active"}]
        client = SimpleNamespace(attempts=SimpleNamespace(requests=0, retries=0))
        with contextlib.ExitStack() as patches:
            for obj, name, value in ((gcom, "fetch_inventory", inventory), (gcom, "fetch_access_policies", []),
                                     (gcom, "fetch_org_members", {"state": "ok", "members": []}),
                                     (scan, "gather_fleet", ({}, [])), (scan, "load_ratecard", None),
                                     (scan, "assistant_gaps", {}), (scan.hydrate, "hydrate", ({}, {}))):
                patches.enter_context(mock.patch.object(obj, name, return_value=value))
            patches.enter_context(mock.patch.object(scan.carry, "load_state", side_effect=scan.carry.StateUnavailable("synthetic")))
            patches.enter_context(mock.patch.object(socket.socket, "connect", side_effect=AssertionError("no network")))
            patches.enter_context(mock.patch.object(subprocess, "run", side_effect=AssertionError("no process/AWS")))
            patches.enter_context(contextlib.redirect_stderr(io.StringIO()))
            result = scan.run_t1(client, cfg_for("t1"))
        metrics = result["_emit"]["metrics"]
        self.assertEqual(budget.check_runtime_metrics(metrics, inventory=inventory), set())
        skips = [labels for name, labels, _ in metrics if name == "gcinsight_scan_stacks_skipped"]
        self.assertEqual(skips, [{"tier": "t1", "reason": "paused"}])
        # Existing full t2/t3/t4 publication witnesses remain active, not AST-only absence.
        for tier in ("t2", "t3", "t4"):
            metrics = RuntimeReserveTest().exercise(tier)
            unresolved = budget.check_runtime_metrics(metrics)  # inventory withheld: identities stay unknown
            self.assertTrue(all(budget.runtime_domains()[pair].kind != "fixed" for pair in unresolved))

    def test_all_current_versions_are_producer_symbols_not_budget_integers(self):
        from collector import observability_score
        from collector.pillars import insights, maturity
        domains = budget.runtime_domains()
        expected = {"D": maturity.RUBRIC_VERSION, "J": insights.METRIC_EPOCH, "K": observability_score.VERSION}
        versions = [(s.name, domains[(s.name, "version")]) for s in CATALOGUE
                    if s.store == "mimir" and "version" in s.labels]
        self.assertEqual(len(versions), 31, "24 J, five maturity and two service-score declarations")
        for spec in CATALOGUE:
            if spec.store == "mimir" and "version" in spec.labels:
                self.assertEqual(domains[(spec.name, "version")].values, (expected[spec.pillar],))
        for path, symbol in (("collector/pillars/maturity.py", "RUBRIC_VERSION"),
                             ("collector/pillars/coverage.py", "observability_score.VERSION")):
            matches = []
            for node in ast.walk(self.tree(path)):
                if isinstance(node, ast.Dict):
                    for key, val in zip(node.keys, node.values):
                        if isinstance(key, ast.Constant) and key.value == "version":
                            matches.append(ast.unparse(val))
            self.assertTrue(matches)
            self.assertEqual(set(matches), {symbol})
        tree = self.tree("collector/pillars/insights.py")
        epochs = [n for n in ast.walk(tree) if isinstance(n, ast.Dict) and any(
            isinstance(key, ast.Constant) and key.value == "version" for key in n.keys)]
        self.assertEqual(len(epochs), 1, "single transitive version attachment seam")
        self.assertEqual(ast.unparse(epochs[0].values[-1]), "METRIC_EPOCH")
        with mock.patch.object(insights, "METRIC_EPOCH", "next"):
            metrics, _ = insights.build([{"slug": "live"}], Coverage("t2", 1), {})
            self.assertTrue(metrics)
            self.assertEqual({labels["version"] for _, labels, _ in metrics}, {"next"})
            self.assertEqual(budget.check_runtime_metrics(metrics), set())
            required, _ = budget.runtime_requirements()
            self.assertIn(("gcinsight_dashboards_estate_stacks", (("kind", "measured"), ("version", "next"))), required)


class RetiredCatalogueTest(unittest.TestCase):
    def test_retired_public_dashboard_scalar_is_not_active_capacity(self):
        name = "gcinsight_risk_public_dashboards_total"
        self.assertNotIn(name, {s.name for s in CATALOGUE})
        self.assertIn(name, budget.RETIRED_METRICS)
        self.assertIn("## Retired metrics", budget.render_table())
        for replacement in ("measured", "enumerated", "enabled", "stacks"):
            self.assertIn(f"gcinsight_risk_public_dashboards_{replacement}", {s.name for s in CATALOGUE})


if __name__ == "__main__":
    unittest.main()
