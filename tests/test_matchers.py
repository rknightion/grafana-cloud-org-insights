"""Fleet Management pipeline matchers, evaluated locally (PLAN 18.15).

**Why this is local at all.** FM exposes no API for "which collectors does this pipeline target". Probed
2026-08-20: `pipeline.v1.PipelineService/ListPipelinesWithCollectors`, `/CountPipelineCollectors` and
`/ListCollectors` all 404, and `GetPipeline` returns the same record `ListPipelines` already gave. So the
count has to be computed from the pipeline's `matchers` against each collector's `attributes`.

**Which makes it the most dangerous number in this module**: a wrong evaluator produces a plausible
count rather than an error. The rules below are Prometheus label-matcher semantics, and the two that
catch people out are both pinned here - regexes are FULLY ANCHORED, and a missing label is the empty
string rather than a non-match.
"""

from __future__ import annotations

import unittest

from collector.sources import matchers as m


class ParseTest(unittest.TestCase):
    def test_the_four_operators_seen_in_the_wild(self):
        """`=`, `!=` and `=~` were all observed on one estate; `!~` is the fourth Prometheus form."""
        self.assertEqual(m.parse('platform="kubernetes"'), ("platform", "=", "kubernetes"))
        self.assertEqual(m.parse('platform!="kubernetes"'), ("platform", "!=", "kubernetes"))
        self.assertEqual(m.parse('collector.os=~".*"'), ("collector.os", "=~", ".*"))
        self.assertEqual(m.parse('collector.os!~"win.*"'), ("collector.os", "!~", "win.*"))

    def test_the_negated_operators_are_tried_before_the_bare_one(self):
        """`!=` contains `=`, so a naive split on `=` turns `a!="b"` into label `a!`."""
        label, op, _v = m.parse('a!="b"')
        self.assertEqual((label, op), ("a", "!="))
        label, op, _v = m.parse('a!~"b"')
        self.assertEqual((label, op), ("a", "!~"))

    def test_a_label_containing_a_dot_survives(self):
        """Every real FM attribute key is dotted: `collector.os`, `collector.version`, `collector.ID`."""
        self.assertEqual(m.parse('collector.version="v1.12.2"'),
                         ("collector.version", "=", "v1.12.2"))

    def test_UNQUOTED_values_are_valid_because_grafana_writes_them(self):
        """Refusing these cost 17 real matchers on 4 stacks.

        Measured across an estate's 1,180 matchers: the unquoted form appears only inside pipelines
        GRAFANA generated for k8s-monitoring onboarding, so it is what the product writes rather than
        user error - and refusing it made the "collectors targeted" figure unknown on every one.
        """
        self.assertEqual(m.parse('workloadType=daemonset'), ("workloadType", "=", "daemonset"))
        self.assertEqual(m.parse('source=k8s-monitoring'), ("source", "=", "k8s-monitoring"))
        self.assertEqual(m.parse('workloadName=alloy-daemon'), ("workloadName", "=", "alloy-daemon"))
        self.assertEqual(m.parse('a!=b'), ("a", "!=", "b"))

    def test_a_hyphenated_label_is_valid(self):
        """`service-discovery=true` is live on four stacks."""
        self.assertEqual(m.parse('service-discovery=true'), ("service-discovery", "=", "true"))

    def test_malformed_matchers_are_still_REFUSED_not_guessed(self):
        """An unparsed matcher that silently matches nothing would understate every count that uses it.

        The unquoted branch stays narrow: a half-quoted string is malformed, and a mistyped operator such
        as `a=="b"` must not be read as equality with the literal `="b"`.
        """
        for bad in ('platform', '', '="x"', 'platform=="k8s"', 'platform~"k8s"',
                    'platform="k8s', 'platform=k8s"', '1platform="k8s"'):
            with self.subTest(matcher=bad):
                self.assertIsNone(m.parse(bad))

    def test_an_empty_value_is_valid(self):
        """`label=""` is the Prometheus idiom for 'this label is absent', not a malformed matcher."""
        self.assertEqual(m.parse('platform=""'), ("platform", "=", ""))


class MatchTest(unittest.TestCase):
    LINUX = {"platform": "kubernetes", "collector.os": "linux", "collector.version": "v1.12.2"}
    WINDOWS = {"platform": "docker", "collector.os": "windows"}

    def test_equality_and_inequality(self):
        self.assertTrue(m.matches(self.LINUX, ['platform="kubernetes"']))
        self.assertFalse(m.matches(self.LINUX, ['platform!="kubernetes"']))
        self.assertTrue(m.matches(self.WINDOWS, ['platform!="kubernetes"']))

    def test_matchers_are_ANDed(self):
        """A pipeline carrying `platform!="kubernetes"` AND `collector.os="darwin"` targets neither
        every non-k8s collector nor every mac one, but the intersection. Observed shape on a real estate.
        """
        self.assertTrue(m.matches(self.WINDOWS, ['platform!="kubernetes"', 'collector.os="windows"']))
        self.assertFalse(m.matches(self.WINDOWS, ['platform!="kubernetes"', 'collector.os="darwin"']))

    def test_regexes_are_FULLY_ANCHORED(self):
        """Prometheus anchors both ends. Unanchored, `collector.os=~"win"` would match `windows` and a
        count built on it would be quietly too high.
        """
        self.assertTrue(m.matches(self.WINDOWS, ['collector.os=~"win.*"']))
        self.assertFalse(m.matches(self.WINDOWS, ['collector.os=~"win"']))
        self.assertTrue(m.matches(self.WINDOWS, ['collector.os=~"windows"']))
        # `.*` is the catch-all seen in the wild, and it must match a PRESENT label.
        self.assertTrue(m.matches(self.WINDOWS, ['collector.os=~".*"']))

    def test_a_negated_regex_is_also_anchored(self):
        self.assertFalse(m.matches(self.WINDOWS, ['collector.os!~"win.*"']))
        self.assertTrue(m.matches(self.WINDOWS, ['collector.os!~"win"']))

    def test_a_MISSING_label_is_the_empty_string(self):
        """Prometheus semantics, and the case that decides thousands of collectors either way.

        A collector with no `platform` attribute matches `platform!="kubernetes"` (empty is not
        kubernetes) and matches `platform=""`. Treating a missing label as a non-match instead would
        exclude it from every negated matcher, which is the opposite answer.
        """
        bare = {"collector.os": "linux"}
        self.assertTrue(m.matches(bare, ['platform!="kubernetes"']))
        self.assertTrue(m.matches(bare, ['platform=""']))
        self.assertFalse(m.matches(bare, ['platform="kubernetes"']))
        # And an anchored `.*` DOES match an absent label, because `.*` matches the empty string.
        self.assertTrue(m.matches(bare, ['platform=~".*"']))
        self.assertFalse(m.matches(bare, ['platform=~".+"']))

    def test_no_matchers_at_all_targets_EVERY_collector(self):
        """An empty selector is unconstrained. Returning 0 instead would hide a fleet-wide pipeline."""
        self.assertTrue(m.matches(self.LINUX, []))

    def test_an_unparsed_matcher_never_silently_matches(self):
        """It raises, so the caller must decide. Returning False would understate; True would overstate."""
        with self.assertRaises(m.UnparsedMatcher):
            m.matches(self.LINUX, ['platform=="kubernetes"'])

    def test_an_invalid_regex_is_refused_rather_than_matching_nothing(self):
        with self.assertRaises(m.UnparsedMatcher):
            m.matches(self.LINUX, ['collector.os=~"([unclosed"'])

    def test_an_overlong_regex_is_refused_before_evaluation(self):
        pattern = "x" * (m.MAX_REGEX_LENGTH + 1)
        with self.assertRaises(m.UnparsedMatcher):
            m.matches(self.LINUX, [f'collector.os=~"{pattern}"'])


class TargetCountTest(unittest.TestCase):
    COLLECTORS = [
        {"attributes": {"platform": "kubernetes", "collector.os": "linux"}},
        {"attributes": {"platform": "kubernetes", "collector.os": "linux"}},
        {"attributes": {"platform": "docker", "collector.os": "windows"}},
        {"attributes": {"collector.os": "darwin"}},
    ]

    def test_it_counts_the_intersection(self):
        out = m.targets(
            [{"matchers": ['platform="kubernetes"'], "enabled": True}], self.COLLECTORS,
        )
        self.assertEqual(out["counts"][0], 2)

    def test_the_catch_all_pipeline_targets_everything(self):
        out = m.targets([{"matchers": ['collector.os=~".*"']}], self.COLLECTORS)
        self.assertEqual(out["counts"][0], len(self.COLLECTORS))

    def test_it_reports_collectors_NO_pipeline_targets(self):
        """The self-check. A collector matched by nothing receives no configuration, which is a finding
        in its own right - and a suspiciously large number of them means the evaluator is wrong.
        """
        out = m.targets(
            [{"matchers": ['platform="kubernetes"'], "enabled": True}], self.COLLECTORS,
        )
        self.assertEqual(out["unmatched"], 2)

    def test_an_unparsed_matcher_makes_that_pipeline_UNKNOWN_not_zero(self):
        """One bad matcher must not turn into a confident 0, and must not poison the other pipelines."""
        out = m.targets(
            [{"matchers": ['platform=="k8s"']}, {"matchers": ['platform="docker"']}],
            self.COLLECTORS,
        )
        self.assertIsNone(out["counts"][0])
        self.assertEqual(out["counts"][1], 1)
        self.assertEqual(out["unparsed"], 1)

    def test_an_overlong_regex_makes_pipeline_reach_unknown(self):
        pattern = "x" * (m.MAX_REGEX_LENGTH + 1)
        out = m.targets(
            [{"matchers": [f'collector.os=~"{pattern}"']}], self.COLLECTORS,
        )
        self.assertEqual(out["counts"], [None])
        self.assertEqual(out["unparsed"], 1)
        self.assertIsNone(out["unmatched"])

    def test_unmatched_is_not_computed_when_a_pipeline_is_unknown(self):
        """With one pipeline's reach unknown, "targeted by nothing" is unknowable too. Saying 2 there
        would report collectors as unconfigured when the broken pipeline might well cover them."""
        out = m.targets([{"matchers": ['platform=="k8s"']}], self.COLLECTORS)
        self.assertIsNone(out["unmatched"])

    def test_a_disabled_pipeline_is_counted_but_flagged_not_silently_included(self):
        """Its matchers still describe a target set; whether it is ACTING on them is the `enabled` flag.
        Collapsing the two would report a switched-off pipeline as covering collectors it never reaches.
        """
        out = m.targets(
            [{"matchers": ['platform="kubernetes"'], "enabled": False}], self.COLLECTORS)
        self.assertEqual(out["counts"][0], 2)
        self.assertEqual(out["enabled_counts"][0], 0)

    def test_a_missing_enabled_field_uses_the_protobuf_false_default(self):
        out = m.targets([{"matchers": ['platform="kubernetes"']}], self.COLLECTORS)
        self.assertEqual(out["counts"][0], 2)
        self.assertEqual(out["enabled_counts"][0], 0)
        self.assertEqual(out["unmatched"], len(self.COLLECTORS))

    def test_no_pipelines_means_every_collector_is_unmatched(self):
        out = m.targets([], self.COLLECTORS)
        self.assertEqual(out["unmatched"], len(self.COLLECTORS))

    def test_no_collectors_is_zero_everywhere_not_an_error(self):
        out = m.targets([{"matchers": ['platform="kubernetes"']}], [])
        self.assertEqual(out["counts"][0], 0)
        self.assertEqual(out["unmatched"], 0)


if __name__ == "__main__":
    unittest.main()
