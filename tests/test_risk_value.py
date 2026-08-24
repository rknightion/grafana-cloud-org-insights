"""Pillars E and F. The recurring defect class here is a gap that renders as a reassuring zero."""

from __future__ import annotations

import json
import pathlib
import unittest

from collector.coverage import Coverage
from collector.emit import guard
from collector.emit.budget import CATALOGUE, CEILING
from collector.pillars import cost, estate, maturity, risk, usage, value
from collector.sources import public_dashboards as pubdash
from collector.sources.gcom import user_record

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"


def _load():
    stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
    dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())
    coverage = Coverage(tier="t3", total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            coverage.record_skipped(str(s["slug"]), "paused")
        else:
            coverage.record_ok(str(s["slug"]))
    return stacks, dataplane, coverage


def _public_dashboards(stacks):
    """Enumeration records shaped like the live API's, including an UNREADABLE stack.

    The unreadable one is the point of the fixture: the endpoint answers 200 with a permission-filtered
    list rather than 403, so a stack that could not be read must contribute to neither the numerator nor
    the denominator. A fixture where every stack succeeds cannot catch that being got wrong.
    """
    slugs = [str(s["slug"]) for s in stacks if s.get("status") != "paused"]
    out = {}
    for i, slug in enumerate(slugs):
        if i == 0:
            out[slug] = {"available": True, "slug": slug, "state": pubdash.OK, "total": 3,
                         "listed": 3, "enabled": 2,
                         "dashboards": [{"title": "Ops", "dashboard_uid": "u1", "enabled": True},
                                        {"title": "Costs", "dashboard_uid": "u2", "enabled": True},
                                        {"title": "Old", "dashboard_uid": "u3", "enabled": False}]}
        elif i == 1:
            out[slug] = {"available": False, "slug": slug, "state": pubdash.FORBIDDEN,
                         "detail": "HTTP 403"}
        else:
            out[slug] = {"available": True, "slug": slug, "state": pubdash.OK, "total": 0,
                         "listed": 0, "enabled": 0, "dashboards": []}
    return out


def _detail():
    users = json.loads((TESTDATA / "gcom-instance-users.json").read_text())["items"]
    return {"obs-hub": {
        "slug": "obs-hub",
        "users": [user_record(u) for u in users],
        "plugins": [
            {"pluginSlug": "yesoreyeram-infinity-datasource", "version": "3.0.0",
             "latestVersion": "3.2.1"},
            {"pluginSlug": "grafana-gitlab-datasource", "version": "1.1.0", "latestVersion": "1.1.0"},
        ],
    }}


def _service_accounts():
    return {"obs-hub": {
        # `ok` means the separate per-stack read really happened, so an empty account list means
        # "none". Anything else means NOT MEASURED and must not render as 0 (PLAN 18.13).
        "state": "ok",
        "accounts": [
            {"name": "extsvc-app1", "kind": "extsvc", "role": "Viewer", "tokens": 1,
             "isDisabled": False},
            {"name": "extsvc-app2", "kind": "extsvc", "role": "Viewer", "tokens": 1,
             "isDisabled": False},
            {"name": "platform.operator", "kind": "custom", "role": "Admin", "tokens": 19,
             "isDisabled": False},
            {"name": "adaptive-telemetry-reporter", "kind": "custom", "role": "Viewer", "tokens": 1,
             "isDisabled": False},
        ],
    }}


def _complete_savings_dataplane(stack, *, remediable=90, unused=70):
    return {str(stack["slug"]): {"adaptive_metrics": {
        "available": True,
        "rules_applied": 0,
        "adopted": False,
        "recommendations_available": True,
        "recommendations_pending": 2,
        "recommendation_records_total": 2,
        "recommendation_records_with_series_counts": 2,
        "recommendation_records_missing_series_counts": 0,
        "series_counts_complete": True,
        "remediable_series": remediable,
        "remediable_series_unused": unused,
    }}}


class RiskTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane, cls.coverage = _load()
        cls.metrics, cls.views = risk.build(
            cls.stacks, cls.coverage, cls.dataplane, _detail(),
            access_policies=[{"name": "gcinsight", "realms": [{"type": "org"}],
                              "scopes": ["set:cloud-admin"], "createdAt": "2026-08-01"}],
            public_dashboards=_public_dashboards(cls.stacks),
            service_accounts=_service_accounts(),
        )
        cls.by = {(n, tuple(sorted(labels.items()))): v for n, labels, v in cls.metrics}

    def test_public_dashboards_are_words_not_a_zero(self):
        """The summary row stays words even now that the count is measurable.

        Pillar E enumerates them as of PLAN 18.17, so the old "cannot see it" reasoning is gone - but
        the row still carries no number, for a reason that is now structural rather than a capability
        gap. Putting the count HERE makes `risk_summary` depend on the `public_dashboards` input, and
        the derivation test proves it: a late per-stack sweep would then withhold the ENTIRE governance
        summary rather than one figure. The count lives in its own panels and its own view.

        A 0 in this cell would still read as a complete inventory when the input was unavailable.
        """
        row = [r for r in self.views["risk_summary"]
               if r[" Metric"] == "Configured public dashboards"][0]
        self.assertEqual(row[" Metric"], "Configured public dashboards")
        value = str(row["Value"])
        self.assertNotEqual(row["Value"], 0)
        self.assertIn("Public dashboards tab", value,
                      "the row must name where the count actually lives")
        # Not a number, of any type. An HTTP status inside the explanation is a fact and is fine; a
        # numeric VALUE is the thing that reads as a compliance verdict.
        self.assertNotIsInstance(row["Value"], (int, float))
        names = {n for n, _, _ in self.metrics}
        self.assertNotIn("gcinsight_risk_public_dashboards_total", names,
                         "the retired metric name must never be emitted - the _enumerated family "
                         "replaced it, and the old name is kept declared only as a record")
        # The enumerated family IS emitted, and every count ships with its denominator.
        for suffix in ("measured", "enumerated", "enabled", "stacks"):
            self.assertIn(f"gcinsight_risk_public_dashboards_{suffix}", names)

    def test_public_dashboard_counts_only_sum_readable_stacks(self):
        """The endpoint answers 200 with a permission-FILTERED list rather than 403, so an unreadable
        stack must contribute to neither side. Counting it as zero would report a breach as compliance.
        """
        measured = self.by[("gcinsight_risk_public_dashboards_measured", ())]
        enumerated = self.by[("gcinsight_risk_public_dashboards_enumerated", ())]
        enabled = self.by[("gcinsight_risk_public_dashboards_enabled", ())]
        stacks = self.by[("gcinsight_risk_public_dashboards_stacks", ())]
        readable = [
            record for record in _public_dashboards(self.stacks).values()
            if record.get("state") in pubdash.READABLE
        ]
        self.assertEqual(measured, len(readable))
        self.assertEqual(enumerated, sum(record["total"] for record in readable))
        self.assertEqual(enabled, sum(record["enabled"] for record in readable))
        self.assertEqual(stacks, sum(record["total"] > 0 for record in readable))
        self.assertGreater(measured, 0, "a zero denominator must not publish a zero numerator")
        self.assertLessEqual(enabled, enumerated, "enabled is a subset of what exists")
        self.assertLessEqual(stacks, measured, "cannot find breaches on more stacks than were read")
        self.assertLessEqual(stacks, enumerated)
        rows = self.views["risk_public_dashboards"]
        self.assertLessEqual(len(rows), enumerated,
                             "the detail can be capped while the scalar count stays complete")
        self.assertTrue(rows, "a measured non-zero inventory must retain actionable detail")
        for r in rows:
            self.assertNotIn("accessToken", r)
            self.assertNotIn("Access token", r)

    def test_departed_payload_entries_do_not_reach_rollups_or_views(self):
        stacks = [self.stacks[0]]
        live_slug = str(stacks[0]["slug"])
        fleet = {
            live_slug: {"available": True, "collectors": 1, "collectors_active": 1,
                        "collectors_inactive": 0, "pipelines": 1, "pipelines_enabled": 1},
            "departed": {"available": True, "collectors": 999, "collectors_active": 999,
                          "collectors_inactive": 0, "pipelines": 999, "pipelines_enabled": 999},
        }
        service_accounts = {
            live_slug: {"state": "ok", "accounts": []},
            "departed": {"state": "ok", "accounts": [
                {"name": "departed-admin", "kind": "custom", "role": "Admin", "tokens": 50}
            ]},
        }
        routing = {
            live_slug: {"available": True, "state": "ok", "slug": live_slug, "rules_total": 1},
            "departed": {"available": True, "state": "ok", "slug": "departed", "rules_total": 999},
        }

        metrics, views = risk.build(
            stacks, self.coverage, fleet=fleet, service_accounts=service_accounts,
            alert_routing=routing,
        )
        by_name = {name: value for name, labels, value in metrics if not labels}
        self.assertEqual(by_name["gcinsight_risk_collectors_total"], 1.0)
        self.assertEqual(by_name["gcinsight_risk_alert_rules_total"], 1.0)
        self.assertNotIn("departed", repr(views))
        self.assertFalse(any(labels.get("stack") == "departed" for _n, labels, _v in metrics))

    def test_partial_hourly_fleet_input_falls_back_per_stack_for_rows_and_totals(self):
        stacks = self.stacks[:2]
        first, second = (str(stack["slug"]) for stack in stacks)
        current = {
            first: {"available": True, "collectors": 2, "pipelines": 1,
                    "provisioned_but_empty": False},
        }
        legacy = {
            second: {"fleet": {"available": True, "collectors": 3, "pipelines": 1,
                               "provisioned_but_empty": False}},
        }

        metrics, views = risk.build(stacks, self.coverage, dataplane=legacy, fleet=current)
        totals = {name: value for name, labels, value in metrics if not labels}
        summary = {row[" Metric"]: row["Value"] for row in views["risk_summary"]}

        self.assertEqual(totals["gcinsight_risk_collectors_total"], 5.0)
        self.assertEqual(summary["Collectors registered org-wide"], 5)

    def test_fleet_management_dead_count_matches_the_findings_register(self):
        self.assertEqual(self.by[("gcinsight_risk_stacks_pipelines_no_collectors", ())], 77.0)
        self.assertEqual(len(self.views["risk_fleet_dead"]), 77)

    def test_collector_total_matches_the_findings_register(self):
        self.assertEqual(self.by[("gcinsight_risk_collectors_total", ())], 2019.0)

    def test_fleet_attributes_and_pipeline_reach_are_published_as_named_views(self):
        fleet = {"obs-hub": {
            "available": True,
            "collectors": 3,
            "collectors_active": 2,
            "collectors_inactive": 1,
            "pipelines": 1,
            "pipelines_enabled": 1,
            "attributes": {
                "collector.version": {"values": {"v1.2.3": 2}, "distinct": 1},
                "collector.os": {"values": {"linux": 2}, "distinct": 1},
            },
            "pipeline_detail": [{
                "name": "default",
                "enabled": True,
                "matchers": ['collector.os="linux"'],
                "source_type": "SOURCE_TYPE_GRAFANA",
                "config_type": "alloy",
                "targeted": 2,
                "targeted_enabled": 2,
                "updated_at": "2026-08-20T12:00:00Z",
            }],
        }}
        _, views = risk.build(self.stacks, self.coverage, fleet=fleet)

        attributes = views["risk_fleet_attributes"]
        self.assertIn({
            " Stack": "obs-hub",
            "Attribute": "collector.version",
            "Value": "v1.2.3",
            "Active collectors": 2,
            "Distinct values": 1,
            "Truncated": False,
        }, attributes)
        pipelines = views["risk_fleet_pipelines"]
        self.assertEqual(pipelines[0]["Pipeline"], "default")
        self.assertEqual(pipelines[0]["Collectors targeted"], 2)
        self.assertEqual(pipelines[0]["Matchers"], 'collector.os="linux"')

    def test_finding_views_project_only_the_fields_their_consumers_use(self):
        """An unrelated source must not become a freshness dependency through a shared wide row."""
        expected = {
            "risk_admin_sprawl": {
                " Stack", "Region", "Users (active)", "Admins", "Admin share %",
                "Delete protection", "Alert rules", "Active series",
            },
            "risk_delete_protection": {
                " Stack", "Region", "Users (active)", "Admins", "Admin share %",
                "Delete protection", "Alert rules", "Active series",
            },
            "risk_fleet_dead": {
                " Stack", "Region", "Collectors", "Collectors (active)",
                "Collectors (inactive)", "Inactive %", "Pipelines", "Pipelines (enabled)",
                "FM dead", "Alert rules", "Active series",
            },
        }
        for view, columns in expected.items():
            with self.subTest(view=view):
                self.assertTrue(self.views[view])
                self.assertEqual(set(self.views[view][0]), columns)

    def test_admin_sprawl_is_led_by_the_biggest_stack(self):
        """The synthetic largest stack has 15 of 16 admins while carrying the largest metrics share.

        The fixture says 15 admins of 16 users, the 16th a Viewer. Pinned here so the calculation
        cannot drift while avoiding a source-estate stack name in the published test.
        """
        rows = self.views["risk_admin_sprawl"]
        self.assertEqual(rows[0][" Stack"], "stack094")
        self.assertEqual(rows[0]["Admins"], 15)
        self.assertEqual(rows[0]["Users (active)"], 16)
        self.assertEqual(rows[0]["Admin share %"], 93.8)
        self.assertFalse(rows[0]["Delete protection"])
        self.assertEqual(rows[0]["Alert rules"], 2)

    def test_median_admin_share_shows_this_is_estate_wide_not_one_stack(self):
        row = [r for r in self.views["risk_summary"] if r[" Metric"] == "Median admin share %"][0]
        self.assertGreaterEqual(row["Value"], 40.0)

    def test_admin_share_is_none_for_a_stack_with_no_users(self):
        nousers = [r for r in self.views["risk"] if r["Users (active)"] == 0]
        self.assertTrue(nousers)
        for r in nousers:
            self.assertIsNone(r["Admin share %"])

    def test_auto_provisioned_service_accounts_are_classified_not_counted_together(self):
        """19 of 24 on the sampled stack are extsvc-*; they drown the one that matters."""
        self.assertEqual(self.by[("gcinsight_risk_service_accounts_total", (("kind", "extsvc"),))], 2.0)
        self.assertEqual(self.by[("gcinsight_risk_service_accounts_total", (("kind", "custom"),))], 2.0)

    def test_the_token_hoarding_admin_sa_is_flagged_first(self):
        rows = self.views["risk_service_accounts"]
        self.assertEqual(rows[0]["Service account"], "platform.operator")
        self.assertEqual(rows[0]["Tokens"], 19)
        self.assertEqual(rows[0]["Flag"], "admin with many tokens")

    def test_an_extsvc_account_is_never_flagged_however_many_tokens(self):
        flagged = [r for r in self.views["risk_service_accounts"] if r["Flag"]]
        for r in flagged:
            self.assertEqual(r["Kind"], "custom")

    def test_plugin_drift_compares_installed_against_latest(self):
        rows = self.views["risk_plugin_drift"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Plugin"], "yesoreyeram-infinity-datasource")
        self.assertEqual(self.by[("gcinsight_risk_plugin_drift_stacks", ())], 1.0)

    def test_service_account_names_never_become_labels(self):
        for name, labels, _ in self.metrics:
            for v in labels.values():
                self.assertNotIn("platform.operator", v)
                self.assertNotIn("extsvc-", v)

    def test_t1_absent_reads_as_needs_a_scan_not_as_zero(self):
        stacks, _, coverage = _load()
        metrics, views = risk.build(stacks, coverage)
        row = [r for r in views["risk_summary"] if "zero collectors" in r[" Metric"]][0]
        self.assertEqual(row["Value"], "needs a T1 scan")
        self.assertNotIn("gcinsight_risk_stacks_pipelines_no_collectors", {n for n, _, _ in metrics})

    def test_every_unreadable_state_is_unmeasurable_not_zero(self):
        """A 0 here publishes "no service-account sprawl org-wide". Every non-`ok` state must withhold.

        `truncated` is in this list deliberately: a short list is worse than no list, because it reads
        as good hygiene. So is `not_gathered`, which is what a hydrated pre-18.13 record looks like.
        """
        stacks, dataplane, coverage = _load()
        for state in sorted(risk.SA_STATE_LABEL):
            with self.subTest(state=state):
                service_accounts = {"obs-hub": {"accounts": [], "state": state}}
                metrics, views = risk.build(
                    stacks, coverage, dataplane, _detail(), service_accounts=service_accounts
                )
                self.assertNotIn("gcinsight_risk_service_accounts_total",
                                 {n for n, _, _ in metrics})
                self.assertNotIn(
                    "risk_service_accounts", views,
                    "an all-unreadable security inventory must be withheld, not published empty",
                )
                row = [r for r in views["risk"] if r[" Stack"] == "obs-hub"][0]
                self.assertIsNone(row["Service accounts"])
                self.assertIsNone(row["SA tokens"])
                summary = [r for r in views["risk_summary"]
                           if r[" Metric"] == "Stacks with service-account detail"][0]
                self.assertIn("NOT MEASURED", str(summary["Value"]))
                self.assertIn(risk.SA_STATE_LABEL[state], str(summary["Value"]),
                              "the row must name the reason, because the repairs differ")

    def test_a_missing_state_field_is_treated_as_not_gathered(self):
        """A service-account record from before this change must not read as a measured zero."""
        stacks, dataplane, coverage = _load()
        service_accounts = {"obs-hub": {"accounts": []}}
        metrics, views = risk.build(
            stacks, coverage, dataplane, _detail(), service_accounts=service_accounts
        )
        self.assertNotIn("gcinsight_risk_service_accounts_total", {n for n, _, _ in metrics})
        summary = [r for r in views["risk_summary"]
                   if r[" Metric"] == "Stacks with service-account detail"][0]
        self.assertIn(risk.SA_STATE_LABEL["not_gathered"], str(summary["Value"]))

    def test_a_successful_read_of_zero_accounts_is_still_zero(self):
        """The other side of it: genuinely having no service accounts must report 0, not unknown."""
        stacks, dataplane, coverage = _load()
        empty = {"obs-hub": {"accounts": [], "state": "ok"}}
        metrics, views = risk.build(
            stacks, coverage, dataplane, _detail(), service_accounts=empty
        )
        self.assertIn("gcinsight_risk_service_accounts_total", {n for n, _, _ in metrics})
        row = [r for r in views["risk"] if r[" Stack"] == "obs-hub"][0]
        self.assertEqual(row["Service accounts"], 0)

    def test_the_readable_state_set_is_exactly_ok(self):
        """Widening this to include a partial state is how an undercount gets published as a fact."""
        self.assertEqual(risk.SA_READABLE, frozenset({"ok"}))
        self.assertNotIn("ok", risk.SA_STATE_LABEL, "SA_STATE_LABEL is the UNREADABLE vocabulary")

    def test_access_policy_scope_is_surfaced(self):
        row = self.views["risk_access_policies"][0]
        self.assertEqual(row[" Policy"], "gcinsight")
        self.assertIn("set:cloud-admin", row["Scopes"])


class ValueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks, cls.dataplane, cls.coverage = _load()
        cls.metrics, cls.views = value.build(cls.stacks, cls.coverage, cls.dataplane)
        cls.by = {(n, tuple(sorted(labels.items()))): v for n, labels, v in cls.metrics}

    def test_unit_economics_uses_billed_users(self):
        series = sum(s.get("hmInstancePromCurrentActiveSeries") or 0 for s in self.stacks)
        billed = sum(s.get("billingActiveUsers") or 0 for s in self.stacks)
        current = sum(s.get("currentActiveUsers") or 0 for s in self.stacks)
        got = self.by[("gcinsight_value_unit_cost_per_billed_user", ())]
        self.assertEqual(got, round(series / billed, 1))
        self.assertNotEqual(got, round(series / current, 1))

    def test_summary_labels_the_active_user_count_as_not_money(self):
        rows = {r[" Metric"]: r["Value"] for r in self.views["value_summary"]}
        self.assertIn("Billed users (the only figure valid for money)", rows)
        self.assertIn("Active users (adoption, NOT money)", rows)
        self.assertEqual(rows["Billed users (the only figure valid for money)"], 811)
        self.assertEqual(rows["Active users (adoption, NOT money)"], 973)

    def test_without_a_rate_card_the_currency_row_explains_itself(self):
        """A blank savings panel reads as 'no savings available', which is the opposite of the truth.
        No measured figure in the text: it is always on screen and would go stale."""
        _, views = value.build(
            [self.stacks[0]], self.coverage, _complete_savings_dataplane(self.stacks[0])
        )
        rows = {r[" Metric"]: r["Value"] for r in views["value_savings"]}
        note = str(rows["Savings basis (series volume)"])
        self.assertIn("VOLUME, not currency", note)
        self.assertIn("ratecard.csv", note)
        self.assertNotRegex(note, r"\d[\d,]{3,}", "no measured figure in always-on prose")

    def test_without_a_rate_card_no_currency_metric_is_emitted(self):
        """Absent, never zero. A zero would read as 'nothing to save'."""
        metrics, _ = value.build(
            [self.stacks[0]], self.coverage, _complete_savings_dataplane(self.stacks[0])
        )
        names = {n for n, _, _ in metrics}
        self.assertIn("gcinsight_value_savings_identified_series", names)
        self.assertNotIn("gcinsight_value_savings_identified_currency", names)

    def test_incomplete_recommendation_counts_emit_no_savings_values(self):
        """One non-verbose record makes the estate reduction unknown, not a smaller confident total."""
        stack = self.stacks[0]
        incomplete = {str(stack["slug"]): {"adaptive_metrics": {
            "available": True,
            "rules_applied": 0,
            "adopted": False,
            "recommendations_available": True,
            "recommendations_pending": 2,
            "recommendation_records_total": 2,
            "recommendation_records_savings_bearing": 2,
            "recommendation_records_with_series_counts": 1,
            "recommendation_records_missing_series_counts": 1,
            "series_counts_complete": False,
            "remediable_series": 90,
            "remediable_series_unused": 90,
        }}}
        metrics, views = value.build([stack], self.coverage, incomplete)

        names = {name for name, _, _ in metrics}
        self.assertNotIn("gcinsight_value_savings_identified_series", names)
        self.assertNotIn("gcinsight_value_savings_unused_series", names)
        self.assertNotIn("gcinsight_value_savings_identified_currency", names)
        rows = {row[" Metric"]: row["Value"] for row in views["value_savings"]}
        self.assertNotIn("Remediable series, applying every recommendation", rows)
        self.assertNotIn("Share of org active series that is remediable %", rows)
        self.assertEqual(
            rows["Savings-bearing add/update records with marginal series counts"], "1 of 2")
        self.assertEqual(
            rows["Savings-bearing add/update records missing marginal series counts"], 1)

    def test_an_unreachable_adaptive_stack_suppresses_the_estate_savings_total(self):
        """A complete subset is still a partial estate total and must not oscillate into view."""
        measured, unavailable = self.stacks[:2]
        dataplane = _complete_savings_dataplane(measured)
        dataplane[str(unavailable["slug"])] = {"adaptive_metrics": {"available": False, "http": 503}}

        metrics, views = value.build([measured, unavailable], self.coverage, dataplane)

        names = {name for name, _, _ in metrics}
        self.assertNotIn("gcinsight_value_savings_identified_series", names)
        rows = {row[" Metric"]: row["Value"] for row in views["value_savings"]}
        self.assertEqual(rows["Stacks with complete recommendation series counts"], "1 of 2 in scope")

    def test_a_paused_complete_payload_cannot_mask_a_live_gap(self):
        active, paused = self.stacks[:2]
        paused = {**paused, "status": "paused"}
        dataplane = _complete_savings_dataplane(paused)

        metrics, views = value.build([active, paused], self.coverage, dataplane)

        names = {name for name, _labels, _value in metrics}
        self.assertNotIn("gcinsight_value_savings_identified_series", names)
        rows = {row[" Metric"]: row["Value"] for row in views["value_savings"]}
        self.assertEqual(rows["Stacks with complete recommendation series counts"], "0 of 1 in scope")

    def test_remediable_series_comes_from_the_recommendations_not_the_stack_total(self):
        """The old figure summed the WHOLE active-series count of every unadopted stack, which claims
        the entire stack is remediable. The real number is the per-metric reduction."""
        metrics, views = value.build(
            [self.stacks[0]], self.coverage, _complete_savings_dataplane(self.stacks[0])
        )
        rows = {r[" Metric"]: r["Value"] for r in views["value_savings"]}
        remediable = rows["Remediable series, applying every recommendation"]
        org_series = self.stacks[0].get("hmInstancePromCurrentActiveSeries") or 0
        self.assertLessEqual(remediable, org_series,
                             "a reduction cannot exceed the series that exist")
        by = {(n, tuple(sorted(labels.items()))): v for n, labels, v in metrics}
        self.assertEqual(by[("gcinsight_value_savings_identified_series", ())], float(remediable))

    def test_the_review_free_subset_never_exceeds_the_total(self):
        _, views = value.build(
            [self.stacks[0]], self.coverage, _complete_savings_dataplane(self.stacks[0])
        )
        rows = {r[" Metric"]: r["Value"] for r in views["value_savings"]}
        self.assertLessEqual(rows["Remediable series observed unused in the API window"],
                             rows["Remediable series, applying every recommendation"])

    def test_with_a_rate_card_the_savings_become_currency(self):
        from collector import ratecard
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,\n"
        )
        metrics, views = value.build(
            [self.stacks[0]], self.coverage, _complete_savings_dataplane(self.stacks[0]), ratecard=card
        )
        by = {(n, tuple(sorted(labels.items()))): v for n, labels, v in metrics}
        rows = {r[" Metric"]: r["Value"] for r in views["value_savings"]}
        series = by[("gcinsight_value_savings_identified_series", ())]
        self.assertGreater(series, 0, "the fixture declares remediable series")
        priced = by[("gcinsight_value_savings_identified_currency", ())]
        self.assertAlmostEqual(priced, round(series / 1000 * 3.37, 2), places=2)
        self.assertIn(
            "Savings from Adaptive Metrics, applying every recommendation "
            "(USD/month; base-rate only; DPM excluded)", rows,
        )

    def test_a_partial_card_names_the_missing_metrics_rate(self):
        """A card for another dimension must not be described as no card or as a priced total."""
        from collector import ratecard
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "logs_ingest_gb,0.28,1,GB,0,USD,month,quantity,\n"
        )
        metrics, views = value.build(
            [self.stacks[0]], self.coverage, _complete_savings_dataplane(self.stacks[0]), ratecard=card
        )

        names = {name for name, _, _ in metrics}
        self.assertNotIn("gcinsight_value_savings_identified_currency", names)
        rows = {row[" Metric"]: row["Value"] for row in views["value_savings"]}
        note = str(rows["Savings basis (series volume)"])
        self.assertIn("does not price `metrics_series`", note)
        self.assertNotIn("has no rate card", note)

    def test_benchmarks_use_median_and_p90_never_a_mean(self):
        """The synthetic extreme stack would define a mean."""
        rows = {r[" Dimension"]: r for r in self.views["value_benchmarks"]}
        self.assertEqual(set(rows), set(value.BENCHMARKS))
        for row in rows.values():
            self.assertNotIn("Mean", row)
            self.assertIn("Median", row)
            self.assertIn("p90", row)
        series = rows["active_series"]
        self.assertLess(series["Median"], series["Worst"] / 10)

    def test_every_benchmark_reports_how_many_stacks_it_covers(self):
        for row in self.views["value_benchmarks"]:
            self.assertIsInstance(row["Stacks with data"], int)
            self.assertGreater(row["Stacks with data"], 0)

    def test_adoption_ratio_is_a_percentage_of_the_estate(self):
        for _, labels, v in [(n, l, v) for n, l, v in self.metrics
                             if n == "gcinsight_value_adoption_ratio"]:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 100.0)

    def test_t3_absent_omits_the_savings_view_entirely(self):
        """Not an empty table  -  a missing one. A T1 run must not overwrite T3's savings figures with
        rows reading 'needs a T3 scan'; last week's real numbers are better than that."""
        stacks, _, coverage = _load()
        metrics, views = value.build(stacks, coverage)
        self.assertNotIn("value_savings", views)
        self.assertIn("value_summary", views)
        self.assertIn("value_benchmarks", views)
        self.assertNotIn("gcinsight_value_savings_identified_series", {n for n, _, _ in metrics})


class AllPillarsTogetherTest(unittest.TestCase):
    """The integration check that matters: six pillars, one remote_write batch, one budget."""

    @classmethod
    def setUpClass(cls) -> None:
        stacks, dataplane, coverage = _load()
        detail = _detail()
        service_accounts = _service_accounts()
        cls.metrics = (
            estate.build(stacks, coverage)[0]
            + cost.build(stacks, coverage, dataplane)[0]
            + usage.build(stacks, coverage, detail)[0]
            + maturity.build(stacks, coverage, dataplane, detail)[0]
            + risk.build(stacks, coverage, dataplane, detail,
                         service_accounts=service_accounts)[0]
            + value.build(stacks, coverage, dataplane)[0]
        )

    def test_no_duplicate_series_across_all_six_pillars(self):
        self.assertEqual(guard.check_no_duplicates(self.metrics), len(self.metrics))

    def test_every_label_passes_the_guard(self):
        self.assertEqual(guard.check_all(self.metrics), len(self.metrics))

    def test_every_metric_is_declared_in_the_budget(self):
        declared = {(s.name, tuple(sorted(s.labels))) for s in CATALOGUE if s.store == "mimir"}
        undeclared = {(n, tuple(sorted(l))) for n, l, _ in self.metrics} - declared
        self.assertEqual(undeclared, set(), f"undeclared metrics: {sorted(undeclared)}")

    def test_the_whole_estate_scan_fits_inside_the_series_ceiling(self):
        """The number SPEC §10.2 accepts against, measured on real data rather than declared."""
        self.assertLessEqual(len(self.metrics), CEILING,
                             f"{len(self.metrics)} series emitted, ceiling {CEILING}")

    def test_actual_emission_is_within_every_declared_cardinality(self):
        declared = {(s.name, tuple(sorted(s.labels))): s for s in CATALOGUE if s.store == "mimir"}
        actual: dict[tuple, int] = {}
        for n, l, _ in self.metrics:
            key = (n, tuple(sorted(l)))
            actual[key] = actual.get(key, 0) + 1
        for key, count in actual.items():
            self.assertLessEqual(count, declared[key].series,
                                 f"{key[0]} emitted {count}, declared {declared[key].series}")


class AdoptionFloorUnitTest(unittest.TestCase):
    """The unit bug that published "logs 0%, traces 0%" for an estate that is 91% and 84% (PLAN 16.4).

    `SIGNAL_FIELDS` mixes two units. Metrics and Graphite count SERIES (estate max 3.16M); logs, traces
    and profiles are VOLUMES (estate max 16.86 and 1.08). Applying the 1,000-SERIES `USAGE_FLOOR` to a
    field whose estate-wide maximum is 16.86 can only return zero  -  so the adoption panel reported no log
    or trace adoption at all, directly beside its own description saying both were near-universal, and
    beside usage-datasource panels showing 230+ stacks ingesting each.

    These tests are about the UNIT, not about today's numbers, so they use synthetic stacks with the real
    magnitudes rather than pinning a live count that will move.
    """

    def _stacks(self):
        # Magnitudes taken from the real estate: a big metrics stack, and log/trace volumes that are
        # unambiguously real usage but far below 1,000 in their own units.
        return [
            {"slug": "big", "hmInstancePromCurrentUsage": 3_164_653,
             "hlInstanceCurrentUsage": 16.86, "htInstanceCurrentUsage": 1.08},
            {"slug": "modest", "hmInstancePromCurrentUsage": 316,
             "hlInstanceCurrentUsage": 0.9, "htInstanceCurrentUsage": 0.05},
            {"slug": "empty"},
        ]

    def _adoption(self):
        from collector.coverage import Coverage
        from collector.pillars import value
        stacks = self._stacks()
        cov = Coverage(tier="t3", total=len(stacks))
        for s in stacks:
            cov.record_ok(str(s["slug"]))
        _metrics, views = value.build(stacks, cov, {})
        return {r[" Signal"]: r for r in views["value_adoption"]}

    def test_a_volume_signal_below_the_series_floor_still_counts_as_adopted(self):
        """The whole defect in one assertion. 16.86 GB of logs is adoption; 16.86 < 1000 is arithmetic."""
        rows = self._adoption()
        self.assertEqual(rows["logs"]["Stacks using"], 2,
                         "log volumes far below 1,000 are real adoption, not zero")
        self.assertEqual(rows["traces"]["Stacks using"], 2)

    def test_a_signal_nobody_reports_is_still_zero(self):
        """The fix must not turn 'absent' into 'adopted'. Nothing here reports profiles."""
        self.assertEqual(self._adoption()["profiles"]["Stacks using"], 0)

    def test_the_adoption_floor_is_not_the_series_floor(self):
        """Pins the two apart so a future tidy-up cannot collapse them back into one constant."""
        from collector.pillars import value
        from collector.pillars.usage import USAGE_FLOOR
        self.assertNotEqual(value.ADOPTION_FLOOR, USAGE_FLOOR)
        self.assertEqual(value.ADOPTION_FLOOR, 0)

    def test_signals_in_use_counts_volume_signals_too(self):
        """With the series floor this counted only the metrics field, so a full-MELT stack scored 1."""
        from collector.coverage import Coverage
        from collector.pillars import value
        stacks = self._stacks()
        cov = Coverage(tier="t3", total=len(stacks))
        for s in stacks:
            cov.record_ok(str(s["slug"]))
        metrics, _views = value.build(stacks, cov, {})
        by = {tuple(sorted(labels.items())): metric_value
              for name, labels, metric_value in metrics
              if name == "gcinsight_value_benchmark"}
        median = by.get((("kind", "signals_in_use"),))
        self.assertIsNotNone(median, "signals_in_use benchmark is not being emitted")
        self.assertGreaterEqual(
            median, 2.0,
            "a stack shipping metrics, logs and traces must count more than one signal in use")


if __name__ == "__main__":
    unittest.main()
