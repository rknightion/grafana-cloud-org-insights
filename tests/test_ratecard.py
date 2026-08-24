"""Rate card: turning measured volume into money, or refusing to.

Every number this produces is money a customer will read, so the loader is deliberately strict. An
unknown dimension, a missing rate or a bad divisor is an ERROR, not a row silently skipped: a rate card
that half-loads produces a currency figure that is quietly too small, which is worse than no figure.
"""

from __future__ import annotations

import unittest

from collector import ratecard

GOOD = """\
dimension,rate,per,unit,included,currency,period,billing_basis,notes
metrics_series,3.37,1000,series,0,USD,month,base_rate_only,"billing line: Metrics"
logs_ingest_gb,0.28,1,GB,0,USD,month,quantity,"Logs Write (Ingest)"
grafana_users,21,1,user,0,USD,month,quantity,
ai_tokens,2,1000000,tokens,0,USD,month,quantity,
"""


class LoadingTest(unittest.TestCase):
    def test_zero_rate_is_rejected_instead_of_pricing_everything_as_free(self):
        with self.assertRaisesRegex(ratecard.InvalidRateCard, "rate.*above zero"):
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,0,1000,series,0,USD,month,base_rate_only,\n"
            )

    def test_a_good_card_loads_every_row(self):
        card = ratecard.loads(GOOD)
        self.assertEqual(card.currency, "USD")
        self.assertEqual(set(card.rates), {"metrics_series", "logs_ingest_gb",
                                          "grafana_users", "ai_tokens"})

    def test_pricing_divides_by_the_per_column(self):
        card = ratecard.loads(GOOD)
        # 120,754 series at $3.37 per 1000
        self.assertAlmostEqual(card.price("metrics_series", 120_754), 406.94, places=2)
        self.assertAlmostEqual(card.price("logs_ingest_gb", 22.5), 6.30, places=2)
        self.assertAlmostEqual(card.price("grafana_users", 811), 17031.0, places=2)
        self.assertAlmostEqual(card.price("ai_tokens", 14_677_233), 29.35, places=2)

    def test_included_usage_is_subtracted_before_pricing(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "logs_ingest_gb,3.37,1,GB,100,USD,month,quantity,\n"
        )
        self.assertAlmostEqual(card.price("logs_ingest_gb", 120.754), 69.94, places=2)

    def test_usage_below_the_included_allowance_costs_nothing(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "logs_ingest_gb,3.37,1,GB,100,USD,month,quantity,\n"
        )
        self.assertEqual(card.price("logs_ingest_gb", 50), 0.0)

    def test_savings_prices_before_minus_after_not_the_reduction_as_a_fresh_bill(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "logs_ingest_gb,1,1,GB,100,USD,month,quantity,\n"
        )
        self.assertEqual(card.savings("logs_ingest_gb", 200, 50), 50.0)

    def test_savings_stops_at_the_included_allowance(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "logs_ingest_gb,1,1,GB,100,USD,month,quantity,\n"
        )
        self.assertEqual(card.savings("logs_ingest_gb", 120, 50), 20.0)

    def test_base_rate_metrics_refuses_an_allowance_without_the_billing_population(self):
        with self.assertRaisesRegex(ratecard.InvalidRateCard, "included.*base-rate"):
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,1,1000,series,100000,USD,month,base_rate_only,\n"
            )

    def test_an_absent_dimension_prices_to_None_not_zero(self):
        """A gap must never read as free. Zero is a measurement; None is 'no rate was given'."""
        card = ratecard.loads(GOOD)
        self.assertIsNone(card.price("traces_ingest_gb", 10))

    def test_pricing_scope_exposes_the_metrics_dpm_limit(self):
        card = ratecard.loads(GOOD)
        self.assertEqual(
            card.pricing_scope("metrics_series"),
            "USD/month; base-rate only; DPM excluded",
        )
        self.assertIsNone(card.pricing_scope("traces_ingest_gb"))

    def test_dpm_aware_metrics_defaults_to_one_included_dpm(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,3.37,1000,series,0,USD,month,dpm_aware,\n"
        )

        self.assertEqual(card.rates["metrics_series"].billing_basis, "dpm_aware")
        self.assertEqual(card.rates["metrics_series"].included_dpm, 1.0)

    def test_dpm_aware_metrics_accepts_the_contract_included_dpm(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
            "metrics_series,3.37,1000,series,0,USD,month,dpm_aware,4,\n"
        )

        self.assertEqual(card.rates["metrics_series"].included_dpm, 4.0)

    def test_dpm_aware_pricing_scope_names_the_contract_divisor(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
            "metrics_series,3.37,1000,series,0,USD,month,dpm_aware,4,\n"
        )

        self.assertEqual(
            card.pricing_scope("metrics_series"),
            "USD/month; DPM-aware; 4 included DPM",
        )

    def test_a_card_with_no_rows_is_not_a_card(self):
        with self.assertRaises(ratecard.InvalidRateCard):
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            )


class RefusalTest(unittest.TestCase):
    def test_dpm_aware_metrics_requires_positive_included_dpm(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
                "metrics_series,3.37,1000,series,0,USD,month,dpm_aware,0,\n"
            )
        self.assertIn("above zero", str(error.exception))

    def test_base_rate_only_refuses_an_included_dpm_value(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
                "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,4,\n"
            )
        self.assertIn("only valid", str(error.exception))

    def test_dpm_aware_metrics_refuses_a_per_stack_included_allowance(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
                "metrics_series,3.37,1000,series,99,USD,month,dpm_aware,4,\n"
            )
        self.assertIn("must be 0", str(error.exception))
        self.assertIn("once per stack", str(error.exception))

    def test_a_blank_unit_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,3.37,1000,,0,USD,month,base_rate_only,\n")
        self.assertIn("unit", str(error.exception).lower())

    def test_a_blank_currency_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,3.37,1000,series,0,,month,base_rate_only,\n")
        self.assertIn("currency", str(error.exception).lower())

    def test_currency_must_be_a_three_letter_code(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,3.37,1000,series,0,DOLLARS,month,base_rate_only,\n"
            )
        self.assertIn("three-letter", str(error.exception))

    def test_non_finite_numeric_fields_are_errors(self):
        for column, row in {
            "rate": "metrics_series,nan,1000,series,0,USD,month,base_rate_only,",
            "per": "metrics_series,3.37,inf,series,0,USD,month,base_rate_only,",
            "included": "metrics_series,3.37,1000,series,-inf,USD,month,base_rate_only,",
        }.items():
            with self.subTest(column=column):
                with self.assertRaises(ratecard.InvalidRateCard) as error:
                    ratecard.loads(
                        "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                        + row + "\n"
                    )
                self.assertIn("finite", str(error.exception).lower())

    def test_an_unknown_dimension_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_serieses,3.37,1000,series,0,USD,month,base_rate_only,\n")
        self.assertIn("metrics_serieses", str(e.exception))
        self.assertIn("metrics_series", str(e.exception), "the error should suggest the real name")

    def test_a_zero_divisor_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard):
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,3.37,0,series,0,USD,month,base_rate_only,\n")

    def test_a_non_numeric_rate_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard):
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,three,1000,series,0,USD,month,base_rate_only,\n")

    def test_a_negative_rate_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard):
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,-3.37,1000,series,0,USD,month,base_rate_only,\n")

    def test_mixed_currencies_are_an_error(self):
        """Summing USD and EUR into one total is the kind of wrong that looks right."""
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,\n"
                           "logs_ingest_gb,0.28,1,GB,0,EUR,month,quantity,\n")
        self.assertIn("currency", str(e.exception).lower())

    def test_a_duplicate_dimension_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard):
            ratecard.loads("dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                           "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,\n"
                           "metrics_series,4.00,1000,series,0,USD,month,base_rate_only,\n")

    def test_a_duplicate_column_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,currency,period,billing_basis,notes\n"
                "metrics_series,3.37,1000,series,0,USD,EUR,month,base_rate_only,\n"
            )
        self.assertIn("duplicate", str(e.exception).lower())
        self.assertIn("currency", str(e.exception).lower())

    def test_a_row_with_more_values_than_the_header_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,note,ignored\n"
            )
        self.assertIn("more values", str(e.exception).lower())

    def test_a_non_empty_row_with_no_dimension_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as error:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                ",3.37,1000,series,0,USD,month,base_rate_only,orphaned price\n"
                "logs_ingest_gb,0.28,1,GB,0,USD,month,quantity,valid row\n"
            )
        self.assertIn("blank dimension", str(error.exception).lower())

    def test_a_delimiter_only_row_is_malformed_not_a_blank_line(self):
        with self.assertRaisesRegex(ratecard.InvalidRateCard, "blank dimension"):
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                ",,,,,,,,\n"
                "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,valid\n"
            )

    def test_a_missing_required_column_is_an_error(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads("dimension,rate,unit\nmetrics_series,3.37,series\n")
        self.assertIn("per", str(e.exception))

    def test_included_is_a_required_column(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,currency,period,billing_basis,notes\n"
                "metrics_series,3.37,1000,series,USD,month,base_rate_only,\n"
            )
        self.assertIn("included", str(e.exception))

    def test_period_is_a_required_column(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,billing_basis,notes\n"
                "metrics_series,3.37,1000,series,0,USD,base_rate_only,\n"
            )
        self.assertIn("period", str(e.exception))

    def test_only_monthly_rates_are_supported(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,40.44,1000,series,0,USD,year,base_rate_only,\n"
            )
        self.assertIn("month", str(e.exception))
        self.assertIn("year", str(e.exception))

    def test_billing_basis_is_a_required_column(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,notes\n"
                "metrics_series,3.37,1000,series,0,USD,month,\n"
            )
        self.assertIn("billing_basis", str(e.exception))

    def test_metrics_series_refuses_an_unrecognised_dpm_basis(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,3.37,1000,series,0,USD,month,dpm_adjusted,\n"
            )
        message = str(e.exception)
        self.assertIn("base_rate_only", message)
        self.assertIn("dpm_aware", message)

    def test_an_unmodelled_dpm_multiplier_column_is_refused_not_ignored(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,dpm_multiplier,notes\n"
                "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,2,\n"
            )
        message = str(e.exception)
        self.assertIn("dpm_multiplier", message)
        self.assertIn("unsupported", message.lower())

    def test_metrics_series_is_explicitly_per_one_thousand_not_per_one(self):
        with self.assertRaises(ratecard.InvalidRateCard) as e:
            ratecard.loads(
                "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
                "metrics_series,3.37,1,series,0,USD,month,base_rate_only,\n"
            )
        message = str(e.exception)
        self.assertIn("1000", message)
        self.assertIn("per", message)

class DimensionContractTest(unittest.TestCase):
    def test_dpm_usage_model_is_a_public_contract(self):
        self.assertTrue(callable(getattr(ratecard, "metrics_usage", None)))

    def test_dpm_usage_defaults_to_one_and_names_a_dpm_dominated_stack(self):
        usage = ratecard.metrics_usage(active_series=100_000, total_dpm=200_000)

        self.assertEqual(getattr(usage, "included_dpm", None), 1.0)
        self.assertEqual(getattr(usage, "dpm_equivalent_series", None), 200_000.0)
        self.assertEqual(getattr(usage, "billable_usage", None), 200_000.0)
        self.assertEqual(getattr(usage, "regime", None), "dpm_dominated")

    def test_dpm_usage_refuses_a_non_positive_contract_divisor(self):
        with self.assertRaisesRegex(ValueError, "included_dpm"):
            ratecard.metrics_usage(active_series=100_000, total_dpm=200_000, included_dpm=0)

    def test_dpm_usage_refuses_negative_measurements(self):
        with self.assertRaisesRegex(ValueError, "active_series"):
            ratecard.metrics_usage(active_series=-1, total_dpm=200_000)

    def test_dpm_dominated_stack_gets_zero_currency_saving_from_series_reduction(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,1,1000,series,0,USD,month,dpm_aware,\n"
        )
        calculate = getattr(card, "metrics_savings", lambda **_kwargs: None)

        result = calculate(active_series=100_000, total_dpm=200_000, reduction=50_000)

        self.assertEqual(getattr(result, "saving", None), 0.0)
        self.assertEqual(getattr(getattr(result, "before", None), "regime", None), "dpm_dominated")
        self.assertEqual(getattr(getattr(result, "after", None), "regime", None), "dpm_dominated")

    def test_dpm_aware_saving_stops_at_the_dpm_floor(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes\n"
            "metrics_series,1,1000,series,0,USD,month,dpm_aware,4,\n"
        )

        result = card.metrics_savings(
            active_series=200_000,
            total_dpm=400_000,
            reduction=150_000,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.before.regime, "active_series_dominated")
        self.assertEqual(result.after.regime, "dpm_dominated")
        self.assertEqual(result.before.billable_usage, 200_000.0)
        self.assertEqual(result.after.billable_usage, 100_000.0)
        self.assertEqual(getattr(result, "before_cost", None), 200.0)
        self.assertEqual(getattr(result, "after_cost", None), 100.0)
        self.assertEqual(result.saving, 100.0)

    def test_dpm_aware_saving_refuses_a_negative_reduction(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,1,1000,series,0,USD,month,dpm_aware,\n"
        )

        with self.assertRaisesRegex(ValueError, "reduction"):
            card.metrics_savings(
                active_series=200_000,
                total_dpm=100_000,
                reduction=-1,
            )

    def test_dpm_aware_saving_refuses_a_non_finite_reduction(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,1,1000,series,0,USD,month,dpm_aware,\n"
        )

        for reduction in (float("nan"), float("inf")):
            with self.subTest(reduction=reduction):
                with self.assertRaisesRegex(ValueError, "reduction"):
                    card.metrics_savings(
                        active_series=200_000,
                        total_dpm=100_000,
                        reduction=reduction,
                    )

    def test_dpm_aware_card_refuses_two_input_savings_without_total_dpm(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,1,1000,series,0,USD,month,dpm_aware,\n"
        )

        self.assertIsNone(card.savings("metrics_series", before=200_000, reduction=50_000))

    def test_dpm_aware_card_refuses_single_quantity_pricing_without_total_dpm(self):
        card = ratecard.loads(
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "metrics_series,1,1000,series,0,USD,month,dpm_aware,\n"
        )

        self.assertIsNone(card.price("metrics_series", quantity=200_000))

    def test_every_declared_dimension_says_what_measures_it(self):
        """A dimension nothing can compute is a permanently blank currency panel."""
        for name, spec in ratecard.DIMENSIONS.items():
            with self.subTest(dimension=name):
                self.assertTrue(spec.source, f"{name} declares no source")
                self.assertTrue(spec.unit, f"{name} declares no unit")
                self.assertGreater(spec.per, 0, f"{name} declares no fixed divisor")
                self.assertIn(spec.billing_basis, {"quantity", "base_rate_only"})

    def test_the_unedited_example_card_is_refused_as_unpriced(self):
        import pathlib
        p = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ratecard.example.csv"
        self.assertTrue(p.exists(), "the documented example must exist")
        with self.assertRaisesRegex(ratecard.InvalidRateCard, "rate.*above zero"):
            ratecard.loads(p.read_text())

    def test_the_example_card_covers_every_dimension(self):
        """Otherwise a customer copying the example silently loses a priceable dimension."""
        import csv
        import io
        import pathlib
        p = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ratecard.example.csv"
        body = "\n".join(
            line for line in p.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        dimensions = {row["dimension"] for row in csv.DictReader(io.StringIO(body))}
        self.assertEqual(dimensions, set(ratecard.DIMENSIONS))


class CommentsTest(unittest.TestCase):
    """The card is hand-edited and the shipped example documents itself in comments."""

    def test_comment_and_blank_lines_are_ignored(self):
        card = ratecard.loads(
            "# my contracted rates, 2026\n"
            "\n"
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "  # metrics is the big one\n"
            "metrics_series,3.37,1000,series,0,USD,month,base_rate_only,\n"
        )
        self.assertAlmostEqual(card.price("metrics_series", 1000), 3.37, places=2)

    def test_errors_report_the_original_file_line_after_comments_and_blanks(self):
        text = (
            "# deployment rates\n"
            "\n"
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "# metrics follows\n"
            "metrics_series,not-a-rate,1000,series,0,USD,month,base_rate_only,\n"
        )
        with self.assertRaisesRegex(ratecard.InvalidRateCard, r"line 5"):
            ratecard.loads(text)

    def test_multiline_csv_errors_report_the_record_start_line(self):
        text = (
            "dimension,rate,per,unit,included,currency,period,billing_basis,notes\n"
            "# explanatory comment\n"
            "unknown_dimension,1,1,GB,0,USD,month,quantity,\"first line\n"
            "second line\"\n"
        )
        with self.assertRaisesRegex(ratecard.InvalidRateCard, r"line 3"):
            ratecard.loads(text)


if __name__ == "__main__":
    unittest.main()
