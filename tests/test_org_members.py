"""Org-level membership governance: clear-PII drill-down and bounded rollups."""

from __future__ import annotations

import datetime as dt
import inspect
import unittest

from collector.coverage import Coverage
from collector.emit import hydrate
from collector.emit.budget import CATALOGUE
from collector.pillars import compose, risk


NOW = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)


def coverage() -> Coverage:
    return Coverage(tier="t1", total=0)


class OrgMembershipGovernanceTest(unittest.TestCase):
    def test_complete_membership_emits_counts_states_and_named_rows(self):
        self.assertIn("org_members", inspect.signature(risk.build).parameters)
        source = {
            "state": "ok",
            "members": [
                {
                    "id": 1, "user_id": 11, "name": "Active Admin",
                    "email": "active@example.test", "login": "active", "role": "Admin",
                    "created_at": "2025-01-01T00:00:00Z", "mfa_enabled": True,
                    "staff_access": {"expires_at": "2027-01-01T00:00:00Z",
                                     "reason": "Support", "ticket_id": "SUP-1"},
                },
                {
                    "id": 2, "user_id": 12, "name": "Direct Admin",
                    "email": "direct@example.test", "login": "direct", "role": "Admin",
                    "created_at": "2025-02-01T00:00:00Z", "mfa_enabled": False,
                    "staff_access": None,
                },
                {
                    "id": 3, "user_id": 13, "name": "Expired Viewer",
                    "email": "viewer@example.test", "login": "viewer", "role": "Viewer",
                    "created_at": "2025-03-01T00:00:00Z", "mfa_enabled": True,
                    "staff_access": {"expires_at": "2026-01-01T00:00:00Z",
                                     "reason": "Expired support", "ticket_id": None},
                },
                {
                    "id": 4, "user_id": 14, "name": "Unknown Window",
                    "email": "unknown@example.test", "login": "unknown", "role": "Editor",
                    "created_at": "2025-04-01T00:00:00Z", "mfa_enabled": None,
                    "staff_access": {"expires_at": None, "reason": None, "ticket_id": None},
                },
            ],
        }

        metrics, views = risk.build([], coverage(), org_members=source, now=NOW)

        values = {(name, tuple(sorted(labels.items()))): value for name, labels, value in metrics}
        self.assertEqual(values[("gcinsight_risk_org_members_admins", ())], 2.0)
        self.assertEqual(values[("gcinsight_risk_org_members_viewers", ())], 1.0)
        self.assertEqual(
            {dict(labels)["status"]: value for (name, labels), value in values.items()
             if name == "gcinsight_risk_org_members_staff_access"},
            {"active": 1.0, "expired": 1.0, "none": 1.0, "unknown": 1.0},
        )
        self.assertEqual([row["Name"] for row in views["risk_org_members"]], [
            "Active Admin", "Direct Admin", "Expired Viewer", "Unknown Window",
        ])
        self.assertEqual(views["risk_org_members"][0], {
            "Name": "Active Admin",
            "Email": "active@example.test",
            "Login": "active",
            "Role": "Admin",
            "MFA enabled": True,
            "Member since": "2025-01-01T00:00:00Z",
            "Staff access": "active",
            "Staff access expires": "2027-01-01T00:00:00Z",
            "Staff access reason": "Support",
            "Staff access ticket": "SUP-1",
        })

    def test_composition_accepts_the_org_level_input(self):
        self.assertIn("org_members", inspect.signature(compose.build_all).parameters)
        metrics, views = compose.build_all(
            [], coverage(), org_members={"state": "ok", "members": []}, now=NOW,
        )
        self.assertIn("gcinsight_risk_org_members_admins", {name for name, _, _ in metrics})
        self.assertEqual(views["risk_org_members"], [])

    def test_absent_or_failed_membership_is_unknown_not_zero(self):
        for source in (None, {}, {"state": "unavailable", "members": []}):
            with self.subTest(source=source):
                metrics, views = risk.build([], coverage(), org_members=source, now=NOW)
                self.assertFalse(
                    {name for name, _, _ in metrics if "org_members" in name},
                    "an unavailable source must not emit confident zero membership counts",
                )
                self.assertNotIn("risk_org_members", views)

    def test_a_malformed_member_makes_the_org_input_unknown(self):
        source = {
            "state": "ok",
            "members": [{"name": "Valid shape", "role": "Admin"}, "not-a-member-record"],
        }

        metrics, views = risk.build([], coverage(), org_members=source, now=NOW)

        self.assertFalse(
            {name for name, _, _ in metrics if "org_members" in name},
            "a partially malformed response must not publish a partial population as complete",
        )
        self.assertNotIn("risk_org_members", views)

    def test_naive_now_is_interpreted_as_utc_for_staff_access(self):
        source = {"state": "ok", "members": [{
            "name": "Active Admin", "role": "Admin",
            "staff_access": {"expires_at": "2027-01-01T00:00:00Z"},
        }]}

        _metrics, views = risk.build(
            [], coverage(), org_members=source, now=NOW.replace(tzinfo=None),
        )

        self.assertEqual(views["risk_org_members"][0]["Staff access"], "active")

    def test_a_successful_empty_org_is_a_measured_zero(self):
        metrics, views = risk.build(
            [], coverage(), org_members={"state": "ok", "members": []}, now=NOW,
        )
        values = {(name, tuple(sorted(labels.items()))): value for name, labels, value in metrics}
        self.assertEqual(values[("gcinsight_risk_org_members_admins", ())], 0.0)
        self.assertEqual(values[("gcinsight_risk_org_members_viewers", ())], 0.0)
        self.assertEqual(
            {dict(labels)["status"]: value for (name, labels), value in values.items()
             if name == "gcinsight_risk_org_members_staff_access"},
            {"active": 0.0, "expired": 0.0, "none": 0.0, "unknown": 0.0},
        )
        self.assertEqual(views["risk_org_members"], [])

    def test_identity_and_governance_verdicts_never_become_metric_labels(self):
        source = {"state": "ok", "members": [{
            "id": 1, "user_id": 11, "name": "Named Person",
            "email": "person@example.test", "login": "person", "role": "Admin",
            "created_at": None, "mfa_enabled": None, "staff_access": None,
        }]}
        metrics, views = risk.build([], coverage(), org_members=source, now=NOW)
        labels = {key for name, ls, _ in metrics if "org_members" in name for key in ls}
        self.assertEqual(labels, {"status"})
        self.assertFalse(labels & {"name", "email", "login", "user", "member"})
        self.assertTrue(all("threshold" not in row and "grade" not in row and "compliance" not in row
                            for row in views["risk_org_members"]))

    def test_membership_is_owned_by_t1_and_guards_its_view(self):
        self.assertEqual(hydrate.INPUT_OWNER.get("org_members"), "t1")
        self.assertEqual(
            hydrate.VIEW_INPUTS.get("risk_org_members"), frozenset({"org_members"}),
        )

    def test_every_membership_output_is_declared_in_the_budget(self):
        declared = {(spec.name, spec.store, tuple(sorted(spec.labels))) for spec in CATALOGUE}
        metrics, views = risk.build(
            [], coverage(), org_members={"state": "ok", "members": []}, now=NOW,
        )
        emitted = {
            (name, "mimir", tuple(sorted(labels)))
            for name, labels, _value in metrics
            if "org_members" in name
        }
        emitted.update(
            (name, "view", ()) for name in views if name == "risk_org_members"
        )
        self.assertTrue(emitted)
        self.assertLessEqual(emitted, declared)


if __name__ == "__main__":
    unittest.main()
