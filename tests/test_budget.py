"""The series budget is only worth having if it cannot drift from what the pillars emit (PLAN 0.12)."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import unittest
from unittest import mock

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

    def test_technology_cardinality_tracks_the_registry(self):
        from collector import technology_registry
        self.assertEqual(budget.TECHNOLOGY, len(technology_registry.REGISTRY.entries))


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
        stacks = data["stacks"]
        coverage = Coverage(tier="t2", total=len(stacks))
        for i in range(data["scanned"]):
            coverage.record_ok(f"s{i}")
        cls.metrics, cls.views = compose.build_all(
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


if __name__ == "__main__":
    unittest.main()
