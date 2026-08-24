"""Rate card: the customer's own prices, so measured volume can be stated as money.

**Optional by design.** Without a card the platform reports remediable VOLUME and every currency panel
says so. That is the honest default: a contracted rate is not something this code can infer, and a
guessed rate presented as money is worse than no figure at all. With a card, the same volumes become a
currency figure the customer can check against their own invoice.

**Only dimensions this platform actually measures are accepted.** A card is not a copy of the billing
page; it is the subset whose quantity the collector can compute. Accepting a dimension nothing measures
would ship a permanently blank panel and look like a bug.

Strict on purpose. An unknown dimension, a missing column, the wrong fixed divisor, an unsupported
period or two currencies in one file are all errors rather than skipped rows: a card that half-loads
produces a number that is quietly too small, and nobody re-checks a number that looks plausible.

Format, one row per dimension:

    dimension,rate,per,unit,included,currency,period,billing_basis,included_dpm,notes
    metrics_series,3.37,1000,series,0,USD,month,dpm_aware,1,"billing line: Metrics"

- `rate` / `per` are read together: `3.37` per `1000` series. `per` avoids the reader having to
  pre-divide, which is where a factor-of-1000 error comes from. Rates must be positive. Omit a
  dimension that has no contracted positive price; a zero placeholder is unknown, not proof it is
  free.
- `included` is the allowance before anything is chargeable, in the same unit. Most spend-commit
  contracts have none, so `0` is the common case. Metrics requires `0` on both bases: DPM-aware is a
  per-stack contract, while the collector's base-rate-only quantity is a current snapshot rather than
  the monthly billing population needed to decide whether an estate allowance was crossed. Applying
  either allowance here would quietly understate or overstate saving.
- `period` is required and currently only `month` is supported. Annual or usage-window rates are
  rejected instead of being silently relabelled as monthly.
- `billing_basis` is fixed per dimension except Metrics, which accepts `base_rate_only` or
  `dpm_aware`. The former excludes DPM explicitly; the latter applies Grafana Cloud's documented
  `max(active_series, total_dpm / included_dpm)` contract per stack.
- `included_dpm` is valid only for DPM-aware Metrics. Blank defaults to `1`; set the contracted value
  (commonly `1` or `4`) when it differs. It is not an arbitrary multiplier.
- `notes` is free text. Put the billing-page label there so the card can be reconciled by eye.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from typing import Mapping

REQUIRED_COLUMNS = (
    "dimension", "rate", "per", "unit", "included", "currency", "period", "billing_basis",
)
OPTIONAL_COLUMNS = ("included_dpm", "notes")


class InvalidRateCard(RuntimeError):
    """The card was present but could not be trusted. Never downgraded to a warning."""


@dataclass(frozen=True)
class MetricsUsage:
    active_series: float
    total_dpm: float
    included_dpm: float
    dpm_equivalent_series: float
    billable_usage: float
    regime: str


@dataclass(frozen=True)
class MetricsSavings:
    billing_basis: str
    before: MetricsUsage
    after: MetricsUsage
    reduction: float
    before_cost: float
    after_cost: float
    saving: float


def metrics_usage(
    active_series: float, total_dpm: float, included_dpm: float = 1.0,
) -> MetricsUsage:
    """Apply Grafana Cloud's DPM-aware metrics usage contract to one stack."""
    active = float(active_series)
    dpm = float(total_dpm)
    included = float(included_dpm)
    if not math.isfinite(active) or active < 0:
        raise ValueError("active_series must be finite and non-negative")
    if not math.isfinite(dpm) or dpm < 0:
        raise ValueError("total_dpm must be finite and non-negative")
    if not math.isfinite(included) or included <= 0:
        raise ValueError("included_dpm must be finite and above zero")
    equivalent = dpm / included
    if active > equivalent:
        regime = "active_series_dominated"
    elif active < equivalent:
        regime = "dpm_dominated"
    else:
        regime = "balanced"
    return MetricsUsage(
        active_series=active,
        total_dpm=dpm,
        included_dpm=included,
        dpm_equivalent_series=equivalent,
        billable_usage=max(active, equivalent),
        regime=regime,
    )


@dataclass(frozen=True)
class Dimension:
    """A priceable dimension, and what in this platform produces its quantity."""

    unit: str
    source: str
    per: float = 1.0
    billing_basis: str = "quantity"


# The whole contract. Adding a row here means something in the collector can compute that quantity;
# if it cannot, the entry does not belong.
DIMENSIONS: Mapping[str, Dimension] = {
    "metrics_series": Dimension(
        "series", "gcom current active series for base-rate-only; grafanacloud-usage 30-day p95 "
        "active series / total DPM for DPM-aware panels; Adaptive savings",
        per=1000.0, billing_basis="base_rate_only"),
    "graphite_series": Dimension(
        "series", "gcom hmInstanceGraphiteBillingUsage"),
    "logs_ingest_gb": Dimension(
        "GB", "gcom hlInstanceBillingUsage"),
    "logs_retain_gb_month": Dimension(
        "GB-mo", "gcom hlInstanceBillingUsage held for the retention period"),
    "traces_ingest_gb": Dimension(
        "GB", "gcom htInstanceBillingUsage"),
    "profiles_ingest_gb": Dimension(
        "GB", "gcom hpInstanceBillingUsage"),
    "grafana_users": Dimension(
        "user", "gcom billingActiveUsers - the only user count valid for money"),
    "irm_users": Dimension(
        "user", "gcom billingOnCallActiveUsers"),
    "assistant_users": Dimension(
        "user", "grafanacloud-usage grafanacloud_instance_assistant_active_users"),
    "ai_tokens": Dimension(
        "tokens", "grafanacloud-usage grafanacloud_ai_tokens_total_tokens", per=1_000_000.0),
}


@dataclass(frozen=True)
class Rate:
    rate: float
    per: float
    unit: str
    included: float
    period: str
    billing_basis: str
    included_dpm: float | None = None


@dataclass(frozen=True)
class RateCard:
    rates: Mapping[str, Rate]
    currency: str

    def price(self, dimension: str, quantity: float) -> float | None:
        """Cost of `quantity` of `dimension`, or None when the card carries no rate for it.

        None rather than 0.0, always. A dimension the customer did not price is unknown, and rendering
        unknown as free is how a total comes out too low with nothing to show it. DPM-aware Metrics also
        returns None here because one quantity cannot supply both active series and total DPM; use
        `metrics_savings`.
        """
        r = self.rates.get(dimension)
        if r is None:
            return None
        if r.billing_basis == "dpm_aware":
            return None
        chargeable = max(0.0, float(quantity) - r.included)
        return chargeable / r.per * r.rate

    def priced(self) -> tuple[str, ...]:
        return tuple(sorted(self.rates))

    def pricing_scope(self, dimension: str) -> str | None:
        """Human-readable scope for money produced from one rate, or None when it is unpriced.

        This is part of the money contract, not presentation decoration. Every caller must carry the
        chosen Metrics basis and, for DPM-aware pricing, the contracted included-DPM divisor next to
        the number.
        """
        r = self.rates.get(dimension)
        if r is None:
            return None
        if r.billing_basis == "base_rate_only":
            return f"{self.currency}/{r.period}; base-rate only; DPM excluded"
        if r.billing_basis == "dpm_aware" and r.included_dpm is not None:
            return (f"{self.currency}/{r.period}; DPM-aware; "
                    f"{r.included_dpm:g} included DPM")
        return f"{self.currency}/{r.period}; quantity basis"

    def savings(self, dimension: str, before: float, reduction: float) -> float | None:
        """Marginal saving from reducing `before` by `reduction`.

        Included allowance belongs to the billed quantity, not to the saving. Pricing the reduction
        directly subtracts the allowance a second time and can turn a real marginal saving into zero.
        DPM-aware Metrics returns None because it requires `total_dpm`; use `metrics_savings`.
        """
        r = self.rates.get(dimension)
        if r is not None and r.billing_basis == "dpm_aware":
            return None
        current = self.price(dimension, before)
        after = self.price(dimension, max(0.0, float(before) - max(0.0, float(reduction))))
        if current is None or after is None:
            return None
        return max(0.0, current - after)

    def metrics_savings(
        self, *, active_series: float, total_dpm: float, reduction: float,
    ) -> MetricsSavings | None:
        """DPM-aware marginal saving for one stack, including its before/after regimes.

        Returns None unless `metrics_series` is priced with the `dpm_aware` basis. A base-rate card
        keeps using `savings`; a DPM-aware card must never fall back to that two-input calculation.
        `total_dpm` is held constant before and after because the model changes series count only.
        """
        r = self.rates.get("metrics_series")
        if r is None or r.billing_basis != "dpm_aware" or r.included_dpm is None:
            return None
        before = metrics_usage(active_series, total_dpm, r.included_dpm)
        reduction_value = float(reduction)
        if not math.isfinite(reduction_value) or reduction_value < 0:
            raise ValueError("reduction must be finite and non-negative")
        after = metrics_usage(
            max(0.0, float(active_series) - reduction_value),
            total_dpm,
            r.included_dpm,
        )

        def cost(usage: float) -> float:
            return usage / r.per * r.rate

        before_cost = cost(before.billable_usage)
        after_cost = cost(after.billable_usage)
        return MetricsSavings(
            billing_basis=r.billing_basis,
            before=before,
            after=after,
            reduction=reduction_value,
            before_cost=before_cost,
            after_cost=after_cost,
            saving=max(0.0, before_cost - after_cost),
        )


def _suggest(name: str) -> str:
    """Closest known dimension, so a typo names its own fix."""
    import difflib
    m = difflib.get_close_matches(name, list(DIMENSIONS), n=1, cutoff=0.5)
    return f" Did you mean {m[0]!r}?" if m else (
        f" Known dimensions: {', '.join(sorted(DIMENSIONS))}.")


def loads(text: str) -> RateCard:
    """Parse a rate card from CSV text. Raises `InvalidRateCard` on anything it cannot trust.

    `#` comment lines and blank lines are stripped first. This is a file people hand-edit, and the
    shipped example explains each column in comments; without this the first comment is read as the
    header and every column reports missing.
    """
    retained = [
        (lineno, line)
        for lineno, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    body = "\n".join(line for _lineno, line in retained)
    reader = csv.DictReader(io.StringIO(body))
    header = reader.fieldnames or []
    duplicates = sorted({c for c in header if header.count(c) > 1})
    if duplicates:
        raise InvalidRateCard(
            f"rate card has duplicate column(s): {', '.join(duplicates)}. "
            "A duplicate header is ambiguous because CSV keeps only one of the values."
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise InvalidRateCard(
            f"rate card is missing required column(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}."
        )
    unsupported = [c for c in header if c not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS]
    if unsupported:
        extra = (
            " An arbitrary DPM multiplier is not the contract. Use billing_basis='dpm_aware' and "
            "set included_dpm to the contracted divisor."
            if "dpm_multiplier" in unsupported else ""
        )
        raise InvalidRateCard(
            f"rate card has unsupported column(s): {', '.join(unsupported)}. "
            f"Supported: {', '.join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)}.{extra}"
        )

    rates: dict[str, Rate] = {}
    currencies: set[str] = set()
    next_row_index = reader.line_num
    for row in reader:
        # `line_num` points at the LAST physical line consumed. Retain the previous boundary so a quoted
        # multi-line record reports where the record starts, mapped back across removed comments/blanks.
        row_index = next_row_index
        next_row_index = reader.line_num
        if row_index >= len(retained):
            raise InvalidRateCard(
                "could not map a parsed CSV row to its original physical line"
            )
        lineno = retained[row_index][0]
        if None in row:
            raise InvalidRateCard(
                f"line {lineno}: row has more values than the header. Refusing to guess which "
                "field the trailing value belongs to."
            )
        name = (row.get("dimension") or "").strip()
        if not name:
            # Genuinely blank physical lines were removed before DictReader. A row that reaches this
            # point consumed delimiters and is malformed even if every parsed value is empty.
            raise InvalidRateCard(f"line {lineno}: row has a blank dimension")
        if name not in DIMENSIONS:
            raise InvalidRateCard(f"line {lineno}: unknown dimension {name!r}.{_suggest(name)}")
        if name in rates:
            raise InvalidRateCard(f"line {lineno}: dimension {name!r} appears twice")

        def num(col: str, default: str = "") -> float:
            raw = (row.get(col) or default).strip()
            try:
                value = float(raw)
            except ValueError:
                raise InvalidRateCard(
                    f"line {lineno}: {col} for {name!r} is {raw!r}, which is not a number"
                ) from None
            if not math.isfinite(value):
                raise InvalidRateCard(
                    f"line {lineno}: {col} for {name!r} must be finite, not {raw!r}"
                )
            return value

        rate = num("rate")
        per = num("per")
        included = num("included")
        if rate <= 0:
            raise InvalidRateCard(
                f"line {lineno}: rate for {name!r} is {rate:g}; it must be above zero"
            )
        if per <= 0:
            raise InvalidRateCard(
                f"line {lineno}: per for {name!r} is {per}. It is the divisor, so it must be above zero"
            )
        expected_per = DIMENSIONS[name].per
        if per != expected_per:
            raise InvalidRateCard(
                f"line {lineno}: per for {name!r} is {per:g}; expected {expected_per:g}. "
                "The divisor is fixed by the billing dimension so a per-unit/per-thousand mismatch "
                "cannot silently scale money by three orders of magnitude."
            )
        if included < 0:
            raise InvalidRateCard(f"line {lineno}: included for {name!r} is negative")

        unit = (row.get("unit") or "").strip()
        expected = DIMENSIONS[name].unit
        if not unit:
            raise InvalidRateCard(f"line {lineno}: unit for {name!r} is blank; expected {expected!r}")
        if unit != expected:
            raise InvalidRateCard(
                f"line {lineno}: {name!r} is measured in {expected!r}, but the card says {unit!r}. "
                "A unit mismatch is a factor error waiting to happen, so it is refused rather than "
                "coerced."
            )
        cur = (row.get("currency") or "").strip().upper()
        if not cur:
            raise InvalidRateCard(f"line {lineno}: currency for {name!r} is blank")
        if re.fullmatch(r"[A-Z]{3}", cur) is None:
            raise InvalidRateCard(
                f"line {lineno}: currency for {name!r} is {cur!r}; expected a three-letter "
                "currency code such as 'USD'"
            )
        period = (row.get("period") or "").strip().lower()
        if period != "month":
            raise InvalidRateCard(
                f"line {lineno}: period for {name!r} is {period!r}; only 'month' is supported. "
                "Annual and usage-window rates cannot be labelled or aggregated as monthly money "
                "without an explicit conversion contract."
            )
        billing_basis = (row.get("billing_basis") or "").strip().lower()
        expected_basis = DIMENSIONS[name].billing_basis
        allowed_bases = ({expected_basis, "dpm_aware"}
                         if name == "metrics_series" else {expected_basis})
        if billing_basis not in allowed_bases:
            raise InvalidRateCard(
                f"line {lineno}: billing_basis for {name!r} is {billing_basis!r}; expected "
                f"one of {', '.join(repr(v) for v in sorted(allowed_bases))}."
            )
        if name == "metrics_series" and billing_basis == "base_rate_only" and included != 0:
            raise InvalidRateCard(
                f"line {lineno}: included for base-rate {name!r} must be 0; the collector has a "
                "current active-series snapshot, not the monthly billing population needed to apply "
                "an estate allowance without inventing marginal savings"
            )
        included_dpm_raw = (row.get("included_dpm") or "").strip()
        if billing_basis != "dpm_aware" and included_dpm_raw:
            raise InvalidRateCard(
                f"line {lineno}: included_dpm is only valid with billing_basis='dpm_aware', "
                f"not {billing_basis!r}"
            )
        included_dpm = (num("included_dpm", "1")
                        if billing_basis == "dpm_aware" else None)
        if billing_basis == "dpm_aware" and included != 0:
            raise InvalidRateCard(
                f"line {lineno}: included for DPM-aware {name!r} must be 0; the documented "
                "per-stack DPM contract has no allowance, and an estate allowance cannot be "
                "subtracted once per stack"
            )
        if included_dpm is not None and included_dpm <= 0:
            raise InvalidRateCard(
                f"line {lineno}: included_dpm for {name!r} is {included_dpm:g}; it is the DPM "
                "divisor, so it must be above zero"
            )
        currencies.add(cur)
        rates[name] = Rate(
            rate=rate, per=per, unit=expected, included=included, period=period,
            billing_basis=billing_basis, included_dpm=included_dpm,
        )

    if not rates:
        raise InvalidRateCard("rate card has a header but no rows")
    if len(currencies) > 1:
        raise InvalidRateCard(
            f"rate card mixes currencies ({', '.join(sorted(currencies))}). One card, one currency - "
            "summing two into a single total is the kind of wrong that looks right."
        )
    return RateCard(rates=rates, currency=currencies.pop())
