"""Fleet Management scrape intervals against the organisation's default (GCI-0046).

A pipeline scraping faster than the default raises DPM, and a high-DPM stack bills across the whole
organisation. Two failures matter most: a parser that reads an unknown interval as the default hides the
exact pipelines this exists to find, and a pillar that reads a payload with no parsed intervals as "no
fast pipelines" publishes a clean zero nobody measured.
"""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import risk
from collector.sources import fleet
from collector.sources import scrape_intervals as SI

ALLOY = '''
// scrape_interval = "1s" in a comment is not configuration
prometheus.scrape "fast" {
  targets    = prometheus.exporter.unix.default.targets
  forward_to = [prometheus.remote_write.default.receiver]
  scrape_interval = "15s"
  job_name = "scrape_interval = \\"2s\\" inside a string"
}

prometheus.scrape "implicit" {
  targets    = discovery.kubernetes.pods.targets
  forward_to = [prometheus.remote_write.default.receiver]
  clustering {
    enabled = true
  }
}

/* prometheus.scrape "commented" { scrape_interval = "1s" } */

pyroscope.scrape "profiles" {
  targets         = discovery.kubernetes.pods.targets
  forward_to      = [pyroscope.write.default.receiver]
  scrape_interval = "5s"
}

prometheus.operator.podmonitors "pods" {
  forward_to = [prometheus.remote_write.default.receiver]
  scrape {
    default_scrape_interval = "30s"
  }
}

prometheus.scrape "from_argument" {
  targets         = argument.targets.value
  forward_to      = argument.forward_to.value
  scrape_interval = argument.interval.value
}
'''

OTEL = '''
receivers:
  otlp:
    protocols:
      grpc: {}
  prometheus:
    config:
      global:
        scrape_interval: 30s
      scrape_configs:
        - job_name: inherits
          static_configs:
            - targets: ["localhost:9100"]
        - job_name: own
          scrape_interval: 10s
          static_configs:
            - targets: ["localhost:9101"]
        - job_name: templated
          scrape_interval: ${env:INTERVAL}
  prometheus/unwired:
    config:
      scrape_configs:
        - job_name: never-run
          scrape_interval: 1s
  prometheus/bare:
    config:
      scrape_configs:
        - job_name: defaults
service:
  pipelines:
    metrics:
      receivers: [otlp, prometheus, prometheus/bare]
      exporters: [otlphttp]
'''


class DurationTest(unittest.TestCase):
    def test_go_and_prometheus_forms(self):
        self.assertEqual(SI.parse_duration("15s"), 15.0)
        self.assertEqual(SI.parse_duration("1m30s"), 90.0)
        self.assertEqual(SI.parse_duration("500ms"), 0.5)
        self.assertEqual(SI.parse_duration("5m"), 300.0)

    def test_non_durations_are_refused_rather_than_guessed(self):
        """A zero would divide every DPM factor by zero; a bare number has no unit to trust."""
        for value in ("", "0s", "15", "fifteen", "${env:X}", None, 15):
            with self.subTest(value=value):
                self.assertIsNone(SI.parse_duration(value))


class AlloyTest(unittest.TestCase):
    def test_it_reads_explicit_and_implicit_prometheus_intervals_only(self):
        intervals, unparsed = SI.alloy_intervals(ALLOY)
        # 15s explicit, 60s implicit default, 30s operator default. Not the 1s or 2s in comments and
        # strings, not the pyroscope 5s, which adds no DPM.
        self.assertEqual(sorted(intervals), [15.0, 30.0, 60.0])
        self.assertEqual(unparsed, 1)

    def test_an_argument_is_unparsed_and_never_the_implicit_default(self):
        """Reading `argument.x.value` as the 60s default would report a fast module as compliant."""
        body = 'prometheus.scrape "m" {\n  scrape_interval = argument.interval.value\n}\n'
        self.assertEqual(SI.alloy_intervals(body), ([], 1))

    def test_a_literal_manual_scrape_interval_is_read_wherever_it_appears(self):
        self.assertEqual(SI.alloy_intervals('argument "x" {\n  manual_scrape_interval = "10s"\n}\n'),
                         ([10.0], 0))


class OtelTest(unittest.TestCase):
    def test_it_reads_wired_prometheus_receivers_with_inheritance(self):
        intervals, unparsed = SI.otel_intervals(OTEL)
        # prometheus: inherits global 30s, own 10s, templated is unparsed. prometheus/bare: 1m default.
        # prometheus/unwired is in no service pipeline, so its 1s scrapes nothing.
        self.assertEqual(sorted(intervals), [10.0, 30.0, 60.0])
        self.assertEqual(unparsed, 1)

    def test_a_fragment_without_a_service_section_is_read_in_full(self):
        body = OTEL.split("service:")[0]
        self.assertIn(1.0, SI.otel_intervals(body)[0])


class OtelCollectionIntervalTest(unittest.TestCase):
    BODY = """
receivers:
  host_metrics:
    collection_interval: 15s
  host_metrics/unwired:
    collection_interval: 1s
  host_metrics/defaulted:
    scrapers:
      cpu: {}
  kubeletstats:
    collection_interval: ${env:KUBELET_INTERVAL}
  prometheus:
    config:
      scrape_configs:
        - job_name: own
          scrape_interval: 30s
service:
  pipelines:
    metrics:
      receivers: [host_metrics, host_metrics/defaulted, kubeletstats, prometheus]
"""

    def test_only_explicit_values_on_wired_receivers_are_read(self):
        """Receiver defaults differ (1m for most, 10s for some), so an omitted value is not guessed."""
        self.assertEqual(SI.otel_collection_intervals(self.BODY), ([15.0], 1))

    def test_the_record_merges_both_attributes_and_says_which_contributed(self):
        rec = SI.summarise(self.BODY, "CONFIG_TYPE_OTEL")
        self.assertEqual(rec["scrape_intervals"], [15.0, 30.0])
        self.assertEqual(rec["scrape_interval_min_seconds"], 15.0)
        self.assertEqual(rec["scrape_intervals_unparsed"], 1)
        self.assertEqual(rec["interval_attributes"], ["collection_interval", "scrape_interval"])

    def test_an_alloy_body_names_only_scrape_interval(self):
        self.assertEqual(SI.summarise(ALLOY, "CONFIG_TYPE_ALLOY")["interval_attributes"],
                         ["scrape_interval"])


class PipelineRecordTest(unittest.TestCase):
    def test_intervals_are_kept_and_the_body_is_not(self):
        pipe = {"name": "p", "enabled": True, "matchers": [], "configType": "CONFIG_TYPE_ALLOY",
                "contents": ALLOY + '\n// token = "glc_secret"\n'}
        rec = fleet.pipeline_record(pipe, 1, 1)
        self.assertEqual(rec["scrape_intervals"], [15.0, 30.0, 60.0])
        self.assertEqual(rec["scrape_interval_min_seconds"], 15.0)
        self.assertEqual(rec["scrape_intervals_unparsed"], 1)
        self.assertNotIn("glc_secret", repr(rec))


def _pipe(name, intervals, *, enabled=True, reach=3, unparsed=0):
    return {"name": name, "enabled": enabled, "source_type": "user", "config_type": "CONFIG_TYPE_ALLOY",
            "targeted": reach, "targeted_enabled": reach if enabled else 0, "updated_at": None,
            "scrape_intervals": intervals,
            "scrape_interval_min_seconds": min(intervals) if intervals else None,
            "scrape_intervals_unparsed": unparsed}


def _fm(pipes, *, parsed=True):
    fm = {"available": True, "collectors": 3, "collectors_active": 3, "collectors_inactive": 0,
          "pipelines": len(pipes), "pipelines_enabled": sum(p["enabled"] for p in pipes),
          "pipeline_detail": pipes}
    if parsed:
        fm["scrape_intervals_parsed"] = True
    return fm


class PillarTest(unittest.TestCase):
    STACKS = [{"slug": "a", "regionSlug": "r"}, {"slug": "b", "regionSlug": "r"},
              {"slug": "c", "regionSlug": "r"}]

    def _build(self, fleet_data, default=60.0):
        metrics, views = risk.build(self.STACKS, Coverage(tier="t1", total=3), fleet=fleet_data,
                                    fleet_default_scrape_interval_seconds=default)
        per_stack = {labels["stack"]: v for name, labels, v in metrics
                     if name == "gcinsight_stack_fleet_fast_scrape_pipelines"}
        estate = {name: v for name, labels, v in metrics if not labels}
        return per_stack, estate, views

    def test_only_enabled_reaching_faster_pipelines_count(self):
        per_stack, estate, views = self._build({
            "a": _fm([_pipe("fast", [15.0, 60.0]), _pipe("off", [5.0], enabled=False),
                      _pipe("nowhere", [5.0], reach=0), _pipe("slow", [300.0]),
                      _pipe("default", [60.0])]),
            "b": _fm([_pipe("fine", [60.0])]),
        })
        self.assertEqual(per_stack, {"a": 1.0, "b": 0.0})
        self.assertEqual(estate["gcinsight_risk_fleet_fast_scrape_stacks"], 1.0)
        rows = {r["Pipeline"]: r for r in views["risk_fleet_scrape_intervals"]}
        self.assertEqual(set(rows), {"fast", "off", "nowhere", "slow"})
        self.assertTrue(rows["fast"]["Faster than default"])
        self.assertEqual(rows["fast"]["DPM factor"], 4.0)
        self.assertEqual(rows["slow"]["Direction"], "slower")
        self.assertFalse(rows["off"]["Faster than default"])

    def test_unknown_reach_counts_so_an_unparsed_matcher_cannot_hide_a_fast_pipeline(self):
        pipe = _pipe("fast", [15.0])
        pipe["targeted"] = pipe["targeted_enabled"] = None
        per_stack, _, _ = self._build({"a": _fm([pipe])})
        self.assertEqual(per_stack["a"], 1.0)

    def test_a_payload_without_parsed_intervals_is_absent_not_zero(self):
        """Hydrated from a scan that predates the parser: nothing was measured."""
        per_stack, estate, views = self._build({"a": _fm([_pipe("x", [])], parsed=False)})
        self.assertEqual(per_stack, {})
        self.assertNotIn("gcinsight_risk_fleet_fast_scrape_stacks", estate)
        self.assertNotIn("risk_fleet_scrape_intervals", views)

    def test_estate_totals_are_withheld_when_one_stack_predates_the_parser(self):
        """Summed over the parsed subset, the stack count would read as the whole estate."""
        per_stack, estate, _ = self._build({
            "a": _fm([_pipe("fast", [15.0])]), "b": _fm([_pipe("x", [])], parsed=False)})
        self.assertEqual(per_stack, {"a": 1.0})
        self.assertNotIn("gcinsight_risk_fleet_fast_scrape_stacks", estate)
        self.assertNotIn("gcinsight_risk_fleet_scrape_intervals_unparsed", estate)

    def test_the_default_is_the_configured_tunable(self):
        per_stack, estate, _ = self._build({"a": _fm([_pipe("p", [30.0])])}, default=15.0)
        self.assertEqual(per_stack["a"], 0.0)
        self.assertEqual(estate["gcinsight_risk_fleet_scrape_interval_default_seconds"], 15.0)
        per_stack, _, _ = self._build({"a": _fm([_pipe("p", [30.0])])}, default=60.0)
        self.assertEqual(per_stack["a"], 1.0)


if __name__ == "__main__":
    unittest.main()
