"""Insight-host resolution - READ from the datasource list, never derived from a slug (PLAN 2.4).

The temptation is obvious: the host looks like `insight-logs-<clusterSlug>.grafana.net`, so why not build
the string? Because the inputs do not support it, and the measurements below are the whole reason this
module exists rather than an f-string.

**`regionSlug` -> `clusterSlug` is not even a function.** Measured over the 271-stack inventory:

    regionSlug        clusterSlug          stacks
    prod-eu-west-2    prod-eu-west-4          127   <-- same region, two clusters
    prod-eu-west-2    prod-eu-west-2           45   <--
    prod-us-east-0    prod-us-east-2           24   <-- same region, two clusters
    prod-us-east-0    prod-us-east-0            5   <--
    eu                prod-eu-west-0            4   legacy GCP, not constructible
    us-azure          prod-us-central-7         3   legacy Azure, not constructible

**158 of 271 stacks (58%) have `regionSlug != clusterSlug`.** So deriving from the region is wrong on the
majority of the estate, and for the 7 legacy stacks no rule can get there at all: going from `eu` to
`prod-eu-west-0` means inventing both `prod-` and `-west-0`. (Careful how you phrase this in a test -
`"eu" in "prod-eu-west-0"` is true as a substring, so containment proves nothing. Construction is
the claim.)

**And a stack has more than one insight host, keyed on different slugs.** On `obs-hub-dev`, measured:

    grafanacloud-obs-hub-dev-usage-insights        -> insight-logs-prod-eu-west-4   (follows CLUSTER)
    grafanacloud-obs-hub-dev-cardinality-management -> insights-prod-eu-west-2      (follows REGION)

Two hosts, two different slugs, same stack. There is no single "the insight host" to derive.

**The other trap: matching on datasource type alone picks the wrong one.**
`grafanacloud-obs-hub-dev-alert-state-history` is *also* `type: loki` and *also* points at
`insight-logs-prod-eu-west-4`. It happens to share a host today, so a type-only match looks correct until
a stack where it does not - a silent wrong-tenant read rather than an error.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from collector import resolver

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


def _inventory():
    return json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]


def _write_stack_datasources():
    return json.loads((TESTDATA / "gcom-instance-datasources.json").read_text())["items"]


class ItReadsTheHostTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ds = _write_stack_datasources()

    def test_the_usage_insights_host_comes_from_the_datasource(self):
        hosts = resolver.insight_hosts(self.ds)
        self.assertEqual(hosts.usage_insights, "https://insight-logs-prod-eu-west-4.grafana.net")

    def test_the_cardinality_host_is_a_DIFFERENT_host_on_the_same_stack(self):
        """The reason there is no single 'insight host' to resolve."""
        hosts = resolver.insight_hosts(self.ds)
        self.assertIn("insights-prod-eu-west-2", hosts.cardinality or "")
        self.assertNotEqual(hosts.cardinality, hosts.usage_insights)

    def test_the_alert_state_history_datasource_is_not_mistaken_for_usage_insights(self):
        """Same `type: loki`, same host today. A type-only match reads the wrong tenant silently."""
        only_alert_history = [
            d for d in self.ds if "alert-state-history" in (d.get("name") or "")
        ]
        self.assertTrue(only_alert_history, "fixture no longer has the alert-state-history datasource")
        hosts = resolver.insight_hosts(only_alert_history)
        self.assertIsNone(hosts.usage_insights,
                          "alert-state-history was accepted as the usage-insights datasource")

    def test_a_missing_datasource_resolves_to_None_not_a_guess(self):
        hosts = resolver.insight_hosts([])
        self.assertIsNone(hosts.usage_insights)
        self.assertIsNone(hosts.cardinality)

    def test_a_datasource_with_no_url_does_not_resolve(self):
        hosts = resolver.insight_hosts([{"name": "grafanacloud-x-usage-insights", "type": "loki"}])
        self.assertIsNone(hosts.usage_insights)


class ItIsNeverDerivedFromASlugTest(unittest.TestCase):
    """The assertions PLAN 2.4 asks for by name."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = _inventory()

    def test_region_to_cluster_is_not_a_function(self):
        """The killer argument: one regionSlug maps to more than one cluster, so no derivation from
        regionSlug can exist even in principle."""
        mapping: dict[str, set[str]] = {}
        for s in self.stacks:
            mapping.setdefault(str(s.get("regionSlug")), set()).add(str(s.get("clusterSlug")))
        ambiguous = {r: c for r, c in mapping.items() if len(c) > 1}
        self.assertTrue(
            ambiguous,
            "regionSlug now maps 1:1 to clusterSlug - re-verify before trusting any derivation",
        )

    def test_the_majority_of_the_estate_has_region_differing_from_cluster(self):
        differ = [s for s in self.stacks
                  if str(s.get("regionSlug")) != str(s.get("clusterSlug"))]
        self.assertGreater(len(differ) / len(self.stacks), 0.5,
                           "expected region != cluster on most of the estate")

    def test_the_legacy_slugs_cannot_be_munged_into_a_host(self):
        """`eu` and `us-azure` cannot be BUILT into their cluster.

        Note the trap in phrasing this: `"eu" in "prod-eu-west-0"` is true as a substring, so a
        containment check proves nothing. The claim that matters is CONSTRUCTION - going from `eu` to
        `prod-eu-west-0` means inventing both `prod-` and `-west-0`, which no rule can do.
        """
        probed = json.loads((TESTDATA / "region-map.json").read_text())
        legacy = {str(s.get("regionSlug")): str(s.get("clusterSlug"))
                  for s in self.stacks if str(s.get("regionSlug")) in ("eu", "us-azure")}
        self.assertTrue(legacy, "the legacy-region stacks are gone from the fixture")
        for region, cluster in legacy.items():
            naive = f"https://insight-logs-{region}.grafana.net"
            actual = probed[cluster]["insight_host"]
            self.assertNotEqual(naive, actual,
                                f"region {region!r} unexpectedly derived the correct host")
            # And the cluster carries components the region simply does not supply.
            self.assertNotEqual(region, cluster)

    def test_deriving_from_the_region_would_be_wrong_for_the_write_stack(self):
        """Concrete: the plausible f-string produces a host that is not this stack's."""
        stack = next(s for s in self.stacks if str(s["slug"]) == "obs-hub-dev")
        naive = f"https://insight-logs-{stack['regionSlug']}.grafana.net"
        actual = resolver.insight_hosts(_write_stack_datasources()).usage_insights
        self.assertNotEqual(naive, actual,
                            "region-derived host coincidentally matched - pick another example stack")

    def test_the_resolver_takes_datasources_not_a_stack_record(self):
        """A signature that cannot see regionSlug cannot be tempted by it. This is the real guard."""
        import inspect
        params = list(inspect.signature(resolver.insight_hosts).parameters)
        self.assertEqual(params, ["datasources"])


class AgainstTheRegionMapTest(unittest.TestCase):
    """`testdata/region-map.json` was produced by `bin/probe_regions.py` reading real datasources."""

    def test_every_probed_host_follows_the_cluster_it_was_found_on(self):
        probed = json.loads((TESTDATA / "region-map.json").read_text())
        self.assertEqual(len(probed), 10, "expected 10 clusters in the probed map")
        for cluster, entry in probed.items():
            self.assertIn(cluster, entry["insight_host"],
                          f"{cluster} host does not carry its own cluster slug")

    def test_the_probe_and_the_resolver_agree_on_shape(self):
        """Both must produce a full https origin, so a caller never has to add a scheme."""
        probed = json.loads((TESTDATA / "region-map.json").read_text())
        for entry in probed.values():
            self.assertTrue(entry["insight_host"].startswith("https://"))
        resolved = resolver.insight_hosts(_write_stack_datasources()).usage_insights
        self.assertTrue(resolved.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
