"""Regression proofs for stable nullable columns and interpretable trend legends."""
from copy import deepcopy
from unittest import mock

from collector.dashboards import build


def test_declared_numeric_column_survives_null_then_numeric_publications():
    schema = [(" Stack", "string"), ("Score", "number"), ("Added later", "number")]
    for rows in ([{" Stack": "example", "Score": None}, {" Stack": "other"}],
                 [{" Stack": "example", "Score": 72.5}], []):
        view = {"rows": rows}
        original = deepcopy(view)
        with mock.patch.object(build, "read_view", return_value=view):
            panel = build.table_panel("Scores", "scores", "infinity", schema=schema)
        query = panel["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        assert query["columns"] == [
            {"selector": " Stack", "text": "Stack", "type": "string"},
            {"selector": "Score", "text": "Score", "type": "number"},
            {"selector": "Added later", "text": "Added later", "type": "number"},
        ]
        assert view == original  # Typing never fills unknown values with zero.


def test_declared_numeric_schema_does_not_coerce_malformed_values():
    for value in ("unknown", "72.5", False):
        columns = build.columns_for({"rows": [{"Score": None}, {"Score": 3}, {"Score": value}]},
                                    [("Score", "number")])
        assert columns[0]["type"] == "string"
    assert build.columns_for({"rows": [{"Score": None}]})[0]["type"] == "string"


def legend_for(exprs, **kwargs):
    panel = build.timeseries_panel("Trend", exprs, **kwargs)
    return panel["spec"]["vizConfig"]["spec"]["options"]["legend"]["showLegend"]


def test_single_query_bounded_categories_have_a_legend():
    assert legend_for([("gcinsight_usage_stacks_by_signal", "{{signal}}")])
    assert legend_for([("gcinsight_maturity_dimension_mean", "{{dimension}}")])
    assert not legend_for([("gcinsight_stack_active_series", "{{stack}}")])
    assert not legend_for([("some_vendor_series", "{{unknown_dimension}}")])
    assert not legend_for([("sum(up)", "Total")])
    assert legend_for([("sum(up)", "A"), ("sum(down)", "B")])


def test_legend_override_is_explicit_for_audited_panels():
    assert legend_for([("some_vendor_series", "{{category}}")], show_legend=True)
    assert not legend_for([("gcinsight_usage_stacks_by_signal", "{{signal}}")], show_legend=False)
