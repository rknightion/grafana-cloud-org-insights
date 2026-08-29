"""The public-repository identifier gate scans reachable history, not only HEAD."""

from __future__ import annotations

import pathlib
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent


class IdentifierGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        (self.repo / "bin").mkdir()
        shutil.copy(ROOT / "bin" / "check-customer-identifiers", self.repo / "bin")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=self.repo, check=True
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def commit(self, message: str) -> None:
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=self.repo, check=True)

    def run_gate(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN"] = "forbidden-customer"
        return subprocess.run(
            [str(self.repo / "bin" / "check-customer-identifiers"), *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_gate_refuses_to_run_without_external_patterns(self):
        result = subprocess.run(
            [str(self.repo / "bin" / "check-customer-identifiers")],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": os.environ["PATH"]},
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("provide --patterns-file", result.stderr)

    def test_gate_fails_closed_on_an_invalid_pattern(self):
        env = os.environ.copy()
        env["GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN"] = "["
        result = subprocess.run(
            [str(self.repo / "bin" / "check-customer-identifiers")],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unable to scan", result.stderr)

    def test_gate_ignores_the_repo_local_virtualenv(self):
        venv_marker = self.repo / ".venv" / "marker.txt"
        venv_marker.parent.mkdir()
        venv_marker.write_text("forbidden-customer\n")

        result = self.run_gate()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gate_rejects_a_tracked_virtualenv(self):
        venv_marker = self.repo / ".venv" / "marker.txt"
        venv_marker.parent.mkdir()
        venv_marker.write_text("forbidden-customer\n")
        subprocess.run(["git", "add", "-f", ".venv/marker.txt"], cwd=self.repo, check=True)

        result = self.run_gate()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(".venv must not be tracked", result.stderr)

    def test_gate_rejects_a_tracked_nested_virtualenv(self):
        venv_marker = self.repo / "tools" / ".venv" / "marker.txt"
        venv_marker.parent.mkdir(parents=True)
        venv_marker.write_text("forbidden-customer\n")
        subprocess.run(
            ["git", "add", "-f", "tools/.venv/marker.txt"], cwd=self.repo, check=True
        )

        result = self.run_gate()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(".venv must not be tracked", result.stderr)

    def test_history_mode_rejects_a_leak_removed_from_head(self):
        (self.repo / "artifact.txt").write_text("forbidden-customer\n")
        self.commit("add unsafe fixture")
        (self.repo / "artifact.txt").write_text("synthetic fixture\n")
        self.commit("anonymise fixture")

        self.assertEqual(self.run_gate().returncode, 0)
        history = self.run_gate("--history")
        self.assertEqual(history.returncode, 1)
        self.assertIn("historical file content", history.stderr)
        self.assertNotIn("forbidden-customer", history.stderr)

    def test_history_mode_rejects_a_leak_in_commit_metadata(self):
        (self.repo / "artifact.txt").write_text("synthetic fixture\n")
        self.commit("mention forbidden-customer in history")

        history = self.run_gate("--history")
        self.assertEqual(history.returncode, 1)
        self.assertIn("commit metadata", history.stderr)
        self.assertNotIn("forbidden-customer", history.stderr)

    def test_history_mode_rejects_a_leak_in_an_old_path_name(self):
        leaked = self.repo / "forbidden-customer-notes.txt"
        leaked.write_text("synthetic fixture\n")
        self.commit("add fixture")
        leaked.rename(self.repo / "fixture-notes.txt")
        self.commit("rename fixture")

        history = self.run_gate("--history")
        self.assertEqual(history.returncode, 1)
        self.assertIn("historical path name", history.stderr)
        self.assertNotIn("forbidden-customer", history.stderr)

    def test_history_mode_accepts_a_clean_lineage(self):
        (self.repo / "artifact.txt").write_text("synthetic fixture\n")
        self.commit("add synthetic fixture")

        result = self.run_gate("--history")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("customer identifier history: clean", result.stdout)


if __name__ == "__main__":
    unittest.main()
