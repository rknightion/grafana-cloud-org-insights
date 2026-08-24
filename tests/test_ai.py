"""Pillar I - `collector/pillars/ai.py` and `collector/emit/gapstate.py`.

The rules this pillar can break silently, each pinned here: a gap published as a zero, a paused stack
counted as a missing credential, `category`/`surface` leaking onto a per-stack series, and the coverage
alert watching a count instead of an age.
"""

from __future__ import annotations

import datetime as dt
import unittest

from collector import provision as prov
from collector.coverage import Coverage
from collector.emit import budget, gapstate, guard
from collector.pillars import ai, findings

NOW = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.timezone.utc)


def record(slug, *, messages=0, users=0, tokens=0, categories=None, tenant=None, objects=(),
           investigations=None, days=0):
    tenant = tenant or {"skills": 0, "rules": 0, "automations": 0, "integrations": 0}
    from collector.sources.assistant import summarise_stack
    hero = {"totalUserMessages": messages, "totalActiveUsers": users, "totalTokens": tokens,
            "totalChatTokens": tokens, "totalInvestigationTokens": 0,
            "totalInvestigationsCreated": sum((investigations or {}).values())}
    return summarise_stack(slug, hero, categories or {},
                           {f"{k} (created)": v for k, v in (investigations or {}).items()},
                           days, tenant, list(objects))


def stack(slug, status="active"):
    return {"slug": slug, "status": status, "regionSlug": "prod-eu-west-2", "currentActiveUsers": 3}


def coverage(total=4, scanned=3):
    cov = Coverage(tier="t2", total=total)
    for i in range(scanned):
        cov.record_ok(f"s{i}")
    return cov


class NoInputTest(unittest.TestCase):
    def test_a_tier_without_the_input_emits_and_publishes_nothing(self):
        """Zeros here would overwrite the gathering tier's real figures on the next write."""
        for payload in (None, {}):
            metrics, views = ai.build([stack("a")], coverage(), payload, now=NOW)
            self.assertEqual(metrics, [])
            self.assertEqual(views, {})


class PerStackMetricsTest(unittest.TestCase):
    def setUp(self):
        self.stacks = [stack("busy"), stack("quiet"), stack("nocred"), stack("sleepy", "paused")]
        self.data = {
            "busy": record("busy", messages=400, users=4, tokens=200_000_000,
                           categories={"Learn (web)": 10, "Learn (cli)": 30}, days=20),
            "quiet": record("quiet", messages=0, users=0),
        }
        self.metrics, self.views = ai.build(self.stacks, coverage(), self.data, now=NOW)
        self.by_name = {}
        for name, labels, value in self.metrics:
            self.by_name.setdefault(name, {})[labels.get("stack") or None] = value

    def test_messages_are_emitted_for_every_measured_stack_including_a_zero(self):
        """An absent series must keep meaning 'not measured', never 'not used'."""
        self.assertEqual(self.by_name["gcinsight_ai_messages"], {"busy": 400.0, "quiet": 0.0})

    def test_no_series_at_all_for_a_stack_that_produced_no_data(self):
        for name in ("gcinsight_ai_messages", "gcinsight_ai_tokens_per_active_user"):
            self.assertNotIn("nocred", self.by_name.get(name, {}))
            self.assertNotIn("sleepy", self.by_name.get(name, {}))

    def test_tokens_per_user_is_absent_where_the_ratio_is_undefined(self):
        """A zero would rank a dormant stack as the most efficient in the estate."""
        ratios = self.by_name["gcinsight_ai_tokens_per_active_user"]
        self.assertIn("busy", ratios)
        self.assertNotIn("quiet", ratios)

    def test_machine_share_is_absent_where_nothing_was_categorised(self):
        shares = self.by_name["gcinsight_ai_machine_share"]
        self.assertEqual(shares["busy"], 0.75)
        self.assertNotIn("quiet", shares)

    def test_exactly_three_per_stack_metrics_are_emitted(self):
        """Three per-stack metrics, deliberately. A fourth is a budget decision, not a code change."""
        per_stack = {n for n, labels, _ in self.metrics if "stack" in labels}
        self.assertEqual(per_stack, {
            "gcinsight_ai_messages",
            "gcinsight_ai_tokens_per_active_user",
            "gcinsight_ai_machine_share",
        })

    def test_assistant_users_per_stack_is_deliberately_not_emitted(self):
        """`grafanacloud-usage` already carries it against `stack_id` - a panel beats a pipeline."""
        self.assertNotIn("gcinsight_ai_users", self.by_name)
        self.assertNotIn("gcinsight_ai_active_users", self.by_name)

    def test_category_and_surface_never_appear_on_a_per_stack_series(self):
        for name, labels, _ in self.metrics:
            if "stack" in labels:
                self.assertEqual(set(labels), {"stack"}, name)

    def test_the_batch_passes_the_label_guard_and_the_duplicate_guard(self):
        guard.check_all(self.metrics)
        guard.check_no_duplicates(self.metrics)


class EstateRollupTest(unittest.TestCase):
    def setUp(self):
        self.data = {
            "a": record("a", messages=100, users=2, tokens=50,
                        categories={"Learn (web)": 10, "Learn (cli)": 5},
                        investigations={"assistant": 3, "user": 1},
                        tenant={"skills": 2, "rules": 1, "automations": 0, "integrations": 0}),
            "b": record("b", messages=50, users=1, tokens=10, categories={"Learn (web)": 5}),
        }
        self.metrics, self.views = ai.build([stack("a"), stack("b")], coverage(), self.data, now=NOW)
        self.flat = {(n, tuple(sorted(l.items()))): v for n, l, v in self.metrics}

    def test_category_surface_is_summed_across_the_estate_with_no_stack_label(self):
        self.assertEqual(self.flat[("gcinsight_ai_estate_messages",
                                    (("category", "Learn"), ("surface", "web")))], 15.0)
        self.assertEqual(self.flat[("gcinsight_ai_estate_messages",
                                    (("category", "Learn"), ("surface", "cli")))], 5.0)

    def test_the_uncategorised_remainder_is_its_own_series(self):
        # 150 messages, 20 categorised.
        self.assertEqual(self.flat[("gcinsight_ai_estate_messages_uncategorised", ())], 130.0)

    def test_combination_count_is_emitted_as_a_drift_detector(self):
        self.assertEqual(self.flat[("gcinsight_ai_estate_category_combos", ())], 2.0)

    def test_stack_population_counts(self):
        self.assertEqual(self.flat[("gcinsight_ai_estate_stacks", (("kind", "measured"),))], 2.0)
        self.assertEqual(self.flat[("gcinsight_ai_estate_stacks", (("kind", "with_usage"),))], 2.0)
        self.assertEqual(
            self.flat[("gcinsight_ai_estate_stacks", (("kind", "with_tenant_config"),))], 1.0)

    def test_tenant_objects_and_investigations_are_split_by_kind(self):
        self.assertEqual(self.flat[("gcinsight_ai_estate_tenant_objects", (("kind", "skills"),))], 2.0)
        self.assertEqual(
            self.flat[("gcinsight_ai_estate_tenant_objects", (("kind", "automations"),))], 0.0)
        self.assertEqual(
            self.flat[("gcinsight_ai_estate_investigations", (("kind", "assistant"),))], 3.0)


class CredentialCoverageTest(unittest.TestCase):
    def setUp(self):
        self.stacks = [stack("ok"), stack("missing"), stack("sleepy", "paused"), stack("declined")]
        self.data = {"ok": record("ok", messages=1, users=1)}

    def test_paused_and_opted_out_stacks_are_not_gaps(self):
        """Counting the estate's automated-test leftovers as missing holds the alert on for ever."""
        self.assertEqual(ai.missing_slugs(self.stacks, self.data, ("declined",)), ["missing"])

    def test_no_gaps_without_the_input_at_all(self):
        self.assertEqual(ai.missing_slugs(self.stacks, None), [])

    def test_the_count_is_emitted_and_the_age_is_the_alert(self):
        gaps = {"missing": (NOW - dt.timedelta(days=3)).isoformat()}
        metrics, _ = ai.build(self.stacks, coverage(), self.data, opted_out=("declined",),
                              gap_first_seen=gaps, now=NOW)
        flat = {n: v for n, l, v in metrics if not l}
        self.assertEqual(flat["gcinsight_stacks_missing_credential"], 1.0)
        self.assertEqual(flat["gcinsight_stacks_provisioned"], 1.0)
        self.assertEqual(flat["gcinsight_missing_credential_age_seconds"], 3 * 86400.0)

    def test_the_age_is_absent_when_there_is_no_gap(self):
        """A zero is indistinguishable from a gap that started this instant - the moment not to fire."""
        metrics, _ = ai.build([stack("ok")], coverage(), self.data, now=NOW)
        self.assertNotIn("gcinsight_missing_credential_age_seconds", {n for n, _, _ in metrics})

    def test_a_stamp_for_a_healed_stack_cannot_inflate_the_age(self):
        gaps = {"missing": NOW.isoformat(), "ok": (NOW - dt.timedelta(days=99)).isoformat()}
        metrics, _ = ai.build(self.stacks, coverage(), self.data, opted_out=("declined",),
                              gap_first_seen=gaps, now=NOW)
        flat = {n: v for n, l, v in metrics if not l}
        self.assertEqual(flat["gcinsight_missing_credential_age_seconds"], 0.0)

    def test_the_coverage_view_says_why_and_whether_it_is_actionable(self):
        _, views = ai.build(self.stacks, coverage(), self.data, opted_out=("declined",), now=NOW)
        rows = {r[" Stack"]: r for r in views["ai_credential_coverage"]}
        self.assertTrue(rows["missing"]["Actionable"])
        self.assertFalse(rows["sleepy"]["Actionable"])
        self.assertEqual(rows["sleepy"]["State"], prov.PAUSED)
        self.assertEqual(rows["declined"]["State"], prov.OPTED_OUT)


class FindingViewTest(unittest.TestCase):
    """The four Pillar I views that findings.py consumes must be pre-filtered by this pillar."""

    def setUp(self):
        objects = [
            {"kind": "integrations", "name": "broken", "enabled": True, "authenticationFailed": True},
            {"kind": "rules", "name": "off", "enabled": False},
            {"kind": "skills", "name": "no-enabled-field", "scope": "tenant"},
        ]
        self.data = {
            "raw": record("raw", messages=ai.ENABLEMENT_MESSAGE_FLOOR, users=1),
            "just_under": record("just_under", messages=ai.ENABLEMENT_MESSAGE_FLOOR - 1, users=1),
            "configured": record("configured", messages=500, users=1,
                                 tenant={"skills": 1, "rules": 1, "automations": 0, "integrations": 1},
                                 objects=objects),
            "burner": record("burner", messages=10, users=1, tokens=ai.TOKENS_PER_USER_OUTLIER),
        }
        self.stacks = [stack(s) for s in self.data]
        _, self.views = ai.build(self.stacks, coverage(), self.data, now=NOW)

    def test_enablement_gap_is_thresholded_and_excludes_configured_stacks(self):
        self.assertEqual([r[" Stack"] for r in self.views["ai_enablement_gap"]], ["raw"])

    def test_token_outliers_are_thresholded_at_the_estate_p90(self):
        self.assertEqual([r[" Stack"] for r in self.views["ai_token_outliers"]], ["burner"])

    def test_mcp_auth_failure_is_its_own_filtered_view(self):
        self.assertEqual([r["name"] for r in self.views["ai_mcp_auth_failed"]], ["broken"])

    def test_a_missing_enabled_field_is_unknown_not_disabled(self):
        """Skills carry no `enabled` at all; treating absent as false would invent findings."""
        self.assertEqual([r["name"] for r in self.views["ai_config_disabled"]], ["off"])

    def test_findings_derive_all_four_kinds_from_these_views(self):
        found, totals = findings.derive(self.views)
        self.assertEqual(totals["assistant_no_tenant_config"], 1)
        self.assertEqual(totals["assistant_token_outlier"], 1)
        self.assertEqual(totals["mcp_auth_failed"], 1)
        self.assertEqual(totals["assistant_config_disabled"], 1)
        self.assertTrue(all(f["pillar"] == "I" for f in found if f["kind"].startswith(("assistant", "mcp"))))

    def test_an_empty_finding_view_is_a_measured_zero_not_an_absent_series(self):
        """Every stack's integrations were read, so nothing failing IS the answer."""
        _, views = ai.build([stack("a")], coverage(), {"a": record("a", messages=1, users=1)}, now=NOW)
        _, totals = findings.derive(views)
        self.assertEqual(totals["mcp_auth_failed"], 0)
        self.assertIn(("gcinsight_findings", {"kind": "mcp_auth_failed"}, 0.0),
                      findings.metrics(totals))


class ViewShapeTest(unittest.TestCase):
    def setUp(self):
        self.data = {"a": record("a", messages=3, users=1, tokens=9,
                                 categories={"Learn (web)": 2, "Learn (cli)": 1},
                                 objects=[{"kind": "skills", "name": "s", "scope": "tenant"}])}
        _, self.views = ai.build([stack("a"), stack("b")], coverage(), self.data, now=NOW)

    def test_every_view_keys_the_stack_with_a_leading_space(self):
        for name, rows in self.views.items():
            if name == "ai_summary" or not rows:
                continue
            self.assertIn(" Stack", rows[0], name)

    def test_an_unmeasured_stack_still_gets_a_row_that_says_why(self):
        rows = {r[" Stack"]: r for r in self.views["ai_assistant"]}
        self.assertFalse(rows["b"]["Measured"])
        self.assertEqual(rows["b"]["Why not"], "no_credential")

    def test_category_surface_is_long_form_one_row_per_combination(self):
        rows = self.views["ai_category_surface"]
        self.assertEqual({(r["Category"], r["Surface"], r["Messages"]) for r in rows},
                         {("Learn", "web", 2), ("Learn", "cli", 1)})
        self.assertEqual({r["Human driven"] for r in rows}, {True, False})

    def test_the_summary_states_the_three_boundaries_as_boundaries(self):
        text = " ".join(str(r["Value"]) for r in self.views["ai_summary"])
        self.assertIn("NOT MEASURABLE", text)
        self.assertEqual(text.count("NOT MEASURABLE"), 3)
        self.assertIn("NOT COLLECTED", text)

    def test_the_summary_never_normalises_categories_to_total_messages(self):
        rows = {r[" Metric"]: r["Value"] for r in self.views["ai_summary"]}
        self.assertIn("no category chart may be normalised", str(rows["Of which categorised"]))

    def test_every_view_this_pillar_produces_is_declared_in_the_budget(self):
        declared = {s.name for s in budget.CATALOGUE if s.store == "view"}
        self.assertLessEqual(set(self.views), declared)


class GapStateTest(unittest.TestCase):
    def test_a_persisting_gap_keeps_its_original_stamp(self):
        old = "2026-08-15T00:00:00+00:00"
        self.assertEqual(gapstate.merge({"a": old}, ["a"], NOW)["a"], old)

    def test_a_new_gap_is_stamped_now(self):
        self.assertEqual(gapstate.merge({}, ["a"], NOW)["a"], NOW.isoformat(timespec="seconds"))

    def test_a_healed_or_departed_stack_is_dropped(self):
        """Left behind, it reports an ever-growing age and holds the alert on for ever."""
        self.assertEqual(gapstate.merge({"a": "2026-01-01T00:00:00+00:00"}, [], NOW), {})

    def test_oldest_age_is_none_rather_than_zero_when_there_is_no_gap(self):
        self.assertIsNone(gapstate.oldest_age_seconds({}, NOW))

    def test_oldest_wins(self):
        state = {"a": (NOW - dt.timedelta(hours=1)).isoformat(),
                 "b": (NOW - dt.timedelta(days=5)).isoformat()}
        self.assertEqual(gapstate.oldest_age_seconds(state, NOW), 5 * 86400.0)

    def test_an_unparseable_stamp_is_skipped_not_treated_as_epoch_zero(self):
        self.assertIsNone(gapstate.oldest_age_seconds({"a": "not a date"}, NOW))
        self.assertEqual(gapstate.oldest_age_seconds(
            {"a": "nope", "b": (NOW - dt.timedelta(days=2)).isoformat()}, NOW), 2 * 86400.0)

    def test_a_naive_stamp_is_read_as_utc(self):
        self.assertEqual(
            gapstate.oldest_age_seconds({"a": "2026-08-19T12:00:00"}, NOW), 86400.0)

    def test_a_dry_run_computes_the_state_and_writes_nothing(self):
        calls: list[list[str]] = []

        class Proc:
            returncode = 1
            stdout = ""
            stderr = ""

        def runner(cmd, **kw):
            calls.append(cmd)
            return Proc()

        state = gapstate.update(["a"], bucket="b", now=NOW, dry_run=True, runner=runner)
        self.assertEqual(list(state), ["a"])
        self.assertEqual(len(calls), 1)
        self.assertIn("cp", calls[0])
        self.assertNotIn("--only-show-errors", calls[0])


class ThresholdProvenanceTest(unittest.TestCase):
    """Each threshold sits at a measured point in the estate's own distribution (2026-08-20)."""

    def test_thresholds_are_the_measured_values(self):
        self.assertEqual(ai.ENABLEMENT_MESSAGE_FLOOR, 100)
        self.assertEqual(ai.TOKENS_PER_USER_OUTLIER, 25_000_000)
        self.assertEqual(ai.MACHINE_DRIVEN_SHARE, 0.5)

    def test_the_declared_finding_kind_count_covers_the_real_one(self):
        self.assertGreaterEqual(budget.FINDING_KIND, len(findings.KINDS))


if __name__ == "__main__":
    unittest.main()
