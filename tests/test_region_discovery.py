"""The estate is DISCOVERED, never configured (the project's golden rule).

A stack can appear in a Grafana Cloud region this project has never seen. Anything that enumerates
regions from a literal tuple silently stops covering the estate the moment that happens - and it fails
*quietly*, by returning fewer rows rather than by erroring, which is the failure mode this codebase
treats as worse than a crash.
"""

from __future__ import annotations

import unittest

from collector.sources import gcom


def _stacks(*regions):
    return [{"slug": f"s{i}", "regionSlug": r} for i, r in enumerate(regions)]


class PolicyRegionDiscoveryTest(unittest.TestCase):
    def test_a_region_only_the_inventory_knows_about_is_still_queried(self):
        regions = gcom.policy_regions(_stacks("prod-ap-southeast-9"))
        self.assertIn("prod-ap-southeast-9", regions)

    def test_the_control_plane_realms_survive_an_inventory_that_never_mentions_them(self):
        """`us` holds this project's own org-realm policies and is not any stack's regionSlug."""
        regions = gcom.policy_regions(_stacks("prod-eu-west-2"))
        for realm in ("us", "eu", "au"):
            self.assertIn(realm, regions)

    def test_no_inventory_falls_back_to_the_known_realms_rather_than_nothing(self):
        self.assertTrue(set(gcom.policy_regions([])) >= {"us", "eu", "au"})

    def test_duplicate_regions_are_queried_once(self):
        regions = gcom.policy_regions(_stacks("prod-eu-west-2", "prod-eu-west-2", "eu"))
        self.assertEqual(len(regions), len(set(regions)))

    def test_a_stack_with_no_region_does_not_produce_an_empty_region_query(self):
        regions = gcom.policy_regions([{"slug": "x"}, {"slug": "y", "regionSlug": None}])
        self.assertNotIn(None, regions)
        self.assertNotIn("", regions)

    def test_the_order_is_stable_so_a_scan_is_reproducible(self):
        a = gcom.policy_regions(_stacks("prod-eu-west-3", "prod-us-east-0"))
        b = gcom.policy_regions(_stacks("prod-us-east-0", "prod-eu-west-3"))
        self.assertEqual(a, b)

    def test_every_region_the_estate_occupies_today_is_covered(self):
        """The eight live regionSlug values as of 2026-08-20, as a regression floor."""
        live = ("prod-eu-west-2", "prod-us-west-0", "prod-us-east-0", "prod-eu-central-0",
                "us-azure", "prod-eu-west-3", "prod-eu-north-0", "eu")
        regions = set(gcom.policy_regions(_stacks(*live)))
        self.assertTrue(regions >= set(live))


if __name__ == "__main__":
    unittest.main()
