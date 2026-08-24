"""Fleet Management collection (PLAN 18.15).

The defect: `collectors` was `len(the list FM returned)`, and 68.7% of that list across the estate's 12
biggest FM stacks was registrations for collectors that no longer exist. Nothing in the record was
consulted to tell the difference, and nothing in the pipeline count distinguished a switched-off
pipeline from a live one.
"""

from __future__ import annotations

import unittest

from collector.sources import fleet


def collector(*, updated="2026-08-20T10:00:00Z", marked=None, **attrs):
    rec = {"id": attrs.pop("id", "c1"), "updatedAt": updated, "enabled": True,
           "collectorType": attrs.pop("collectorType", "COLLECTOR_TYPE_ALLOY"),
           "attributes": attrs}
    if marked is not None:
        rec["markedInactiveAt"] = marked
    return rec


class IsInactiveTest(unittest.TestCase):
    def test_no_marking_is_alive(self):
        self.assertFalse(fleet.is_inactive(collector()))

    def test_marked_and_never_seen_again_is_dead(self):
        self.assertTrue(fleet.is_inactive(
            collector(updated="2026-08-19T18:51:00Z", marked="2026-08-19T22:00:00Z")))

    def test_marked_then_reported_again_is_ALIVE(self):
        """A flapping collector must not be counted dead. Measured on one estate: zero had come back, so
        this comparison changes nothing today and prevents a wrong answer the first time one does."""
        self.assertFalse(fleet.is_inactive(
            collector(updated="2026-08-20T09:00:00Z", marked="2026-08-19T22:00:00Z")))

    def test_marked_at_exactly_the_update_time_is_dead(self):
        """Equal timestamps mean the marking is not superseded. Chosen over the alternative because the
        alternative resurrects a collector on a clock tie."""
        self.assertTrue(fleet.is_inactive(
            collector(updated="2026-08-19T22:00:00Z", marked="2026-08-19T22:00:00Z")))

    def test_an_unparseable_timestamp_does_not_crash_or_resurrect(self):
        self.assertTrue(fleet.is_inactive(collector(updated="not-a-date", marked="2026-08-19T22:00:00Z")))
        self.assertFalse(fleet.is_inactive(collector(updated="2026-08-20T10:00:00Z", marked="nonsense")))

    def test_offsetless_and_offset_timestamps_are_safely_comparable(self):
        c = collector(updated="2026-08-19T18:00:00", marked="2026-08-19T22:00:00Z")
        self.assertTrue(fleet.is_inactive(c))


class AttributeBreakdownTest(unittest.TestCase):
    FLEET = [
        collector(**{"collector.version": "v1.12.2", "collector.os": "linux", "platform": "kubernetes"}),
        collector(**{"collector.version": "v1.12.2", "collector.os": "linux", "platform": "kubernetes"}),
        collector(**{"collector.version": "v1.10.0", "collector.os": "windows", "platform": "docker"}),
    ]

    def test_it_counts_values_per_kept_attribute(self):
        out = fleet.attribute_breakdown(self.FLEET)
        self.assertEqual(out["collector.version"]["values"], {"v1.12.2": 2, "v1.10.0": 1})
        self.assertEqual(out["collector.os"]["distinct"], 2)

    def test_a_missing_attribute_becomes_unknown_rather_than_vanishing(self):
        """Dropping it would make the per-attribute totals disagree with the collector count."""
        out = fleet.attribute_breakdown([collector()])
        self.assertEqual(out["collector.version"]["values"], {"unknown": 1})

    def test_the_dropped_attributes_are_never_reported(self):
        """`collector.ID` is a HOSTNAME and the rest are per-workload and unbounded."""
        out = fleet.attribute_breakdown([
            collector(**{"cluster": "c", "namespace": "n", "workloadName": "w",
                         "collector.ID": "host.internal"})])
        for key in fleet.DROPPED_ATTRIBUTES:
            self.assertNotIn(key, out)

    def test_the_value_list_is_bounded_but_the_distinct_count_is_not(self):
        """Truncating silently would make version drift look tidier than it is."""
        many = [collector(**{"collector.version": f"v{i}"}) for i in range(40)]
        out = fleet.attribute_breakdown(many)
        self.assertEqual(len(out["collector.version"]["values"]), fleet.MAX_ATTRIBUTE_VALUES)
        self.assertEqual(out["collector.version"]["distinct"], 40)

    def test_the_widest_values_survive_truncation(self):
        many = [collector(**{"collector.os": "linux"}) for _ in range(50)]
        many += [collector(**{"collector.os": f"other{i}"}) for i in range(30)]
        out = fleet.attribute_breakdown(many)
        self.assertIn("linux", out["collector.os"]["values"])


class PipelineRecordTest(unittest.TestCase):
    LIVE = {"name": "self_monitoring_metrics", "enabled": True, "matchers": ['collector.os=~".*"'],
            "contents": "// 4KB of Alloy configuration" * 200,
            "source": {"type": "SOURCE_TYPE_GRAFANA"}, "configType": "CONFIG_TYPE_ALLOY",
            "updatedAt": "2026-04-27T16:06:39Z"}

    def test_contents_is_NEVER_kept(self):
        """Kilobytes per pipeline, and it is the customer's own configuration."""
        rec = fleet.pipeline_record(self.LIVE, 10, 10)
        self.assertNotIn("contents", rec)
        self.assertNotIn("// 4KB", repr(rec))

    def test_a_generated_pipeline_is_distinguishable_from_a_hand_written_one(self):
        """The difference between 'onboarding created this' and 'a team owns this'."""
        self.assertEqual(fleet.pipeline_record(self.LIVE, 1, 1)["source_type"], "SOURCE_TYPE_GRAFANA")
        bare = {k: v for k, v in self.LIVE.items() if k != "source"}
        self.assertEqual(fleet.pipeline_record(bare, 1, 1)["source_type"], "user")

    def test_targeted_may_be_none_and_is_not_coerced_to_zero(self):
        self.assertIsNone(fleet.pipeline_record(self.LIVE, None, 0)["targeted"])


class ProbeStackTest(unittest.TestCase):
    STACK = {"slug": "alpha", "id": 123, "agentManagementInstanceUrl": "https://fm.example"}

    def _probe(self, collectors, pipelines):
        calls: list[str] = []

        def fake_rpc(url, user, cap, timeout=30.0):
            calls.append(url)
            if fleet.LIST_COLLECTORS in url:
                return {"collectors": collectors}
            return {"pipelines": pipelines}

        original = fleet._connect_rpc
        fleet._connect_rpc = fake_rpc
        try:
            return fleet.probe_stack(self.STACK, "cap"), calls
        finally:
            fleet._connect_rpc = original

    def test_the_alive_and_dead_split_is_reported_and_the_total_is_UNCHANGED(self):
        """`collectors` keeps its old meaning so the published series stays continuous."""
        out, _ = self._probe(
            [collector(id="a"), collector(id="b", updated="2026-08-19T18:00:00Z",
                                          marked="2026-08-19T22:00:00Z")],
            [])
        self.assertEqual(out["collectors"], 2)
        self.assertEqual(out["collectors_active"], 1)
        self.assertEqual(out["collectors_inactive"], 1)

    def test_provisioned_but_empty_counts_ALIVE_collectors(self):
        """The old check compared against every registration, so a stack whose collectors were all dead
        read as healthy. That is the population the finding is about."""
        dead = collector(id="d", updated="2026-08-19T18:00:00Z", marked="2026-08-19T22:00:00Z")
        out, _ = self._probe([dead], [{"name": "p", "enabled": True, "matchers": []}])
        self.assertTrue(out["provisioned_but_empty"])

    def test_pipelines_split_enabled_from_configured_and_generated_from_authored(self):
        out, _ = self._probe([collector()], [
            {"name": "on", "enabled": True, "matchers": [], "source": {"type": "SOURCE_TYPE_GRAFANA"}},
            {"name": "off", "enabled": False, "matchers": []},
        ])
        self.assertEqual(out["pipelines"], 2)
        self.assertEqual(out["pipelines_enabled"], 1)
        self.assertEqual(out["pipelines_generated"], 1)

    def test_targeting_is_computed_against_the_ALIVE_fleet(self):
        """A pipeline's reach over registrations that no longer exist is not a fact about anything."""
        dead = collector(id="d", updated="2026-08-19T18:00:00Z", marked="2026-08-19T22:00:00Z",
                         **{"platform": "kubernetes"})
        alive = collector(id="a", **{"platform": "kubernetes"})
        out, _ = self._probe([dead, alive],
                             [{"name": "k8s", "enabled": True, "matchers": ['platform="kubernetes"']}])
        self.assertEqual(out["pipeline_detail"][0]["targeted"], 1)

    def test_version_breakdown_excludes_dead_registrations(self):
        """Otherwise it describes the fleet as it WAS, which is the same defect one level down."""
        dead = collector(id="d", updated="2026-08-19T18:00:00Z", marked="2026-08-19T22:00:00Z",
                         **{"collector.version": "v1.0.0"})
        alive = collector(id="a", **{"collector.version": "v2.0.0"})
        out, _ = self._probe([dead, alive], [])
        self.assertEqual(out["collector_versions"], ["v2.0.0"])
        self.assertEqual(out["attributes"]["collector.version"]["values"], {"v2.0.0": 1})

    def test_a_stack_with_no_fm_url_is_unavailable_with_a_reason(self):
        out = fleet.probe_stack({"slug": "x", "id": 1}, "cap")
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], "no_fm_url")

    def test_empty_protobuf_messages_are_valid_empty_lists(self):
        """Connect's JSON encoding omits repeated fields when they are empty, yielding `{}` live."""
        def fake_rpc(url, user, cap, timeout=30.0):
            return {}

        original = fleet._connect_rpc
        fleet._connect_rpc = fake_rpc
        try:
            out = fleet.probe_stack(self.STACK, "cap")
        finally:
            fleet._connect_rpc = original

        self.assertTrue(out["available"])
        self.assertEqual(out["collectors"], 0)
        self.assertEqual(out["pipelines"], 0)

    def test_an_http_error_is_unavailable_and_never_zero_collectors(self):
        def fake_rpc(url, user, cap, timeout=30.0):
            return {"_http": 503}
        original = fleet._connect_rpc
        fleet._connect_rpc = fake_rpc
        try:
            out = fleet.probe_stack(self.STACK, "cap")
        finally:
            fleet._connect_rpc = original
        self.assertFalse(out["available"])
        self.assertNotIn("collectors", out)

    def test_a_pipeline_http_error_is_unavailable_and_never_zero_pipelines(self):
        """Both RPCs are one logical input; a good collector list cannot mask a refused pipeline list."""
        def fake_rpc(url, user, cap, timeout=30.0):
            if fleet.LIST_COLLECTORS in url:
                return {"collectors": [collector()]}
            return {"_http": 403}

        original = fleet._connect_rpc
        fleet._connect_rpc = fake_rpc
        try:
            out = fleet.probe_stack(self.STACK, "cap")
        finally:
            fleet._connect_rpc = original
        self.assertFalse(out["available"])
        self.assertEqual(out["failed_rpc"], "pipelines")
        self.assertNotIn("pipelines", out)

    def test_only_list_methods_are_called(self):
        """`_connect_rpc` refuses anything else, but the URLs are asserted here too so a future edit
        cannot reach a mutating method by construction."""
        _out, calls = self._probe([collector()], [])
        for url in calls:
            self.assertIn("Service/List", url)


class ProbeAllTest(unittest.TestCase):
    def test_paused_stacks_are_skipped_and_departed_stacks_get_no_row(self):
        stacks = [{"slug": "a", "id": 1, "agentManagementInstanceUrl": "https://fm.example"},
                  {"slug": "p", "id": 2, "status": "paused",
                   "agentManagementInstanceUrl": "https://fm.example"}]

        def fake_rpc(url, user, cap, timeout=30.0):
            return {"collectors": []} if fleet.LIST_COLLECTORS in url else {"pipelines": []}

        original = fleet._connect_rpc
        fleet._connect_rpc = fake_rpc
        try:
            out = fleet.probe_all(stacks, "cap")
        finally:
            fleet._connect_rpc = original
        self.assertEqual(set(out), {"a"})

    def test_one_failing_stack_does_not_fail_the_sweep(self):
        stacks = [{"slug": "boom", "id": 1, "agentManagementInstanceUrl": "https://fm.example"},
                  {"slug": "ok", "id": 2, "agentManagementInstanceUrl": "https://fm.example"}]
        seen: list[tuple[str, str]] = []

        def fake_rpc(url, user, cap, timeout=30.0):
            if user == "1":
                raise TimeoutError("boom")
            return {"collectors": []} if fleet.LIST_COLLECTORS in url else {"pipelines": []}

        original = fleet._connect_rpc
        fleet._connect_rpc = fake_rpc
        try:
            out = fleet.probe_all(stacks, "cap", on_error=lambda s, m: seen.append((s, m)))
        finally:
            fleet._connect_rpc = original
        self.assertFalse(out["boom"]["available"])
        self.assertTrue(out["ok"]["available"])
        self.assertEqual([s for s, _m in seen], ["boom"])


if __name__ == "__main__":
    unittest.main()
