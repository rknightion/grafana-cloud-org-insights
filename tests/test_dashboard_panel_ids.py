"""Stable panel identities for assembled v2 dashboards."""

from __future__ import annotations

import unittest
from unittest import mock

from collector.dashboards import build


def _elements() -> dict[str, dict]:
    return {
        "flat": build.text_panel("Flat", "flat"),
        "row_a": build.text_panel("Row A", "row a"),
        "row_b": build.text_panel("Row B", "row b"),
    }


def _dashboard(elements: dict[str, dict]) -> dict:
    return build.dashboard(
        "Panel identity test",
        "",
        elements,
        [
            build.tab("Flat", ["flat"]),
            build.rows_tab("Nested", [
                build.row("First row", ["row_a"]),
                build.row("Second row", ["row_b"]),
            ]),
        ],
    )


class DashboardPanelIdTest(unittest.TestCase):
    def test_final_assembly_assigns_unique_nonzero_numeric_ids_to_every_panel(self):
        spec = _dashboard(_elements())

        ids = [panel["spec"]["id"] for panel in spec["spec"]["elements"].values()]
        self.assertTrue(all(isinstance(panel_id, int) and not isinstance(panel_id, bool)
                            for panel_id in ids))
        self.assertTrue(all(panel_id > 0 for panel_id in ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_ids_are_stable_by_element_key_across_repeated_and_reordered_builds(self):
        first = _dashboard(_elements())["spec"]["elements"]
        reordered = dict(reversed(list(_elements().items())))
        second = _dashboard(reordered)["spec"]["elements"]

        first_ids = {key: panel["spec"]["id"] for key, panel in first.items()}
        second_ids = {key: panel["spec"]["id"] for key, panel in second.items()}
        self.assertEqual(first_ids, second_ids)

    def test_a_hash_collision_fails_the_build(self):
        with mock.patch.object(build, "_panel_id", return_value=7):
            with self.assertRaisesRegex(build.PanelIdCollision, "flat.*row_a"):
                _dashboard(_elements())


if __name__ == "__main__":
    unittest.main()
