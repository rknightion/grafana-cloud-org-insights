"""BI-inspired aggregate AI cost model and transient live identity detail.

All identity arithmetic runs upstream. History retains its captured allowance/pricing basis;
these live inputs do not retrospectively reconstruct another allowance from compact totals.
"""
from __future__ import annotations

import math

from collector.dashboards import build

_P = 'grafanacloud_ai_tokens_user_total_tokens{user_type="user",__ignore_usage__=""}'
_S = 'grafanacloud_ai_tokens_user_total_tokens{user_type="service",__ignore_usage__=""}'
_U = f"sum by(email) ({_P})"
_PERSONAL_EXCESS = f"sum(clamp_min(({_U}) - (${{personal_allowance:raw}}), 0))"
_SYSTEM_EXCESS = f"clamp_min(sum({_S}) - (${{system_allowance:raw}}), 0)"
_SEATS = f"sum(({_U}) > bool 0)"
_RATE = "(${overage_per_million_usd:raw}) / 1000000"
_SCOPE = (
    "Org-wide at the selected range endpoint; the Stack selector does not change shared allowances "
    "or deduplicated identities. Dated month-to-date gauge observation, not final invoice totals. "
    "Missing inputs remain unavailable. "
)


def variables(seat_price: float = 20) -> list[dict]:
    """Native v2 textbox variables; only the generic/customer seat default differs."""
    if isinstance(seat_price, bool) or not isinstance(seat_price, (int, float)) \
            or not math.isfinite(seat_price) or seat_price < 0:
        raise ValueError("seat price must be finite and nonnegative")
    values = (
        ("seat_price_usd", "Model USD per token-active user", f"{seat_price:g}"),
        ("overage_per_million_usd", "Model USD per million excess tokens", "2"),
        ("personal_allowance", "Live personal allowance (tokens)", "40000000"),
        ("system_allowance", "Live org system allowance (tokens)", "500000000"),
    )
    return [{"kind": "TextVariable", "spec": {
        "name": name, "label": label, "query": value,
        "current": {"text": value, "value": value}, "hide": "dontHide", "skipUrlSync": False,
    }} for name, label, value in values]


def _guard(expr: str, *parameters: str) -> str:
    # Invalid text produces an explicit PromQL query error. Negative, infinite and NaN
    # numeric inputs select no result instead of manufacturing a zero-cost model.
    for name in parameters:
        scalar = "${" + name + ":raw}"
        expr = f"({expr}) and on() (vector({scalar}) >= 0) and on() (vector({scalar}) < +Inf)"
    return expr


def _stat(title: str, expr: str, description: str, *, parameters: tuple[str, ...] = (),
          currency: bool = False) -> dict:
    panel = build.stat_panel(title, _guard(expr, *parameters), description=_SCOPE + description,
                             unit="currencyUSD" if currency else "short",
                             decimals=2 if currency else 0, ds_uid=build.USAGE_UID)
    # Live billing is dense. Instant evaluation avoids resurrecting a formerly available
    # source via range lastNotNull, especially when a month gauge has rolled over.
    query = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
    query.update(instant=True, range=False)
    return panel


def elements(ds: str) -> dict:
    """Return cost-tab elements; ds is the existing private-view Infinity datasource."""
    personal_usd = f"({_PERSONAL_EXCESS}) * {_RATE}"
    system_usd = f"({_SYSTEM_EXCESS}) * {_RATE}"
    seat_usd = f"({_SEATS}) * (${{seat_price_usd:raw}})"
    el = {
        "ai_cost_help": build.text_panel("AI cost model", (
            "Prices and allowances above configure the live org model. A model seat is a token-active "
            "`user_type=user` identity, deduplicated across all apps and stacks; it is not a licensed-seat "
            "count or independently verified human. Personal allowance is deducted once per org identity; "
            "the system allowance is one org pool. Native billing previews are shown separately.\n\n"
            "History is dated observed month-to-date data, with source, capture time and captured allowances "
            "as their basis. Live allowance changes do not recalculate history. BI backfill and billing observations "
            "are separate overlapping sources; never add them. A backfill boundary is not a "
            "verified billing start. Only per-stack tables follow the Stack selector. "
            "User detail is queried live and is not stored in collector views."
        )),
        "ai_cost_seats": _stat("Token-active user-category identities", _SEATS,
                               "One identity working across several stacks is counted once."),
        "ai_cost_personal_tokens": _stat("User-category tokens", f"sum({_P})",
                                         "Sum across apps and stacks before allowance deductions."),
        "ai_cost_system_tokens": _stat("Service-category tokens", f"sum({_S})",
                                       "The series category does not independently prove a service account."),
        "ai_cost_over_allowance": _stat("User identities above personal allowance",
            f"sum(({_U}) > bool (${{personal_allowance:raw}}))",
            "Boolean comparison preserves a measured zero when no observed identity exceeds the allowance.",
            parameters=("personal_allowance",)),
        "ai_cost_personal_excess": _stat("Personal excess tokens", _PERSONAL_EXCESS,
            "Sum of positive excess after deduplicating each identity across the full org.",
            parameters=("personal_allowance",)),
        "ai_cost_system_excess": _stat("Org system excess tokens", _SYSTEM_EXCESS,
            "One configurable org pool is deducted from the full service-category total.",
            parameters=("system_allowance",)),
        "ai_cost_model_seats": _stat("Model seat cost", seat_usd,
            "Token-active user-category identities multiplied by the configurable seat price.",
            parameters=("seat_price_usd",), currency=True),
        "ai_cost_model_personal": _stat("Model personal token overage", personal_usd,
            "Personal excess multiplied by the configurable USD per million tokens.",
            parameters=("personal_allowance", "overage_per_million_usd"), currency=True),
        "ai_cost_model_system": _stat("Model org system overage", system_usd,
            "Org system excess multiplied by the configurable USD per million tokens.",
            parameters=("system_allowance", "overage_per_million_usd"), currency=True),
        "ai_cost_model_total": _stat("Total configurable org model", f"({seat_usd}) + ({personal_usd}) + ({system_usd})",
            "Seat and token what-if model. Subscription rates, proration and invoice adjustments can differ.",
            parameters=("seat_price_usd", "personal_allowance", "system_allowance", "overage_per_million_usd"),
            currency=True),
        "ai_cost_billed_seats": _stat("Native Assistant overage observation",
            'sum(grafanacloud_org_assistant_overage{__ignore_usage__=""})',
            "Raw Assistant overage gauge, independent of the seat model. Its name alone does not prove money or licensing."),
        "ai_cost_billed_tokens": _stat("Native AI token billing preview",
            'sum(grafanacloud_org_ai_tokens_overage{__ignore_usage__="",monetary="true"})',
            "Native monetary gauge beside the model overage. A reported zero is distinct from missing input.", currency=True),
        "ai_cost_live_users": build.prometheus_table_panel(
            "Top 100 user-category identities: live month-to-date tokens",
            f"topk(100, {_U})", legend="{{email}}", ds_uid=build.USAGE_UID, endpoint=True, limit=100,
            label_column="Identity", value_column="Observed tokens",
            description=_SCOPE + "Live identity detail only; no stored emails or identity drilldown links. "
            "The ranking sums all stacks/apps for each email, without counter deltas or range maxima."),
    }
    el["ai_cost_model_vs_billing"] = _stat(
        "Model token overage minus native preview (USD)",
        f"(({personal_usd}) + ({system_usd})) - sum(grafanacloud_org_ai_tokens_overage{{__ignore_usage__=\"\",monetary=\"true\"}})",
        "Comparison at the same selected endpoint. Configurable model uses recorded source-month gauges; "
        "native preview can differ through subscription terms, proration and adjustments. Not an invoice discrepancy.",
        parameters=("personal_allowance", "system_allowance", "overage_per_million_usd"), currency=True)
    el["ai_cost_live_user_model"] = build.prometheus_table_panel(
        "User-category identities: live model cost (USD)",
        _guard(f"topk(100, (({_U}) * 0 + (${{seat_price_usd:raw}})) + "
               f"clamp_min(({_U}) - (${{personal_allowance:raw}}), 0) * ({_RATE}))",
               "seat_price_usd", "personal_allowance", "overage_per_million_usd"),
        legend="{{email}}", ds_uid=build.USAGE_UID, endpoint=True, limit=100,
        label_column="Identity", value_column="Model USD", unit="currencyUSD",
        description=_SCOPE + "Token-active user-category model seats; allowances deducted once across stacks. "
        "Live table only, never identity storage or a licensed-user claim.")
    el["ai_cost_live_categories"] = build.prometheus_table_panel(
        "Monthly token observations by app, feature and category",
        'sum by(app, app_feature, user_type)(grafanacloud_ai_tokens_total_tokens{__ignore_usage__=""})',
        legend="{{app}} / {{app_feature}} / {{user_type}}", ds_uid=build.USAGE_UID, endpoint=True,
        label_column="App / feature / category", value_column="Observed tokens",
        description=_SCOPE + "An empty feature label is unspecified; it is not proof of personal or watcher usage.")
    el.update(_history_elements(ds))
    return el


def _history_elements(ds: str) -> dict:
    from collector.pillars.ai_cost import VIEW_SCHEMAS

    tables = (
        ("ai_cost_captured_current", "Captured org model: recorded basis", "ai_cost_current", False),
        ("ai_cost_history", "Monthly history: independent source observations", "ai_cost_monthly", False),
        ("ai_cost_stack_history", "Selected stacks: token observations and memberships", "ai_cost_stacks", True),
    )
    panels = {}
    for key, title, view, filtered in tables:
        try:
            panel = build.table_panel(
                title, view, ds, schema=VIEW_SCHEMAS[view], stack_filter=filtered,
                description=("Dated observed month-to-date aggregates; source, capture time and allowance basis are stored. "
                             "Model price inputs reprice captured counts/excess; live allowances do not change history. "
                             "USD20/USD2 columns are the generic reference basis, not the customer contract. "
                             "BI and billing observations overlap and must not be added; no final invoice claim. "
                             if not filtered else
                             "Only this table follows Stack. Memberships are not additive people. "
                             "Personal excess uses one org-wide identity allowance before filtering; no stack currency."),
                units={name.strip(): "currencyUSD" for name, _kind in VIEW_SCHEMAS[view] if "USD" in name},
            )
        except FileNotFoundError:
            panels[key] = build.text_panel(
                title,
                "**No published snapshot at dashboard build.** Current state is unknown, never measured zero. "
                "Live billing panels remain available independently. Rebuild after an accepted collector "
                "capture publishes this optional view. Access and transport errors are not treated as absence.")
            continue
        if not filtered:
            query = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
            # Backend computed-column contract is witnessed on the deployed Infinity plugin.
            query["columns"] += [
                {"selector": "Token-active users", "text": "model_users", "type": "number"},
                {"selector": "User excess tokens", "text": "model_user_excess", "type": "number"},
                {"selector": "System excess tokens", "text": "model_system_excess", "type": "number"},
            ]
            query["computed_columns"] = [
                {"selector": "model_users * (${seat_price_usd:raw})", "text": "Configured model seats USD", "type": "number"},
                {"selector": "(model_user_excess + model_system_excess) * (${overage_per_million_usd:raw}) / 1000000", "text": "Configured model tokens USD", "type": "number"},
                {"selector": "model_users * (${seat_price_usd:raw}) + (model_user_excess + model_system_excess) * (${overage_per_million_usd:raw}) / 1000000", "text": "Configured model total USD", "type": "number"},
            ]
            query["filterExpression"] = ("(${seat_price_usd:raw}) >= 0 && (${seat_price_usd:raw}) < 10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000 && "
                                         "(${overage_per_million_usd:raw}) >= 0 && (${overage_per_million_usd:raw}) < 10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")
            transform = panel["spec"]["data"]["spec"]["transformations"][0]["spec"]["options"]
            transform.setdefault("excludeByName", {}).update({name: True for name in
                ("model_users", "model_user_excess", "model_system_excess")})
            order = transform.setdefault("indexByName", {})
            for number, field in enumerate(query["computed_columns"]):
                order[field["text"]] = len(VIEW_SCHEMAS[view]) + number
                panel["spec"]["vizConfig"]["spec"]["fieldConfig"]["overrides"].append({
                    "matcher": {"id": "byName", "options": field["text"]},
                    "properties": [{"id": "unit", "value": "currencyUSD"}]})
        panels[key] = panel
    return panels


def tab() -> dict:
    return build.rows_tab("AI cost model", [
        build.row("Model scope and history", ["ai_cost_help"], max_columns=1),
        build.row("Observed org usage", ["ai_cost_seats", "ai_cost_personal_tokens", "ai_cost_system_tokens"],
                  max_columns=3, row_height="short"),
        build.row("Allowance deductions", ["ai_cost_over_allowance", "ai_cost_personal_excess", "ai_cost_system_excess"],
                  max_columns=3, row_height="short"),
        build.row("Configurable org model", ["ai_cost_model_seats", "ai_cost_model_personal", "ai_cost_model_system",
                                             "ai_cost_model_total"], max_columns=4, row_height="short"),
        build.row("Independent native billing preview", ["ai_cost_billed_seats", "ai_cost_billed_tokens", "ai_cost_model_vs_billing"],
                  max_columns=3, row_height="short"),
        build.row("Captured model and independent history", ["ai_cost_captured_current", "ai_cost_history"],
                  max_columns=1, row_height="tall"),
        build.row("Selected-stack observations", ["ai_cost_stack_history"], max_columns=1, row_height="tall"),
        build.row("Live identity detail", ["ai_cost_live_users", "ai_cost_live_user_model"], max_columns=1, row_height="tall"),
        build.row("Billing category observations", ["ai_cost_live_categories"], max_columns=1, row_height="tall"),
    ])
