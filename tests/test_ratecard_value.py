"""Money emitted by Pillar F must disclose exactly what the card can represent."""

from __future__ import annotations

import unittest

from collector import ratecard
from collector.coverage import Coverage
from collector.pillars import value


def _inputs():
    stack = {
        "slug": "example",
        "status": "active",
        "hmInstancePromUrl": "https://prometheus.example.invalid",
        "hmInstancePromCurrentActiveSeries": 200_000,
        "billingActiveUsers": 10,
        "currentActiveUsers": 10,
    }
    dataplane = {"example": {"adaptive_metrics": {
        "available": True,
        "adopted": False,
        "rules_applied": 0,
        "recommendations_pending": 1,
        "recommendation_records_total": 1,
        "recommendation_records_with_series_counts": 1,
        "recommendation_records_missing_series_counts": 0,
        "series_counts_complete": True,
        "remediable_series": 50_000,
        "remediable_series_unused": 40_000,
    }}}
    coverage = Coverage(tier="t3", total=1)
    coverage.record_ok("example")
    return [stack], coverage, dataplane


class ValuePricingDisclosureTest(unittest.TestCase):
    def test_priced_rows_say_base_rate_only_and_dpm_excluded(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,\n"
        )

        _, views = value.build(*_inputs(), ratecard=card)
        labels = [str(row[" Metric"]) for row in views["value_savings"]]

        priced = [label for label in labels if "USD/month" in label]
        self.assertEqual(len(priced), 2)
        for label in priced:
            self.assertIn("base-rate", label.lower())
            self.assertIn("DPM excluded", label)
            self.assertNotIn("total", label.lower())

    def test_a_partial_card_without_metrics_series_emits_no_currency_metric(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "logs_ingest_gb,0.28,1,GB,0,USD,month,quantity,\n"
        )

        metrics, views = value.build(*_inputs(), ratecard=card)
        names = {name for name, _, _ in metrics}
        rows = {str(row[" Metric"]): row["Value"] for row in views["value_savings"]}

        self.assertNotIn("gcinsight_value_savings_identified_currency", names)
        self.assertNotIn("gcinsight_value_savings_unused_currency", names)
        self.assertIn("does not price `metrics_series`", str(rows["Savings basis (series volume)"]))

    def test_dpm_aware_card_keeps_pipeline_currency_absent_and_points_to_live_inputs(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,3.37,1000,series,0,USD,month,dpm_aware,\n"
        )

        metrics, views = value.build(*_inputs(), ratecard=card)
        names = {name for name, _, _ in metrics}
        rows = {str(row[" Metric"]): row["Value"] for row in views["value_savings"]}
        note = str(rows["Savings basis (series volume)"])

        self.assertNotIn("gcinsight_value_savings_identified_currency", names)
        self.assertNotIn("gcinsight_value_savings_unused_currency", names)
        self.assertIn("DPM-aware", note)
        self.assertIn("30-day", note)
        self.assertIn("grafanacloud-usage", note)
        self.assertNotIn("does not price `metrics_series`", note)


if __name__ == "__main__":
    unittest.main()
