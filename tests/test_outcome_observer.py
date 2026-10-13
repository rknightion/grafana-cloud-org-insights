"""Public observer CLI evidence, with synthetic provider responses only."""
import json
from datetime import datetime, timezone

import pytest


def event(name, seq, payload, *, tier="t1", attempt="11111111-1111-4111-8111-111111111111", start="2026-10-13T12:00:00Z", at=None):
    return dict(kind="gcinsight_outcome", version=1, event=name, attempt_id=attempt,
                tier=tier, started_at=start, at=at or start, sequence=seq,
                source_revision=None, payload=payload)


def trace(*, tier="t1", task="a" * 32, attempt="11111111-1111-4111-8111-111111111111", start="2026-10-13T12:00:00Z"):
    envelopes = [event("attempt_started", 1, {"deadline_seconds": 60}, tier=tier, attempt=attempt, start=start),
                 event("inventory_result", 2, {"state": "success", "reason": "none", "count": 4,
                       "read_started_at": start, "read_completed_at": start}, tier=tier, attempt=attempt, start=start),
                 event("view_write_result", 3, {"view": "cost_summary", "state": "acknowledged", "sha256": "b" * 64,
                       "request_started_at": start, "request_completed_at": start}, tier=tier, attempt=attempt, start=start),
                 event("attempt_finished", 4, {"state": "success", "reason": "none", "exit_code": 0}, tier=tier, attempt=attempt, start=start)]
    return [{"logStreamName": f"{tier}/collector/{task}", "message": json.dumps(e)} for e in envelopes]


def run_fixture(tmp_path, records, *, priors=None, now="2026-10-13T12:10:00Z", name="run"):
    from collector.observer import main
    fixture = tmp_path / f"{name}.json"
    fixture.write_text(json.dumps({"events": records, "priors": priors or {}, "now": now}))
    directory = tmp_path / name
    rc = main(["--fixture", str(fixture), "--output-dir", str(directory)])
    projections = {tier: json.loads((directory / f"{tier}.json").read_text()) for tier in ("t1", "t2", "t3", "t4")} if directory.exists() else {}
    return rc, projections


def test_fixture_cli_preserves_unknown_membership_and_independent_receipt(tmp_path):
    rc, projections = run_fixture(tmp_path, trace())
    assert rc == 0
    rows = projections["t1"]["rows"]
    assert rows[0]["state"] == "success"
    assert rows[1]["last_success_count"] == 4
    assert rows[2]["state"] == "acknowledged"
    assert projections["t1"]["meta"]["current_membership"] == "unknown"
    assert projections["t1"]["meta"]["actual_latest_outcome"] == "unknown"
    assert all((tmp_path / "run" / f"{tier}.json").stat().st_mode & 0o777 == 0o600 for tier in projections)


def test_fixture_reconciles_later_conflict_and_cross_tier_uuid_reuse(tmp_path):
    _, prior = run_fixture(tmp_path, trace(), name="first")
    conflict = trace()[1]
    changed = json.loads(conflict["message"])
    changed["payload"]["count"] = 7
    conflict["message"] = json.dumps(changed)
    _, after = run_fixture(tmp_path, [conflict], priors=prior, name="conflict")
    assert after["t1"]["rows"][1]["last_success_at"] is None
    assert after["t1"]["rows"][2]["last_success_at"] is None
    assert after["t1"]["_state"]["attempts"][0]["conflict"] is True
    _, replay = run_fixture(tmp_path, trace(), priors=after, name="replay")
    assert replay["t1"]["rows"][2]["sha256"] is None
    _, reused = run_fixture(tmp_path, trace(tier="t2", task="c" * 32), priors=prior, name="reuse")
    assert reused["t1"]["rows"][1]["last_success_count"] is None
    assert reused["t2"]["rows"][1]["last_success_count"] is None


def test_fixture_revokes_only_conflicted_support_and_expires_without_new_logs(tmp_path):
    old = trace(attempt="22222222-2222-4222-8222-222222222222", task="d" * 32, start="2026-10-13T11:00:00Z")
    _, prior = run_fixture(tmp_path, old + trace(), name="history")
    changed = trace()[1]
    value = json.loads(changed["message"])
    value["payload"]["count"] = 9
    changed["message"] = json.dumps(value)
    _, after = run_fixture(tmp_path, [changed], priors=prior, name="revoke")
    assert after["t1"]["rows"][1]["last_success_at"] == "2026-10-13T11:00:00Z"
    _, expired = run_fixture(tmp_path, [], priors=after, now="2026-10-17T12:00:00Z", name="expired")
    assert expired["t1"]["rows"][1]["last_success_at"] is None
    _, pending = run_fixture(tmp_path, trace()[:1], name="pending")
    assert pending["t1"]["rows"][0]["state"] == "incomplete"
    assert pending["t1"]["rows"][0]["reason"] == "expired"


def test_fixture_gap_spoof_and_partial_retrieval_never_claim_success(tmp_path):
    from collector.observer import main
    _, gap = run_fixture(tmp_path, trace()[:1] + trace()[2:], name="gap")
    assert gap["t1"]["rows"][0]["state"] == "incomplete"
    assert gap["t1"]["rows"][2]["state"] == "unknown"
    bad = trace()
    bad[0]["logStreamName"] = "observer/status/" + "a" * 32
    _, spoof = run_fixture(tmp_path, bad, name="spoof")
    assert spoof["t1"]["rows"][0]["state"] != "success"
    source = tmp_path / "partial.json"
    source.write_text(json.dumps({"events": trace(), "now": "2026-10-13T12:10:00Z", "observation_state": "partial", "reason": "cap"}))
    assert main(["--fixture", str(source), "--output-dir", str(tmp_path / "partial")]) == 0
    partial = json.loads((tmp_path / "partial" / "t1.json").read_text())
    assert partial["rows"][0]["state"] == "incomplete"
    assert partial["rows"][1]["last_success_at"] is None


def test_fixture_rejects_malformed_future_prior_and_never_overwrites_directory(tmp_path):
    from collector.observer import main
    _, prior = run_fixture(tmp_path, trace(), name="safe")
    prior["t1"]["meta"]["generated_at"] = "2026-10-14T12:00:00Z"
    rc, projections = run_fixture(tmp_path, [], priors=prior, name="future")
    assert rc == 1 and projections == {}
    before = (tmp_path / "safe" / "t1.json").read_bytes()
    source = tmp_path / "collision.json"
    source.write_text(json.dumps({"events": [], "now": "2026-10-13T12:10:00Z"}))
    assert main(["--fixture", str(source), "--output-dir", str(tmp_path / "safe")]) == 1
    assert (tmp_path / "safe" / "t1.json").read_bytes() == before

    # A newer accepted writer can be two minutes ahead of this observer's clock.
    _, newer = run_fixture(tmp_path, trace(), name="newer-clock")
    rc, carried = run_fixture(tmp_path, [], priors=newer,
                             now="2026-10-13T12:08:00Z", name="slower-clock")
    assert rc == 0
    assert carried["t1"]["meta"]["observation_completed_at"] == newer["t1"]["meta"]["observation_completed_at"]
    rc, _ = run_fixture(tmp_path, [], priors=carried,
                        now="2026-10-13T12:08:01Z", name="slower-reread")
    assert rc == 0  # writer output must remain admissible to the next reader


def test_equal_time_attempts_expose_no_arbitrary_inventory_winner(tmp_path):
    _, projections = run_fixture(tmp_path, trace() + trace(attempt="33333333-3333-4333-8333-333333333333", task="e" * 32), name="equal")
    assert projections["t1"]["rows"][0]["state"] == "ambiguous"
    assert projections["t1"]["rows"][1]["state"] in {"unknown", "ambiguous"}
    assert projections["t1"]["rows"][1]["count"] is None


FAKE_AWS = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p=Path(os.environ['OBSERVER_FAKE_STATE'])
s=json.loads(p.read_text())
a=sys.argv[1:]
s.setdefault('calls',[]).append(a)
def finish(code=0, output=None, err=None):
 p.write_text(json.dumps(s))
 if output is not None: print(json.dumps(output))
 if err is not None: print(err,file=sys.stderr)
 sys.exit(code)
def arg(name): return a[a.index(name)+1]
def error(code,op):
 annotation=s.get('retry_annotation','')
 finish(254,err=f'aws: [ERROR]: An error occurred ({code}) when calling the {op} operation{annotation}: deliberately private provider prose')
if 'filter-log-events' in a:
 request=json.loads(arg('--cli-input-json'))
 s.setdefault('requests',[]).append(request)
 finish(output=s['pages'].pop(0) if s.get('pages') else {'events':[]})
key=arg('--key')
if 'get-object' in a:
 directives=s.get('gets',{}).get(key,[])
 directive=directives.pop(0) if directives else None
 if directive and directive!='present': error(directive,'GetObject')
 obj=s.get('objects',{}).get(key)
 if obj is None: error('NoSuchKey','GetObject')
 Path(a[-1]).write_text(obj['raw'])
 finish(output={'ETag':obj['etag']})
if 'put-object' in a:
 directives=s.get('puts',{}).get(key,[])
 directive=directives.pop(0) if directives else None
 if directive:
  if isinstance(directive,dict):
   s.setdefault('objects',{})[key]=directive['replace']
   error('PreconditionFailed','PutObject')
  error(directive,'PutObject')
 existing=s.get('objects',{}).get(key)
 if '--if-none-match' in a and existing is not None: error('PreconditionFailed','PutObject')
 if '--if-match' in a and (existing is None or existing['etag']!=arg('--if-match')): error('PreconditionFailed','PutObject')
 raw=Path(arg('--body')).read_text()
 s.setdefault('objects',{})[key]={'raw':raw,'etag':'"synthetic"'}
 finish(output={'ETag':'"synthetic"'})
finish(2)
'''


def production(tmp_path, monkeypatch, *, records=None, plan=None):
    from collector import observer
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    executable = tmp_path / "aws"
    executable.write_text(FAKE_AWS)
    executable.chmod(0o700)
    path = tmp_path / "aws-state.json"
    state = {"pages": [{"events": records if records is not None else trace(start=now)}], **(plan or {})}
    path.write_text(json.dumps(state))
    monkeypatch.setenv("OBSERVER_FAKE_STATE", str(path))
    monkeypatch.setenv("PATH", str(tmp_path) + ":" + __import__("os").environ["PATH"])
    monkeypatch.setattr(observer, "verified_ecs_runtime", lambda: True)
    rc = observer.main(["--bucket", "synthetic-bucket", "--region", "eu-west-1", "--log-group", "/synthetic/logs"])
    return rc, json.loads(path.read_text())


@pytest.mark.parametrize("retry_annotation", ["", " (reached max retries: 0)"])
def test_production_cli_bootstrap403_conditional_create_and_readback(tmp_path, monkeypatch, capsys, retry_annotation):
    key = "views/outcomes/t1.json"
    rc, state = production(tmp_path, monkeypatch, plan={"gets": {key: ["AccessDenied", "present"]}, "retry_annotation": retry_annotation})
    assert rc == 0
    writes = [a for a in state["calls"] if "put-object" in a]
    assert len(writes) == 4 and all("--if-none-match" in a for a in writes)
    assert "prior_read_denied" in capsys.readouterr().out
    obj = json.loads(state["objects"][key]["raw"])
    assert obj["meta"]["observation_state"] == "partial"
    assert obj["meta"]["current_membership"] == "unknown"
    assert all("--no-paginate" in a for a in state["calls"] if "filter-log-events" in a)


@pytest.mark.parametrize("annotation, operation, expected", [
    ("", "GetObject", "NoSuchKey"),
    (" (reached max retries: 0)", "GetObject", "NoSuchKey"),
    (" (reached max retries: 2)", "PutObject", "NoSuchKey"),
    (" (reached max retries: x)", "GetObject", None),
    (" (reached max retries: 12345678901)", "GetObject", None),
    (" (arbitrary provider text)", "GetObject", None),
    (" (reached max retries: 0)", "DeleteObject", None),
])
def test_service_error_code_accepts_only_exact_retry_annotation(annotation, operation, expected):
    from collector.observer import CommandResult, _code
    stderr = f"aws: [ERROR]: An error occurred (NoSuchKey) when calling the {operation} operation{annotation}: private prose".encode()
    result = CommandResult(254, b"", stderr)
    assert _code(result, operation) == expected
    assert _code(result, "PutObject" if operation == "GetObject" else "GetObject") is None
    assert _code(CommandResult(254, b"", stderr, "deadline"), operation) is None


def test_production_cli_existing_denied_bytes_preserved_and_denied_readback_nonzero(tmp_path, monkeypatch, capsys):
    key = "views/outcomes/t1.json"
    original = '{"private":"prior-existing-bytes"}'
    rc, state = production(tmp_path, monkeypatch, plan={"objects": {key: {"raw": original, "etag": '"old"'}}, "gets": {key: ["AccessDenied", "AccessDenied"]}})
    assert rc == 1 and state["objects"][key]["raw"] == original
    assert len([a for a in state["calls"] if "put-object" in a and key in a]) == 1
    output = capsys.readouterr().out
    assert "private" not in output
    # Creation completion alone does not prove readable status storage.
    next_path = tmp_path / "readback"
    next_path.mkdir()
    rc, state = production(next_path, monkeypatch, plan={"gets": {key: ["AccessDenied", "AccessDenied"]}})
    assert rc == 1 and key in state["objects"]
    assert "created_but_readback_unverified" in capsys.readouterr().out


def test_production_cli_malformed_prior_never_writes_key_and_auth_failure_never_bootstraps(tmp_path, monkeypatch):
    key = "views/outcomes/t1.json"
    rc, state = production(tmp_path, monkeypatch, plan={"objects": {key: {"raw": '{"meta":{}}', "etag": '"bad"'}}})
    assert rc == 1
    assert not [a for a in state["calls"] if "put-object" in a and key in a]
    other = tmp_path / "auth"
    other.mkdir()
    rc, state = production(other, monkeypatch, plan={"gets": {key: ["ExpiredToken"]}})
    assert rc == 1 and key not in state.get("objects", {})


def test_production_cli_empty_page_paginates_then_cycle_is_partial(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rc, state = production(tmp_path, monkeypatch, plan={"pages": [{"events": [], "nextToken": "provider-token"}, {"events": trace(start=now)}]})
    assert rc == 0
    assert len(state["requests"]) == 2
    assert "nextToken" not in state["requests"][0]
    assert state["requests"][1]["nextToken"] == "provider-token"
    other = tmp_path / "cycle"
    other.mkdir()
    rc, state = production(other, monkeypatch, plan={"pages": [{"events": trace(start=now), "nextToken": "cycle"}, {"events": [], "nextToken": "cycle"}]})
    assert rc == 0
    value = json.loads(state["objects"]["views/outcomes/t1.json"]["raw"])
    assert value["meta"]["reason"] == "cap"
    assert value["rows"][0]["state"] == "incomplete"


def test_production_cli_cas_reread_revokes_retained_success(tmp_path, monkeypatch):
    from collector.observer import reduce_projections, encode
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now.isoformat().replace("+00:00", "Z")
    records = trace(start=start)
    prior = reduce_projections(records, {}, now=now)
    conflict = dict(records[1])
    changed = json.loads(conflict["message"])
    changed["payload"]["count"] = 11
    conflict["message"] = json.dumps(changed)
    newer = reduce_projections([conflict], prior, now=now)
    key = "views/outcomes/t1.json"
    old = {"raw": encode(prior["t1"]).decode(), "etag": '"old"'}
    concurrent = {"raw": encode(newer["t1"]).decode(), "etag": '"new"'}
    rc, state = production(tmp_path, monkeypatch, records=[], plan={"objects": {key: old}, "puts": {key: [{"replace": concurrent}]}})
    assert rc == 0
    writes = [a for a in state["calls"] if "put-object" in a and key in a]
    assert len(writes) == 2 and all("--if-match" in a for a in writes)
    result = json.loads(state["objects"][key]["raw"])
    assert result["rows"][1]["last_success_at"] is None
    assert result["rows"][2]["last_success_at"] is None


def test_aws_pipe_cap_terminates_and_reaps_before_json_parse(tmp_path, monkeypatch):
    import os
    import time
    from collector.observer import Aws, MAX_RESPONSE_BYTES
    executable = tmp_path / "aws"
    executable.write_text("#!/usr/bin/env python3\nimport os\nwhile True: os.write(1,b'x'*65536)\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + ":" + os.environ["PATH"])
    before = time.monotonic()
    result = Aws("eu-west-1", before + 5).call("logs", "filter-log-events", [])
    assert result.failure == "cap"
    assert len(result.stdout) + len(result.stderr) <= MAX_RESPONSE_BYTES
    assert time.monotonic() - before < 5


def test_cache_without_support_is_not_evidence_and_attempt_cap_refuses_update(tmp_path):
    _, prior = run_fixture(tmp_path, trace(), name="supported")
    prior["t1"]["_state"]["attempts"] = []
    _, orphan = run_fixture(tmp_path, [], priors=prior, name="orphan")
    assert orphan["t1"]["rows"][1]["last_success_at"] is None
    assert orphan["t1"]["rows"][2]["last_success_at"] is None
    many = []
    import uuid
    for index in range(129):
        attempt = str(uuid.UUID(int=index, version=4))
        many += trace(attempt=attempt, task=f"{index:032x}")[:1]
    rc, projections = run_fixture(tmp_path, many, name="overflow")
    assert rc == 1 and not projections


def test_production_write_denial_is_terminal_and_never_calls_delete_or_list(tmp_path, monkeypatch, capsys):
    key = "views/outcomes/t1.json"
    rc, state = production(tmp_path, monkeypatch, plan={"gets": {key: ["AccessDenied"]}, "puts": {key: ["AccessDenied"]}})
    assert rc == 1
    assert len([a for a in state["calls"] if "put-object" in a and key in a]) == 1
    assert not any(any(v in a for v in ("list-objects", "list-objects-v2", "delete-object")) for a in state["calls"])
    output = capsys.readouterr().out
    assert "prior_read_denied" in output and "write_failed" in output
    assert "deliberately private" not in output


def test_production_bootstrap_contender_rereads_then_merges_conditionally(tmp_path, monkeypatch):
    from collector.observer import reduce_projections, encode
    now = datetime.now(timezone.utc).replace(microsecond=0)
    key = "views/outcomes/t1.json"
    concurrent = reduce_projections([], {}, now=now)["t1"]
    rc, state = production(tmp_path, monkeypatch, plan={"puts": {key: [{"replace": {"raw": encode(concurrent).decode(), "etag": '"contender"'}}]}})
    assert rc == 0
    writes = [a for a in state["calls"] if "put-object" in a and key in a]
    assert len(writes) == 2
    assert "--if-none-match" in writes[0]
    assert "--if-match" in writes[1] and '"contender"' in writes[1]


def test_aws_total_deadline_reaps_silent_process(tmp_path, monkeypatch):
    import os
    import time
    from collector.observer import Aws
    executable = tmp_path / "aws"
    executable.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + ":" + os.environ["PATH"])
    before = time.monotonic()
    result = Aws("eu-west-1", before + 0.2).call("logs", "filter-log-events", [])
    assert result.failure == "deadline"
    assert time.monotonic() - before < 2
