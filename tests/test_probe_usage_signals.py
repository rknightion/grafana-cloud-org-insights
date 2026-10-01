"""Offline proofs at the probe's CLI boundary, with process-edge tripwires."""
import builtins
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin/probe_usage_signals.py"
CODE = compile(SCRIPT.read_text(), str(SCRIPT), "exec")


def invoke(monkeypatch, args, *, queries=None, writes=False):
    monkeypatch.setenv("GCINSIGHT_GCX_CONTEXT", "synthetic-environment-context")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *args])

    def forbidden(*args, **kwargs):
        pytest.fail("CLI reached a forbidden process-edge primitive")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(subprocess, "run", queries or forbidden)
    allowed_output = Path(args[args.index("--out") + 1]) if writes else None
    for module in (builtins, io):
        original = module.open

        def guarded(file, mode="r", *args, _open=original, **kwargs):
            if any(flag in mode for flag in "wax+") and Path(file) != allowed_output:
                forbidden()
            return _open(file, mode, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)
    original_os_open = os.open

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            if Path(path) != allowed_output:
                forbidden()
        return original_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_os_open)
    with pytest.raises(SystemExit) as exc:
        exec(CODE, {"__name__": "__main__", "__file__": str(SCRIPT)})
    return exc.value.code


def test_help_has_no_side_effects(monkeypatch, capsys):
    assert invoke(monkeypatch, ["--help"]) == 0
    assert "--context" in capsys.readouterr().out


@pytest.mark.parametrize("args", [[], ["--unknown"], ["--context", "synthetic"],
                                      ["--out", "unused.json"],
                                      ["--context", " ", "--out", "unused.json"]])
def test_invalid_arguments_have_no_side_effects(monkeypatch, args):
    assert invoke(monkeypatch, args) == 2


def test_existing_output_refused_before_queries(monkeypatch, tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("keep this artifact")
    assert invoke(monkeypatch, ["--context", "synthetic", "--out", str(output)]) == 2
    assert output.read_text() == "keep this artifact"


def test_committed_artifact_refused_before_queries(monkeypatch):
    output = ROOT / "testdata/usage-datasource-signals.json"
    before = output.read_bytes()
    assert invoke(monkeypatch, ["--context", "synthetic", "--out", str(output)]) == 2
    assert output.read_bytes() == before


@pytest.mark.parametrize("overwrite", [False, True])
def test_explicit_output_with_fake_gcx(monkeypatch, tmp_path, overwrite):
    import json

    output = tmp_path / "probe.json"
    if overwrite:
        output.write_text("old artifact")
    calls = []

    def fake_gcx(command, **kwargs):
        calls.append(command)
        payload = {"status": "success", "data": {"result": []}} if command[2] == "query" else {"data": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    args = ["--context", "explicit-synthetic", "--out", str(output)]
    if overwrite:
        args.append("--overwrite")
    assert invoke(monkeypatch, args, queries=fake_gcx, writes=True) == 0
    artifact = json.loads(output.read_text())
    assert artifact["source"]["stack_context"] == "explicit-synthetic"
    assert calls and all(cmd[:2] == ["gcx", "metrics"] and cmd[2] in {"query", "series"} for cmd in calls)
    assert all(cmd[cmd.index("--context") + 1] == "explicit-synthetic" for cmd in calls)
