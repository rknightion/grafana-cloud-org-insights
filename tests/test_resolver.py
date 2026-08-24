"""Resolver tests. Every assertion here is a real regression case from `testdata/`, not a fixture
someone invented - these are the traps that actually cost time."""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.resolver import KNOWN_SIGNALS, InstanceResolver

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


def load(name: str):
    return json.loads((TESTDATA / name).read_text())


class ResolverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = load("gcom-instances-2026-08-17.json")["items"]
        cls.ids = load("ui-instance-ids.json")["data"]
        cls.pairs = load("ui-series-pairs.json")["data"]

    def setUp(self) -> None:
        self.resolver = InstanceResolver(self.stacks)

    # -- stack resolution ----------------------------------------------------------

    def test_no_cross_stack_collisions(self):
        """The property that makes stack resolution unambiguous by number alone."""
        self.assertEqual(self.resolver.cross_stack_collisions(), {})

    def test_every_label_values_id_resolves(self):
        """All 474 ids from the label-values snapshot map to a stack."""
        unresolved = [i for i in self.ids if not self.resolver._by_id.get(str(i))]
        self.assertEqual(unresolved, [], f"{len(unresolved)} ids did not resolve")

    def test_three_way_id_identity_on_every_stack(self):
        """`id` == `hpInstanceId` == `agentManagementInstanceId` on 271/271.

        The reason the field a number matches can never identify a signal.
        """
        mismatched = [
            s["slug"]
            for s in self.stacks
            if not (
                str(s.get("hpInstanceId")) == str(s["id"])
                and str(s.get("agentManagementInstanceId")) == str(s["id"])
            )
        ]
        self.assertEqual(mismatched, [])
        self.assertEqual(len(self.stacks), 271)

    # -- signal attribution --------------------------------------------------------

    def test_all_observed_pairs_resolve_with_their_signal(self):
        """561 distinct (instance_id, instance_type) pairs, all resolving."""
        pairs = {(str(p["instance_id"]), str(p["instance_type"])) for p in self.pairs}
        self.assertEqual(len(pairs), 561)
        failed = [p for p in pairs if self.resolver.resolve(*p) is None]
        self.assertEqual(failed, [], f"{len(failed)} observed pairs failed to resolve")
        self.assertEqual(self.resolver.stats.resolved, len(pairs))

    def test_graphite_field_id_resolves_to_metrics(self):
        """The mis-attribution trap: a graphite-field id is a METRICS id.

        Under the original inferred mapping this would have reported Graphite activity across ~136
        stacks on an estate using Graphite on 2.
        """
        stack = next(
            s
            for s in self.stacks
            if s.get("hmInstanceGraphiteId") and s["hmInstanceGraphiteId"] != s.get("hmInstancePromId")
        )
        got = self.resolver.resolve(stack["hmInstanceGraphiteId"], "metrics")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.stack, stack["slug"])
        self.assertEqual(got.signal, "metrics")

    def test_graphite_and_prom_ids_are_adjacent_and_both_metrics(self):
        """`hmInstanceGraphiteId == hmInstancePromId + 1` on 269/271 - why the trap is so easy to hit."""
        adjacent = [
            s
            for s in self.stacks
            if s.get("hmInstanceGraphiteId")
            and s.get("hmInstancePromId")
            and s["hmInstanceGraphiteId"] == s["hmInstancePromId"] + 1
        ]
        self.assertEqual(len(adjacent), 269)
        sample = adjacent[0]
        for fieldname in ("hmInstancePromId", "hmInstanceGraphiteId"):
            got = self.resolver.resolve(sample[fieldname], "metrics")
            assert got is not None
            self.assertEqual(got.signal, "metrics")

    def test_only_the_five_observed_signals_are_accepted(self):
        self.assertEqual(KNOWN_SIGNALS, {"alerts", "grafana", "logs", "metrics", "traces"})
        for absent in ("graphite", "profiles"):
            self.assertNotIn(absent, KNOWN_SIGNALS)

    def test_unknown_signal_is_counted_not_dropped(self):
        stack = self.stacks[0]
        self.assertIsNone(self.resolver.resolve(stack["id"], "quantum"))
        self.assertEqual(self.resolver.stats.unknown_signal["quantum"], 1)
        self.assertEqual(self.resolver.stats.resolved, 0)

    def test_unknown_instance_id_is_counted_not_dropped(self):
        self.assertIsNone(self.resolver.resolve("999999999", "metrics"))
        self.assertEqual(self.resolver.stats.unknown_instance["999999999"], 1)

    def test_ambiguous_id_refuses_to_guess(self):
        """A number claimed by two stacks must not silently resolve to the first one."""
        resolver = InstanceResolver(
            [
                {"slug": "a", "regionSlug": "r", "clusterSlug": "c", "id": 1},
                {"slug": "b", "regionSlug": "r", "clusterSlug": "c", "id": 1},
            ]
        )
        self.assertEqual(list(resolver.cross_stack_collisions()), ["1"])
        self.assertIsNone(resolver.resolve(1, "grafana"))
        self.assertEqual(resolver.stats.ambiguous["1"], 1)

    def test_coverage_per_signal_matches_the_measured_figures(self):
        """The numbers Phase 2's scope rests on. 63 is the dashboard-views figure, not 139 or 8."""
        per_signal: dict[str, set[str]] = {}
        for p in self.pairs:
            got = self.resolver.resolve(p["instance_id"], p["instance_type"])
            if got:
                per_signal.setdefault(got.signal, set()).add(got.stack)
        counts = {k: len(v) for k, v in per_signal.items()}
        self.assertEqual(
            counts, {"metrics": 139, "traces": 139, "grafana": 63, "logs": 59, "alerts": 22}
        )


if __name__ == "__main__":
    unittest.main()
