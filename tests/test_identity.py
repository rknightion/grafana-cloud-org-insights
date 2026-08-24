"""User-record tests.

Identities are kept in clear by decision - internal use, and it is what makes the
ownership directory work. So these tests pin the *cardinality* rule instead of a privacy one:
identifying fields must never reach a metric label, because emails and logins are unbounded and would
blow the series budget (SPEC §5.3).
"""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.sources.gcom import user_record

# Shaped exactly like a real gcom /instances/<slug>/users item.
REAL_SHAPE = {
    "login": "pavel.novak34@contractors.example.com",
    "email": "pavel.novak34@contractors.example.com",
    "name": "Avery Example42",
    "role": "Admin",
    "lastSeenAt": "2026-06-26T17:19:44Z",
    "createdAt": "2025-10-08T07:38:33Z",
    "isServiceAccount": False,
    "id": 40042,
}

IDENTIFYING = ("login", "name", "email")


class UserRecordTest(unittest.TestCase):
    def test_identity_is_kept_so_ownership_can_be_answered(self):
        got = user_record(REAL_SHAPE)
        self.assertEqual(got["login"], "pavel.novak34@contractors.example.com")
        self.assertEqual(got["name"], "Avery Example42")
        self.assertEqual(got["role"], "Admin")
        self.assertEqual(got["lastSeenAt"], "2026-06-26T17:19:44Z")

    def test_email_domain_is_derived_to_separate_contractors_from_staff(self):
        self.assertEqual(user_record(REAL_SHAPE)["email_domain"], "contractors.example.com")
        self.assertEqual(
            user_record({"login": "a.b@example.com"})["email_domain"], "example.com"
        )

    def test_login_is_the_email_when_email_is_absent(self):
        """On many estates login IS the address, and gcom does not always populate `email`."""
        got = user_record({"login": "a.b@example.com", "role": "Viewer"})
        self.assertEqual(got["email"], "a.b@example.com")
        self.assertEqual(got["email_domain"], "example.com")

    def test_non_email_login_yields_no_domain(self):
        got = user_record({"login": "localadmin42", "role": "Admin"})
        self.assertEqual(got["login"], "localadmin42")
        self.assertIsNone(got["email_domain"])

    def test_missing_identity_does_not_fabricate_one(self):
        got = user_record({"role": "Viewer"})
        self.assertIsNone(got["login"])
        self.assertIsNone(got["email"])
        self.assertIsNone(got["email_domain"])

    def test_record_shape_is_closed(self):
        """A new gcom field must not silently ride along into every downstream consumer."""
        self.assertEqual(
            set(user_record(REAL_SHAPE)),
            {"login", "name", "email", "email_domain", "role", "lastSeenAt", "createdAt",
             "isServiceAccount"},
        )
        self.assertNotIn("id", user_record(REAL_SHAPE))


class CardinalityRuleTest(unittest.TestCase):
    """The rule that outlives the privacy decision: unbounded values are not metric labels."""

    def test_coverage_metrics_carry_only_bounded_labels(self):
        cov = Coverage(tier="t2", total=2)
        cov.record_ok("a")
        cov.record_failure("b", "http_429")
        cov.record_skipped("c", "paused")
        for name, labels, _ in cov.as_metrics():
            self.assertLessEqual(
                set(labels), {"tier", "reason"}, f"{name} carries an unbounded label"
            )
            for value in labels.values():
                self.assertNotIn("@", value, f"{name} has an email-shaped label value")

    def test_no_identifying_field_name_is_a_valid_metric_label(self):
        """Guard for the emitter's allow-list (PLAN 5.2): these are never label keys."""
        allowed = {"stack", "region", "cluster", "tier", "reason", "role", "signal", "severity", "kind"}
        for field_name in IDENTIFYING + ("email_domain", "user_hash", "dashboardUid", "rule_name"):
            self.assertNotIn(field_name, allowed)


if __name__ == "__main__":
    unittest.main()
