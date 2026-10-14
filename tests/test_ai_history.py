"""The stored AI history boundary rejects identity detail and never revives a failed read."""

import copy
import datetime as dt
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from collector.emit import ai_history

NOW = dt.datetime(2026, 10, 14, 12, tzinfo=dt.timezone.utc)
STACKS = [{"id": 1, "slug": "synthetic-one"}]


def observation(**changes):
    result = {"available": True, "source": "billing_observation",
              "query_time": NOW.isoformat(), "captured_month": "2026-10",
              "period_status": "observed_mtd", "personal_allowance": 40_000_000,
              "system_allowance": 500_000_000,
              "org": {"users": 1, "service_users": 0, "user_tokens": 50_000_000,
                      "service_tokens": 0, "user_excess": 10_000_000,
                      "users_over_allowance": 1, "system_excess": 0,
                      "billed_overage": None},
              "stacks": {"1": {"users": 1, "service_users": 0,
                                "user_tokens": 50_000_000, "service_tokens": 0,
                                "user_excess": 10_000_000, "billed_overage": None}}}
    result.update(changes)
    return result


class S3:
    def __init__(self, state=None, failure=None):
        self.state, self.failure, self.calls = state, failure, []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        assert 0 < kwargs["timeout"] <= 30
        command = args[2]
        if self.failure == command:
            return SimpleNamespace(returncode=1, stdout="", stderr="AccessDenied private-data")
        if command == "head-object":
            if self.state is None:
                return SimpleNamespace(returncode=1, stdout="", stderr="An error occurred (404) when calling the HeadObject operation: Not Found")
            encoded = json.dumps(self.state).encode()
            return SimpleNamespace(returncode=0, stdout=json.dumps({"ETag": '"abc123"', "ContentLength": len(encoded)}), stderr="")
        if command == "get-object":
            assert args[args.index("--if-match") + 1] == '"abc123"'
            Path(args[-1]).write_text(json.dumps(self.state))
            return SimpleNamespace(returncode=0, stdout=json.dumps({"ETag": '"abc123"'}), stderr="")
        if command == "put-object":
            self.state = json.loads(Path(args[args.index("--body") + 1]).read_text())
            return SimpleNamespace(returncode=0, stdout='{"ETag":"new"}', stderr="")
        raise AssertionError(command)


def test_sources_are_separate_and_departed_stack_rows_are_removed():
    previous = observation(source="bi_one_time", query_time="2026-10-13T12:00:00+00:00")
    previous["stacks"]["2"] = copy.deepcopy(previous["stacks"]["1"])
    rows = ai_history.merge([previous], observation(), STACKS, now=NOW)
    assert len(rows) == 2
    assert {row["source"] for row in rows} == {"billing_observation", "bi_one_time"}
    assert all(set(row["stacks"]) == {"1"} for row in rows)
    assert all(row["org"]["user_tokens"] == 50_000_000 for row in rows)


def test_duplicate_source_month_and_unknown_identity_fields_fail_closed():
    with pytest.raises(ai_history.HistoryError, match="invalid_history"):
        ai_history.merge([observation(), observation()], observation(), STACKS, now=NOW)
    bad = observation()
    bad["org"]["email"] = "private@example.invalid"
    with pytest.raises(ai_history.HistoryError, match="invalid_snapshot") as error:
        ai_history.merge([], bad, STACKS, now=NOW)
    assert "private" not in str(error.value)
    with pytest.raises(ai_history.HistoryError):
        ai_history.merge([], observation(captured_month="2026-09"), STACKS, now=NOW)


def test_rollover_cannot_update_accepted_history_or_write_s3():
    old = observation()
    rollover = observation(query_time="2026-11-01T00:30:00Z", captured_month="2026-11",
                           period_status="rollover_unverified")
    runner = S3({"schema_version": 1, "history": [old]})
    rows = ai_history.update(rollover, STACKS, bucket="synthetic-bucket",
                             now=dt.datetime(2026, 11, 1, 1, tzinfo=dt.timezone.utc), runner=runner)
    assert rows == [old]
    assert not any(args[2] == "put-object" for args, _ in runner.calls)


def test_read_failure_is_not_empty_and_cas_failure_preserves_previous():
    runner = S3(failure="head-object")
    with pytest.raises(ai_history.HistoryError, match="read_failed"):
        ai_history.update(observation(), STACKS, bucket="synthetic-bucket", now=NOW, runner=runner)
    assert len(runner.calls) == 1
    runner = S3({"schema_version": 1, "history": []}, failure="put-object")
    with pytest.raises(ai_history.HistoryError, match="write_failed") as error:
        ai_history.update(observation(), STACKS, bucket="synthetic-bucket", now=NOW, runner=runner)
    assert "private" not in str(error.value)
    put = runner.calls[-1][0]
    assert put[put.index("--if-match") + 1] == '"abc123"'
    assert runner.state["history"] == []


def test_new_state_is_conditional_and_dry_run_has_no_put():
    runner = S3()
    assert ai_history.update(observation(), STACKS, bucket="synthetic-bucket", now=NOW, runner=runner) == [observation()]
    args = runner.calls[-1][0]
    assert args[args.index("--if-none-match") + 1] == "*"
    assert args[args.index("--server-side-encryption") + 1] == "AES256"
    runner = S3()
    ai_history.update(observation(), STACKS, bucket="synthetic-bucket", now=NOW, dry_run=True, runner=runner)
    assert not any(args[2] == "put-object" for args, _ in runner.calls)


def test_future_nonfinite_oversize_and_missing_estate_refuse():
    bad = observation()
    bad["org"]["user_excess"] = float("nan")
    huge = observation()
    huge["org"]["user_tokens"] = 10**1000
    for candidate in (bad, huge, observation(source=[]),
                      observation(query_time="2026-10-14T12:06:00Z")):
        with pytest.raises(ai_history.HistoryError):
            ai_history.merge([], candidate, STACKS, now=NOW)
    with pytest.raises(ai_history.HistoryError, match="empty_inventory"):
        ai_history.merge([], observation(), [], now=NOW)
    runner = S3({"schema_version": 1, "history": []})
    runner.state["history"] = [observation() for _ in range(27)]
    with pytest.raises(ai_history.HistoryError):
        ai_history.load(bucket="synthetic-bucket", now=NOW, runner=runner)


def test_history_retains_only_thirteen_months_without_summing_observations():
    previous = []
    for year, month in [(2025, month) for month in range(9, 13)] + [(2026, month) for month in range(1, 10)]:
        previous.append(observation(query_time=f"{year}-{month:02d}-14T12:00:00Z",
                                    captured_month=f"{year}-{month:02d}"))
    rows = ai_history.merge(previous, observation(), STACKS, now=NOW)
    assert len(rows) == 13
    assert rows[0]["captured_month"] == "2025-10"
    assert rows[-1]["org"]["user_tokens"] == 50_000_000
    bad = observation()
    bad["stacks"] = {str(i): copy.deepcopy(bad["stacks"]["1"]) for i in range(1, 20_001)}
    with pytest.raises(ai_history.HistoryError):
        ai_history.merge([], bad, STACKS, now=NOW)


def test_timeout_and_malformed_read_are_generic_and_never_put():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private", 30)

    with pytest.raises(ai_history.HistoryError, match="read_failed"):
        ai_history.load(bucket="synthetic-bucket", now=NOW, runner=timeout)
    runner = S3({"schema_version": 1, "history": [], "email": "private@example.invalid"})
    with pytest.raises(ai_history.HistoryError, match="invalid_history"):
        ai_history.load(bucket="synthetic-bucket", now=NOW, runner=runner)
