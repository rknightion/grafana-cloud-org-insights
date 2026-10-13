"""Default-off outcome recording and old consumer runtime boundary."""
from unittest import mock
import unittest
from collector import config, identity

FLAG = "GCINSIGHT_OUTCOME_OBSERVER_ENABLED"

class OutcomeConfigTest(unittest.TestCase):
    def test_flag_is_validated_and_loaded(self):
        base = {name: "synthetic" for name, _ in config.REQUIRED_ENV}
        base["GCINSIGHT_READ_TOKEN"] = "synthetic-reader"
        for value, expected in (("0", False), ("1", True)):
            with mock.patch.dict("os.environ", dict(base, **{FLAG: value}), clear=True):
                self.assertIs(config.load(tier="t1").outcome_observer_enabled, expected)
        with mock.patch.dict("os.environ", dict(base, **{FLAG: "perhaps"}), clear=True):
            with self.assertRaises(config.MissingConfig):
                config.load(tier="t1")

    def test_enabled_recording_cannot_use_old_scan_digest(self):
        old = {name: "synthetic" for name in identity.SCAN_ENV
               if name not in identity.LABEL_INVENTORY_DEFAULTS
               and name not in identity.PRODUCER_RULE_DEFAULTS and name != FLAG}
        digest = identity.projection_digest("scan", old)
        for value in (None, "0"):
            source = dict(old, GCINSIGHT_RUNTIME_CONFIG_DIGEST=digest)
            if value is not None:
                source[FLAG] = value
            self.assertEqual(identity.verify_runtime_projection("scan", environ=source), digest)
        with self.assertRaises(identity.InvalidIdentity):
            identity.verify_runtime_projection("scan", environ=dict(
                old, **{FLAG: "1", "GCINSIGHT_RUNTIME_CONFIG_DIGEST": digest}))
