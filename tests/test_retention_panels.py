"""Contract tests for the live usage-datasource retention panels."""

from __future__ import annotations

import unittest

from collector.dashboards import build
from collector.dashboards.retention_panels import retention_panels


def _expressions(panel: dict) -> list[str]:
    return [
        query["spec"]["query"]["spec"]["expr"]
        for query in panel["spec"]["data"]["spec"]["queries"]
    ]


class RetentionPanelsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.panels = retention_panels()

    def test_exports_the_five_frozen_panel_keys(self):
        self.assertEqual(
            set(self.panels),
            {
                "_ret_denom",
                "_ret_global",
                "_ret_candidates",
                "_ret_candidate_table",
                "_ret_trend",
            },
        )

    def test_each_panel_has_a_non_empty_description_and_uses_usage_datasource(self):
        for key, panel in self.panels.items():
            with self.subTest(panel=key):
                self.assertTrue(panel["spec"]["description"].strip())
                for query in panel["spec"]["data"]["spec"]["queries"]:
                    self.assertEqual(
                        query["spec"]["query"]["datasource"]["name"],
                        build.USAGE_UID,
                    )

    def test_duration_values_are_converted_from_nanoseconds_to_days(self):
        expressions = "\n".join(
            expression
            for panel in self.panels.values()
            for expression in _expressions(panel)
        )
        self.assertIn("/ 1e9 / 86400", expressions)

    def test_candidate_expression_preserves_the_stack_join_shape(self):
        expression = _expressions(self.panels["_ret_candidates"])[0]
        self.assertIn(
            'count(grafanacloud_logs_instance_limits{limit_name="max_query_lookback"} '
            "!= on(stack_id) group_left() "
            'grafanacloud_logs_instance_limits{limit_name="retention_period"})',
            expression,
        )

    def test_global_stat_selects_the_modal_retention_value_and_counts_distinct_values(
        self,
    ):
        expressions = _expressions(self.panels["_ret_global"])
        self.assertIn("topk(1, count_values", expressions[0])
        self.assertIn("count(count_values", expressions[1])
        transformations = self.panels["_ret_global"]["spec"]["data"]["spec"][
            "transformations"
        ]
        self.assertEqual(
            [transform["spec"]["id"] for transform in transformations],
            ["labelsToFields", "merge", "organize"],
        )
        organize = transformations[-1]["spec"]["options"]
        self.assertTrue(organize["excludeByName"]["Value #A"])
        self.assertEqual(
            organize["renameByName"]["retention_days"], "Modal retention days"
        )

    def test_every_description_states_estate_wide_scope_and_individual_confirmation(
        self,
    ):
        for key, panel in self.panels.items():
            with self.subTest(panel=key):
                description = panel["spec"]["description"].lower()
                self.assertIn("estate-wide", description)
                self.assertIn(
                    "collector tier confirms an individual stack", description
                )

    def test_override_wording_is_qualified_as_candidate_or_likely(self):
        for key, panel in self.panels.items():
            with self.subTest(panel=key):
                description = panel["spec"]["description"].lower()
                for start in range(len(description)):
                    if description.startswith("override", start):
                        prefix = description[max(0, start - 32) : start]
                        self.assertRegex(prefix, r"(candidate|likely)[^.!?]*$")


if __name__ == "__main__":
    unittest.main()
