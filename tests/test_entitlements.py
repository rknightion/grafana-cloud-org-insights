"""gcom provisioning flags, and the one that is routinely misread (Pillar A source).

**Measured 2026-08-18: `incident` set on 0 of 271 stacks, `machineLearning` on 0 of 271, and `k6OrgId`
set on 98 of 271.** All three fields were already whitelisted into every scan and none of them reached a
metric, a view or a panel - collected and never surfaced.

**`incident: 0` does NOT mean incident response is unused. That reading is WRONG.** An earlier version of
this docstring called all three "capability the estate is not using", and for `incident` that is false:
gcom's `incident` field is the legacy standalone Grafana Incident product, which IRM and OnCall do not
set. Measured the same day from `grafanacloud-usage`, **20 stacks carry 11,549 OnCall alert groups and
2,905 user notifications** - with `incident: 0` and `billingOnCallActiveUsers: 0` on every one of them.
See `testdata/usage-datasource-signals.json` key `irm_in_use` for the named stacks.

So what these three series honestly support is narrow: a flag is set or it is not. For genuine product
entitlement, `grafanacloud_product_activation_status` on the usage datasource is the real signal and
reports five products none of these booleans can see.

**A zero here is a MEASURED zero, not a gap**, and that distinction matters because the rest of this
platform treats a zero as a defect. `gcinsight_maturity_stacks_by_tier = 0` from an hourly tier was a
real bug - the tier could not compute it. This is different: the inventory is present, the question was
asked, and the answer is genuinely none. So it emits 0 and the panel must read "0 of 271", never blank.

**What the source does NOT tell us is whether these are contractually paid for.** `incident: 0` proves it
is off, not that the org bought it. Nothing here may be presented as wasted spend without the contract.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit import guard
from collector.emit.budget import CATALOGUE
from collector.pillars import estate

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

METRIC = "gcinsight_estate_feature_stacks"


def _stacks():
    return json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]


def _coverage(stacks):
    cov = Coverage(tier="t1", total=len(stacks))
    for s in stacks:
        cov.record_ok(str(s["slug"]))
    return cov


def _build(stacks):
    return estate.build(stacks, _coverage(stacks))


def _features(metrics) -> dict[str, float]:
    return {l["kind"]: v for n, l, v in metrics if n == METRIC}


class ItCountsWhatIsEnabledTest(unittest.TestCase):
    def test_a_disabled_feature_is_zero_not_absent(self):
        """The opposite of this platform's usual rule, and deliberately so: the zero IS the finding."""
        metrics, _ = _build([{"slug": "a", "incident": 0, "machineLearning": 0, "k6OrgId": None}])
        feats = _features(metrics)
        self.assertEqual(feats["incident"], 0.0)
        self.assertEqual(feats["machine_learning"], 0.0)
        self.assertEqual(feats["k6"], 0.0)

    def test_an_enabled_feature_is_counted(self):
        metrics, _ = _build([
            {"slug": "a", "incident": 1, "machineLearning": 0, "k6OrgId": 4242},
            {"slug": "b", "incident": 1, "machineLearning": 1, "k6OrgId": None},
        ])
        feats = _features(metrics)
        self.assertEqual(feats["incident"], 2.0)
        self.assertEqual(feats["machine_learning"], 1.0)
        self.assertEqual(feats["k6"], 1.0)

    def test_k6_is_keyed_off_an_id_being_present_not_a_boolean(self):
        """`k6OrgId` is an id or null, unlike the other two which are 0/1. A truthiness test on the id
        is right; a `== 1` test would silently count nothing."""
        metrics, _ = _build([{"slug": "a", "k6OrgId": 987654}])
        self.assertEqual(_features(metrics)["k6"], 1.0)

    def test_a_missing_field_counts_as_not_enabled(self):
        """Absent and null are not distinguishable upstream, so both mean off."""
        metrics, _ = _build([{"slug": "a"}])
        self.assertEqual(_features(metrics)["incident"], 0.0)

    def test_all_three_features_are_always_emitted(self):
        """One series per feature, every run - so a panel can say '0 of 271' rather than going blank."""
        metrics, _ = _build([{"slug": "a"}])
        self.assertEqual(set(_features(metrics)), {"incident", "machine_learning", "k6"})


class CardinalityTest(unittest.TestCase):
    def test_the_labels_pass_the_guard(self):
        metrics, _ = _build(_stacks())
        guard.check_all([m for m in metrics if m[0] == METRIC])

    def test_it_reuses_the_kind_label_rather_than_adding_a_key(self):
        """`kind` is the established discriminator here; a new key would need an allow-list decision."""
        metrics, _ = _build([{"slug": "a"}])
        for name, labels, _ in metrics:
            if name == METRIC:
                self.assertEqual(set(labels), {"kind"})

    def test_it_is_declared_in_the_budget(self):
        spec = next((s for s in CATALOGUE if s.name == METRIC), None)
        self.assertIsNotNone(spec, f"{METRIC} is not declared in budget.py")
        self.assertEqual(spec.labels.get("kind"), 3)

    def test_it_costs_exactly_three_series(self):
        metrics, _ = _build(_stacks())
        self.assertEqual(len([m for m in metrics if m[0] == METRIC]), 3)


class AgainstTheRealEstateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = _stacks()
        cls.metrics, _ = _build(cls.stacks)

    def test_the_incident_and_ml_flags_are_unset_across_the_whole_estate(self):
        """Pins the headline. If the fixture gains one this fails - update the number, keep the test.

        Named for what it measures: the FLAG is unset. Whether the capability is used is a different
        question with a different answer, pinned below.
        """
        feats = _features(self.metrics)
        self.assertEqual(feats["incident"], 0.0)
        self.assertEqual(feats["machine_learning"], 0.0)

    def test_the_incident_flag_being_zero_does_not_mean_oncall_is_unused(self):
        """The correction, pinned against committed evidence so it cannot quietly regress.

        20 stacks run OnCall while gcom reports `incident: 0` on all of them. This asserts the two
        sources genuinely disagree, because the moment they stop disagreeing the caveat can go.
        """
        evidence = json.loads((TESTDATA / "usage-datasource-signals.json").read_text())["irm_in_use"]
        self.assertGreater(evidence["stacks_with_oncall_alert_groups"], 0,
                           "no stack runs OnCall any more - recheck before deleting the caveat")
        self.assertGreater(evidence["oncall_alert_groups_total"], 1000)
        oncall_slugs = {r["slug"] for r in evidence["stacks_by_oncall_groups"]}
        by_slug = {str(s["slug"]): s for s in self.stacks}
        overlap = oncall_slugs & set(by_slug)
        self.assertTrue(overlap, "no OnCall stack is in the inventory fixture - one of them is stale")
        for slug in sorted(overlap):
            self.assertFalse(
                by_slug[slug].get("incident"),
                f"{slug} runs OnCall AND has gcom incident set - the two fields now agree, so the "
                f"correction in this file and in estate.py should be revisited",
            )

    def test_k6_is_provisioned_on_a_substantial_minority(self):
        """98 of 271 measured. Provisioned is not the same as used - that needs the k6 API, not this."""
        self.assertGreater(_features(self.metrics)["k6"], 50)
        self.assertLess(_features(self.metrics)["k6"], len(self.stacks))

    def test_no_feature_count_exceeds_the_estate(self):
        for kind, value in _features(self.metrics).items():
            self.assertLessEqual(value, len(self.stacks), kind)


if __name__ == "__main__":
    unittest.main()
