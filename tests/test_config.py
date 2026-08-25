"""Configuration is REQUIRED, not defaulted.

Every value here names a specific Grafana Cloud org, stack or tenant. A default would be one
deployment's identifiers baked into everyone else's collector, and the failure mode is silent: the
scan runs, authenticates, and writes a correct-looking set of series to somebody else's tenant.

So `load()` refuses rather than guessing, and the message names the variable and what it is for.
"""

from __future__ import annotations

import os
import unittest

from collector import config

REQUIRED = (
    "GCINSIGHT_READ_TOKEN",
    "GCINSIGHT_ORG_ID",
    "GCINSIGHT_WRITE_STACK",
    "GCINSIGHT_MIMIR_URL",
    "GCINSIGHT_MIMIR_TENANT",
    "GCINSIGHT_LOKI_URL",
    "GCINSIGHT_LOKI_TENANT",
)

COMPLETE = {
    "GCINSIGHT_READ_TOKEN": "read-token",
    "GCINSIGHT_WRITE_TOKEN": "write-token",
    "GCINSIGHT_ORG_ID": "123456",
    "GCINSIGHT_WRITE_STACK": "obs-hub",
    "GCINSIGHT_MIMIR_URL": "https://prometheus-prod-01-eu-west-0.grafana.net",
    "GCINSIGHT_MIMIR_TENANT": "111111",
    "GCINSIGHT_LOKI_URL": "https://logs-prod-001.grafana.net",
    "GCINSIGHT_LOKI_TENANT": "222222",
}


class _Env:
    """Replace the whole GCINSIGHT_* namespace, so a developer's own shell cannot mask a failure."""

    def __init__(self, **values: str):
        self.values = values

    def __enter__(self):
        self.saved = {k: v for k, v in os.environ.items() if k.startswith("GCINSIGHT_")}
        for k in self.saved:
            del os.environ[k]
        os.environ.update(self.values)
        return self

    def __exit__(self, *exc):
        for k in [k for k in os.environ if k.startswith("GCINSIGHT_")]:
            del os.environ[k]
        os.environ.update(self.saved)
        return False


class RequiredConfigTest(unittest.TestCase):
    def test_a_complete_environment_loads(self):
        with _Env(**COMPLETE):
            cfg = config.load(tier="t1")
        self.assertEqual(cfg.org_id, "123456")
        self.assertEqual(cfg.write_stack, "obs-hub")
        self.assertEqual(cfg.mimir_tenant, "111111")
        self.assertEqual(cfg.coverage_score_weights, {
            component: 1.0 for component in config.observability_score.COMPONENTS
        })

    def test_invalid_coverage_weights_fail_configuration_loading(self):
        with _Env(**dict(COMPLETE, GCINSIGHT_COVERAGE_SCORE_WEIGHTS='{"slo": -1}')):
            with self.assertRaisesRegex(
                config.MissingConfig, "GCINSIGHT_COVERAGE_SCORE_WEIGHTS"
            ):
                config.load(tier="t1")

    def test_every_required_variable_is_refused_when_absent(self):
        for missing in REQUIRED:
            env = {k: v for k, v in COMPLETE.items() if k != missing}
            with self.subTest(missing=missing), _Env(**env):
                with self.assertRaises(config.IncompleteConfig) as caught:
                    config.load(tier="t1")
                self.assertIn(missing, str(caught.exception),
                              "the error must name the variable, or it is a scavenger hunt")

    def test_an_empty_string_counts_as_absent(self):
        """A blank env var is how a broken deployment presents - Terraform passing through an unset
        variable gives "" rather than removing the key."""
        with _Env(**dict(COMPLETE, GCINSIGHT_MIMIR_TENANT="   ")):
            with self.assertRaises(config.MissingConfig):
                config.load(tier="t1")

    def test_both_refusals_share_one_base_so_a_caller_needs_one_except(self):
        """scan.py exits on `IncompleteConfig`. When these were unrelated classes, a missing org id
        escaped as a traceback while a missing token exited cleanly."""
        self.assertTrue(issubclass(config.MissingCredential, config.IncompleteConfig))
        self.assertTrue(issubclass(config.MissingConfig, config.IncompleteConfig))

    def test_the_write_token_still_falls_back_to_the_read_token(self):
        """One credential is enough for an interactive read-only run; deployment sets both."""
        env = {k: v for k, v in COMPLETE.items() if k != "GCINSIGHT_WRITE_TOKEN"}
        with _Env(**env):
            cfg = config.load(tier="t1")
        self.assertEqual(cfg.write_token, cfg.cap)
        self.assertFalse(cfg.redacted["credentials_split"])

    def test_no_module_constant_carries_a_deployment_identifier(self):
        """The regression this file exists for: a default org id or stack slug reintroduced as a
        convenience, so a fresh deployment silently writes to whoever's identifiers were left here."""
        for name in dir(config):
            if not name.isupper():
                continue
            value = getattr(config, name)
            if not isinstance(value, str):
                continue
            self.assertFalse(
                value.isdigit() and len(value) >= 5,
                f"config.{name} = {value!r} looks like an org or tenant id",
            )
            self.assertNotIn("grafana.net", value,
                             f"config.{name} = {value!r} names a specific stack endpoint")

    def test_no_credential_is_ever_in_the_redacted_form(self):
        with _Env(**COMPLETE):
            red = config.load(tier="t1").redacted
        self.assertNotIn("read-token", str(red))
        self.assertNotIn("write-token", str(red))


if __name__ == "__main__":
    unittest.main()


class BuildToolTargetsAreNotDefaultedTest(unittest.TestCase):
    """The two BUILD tools name their target in module-level constants, outside `config.load()`.

    They were therefore missed by the sweep that made everything else required, and each one carried a
    real deployment's identifier as its default: `bin/dashboards.py` defaulted the write stack's numeric
    id, and `bin/alerts.py` defaulted the insights folder uid. Neither fails loudly - the v2 resource API
    namespaces dashboards as `stacks-<id>`, so an id is all it needs, and a folder uid that exists on
    the stack it came from takes alert rules straight into somebody else's folder.

    Read as SOURCE, not imported: importing evaluates the constants against this process's environment,
    so a variable set in the shell running the suite would hide the default entirely.
    """

    #: file -> (target variables, the argv that reaches the publish path). `--publish` takes a
    #: dashboard name in one tool and is a bare flag in the other, so the argv cannot be shared.
    TARGETS = {
        "bin/dashboards.py": (("GCINSIGHT_WRITE_STACK_URL", "GCINSIGHT_WRITE_STACK_ID"),
                              ["--publish", "estate"]),
        "bin/alerts.py": (("GCINSIGHT_WRITE_STACK_URL", "GCINSIGHT_INSIGHTS_FOLDER_UID"),
                          ["--publish"]),
    }

    def _source(self, path: str) -> str:
        import pathlib
        return (pathlib.Path(__file__).resolve().parent.parent / path).read_text()

    def test_no_target_variable_has_a_default(self):
        import re
        for path, (variables, _argv) in self.TARGETS.items():
            src = self._source(path)
            for var in variables:
                with self.subTest(file=path, var=var):
                    found = re.findall(rf'os\.environ\.get\(\s*"{var}"\s*,\s*("[^"]*")\s*\)', src)
                    self.assertTrue(found, f"{var} is not read in {path} - has it been renamed?")
                    for default in found:
                        self.assertEqual(default, '""', f"{var} in {path} defaults to {default}")

    def test_each_tool_refuses_when_a_target_is_unset(self):
        """A default is only half of it: unset must exit non-zero rather than build a relative URL."""
        import subprocess
        import sys
        for path, (variables, argv) in self.TARGETS.items():
            for var in variables:
                with self.subTest(file=path, missing=var):
                    env = {k: v for k, v in os.environ.items() if not k.startswith("GCINSIGHT_")}
                    env["GCINSIGHT_GRAFANA_TOKEN"] = "t"
                    for other in variables:
                        if other != var:
                            env[other] = "x"
                    proc = subprocess.run(
                        [sys.executable, path, *argv],
                        capture_output=True, text=True, env=env,
                        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
                    )
                    self.assertNotEqual(proc.returncode, 0,
                                        f"{path} ran with {var} unset:\n{proc.stdout[-400:]}")
                    self.assertIn(var, proc.stderr, proc.stderr[-400:])
