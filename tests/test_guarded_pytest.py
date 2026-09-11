"""Resource-boundary tests for the guarded pytest runner."""

from __future__ import annotations

import unittest
from unittest import mock

from tests import guarded_pytest
from tests.combinatorics import subsets_up_to


class ProcessTreeMemoryTest(unittest.TestCase):
    def test_rss_includes_the_root_and_every_descendant_only(self):
        rows = {
            10: (1, 100),
            11: (10, 200),
            12: (11, 300),
            20: (1, 9_999),
        }
        self.assertEqual(guarded_pytest._descendant_rss_kib(10, rows), 600)

    def test_malformed_process_rows_are_ignored(self):
        self.assertEqual(
            guarded_pytest._parse_process_table("10 1 100\nheading\n11 x 200\n"),
            {10: (1, 100)},
        )


class BoundedCombinatoricsTest(unittest.TestCase):
    def test_subsets_are_complete_inside_the_cap(self):
        self.assertEqual(
            set(subsets_up_to(("a", "b", "c"), max_size=2, max_subsets=7)),
            {
                frozenset(),
                frozenset({"a"}),
                frozenset({"b"}),
                frozenset({"c"}),
                frozenset({"a", "b"}),
                frozenset({"a", "c"}),
                frozenset({"b", "c"}),
            },
        )

    def test_cap_is_checked_before_the_first_subset_is_yielded(self):
        candidates = subsets_up_to(range(18), max_size=18, max_subsets=512)
        with self.assertRaisesRegex(AssertionError, "262144 subsets"):
            next(candidates)


class GuardActionTest(unittest.TestCase):
    def test_the_test_process_tree_is_stopped_at_the_memory_cap(self):
        process = mock.Mock(pid=123, returncode=None)
        process.poll.return_value = None
        with (
            mock.patch.object(guarded_pytest.subprocess, "Popen", return_value=process),
            mock.patch.object(
                guarded_pytest, "_tree_rss_kib", return_value=(2048 * 1024) + 1
            ),
            mock.patch.object(guarded_pytest, "_stop") as stop,
            mock.patch.dict(
                guarded_pytest.os.environ,
                {"GCINSIGHT_TEST_MAX_RSS_MIB": "2048"},
                clear=False,
            ),
        ):
            self.assertEqual(guarded_pytest.main(["tests"]), 137)
        stop.assert_called_once_with(process)

    def test_stop_kills_the_group_when_a_descendant_survives_sigterm(self):
        process = mock.Mock(pid=123)
        with (
            mock.patch.object(guarded_pytest.os, "killpg") as killpg,
            mock.patch.object(guarded_pytest, "_group_exists", return_value=True),
            mock.patch.object(guarded_pytest.time, "monotonic", side_effect=[0.0, 6.0]),
        ):
            guarded_pytest._stop(process)

        self.assertEqual(
            killpg.call_args_list,
            [mock.call(123, guarded_pytest.signal.SIGTERM), mock.call(123, guarded_pytest.signal.SIGKILL)],
        )
        process.wait.assert_called_once_with(timeout=guarded_pytest.GROUP_GRACE_SECONDS)


if __name__ == "__main__":
    unittest.main()
