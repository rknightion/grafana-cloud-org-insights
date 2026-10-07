"""Fail-closed contracts at the serialized source -> evaluator boundary."""
import copy
import json

import pytest

from collector import label_rules as lr


def sample(value=0, semantics="exact", population=1000, kind="dynamic",
           population_semantics="exact"):
    return {"value": value, "semantics": semantics, "population": population,
            "population_semantics": population_semantics, "label_kind": kind}


def envelope(input_id="distinct_values", samples=None, *, state="complete", reason="none",
             names_truncated=0, values_overflow=0, data="present"):
    return {"schema_version": 1, "signals": {"metrics": {
        "data": data, "state": state, "reason": reason, "window": "head",
        "register": [], "register_truncated": 0,
        "inputs": {input_id: {"state": state, "reason": reason,
                              "names_truncated": names_truncated,
                              "values_overflow": values_overflow,
                              "samples": samples if samples is not None else [sample()]}}}}}


def rule(rule_id="M4"):
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    raw["rules"] = [r for r in raw["rules"] if r["id"] == rule_id]
    raw["threshold_sources"] = {k: v for k, v in raw["threshold_sources"].items() if k == rule_id}
    return lr.validate_catalogue(raw)


def evaluate(env=None, catalogue=None, tunables=None):
    return lr.evaluate({"synthetic": env or envelope()}, catalogue or rule(), tunables)


def result(env=None, catalogue=None, tunables=None):
    return evaluate(env, catalogue, tunables)["results"][0]


def test_missing_input_never_passes():
    env = envelope()
    env["signals"]["metrics"]["inputs"] = {}
    assert result(env)["result"] == "not_evaluated"
    assert result(env)["reason"] == "missing_input"


@pytest.mark.parametrize("value,expected,band", [(99, "not_evaluated", "none"),
                                               (100, "fail", "warn"),
                                               (1000, "fail", "high"),
                                               (10000, "fail", "critical")])
def test_lower_bounds(value, expected, band):
    r = result(envelope(samples=[sample(value, "at_least")], state="partial", reason="truncated"))
    assert r["result"] == expected
    assert r["evidence"]["worst_band"] == band
    assert r["evidence"]["at_least"] == 1
    if expected == "not_evaluated":
        assert r["reason"] == "truncated"
    else:
        assert r["severity"] == ("medium" if band == "warn" else "high")


def test_overflow_fails_at_warn_even_without_samples():
    r = result(envelope(samples=[], state="partial", reason="overflow", values_overflow=1))
    assert r["result"] == "fail"
    assert r["severity"] == "medium"
    assert r["evidence"]["condition"] == "overflow"
    assert r["evidence"]["worst_band"] == "warn"


def test_truncated_names_cannot_establish_absence_or_pass():
    for value in (0, 1):
        r = result(envelope("missing_identity", [sample(value)], state="partial",
                            reason="truncated", names_truncated=1), rule("M_identity"))
        assert (r["result"], r["reason"]) == ("not_evaluated", "truncated")


@pytest.mark.parametrize("state,reason", [("unavailable", "missing_input"),
                                          ("partial", "deadline")])
def test_unavailable_or_deadline_zero_does_not_pass(state, reason):
    r = result(envelope(state=state, reason=reason,
                        data="unknown" if state == "unavailable" else "present"))
    assert (r["result"], r["reason"]) == ("not_evaluated", reason)


def test_measured_empty_and_unknown_are_different():
    env = envelope(data="empty", samples=[])
    assert result(env)["reason"] == "no_signal_data"
    assert result(env)["result"] == "not_applicable"
    env["signals"]["metrics"]["data"] = "unknown"
    assert result(env)["result"] == "not_evaluated"
    assert result(env)["reason"] == "missing_input"


def test_cross_signal_requires_both_data_and_inputs():
    env = envelope("service_gap", [sample(0)])
    assert result(env, rule("X_service"))["result"] == "not_evaluated"
    env["signals"]["traces"] = copy.deepcopy(env["signals"]["metrics"])
    env["signals"]["traces"]["window"] = "24h"
    env["signals"]["traces"]["data"] = "empty"
    env["signals"]["traces"]["inputs"] = {}
    assert result(env, rule("X_service"))["reason"] == "no_signal_data"
    env["signals"]["traces"]["data"] = "present"
    assert result(env, rule("X_service"))["reason"] == "missing_input"
    env["signals"]["traces"]["inputs"] = copy.deepcopy(env["signals"]["metrics"]["inputs"])
    assert result(env, rule("X_service"))["result"] == "pass"
    env["signals"]["traces"]["inputs"]["service_gap"]["samples"] = [sample(2)]
    assert result(env, rule("X_service"))["result"] == "fail"


def test_size_floor_and_static_band():
    assert result(envelope(samples=[sample(10000, population=99)]))["reason"] == "precondition_false"
    assert result(envelope(samples=[sample(1000, population=99,
                                          population_semantics="at_least")]))["reason"] == "truncated"
    assert result(envelope(samples=[sample(100, kind="static")]))["result"] == "pass"
    assert result(envelope(samples=[sample(1000, kind="static")]))["result"] == "fail"
    assert result(envelope(samples=[sample(100, population=None)]))["reason"] == "missing_input"
    assert result(envelope(samples=[sample(10000)]), tunables={"size_floor": 1001})["result"] == "not_applicable"


def test_coverage_floor_is_weighted_and_withholds_score():
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    base = next(r for r in raw["rules"] if r["id"] == "M4")
    raw["threshold_sources"] = {}
    raw["rules"] = [{**base, "id": f"test_{i}", "input": "distinct_values" if i < 4 else "shape_count",
                     "size_floor": i < 4} for i in range(5)]
    summary = evaluate(catalogue=lr.validate_catalogue(raw))["summaries"][0]
    assert summary["coverage"] == 0.8
    assert summary["score"] == 100
    raw["rules"].append({**base, "id": "test_5", "input": "shape_count", "size_floor": False})
    summary = evaluate(catalogue=lr.validate_catalogue(raw))["summaries"][0]
    assert summary["coverage"] < 0.8
    assert "score" not in summary
    assert summary["applicable_weight"] == 18
    assert summary["evaluated_weight"] == 12


def test_excluded_rules_do_not_dilute_coverage():
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    raw["rules"] = [r for r in raw["rules"] if r["id"] in {"M4", "M6", "L_query_use", "T_semconv"}]
    output = evaluate(catalogue=lr.validate_catalogue(raw))
    for r in output["results"]:
        if r["rule"] != "M4":
            assert (r["result"], r["reason"]) == ("not_evaluated", "route_parked")
    assert output["summaries"][0]["coverage"] == 1
    assert output["catalogue_version"] == lr.CATALOGUE.version


@pytest.mark.parametrize("evidence", [{"label": "SECRET_SENTINEL"}, {"observed": "123"},
    {"worst_band": "SECRET_SENTINEL"}, {"condition": "raw"}, {"observed": float("nan")},
    {"observed": float("inf")}, {"observed": True}, {"at_least": 2}, {"observed": -1}])
def test_evidence_refuses_non_enum_non_numeric_or_nonfinite(evidence):
    with pytest.raises(lr.RuleError) as exc:
        lr.validate_evidence(evidence)
    assert "SECRET_SENTINEL" not in str(exc.value)


def test_catalogue_schema_evidence_and_provenance():
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    assert lr.load().version == raw["catalogue_version"]
    for mutate in (lambda r: r["evidence_schema"].update({"label": "string"}),
                   lambda r: r["rules"][0].update({"verified_on": None}),
                   lambda r: r["rules"][0].update({"thresholds": {"warn": "100"}}),
                   lambda r: r["rules"][0].update({"severity": "critical"}),
                   lambda r: r["rules"][0].update({"input": "unregistered"})):
        bad = copy.deepcopy(raw)
        mutate(bad)
        with pytest.raises(lr.RuleError):
            lr.validate_catalogue(bad)


def test_register_is_bounded_minimized_and_never_finding_evidence():
    env = envelope()
    row = {"name": "synthetic_safe_name", "name_class": "ordinary", "name_count": 1,
           "scope": "label", "distinct_count": 10, "count_semantics": "exact",
           "shape_counts": {"uuid": 2}, "series_count": 1000, "stream_count": None}
    env["signals"]["metrics"]["register"] = [row]
    output = evaluate(env)
    assert "synthetic_safe_name" not in json.dumps(output)
    assert lr.validate_inventory(env) == env
    for field, value in (("name", "email"), ("name", "x" * 513),
                         ("name", "test@example.org"), ("raw_values", ["SECRET_SENTINEL"]),
                         ("shape_counts", {"email": 1})):
        bad = copy.deepcopy(env)
        bad["signals"]["metrics"]["register"][0][field] = value
        with pytest.raises(lr.RuleError) as exc:
            lr.validate_inventory(bad)
        assert "SECRET_SENTINEL" not in str(exc.value)
    row.update(name=None, name_class="pii", name_count=2, distinct_count=None,
               series_count=None, shape_counts={})
    assert lr.validate_inventory(env) == env
    env["signals"]["metrics"]["register"] *= lr.MAX_REGISTER_ROWS + 1
    with pytest.raises(lr.RuleError):
        lr.validate_inventory(env)


def test_register_truncation_and_aggregate_input_truncation_cannot_pass():
    env = envelope()
    env["signals"]["metrics"].update(register_truncated=1, state="partial", reason="truncated")
    assert result(env)["reason"] == "truncated"
    env = envelope(samples=[sample()] * (lr.MAX_SAMPLES + 1))
    with pytest.raises(lr.RuleError):
        result(env)


@pytest.mark.parametrize("tunables", [{"coverage_floor": 0.79}, {"size_floor": True},
                                      {"unknown": 1}, {"thresholds": {"M4": {"warn": 1000, "high": 100}}}])
def test_invalid_tunables_rejected(tunables):
    with pytest.raises(lr.RuleError):
        evaluate(tunables=tunables)


def test_round_trip_real_serialized_artifact():
    env = json.loads(json.dumps(envelope(samples=[sample(1000)])))
    output = lr.evaluate({"synthetic": env}, lr.load())
    assert next(r for r in output["results"] if r["rule"] == "M4")["result"] == "fail"
    for r in output["results"]:
        lr.validate_evidence(r["evidence"])
    assert json.loads(json.dumps(output, allow_nan=False)) == output


def test_threshold_provenance_and_tunables_never_manufacture_published_claims():
    bands = lr.threshold_provenance("M4")
    assert bands["warn"]["provenance"] == "ps"
    assert bands["critical"]["provenance"] == "policy"
    published = lr.threshold_provenance("L1")
    assert published["high"]["provenance"] == "published"
    tuned = lr.threshold_provenance("L1", tunables={"thresholds": {"L1": {"high": 20}}})
    assert tuned["high"]["provenance"] == "policy"
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    for r in raw["rules"]:
        if r["provenance"] == "published":
            assert r["verification"] == "verified" and r["verified_on"] == "2026-10-07"


@pytest.mark.parametrize("field,value", [("value", "SECRET_SENTINEL"), ("value", True),
    ("value", -1), ("value", lr.MAX_COUNT + 1), ("semantics", "approximate"),
    ("label_kind", "user_id"), ("population", "1000")])
def test_numeric_sample_schema_is_strict(field, value):
    env = envelope()
    env["signals"]["metrics"]["inputs"]["distinct_values"]["samples"][0][field] = value
    with pytest.raises(lr.RuleError) as exc:
        evaluate(env)
    assert "SECRET_SENTINEL" not in str(exc.value)


def test_serialized_byte_bound_and_empty_payload_consistency():
    env = envelope()
    payload = env["signals"]["metrics"]
    row = {"name": "x" * 512, "name_class": "ordinary", "name_count": 1,
           "scope": "label", "distinct_count": 10, "count_semantics": "exact",
           "shape_counts": {"uuid": 2}, "series_count": 1000, "stream_count": None}
    payload["register"] = [row] * lr.MAX_REGISTER_ROWS
    inp = payload["inputs"]["distinct_values"]
    inp["samples"] = [sample(lr.MAX_COUNT)] * lr.MAX_SAMPLES
    payload["inputs"] = {key: copy.deepcopy(inp) for key, spec in lr.CATALOGUE.inputs.items()
                         if "metrics" in spec["signals"]}
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()) > lr.MAX_SIGNAL_BYTES
    with pytest.raises(lr.RuleError, match="serialized input exceeds bound"):
        evaluate(env)
    env = envelope(data="empty")
    with pytest.raises(lr.RuleError):
        evaluate(env)


def test_fail_and_missing_weights_are_not_dynamic_severity_weights():
    out = evaluate(envelope(samples=[sample(10000)]))
    assert out["results"][0]["severity"] == "high"
    assert out["results"][0]["weight"] == 3
    summary = out["summaries"][0]
    assert summary["coverage"] == 1 and summary["score"] == 0
    assert lr.evaluate({}) == {"catalogue_version": 3, "results": [], "summaries": []}


def test_zero_coverage_no_score_and_no_applicable_rules_no_score():
    env = envelope()
    env["signals"]["metrics"]["inputs"] = {}
    summary = evaluate(env)["summaries"][0]
    assert summary["coverage"] == 0 and "score" not in summary
    summary = evaluate(envelope(data="empty", samples=[]))["summaries"][0]
    assert summary["coverage"] is None and "score" not in summary


def simulated_extension(rule_id):
    """Future source extension on a witnessed route, not a shipping route grant."""
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    raw["catalogue_version"] += 1
    raw["rules"] = [r for r in raw["rules"] if r["id"] == rule_id]
    raw["threshold_sources"] = {}
    inp = raw["rules"][0]["input"]
    raw["inputs"][inp]["route"] = "approved"
    return lr.validate_catalogue(raw)


@pytest.mark.parametrize("rule_id,input_id,signal,unit,threshold", [
    ("M5", "metric_series", "metrics", "series_per_metric", 1000),
    ("M6", "labels_per_series", "metrics", "labels_per_series", 30),
    ("L1", "labels_per_stream", "logs", "labels_per_stream", 16)])
def test_raw_size_extension_compares_sizes_and_counts_offending_objects(
        rule_id, input_id, signal, unit, threshold):
    catalogue = simulated_extension(rule_id)
    env = envelope(input_id, [sample(threshold - 1), sample(threshold), sample(threshold + 1)])
    env["signals"][signal] = env["signals"].pop("metrics")
    env = json.loads(json.dumps(env))
    r = result(env, catalogue)
    assert r["result"] == "fail"
    assert r["evidence"]["observed"] == threshold + 1
    assert r["evidence"]["offending_labels"] == 2  # objects, never sum of sizes
    assert r["evidence"]["at_least"] == 0
    entry = catalogue.inputs[input_id]
    assert entry["unit"] == unit
    assert entry["aggregation"] == "offending_objects"
    env["signals"][signal]["inputs"][input_id]["samples"] = [sample(threshold - 1)]
    assert result(env, catalogue)["result"] == "pass"
    env["signals"][signal]["inputs"][input_id]["samples"] = [sample(threshold)]
    assert result(env, catalogue)["result"] == "fail"
    env["signals"][signal]["inputs"][input_id]["samples"] = [sample(threshold, "at_least")]
    assert result(env, catalogue)["evidence"]["at_least"] == 1
    # C1 metric-series and C2 selected stream sizes now ship; metric series samples stay parked.
    assert lr.CATALOGUE.inputs[input_id]["route"] == ("approved" if rule_id in {"M5", "L1"} else "parked")


@pytest.mark.parametrize("values,expected,lower", [
    ([lr.MAX_COUNT], lr.MAX_COUNT, 0),
    ([lr.MAX_COUNT - 1, 1], lr.MAX_COUNT, 0),
    ([lr.MAX_COUNT, 1], lr.MAX_COUNT, 1),
    ([lr.MAX_COUNT, lr.MAX_COUNT], lr.MAX_COUNT, 1),
    ([lr.MAX_COUNT] * lr.MAX_SAMPLES, lr.MAX_COUNT, 1)])
def test_valid_violation_counts_saturate_without_crash_or_false_exactness(values, expected, lower):
    env = envelope("shape_count", [sample(value) for value in values])
    catalogue = rule("M_shape")
    assert lr.validate_inventory(env, catalogue) == env
    r = result(env, catalogue)
    assert r["result"] == "fail"
    assert r["evidence"]["offending_labels"] == expected
    assert r["evidence"]["at_least"] == lower
    assert r["evidence"]["observed"] == max(values)
    assert r["evidence"]["condition"] == "none"  # not a values-read byte-cap
    lr.validate_evidence(r["evidence"])
    entry = catalogue.inputs["shape_count"]
    assert entry["unit"] == "violation_count" and entry["aggregation"] == "sum_violations"


def test_cross_signal_violation_aggregation_saturates_across_signals():
    env = envelope("service_gap", [sample(lr.MAX_COUNT)])
    env["signals"]["traces"] = copy.deepcopy(env["signals"]["metrics"])
    r = result(env, rule("X_service"))
    assert r["result"] == "fail"
    assert r["evidence"]["offending_labels"] == lr.MAX_COUNT
    assert r["evidence"]["at_least"] == 1


def test_input_registry_units_and_aggregation_cannot_be_omitted_or_contradicted():
    raw = json.loads(lr.CATALOGUE_PATH.read_text())
    for inp in raw["inputs"].values():
        assert inp.get("unit") and inp.get("aggregation")
    for change in ({"unit": "arbitrary"}, {"aggregation": "average"},
                   {"unit": "violation_count"}, {"aggregation": "sum_violations"}):
        bad = copy.deepcopy(raw)
        bad["inputs"]["labels_per_stream"].update(change)
        with pytest.raises(lr.RuleError):
            lr.validate_catalogue(bad)
    bad = copy.deepcopy(raw)
    del bad["inputs"]["metric_series"]["unit"]
    with pytest.raises(lr.RuleError):
        lr.validate_catalogue(bad)
