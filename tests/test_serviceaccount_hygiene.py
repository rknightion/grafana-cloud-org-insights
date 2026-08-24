"""Decision-ready service-account token hygiene in Pillar E's S3 inventory."""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import risk
from collector.sources import serviceaccounts as sa


STACKS = [{
    "slug": "alpha",
    "regionSlug": "prod-eu-west-2",
    "currentActiveUsers": 2,
    "currentActiveAdminUsers": 1,
    "deleteProtection": True,
    "alertCnt": 0,
    "hmInstancePromCurrentActiveSeries": 1,
}]
COVERAGE = Coverage(tier="t2", total=1, scanned=1)


def account(
    name: str,
    *,
    kind: str = "custom",
    role: str = "Viewer",
    hygiene_state: str = sa.OK,
    non_expiring: int | None = 0,
    never_used: int | None = 0,
    stale: int | None = 0,
    nearest: str | None = None,
) -> dict:
    return {
        "name": name,
        "kind": kind,
        "role": role,
        "tokens": 1,
        "tokens_state": sa.OK,
        "token_hygiene_state": hygiene_state,
        "tokens_non_expiring": non_expiring,
        "tokens_never_used": never_used,
        "tokens_stale": stale,
        "token_nearest_future_expiry": nearest,
        "isDisabled": False,
    }


def rows(*accounts: dict) -> list[dict]:
    _, views = risk.build(
        STACKS,
        COVERAGE,
        service_accounts={"alpha": {"state": sa.OK, "accounts": list(accounts)}},
    )
    return views["risk_service_accounts"]


class ServiceAccountHygieneViewTest(unittest.TestCase):
    def test_inventory_exposes_the_bounded_token_hygiene_contract(self):
        row = rows(account(
            "automation",
            non_expiring=2,
            never_used=1,
            stale=1,
            nearest="2026-09-01T00:00:00Z",
        ))[0]

        self.assertEqual(row["Non-expiring tokens"], 2)
        self.assertEqual(row["Never-used tokens"], 1)
        self.assertEqual(row[f"Stale live tokens ({sa.TOKEN_STALE_AFTER_DAYS}d)"], 1)
        self.assertEqual(row["Nearest token expiry"], "2026-09-01T00:00:00Z")
        self.assertEqual(row["Token hygiene"], sa.OK)

    def test_unknown_hygiene_never_becomes_zero(self):
        row = rows(account(
            "unknown",
            hygiene_state=sa.PARTIAL_METADATA,
            non_expiring=None,
            never_used=None,
            stale=None,
        ))[0]

        for column in (
            "Non-expiring tokens",
            "Never-used tokens",
            f"Stale live tokens ({sa.TOKEN_STALE_AFTER_DAYS}d)",
            "Nearest token expiry",
        ):
            self.assertIsNone(row[column])
        self.assertEqual(row["Token hygiene"], sa.PARTIAL_METADATA)

    def test_custom_accounts_with_permanent_or_stale_tokens_are_flagged(self):
        permanent, stale = rows(
            account("permanent", non_expiring=1),
            account("stale", stale=1),
        )

        self.assertIn("non-expiring", permanent["Flag"])
        self.assertIn("stale", stale["Flag"])

    def test_a_fresh_never_used_token_is_context_not_a_finding(self):
        row = rows(account("fresh", never_used=1))[0]

        self.assertEqual(row["Never-used tokens"], 1)
        self.assertIsNone(row["Flag"])

    def test_grafana_managed_accounts_are_not_flagged_from_unread_hygiene(self):
        row = rows(account(
            "extsvc-plugin",
            kind="extsvc",
            role="Admin",
            hygiene_state=sa.SKIPPED_EXTSVC,
            non_expiring=None,
            never_used=None,
            stale=None,
        ))[0]

        self.assertIsNone(row["Flag"])


if __name__ == "__main__":
    unittest.main()
