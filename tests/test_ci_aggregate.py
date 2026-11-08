"""Execute the local CI aggregate's actual shell with bounded synthetic needs.

This deliberately supports only the small YAML/expression surface used by this
job, without adding a product dependency on a YAML or Actions interpreter.
Unsupported wiring fails closed rather than silently dropping a step.
"""

import os
from pathlib import Path
import re
import subprocess
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
REQUIRED = ("tests", "identifiers", "terraform", "ac-evidence", "privacy-sweep", "backlog-freeze")
PR_ONLY = ("ac-evidence", "privacy-sweep", "backlog-freeze")
REPO = "owner/repo"


def aggregate():
    workflow = WORKFLOW.read_text()
    jobs = re.findall(r"^  ([\w-]+):$", workflow.split("\njobs:\n", 1)[1], re.MULTILINE)
    block = workflow.split("  ci-success:\n", 1)[1]
    block = re.split(r"\n  [\w-]+:\n", block, maxsplit=1)[0]
    assert re.search(r"^    if: always\(\)$", block, re.MULTILINE)
    needs = re.search(r"^    needs: \[([^\]]+)\]$", block, re.MULTILINE)
    assert needs is not None
    leaves = tuple(part.strip() for part in needs[1].split(","))
    assert set(leaves) == set(REQUIRED) == set(jobs) - {"ci-success"}
    assert len(leaves) == len(REQUIRED)
    steps = block.split("    steps:\n", 1)[1]
    parsed = []
    for raw in steps.split("      - name: ")[1:]:
        lines = raw.splitlines()
        condition = None
        env = {}
        script = None
        index = 1
        while index < len(lines):
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                index += 1
                continue
            if line.startswith("        if: "):
                condition = line.removeprefix("        if: ")
            elif line == "        env:":
                index += 1
                while index < len(lines) and lines[index].startswith("          "):
                    key, value = lines[index].strip().split(": ", 1)
                    env[key] = value
                    index += 1
                continue
            elif line.startswith("        run: "):
                value = line.removeprefix("        run: ")
                if value == "|":
                    body = lines[index + 1:]
                    assert all(not item.strip() or item.startswith("          ") for item in body)
                    script = "\n".join(item[10:] for item in body)
                    index = len(lines)
                    continue
                script = value
            else:
                raise AssertionError(f"Unsupported aggregate step field: {line}")
            index += 1
        assert script is not None
        parsed.append((condition, env, script))
    assert parsed and len(parsed) == steps.count("      - ")
    return leaves, parsed


def resolve(value, leaves, results, context):
    """Resolve only witnessed needs and github context expressions; omitted results become empty."""
    joined = "${{ join(needs.*.result, ', ') }}"
    if value == joined:
        return ", ".join(results[leaf] for leaf in leaves if leaf in results)
    if value in context:
        return context[value]
    match = re.fullmatch(r"\$\{\{ needs\.([\w-]+)\.result \}\}", value)
    assert match is not None, f"Unsupported aggregate env expression: {value}"
    assert match[1] in leaves
    return results.get(match[1], "")


def enabled(condition, results):
    if condition is None:
        return True
    # The original aggregate uses this OR of contains predicates. Keeping it
    # executable makes the pre-fix skipped/missing acceptance visible.
    match = re.fullmatch(r"\$\{\{ (.+) \}\}", condition)
    assert match is not None, f"Unsupported step condition: {condition}"
    predicates = match[1].split(" || ")
    states = []
    for predicate in predicates:
        found = re.fullmatch(r"contains\(needs\.\*\.result, '([a-z]+)'\)", predicate)
        assert found is not None, f"Unsupported step predicate: {predicate}"
        states.append(found[1])
    return any(state in results.values() for state in states)


def run_aggregate(results, event="pull_request", head_repo=REPO):
    leaves, steps = aggregate()
    context = {
        "${{ github.event_name }}": event,
        "${{ github.event.pull_request.head.repo.full_name }}": head_repo if event == "pull_request" else "",
        "${{ github.repository }}": REPO,
    }
    output = []
    for condition, expressions, script in steps:
        if not enabled(condition, results):
            continue
        env = {"PATH": os.defpath, "LC_ALL": "C"}
        env.update({key: resolve(value, leaves, results, context) for key, value in expressions.items()})
        completed = subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
            env=env, capture_output=True, text=True, timeout=5,
        )
        output.append(completed.stdout + completed.stderr)
        if completed.returncode:
            return completed.returncode, "".join(output)
    return 0, "".join(output)


BAD = ("failure", "cancelled", "skipped", "missing", "", "unknown")


def scenario(event, **overrides):
    """All-green results for an event: the pull request jobs are skipped off a pull request."""
    results = dict.fromkeys(REQUIRED, "success")
    if event != "pull_request":
        results.update(dict.fromkeys(PR_ONLY, "skipped"))
    results.update(overrides)
    return results


def with_state(results, leaf, state):
    results = dict(results)
    if state == "missing":
        del results[leaf]
    else:
        results[leaf] = state
    return results


class CIAggregateTests(unittest.TestCase):
    def test_same_repository_pull_request_succeeds(self):
        code, output = run_aggregate(scenario("pull_request"))
        self.assertEqual(code, 0, output)
        self.assertIn("ci-success", output)

    def test_same_repository_pull_request_rejects_every_non_success(self):
        for leaf in REQUIRED:
            for state in BAD:
                with self.subTest(leaf=leaf, state=state):
                    code, output = run_aggregate(with_state(scenario("pull_request"), leaf, state))
                    self.assertNotEqual(code, 0, f"Accepted {leaf}={state!r}: {output}")

    def test_push_and_dispatch_accept_skipped_pull_request_checks_only(self):
        for event in ("push", "workflow_dispatch"):
            with self.subTest(event=event):
                code, output = run_aggregate(scenario(event), event=event)
                self.assertEqual(code, 0, output)
                code, output = run_aggregate(scenario(event, **dict.fromkeys(PR_ONLY, "success")), event=event)
                self.assertEqual(code, 0, output)
                for leaf in REQUIRED:
                    for state in BAD:
                        if leaf in PR_ONLY and state == "skipped":
                            continue
                        with self.subTest(leaf=leaf, state=state):
                            code, output = run_aggregate(with_state(scenario(event), leaf, state), event=event)
                            self.assertNotEqual(code, 0, f"Accepted {event} {leaf}={state!r}: {output}")

    def test_fork_pull_request_accepts_skipped_identifiers_only(self):
        fork = "someone/fork"
        code, output = run_aggregate(scenario("pull_request", identifiers="skipped"), head_repo=fork)
        self.assertEqual(code, 0, output)
        code, output = run_aggregate(scenario("pull_request"), head_repo=fork)
        self.assertEqual(code, 0, output)
        for leaf in REQUIRED:
            for state in BAD:
                if leaf == "identifiers" and state == "skipped":
                    continue
                with self.subTest(leaf=leaf, state=state):
                    code, output = run_aggregate(with_state(scenario("pull_request"), leaf, state), head_repo=fork)
                    self.assertNotEqual(code, 0, f"Accepted fork {leaf}={state!r}: {output}")

    def test_deleted_fork_counts_as_a_fork(self):
        code, output = run_aggregate(scenario("pull_request", identifiers="skipped"), head_repo="")
        self.assertEqual(code, 0, output)

    def test_entire_needs_payload_missing_is_rejected(self):
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                code, output = run_aggregate({}, event=event)
                self.assertNotEqual(code, 0, f"Accepted an absent needs payload: {output}")
