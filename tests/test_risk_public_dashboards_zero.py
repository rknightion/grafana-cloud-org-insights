"""Successful public-dashboard zeroes must clear stale S3 findings."""

from __future__ import annotations

import unittest

from collector.coverage import Coverage
from collector.pillars import risk
from collector.sources import public_dashboards


STACK = {"slug": "alpha", "status": "active"}


def build(public_record):
    coverage = Coverage(tier="t2", total=1)
    coverage.record_ok("alpha")
    return risk.build(
        [STACK],
        coverage,
        public_dashboards={"alpha": public_record},
    )


class SuccessfulZeroTest(unittest.TestCase):
    def test_successful_zero_publishes_an_empty_view_to_clear_stale_findings(self):
        _metrics, views = build({
            "available": True,
            "slug": "alpha",
            "state": public_dashboards.OK,
            "total": 0,
            "listed": 0,
            "enabled": 0,
            "dashboards": [],
        })
        self.assertIn("risk_public_dashboards", views)
        self.assertEqual(views["risk_public_dashboards"], [])

    def test_unavailable_input_withholds_the_view_instead_of_clearing_it(self):
        _metrics, views = build({
            "available": False,
            "slug": "alpha",
            "state": public_dashboards.FORBIDDEN,
            "detail": "HTTP 403",
        })
        self.assertNotIn("risk_public_dashboards", views)


if __name__ == "__main__":
    unittest.main()
