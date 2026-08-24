import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "bin" / "build-and-push.sh"


class BuildAndPushTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        (self.repo / "bin").mkdir(parents=True)
        shutil.copy2(SCRIPT, self.repo / "bin" / SCRIPT.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)

        self.calls = root / "calls"
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        for name in ("docker", "aws"):
            command = fake_bin / name
            command.write_text(f'#!/bin/sh\necho "{name} $*" >> "$CALLS"\n')
            command.chmod(0o755)
        self.env = os.environ | {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "CALLS": str(self.calls),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        return subprocess.run(
            ["bash", "bin/build-and-push.sh", "--repo", "registry.example/insights", *args],
            cwd=self.repo,
            env=self.env,
            text=True,
            capture_output=True,
        )

    def test_untracked_file_makes_push_refuse(self):
        (self.repo / "untracked.txt").write_text("not in the commit\n")

        result = self.run_script()

        self.assertEqual(3, result.returncode, result.stdout + result.stderr)
        self.assertIn("untracked.txt", result.stderr)
        self.assertFalse(self.calls.exists(), "the image build must not start")

    def test_default_push_publishes_only_commit_tag(self):
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.repo,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

        result = self.run_script()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        calls = self.calls.read_text()
        self.assertIn(f"docker push -q registry.example/insights:sha-{sha}", calls)
        self.assertNotIn(":latest", calls)

    def test_publish_latest_explicitly_moves_live_tag_after_commit_tag(self):
        result = self.run_script("--publish-latest")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        pushes = [line for line in self.calls.read_text().splitlines() if line.startswith("docker push")]
        self.assertEqual(2, len(pushes))
        self.assertIn(":sha-", pushes[0])
        self.assertEqual("docker push -q registry.example/insights:latest", pushes[1])
        self.assertIn(
            "production task definitions remain on their immutable Terraform pin",
            result.stdout,
        )

    def test_push_without_a_git_commit_is_refused_before_building(self):
        git_dir = self.repo / ".git"
        hidden = self.repo.parent / "git-metadata"
        git_dir.rename(hidden)
        try:
            result = self.run_script()
        finally:
            hidden.rename(git_dir)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("cannot determine a git commit", result.stderr)
        self.assertFalse(self.calls.exists(), "an unattributable image must not be built or pushed")

    def test_no_push_build_without_git_uses_the_nogit_tag(self):
        git_dir = self.repo / ".git"
        hidden = self.repo.parent / "git-metadata"
        git_dir.rename(hidden)
        try:
            result = self.run_script("--no-push")
        finally:
            hidden.rename(git_dir)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("docker build", self.calls.read_text())
        self.assertIn("sha-nogit", result.stdout)


if __name__ == "__main__":
    unittest.main()
