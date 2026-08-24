"""Adaptive Logs recommendations (PLAN 18.16).

Three of these tests exist because the live payload contradicts something plausible:

- `volume` on an already-dropped pattern is ~0, so the applied saving is NOT derivable here. A test
  pins that we never claim it.
- `tokens` carries raw log lines. A test pins that nothing leaving the module carries it.
- the API states no window and ignores every window parameter, so nothing may be expressed as a rate.
"""

from __future__ import annotations

import unittest

from collector.sources import adaptive_logs as al

GB = 1024 ** 3


def rec(volume=0, configured=0, recommended=99, queried=0, ingested=1000,
        levels=("info",), locked=False, superseded=False, tokens=("ts=<TIMESTAMP> ", "host.internal ")):
    return {"volume": volume, "configured_drop_rate": configured,
            "recommended_drop_rate": recommended, "queried_lines": queried,
            "ingested_lines": ingested, "levels": list(levels), "locked": locked,
            "superseded": superseded, "segments": {}, "tokens": list(tokens)}


class NeverStoreTokensTest(unittest.TestCase):
    def test_strip_removes_tokens(self):
        self.assertNotIn("tokens", al.strip(rec()))

    def test_every_field_except_tokens_survives(self):
        """The stripping must be surgical - losing `queried_lines` would silently break the
        'safe to drop' split, which is the half of the finding that is actionable."""
        out = al.strip(rec(volume=5, queried=7))
        for key in ("volume", "configured_drop_rate", "recommended_drop_rate", "queried_lines",
                    "ingested_lines", "levels", "locked", "superseded", "segments"):
            self.assertIn(key, out)

    def test_no_raw_log_fragment_reaches_a_summary(self):
        """The end-to-end guarantee, asserted on the text of the whole record rather than on a key -
        a future field carrying the same content would slip past a key-name check."""
        out = al.summarise("s", [al.strip(rec(volume=GB))])
        self.assertNotIn("host.internal", repr(out))
        self.assertNotIn("TIMESTAMP", repr(out))


class PendingBytesTest(unittest.TestCase):
    def test_an_undropped_pattern_yields_its_recommended_share(self):
        self.assertAlmostEqual(al.pending_bytes(rec(volume=100 * GB, configured=0, recommended=99)),
                               99 * GB, delta=GB * 0.01)

    def test_a_fully_dropped_pattern_yields_NOTHING_PENDING(self):
        """Live shape: 174 of 222 recommendations on one stack sit at configured=recommended=99."""
        self.assertEqual(al.pending_bytes(rec(volume=0, configured=99, recommended=99)), 0)

    def test_a_partially_dropped_pattern_yields_only_the_DIFFERENCE(self):
        self.assertAlmostEqual(al.pending_bytes(rec(volume=100 * GB, configured=50, recommended=90)),
                               40 * GB, delta=GB * 0.01)

    def test_over_configured_is_ZERO_not_NEGATIVE(self):
        """A stack more aggressive than the recommendation has nothing pending. Letting this go
        negative would net a real saving elsewhere down and understate the estate total."""
        self.assertEqual(al.pending_bytes(rec(volume=100 * GB, configured=99, recommended=50)), 0)

    def test_missing_fields_do_not_crash(self):
        self.assertEqual(al.pending_bytes({}), 0)


class SummariseTest(unittest.TestCase):
    # The measured shape in miniature: a few big undropped patterns, a long tail already
    # at 99% reporting ~zero residual volume.
    LIVE_SHAPE = [
        rec(volume=140 * GB, configured=0, recommended=99, queried=0),
        rec(volume=40 * GB, configured=0, recommended=99, queried=0),
        rec(volume=30 * GB, configured=0, recommended=99, queried=1469, levels=("error",)),
    ] + [rec(volume=0, configured=99, recommended=99) for _ in range(174)]

    def setUp(self):
        self.out = al.summarise("stack076", [al.strip(r) for r in self.LIVE_SHAPE])

    def test_recommendations_counts_everything_pending_counts_only_the_actionable(self):
        self.assertEqual(self.out["recommendations"], 177)
        self.assertEqual(self.out["pending"], 3)

    def test_applied_is_a_COUNT_and_there_is_no_applied_SAVING_field(self):
        """The whole point of the residual-volume finding. A pattern already at 99% reports ~0 volume,
        so no field here can reconstruct what it used to be. Publishing an `applied_bytes` computed as
        `volume * configured/100` would read 0.00 GB and be presented as 'nothing has been saved',
        which is the opposite of the truth - the datasource metric says 743 GB/day estate-wide."""
        self.assertEqual(self.out["applied"], 174)
        for forbidden in ("applied_bytes", "applied_saving", "saved_bytes", "realised_bytes"):
            self.assertNotIn(forbidden, self.out)

    def test_pending_bytes_sums_only_the_pending(self):
        self.assertAlmostEqual(self.out["pending_bytes"] / GB, (140 + 40 + 30) * 0.99, delta=0.5)

    def test_the_unqueried_subset_is_reported_separately(self):
        """Unqueried is droppable without a review conversation; queried is not. Reporting only the
        total is what invites 'why has nobody done this'."""
        self.assertEqual(self.out["pending_unqueried"], 2)
        self.assertAlmostEqual(self.out["pending_bytes_unqueried"] / GB, (140 + 40) * 0.99, delta=0.5)

    def test_NOTHING_in_the_summary_is_a_rate(self):
        """The API names no window and ignores every window parameter, so a per-second or per-day
        figure here would be invented. Bytes only."""
        for key in self.out:
            for banned in ("per_second", "per_day", "_rate", "bytes_per", "daily"):
                self.assertNotIn(banned, key, f"{key} looks like a rate")

    def test_the_sample_is_ranked_by_pending_and_bounded(self):
        self.assertEqual(len(self.out["sample"]), 3)
        vals = [s["pending_bytes"] for s in self.out["sample"]]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_the_sample_carries_no_tokens_and_no_pattern_text(self):
        for s in self.out["sample"]:
            self.assertNotIn("tokens", s)
            self.assertNotIn("segments", s)

    def test_sample_is_capped(self):
        many = [al.strip(rec(volume=(i + 1) * GB)) for i in range(40)]
        self.assertEqual(len(al.summarise("s", many)["sample"]), al.SAMPLE)

    def test_levels_are_collected_across_the_whole_payload(self):
        out = al.summarise("s", [al.strip(rec(levels=("info",))), al.strip(rec(levels=("error", "warn")))])
        self.assertEqual(out["levels"], ["error", "info", "warn"])

    def test_an_empty_payload_is_a_real_ZERO_not_unavailable(self):
        """A measured empty response is a genuine
        'nothing to drop', and it must be distinguishable from a stack that could not be read."""
        out = al.summarise("obs-hub", [])
        self.assertTrue(out["available"])
        self.assertEqual(out["recommendations"], 0)
        self.assertEqual(out["pending_bytes"], 0)


class ProbeStackTest(unittest.TestCase):
    STACK = {"slug": "alpha", "url": "https://alpha.grafana.net", "id": 1}

    class FakeClient:
        def __init__(self, statuses, body=None):
            self.statuses = list(statuses)
            self.body = body if body is not None else []
            self.urls = []

        def get(self, url, **kw):
            self.urls.append(url)
            status = self.statuses.pop(0)
            payload = self.body

            class R:
                def __init__(self, s, p):
                    self.status, self._p = s, p

                @property
                def ok(self):
                    return 200 <= self.status < 300

                def json(self):
                    return self._p
            return R(status, payload)

    def test_the_host_comes_from_the_stacks_own_url(self):
        c = self.FakeClient([200], [])
        al.probe_stack(c, {"slug": "a", "url": "https://odd-name.grafana.net"}, "t")
        self.assertTrue(c.urls[0].startswith("https://odd-name.grafana.net/"))

    def test_missing_url_is_unmeasured_and_never_receives_the_reader_token(self):
        c = self.FakeClient([200], [])
        out = al.probe_stack(c, {"slug": "must-not-be-a-hostname"}, "reader-token")
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], "invalid_url")
        self.assertEqual(c.urls, [])

    def test_a_403_is_retried_ONCE_because_rbac_is_cached(self):
        c = self.FakeClient([403, 200], [al.strip(rec(volume=GB))])
        out = al.probe_stack(c, self.STACK, "t", sleep=lambda _s: None)
        self.assertTrue(out["available"])
        self.assertEqual(len(c.urls), 2)

    def test_a_401_is_NEVER_retried(self):
        """A wrong token does not become a right one in three seconds; retrying doubles the sweep."""
        c = self.FakeClient([401], [])
        out = al.probe_stack(c, self.STACK, "t", sleep=lambda _s: None)
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], al.UNAUTHORISED)
        self.assertEqual(len(c.urls), 1)

    def test_a_404_is_NEVER_retried_and_reads_as_plugin_absent(self):
        c = self.FakeClient([404], [])
        out = al.probe_stack(c, self.STACK, "t", sleep=lambda _s: None)
        self.assertEqual(out["reason"], al.PLUGIN_ABSENT)
        self.assertEqual(len(c.urls), 1)

    def test_a_200_that_is_not_a_list_is_an_ERROR_not_an_empty_estate(self):
        c = self.FakeClient([200], {"message": "something else"})
        out = al.probe_stack(c, self.STACK, "t")
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], al.HTTP_ERROR)


class ProbeAllTest(unittest.TestCase):
    STACKS = [
        {"slug": "a", "url": "https://a.grafana.net"},
        {"slug": "paused", "url": "https://p.grafana.net", "status": "paused"},
        {"slug": "nocred", "url": "https://n.grafana.net"},
    ]

    class OK:
        def get(self, url, **kw):
            class R:
                status = 200
                ok = True

                def json(self):
                    return []
            return R()

    def test_paused_is_skipped_and_a_missing_credential_is_its_own_state(self):
        out = al.probe_all(self.OK(), self.STACKS, {"a": {"token": "t"}})
        self.assertEqual(set(out), {"a", "nocred"})
        self.assertTrue(out["a"]["available"])
        self.assertEqual(out["nocred"]["reason"], al.NO_CREDENTIAL)

    def test_a_stack_that_left_the_estate_gets_no_row_however_stale_the_store(self):
        """The golden rule: iterate the inventory, look the credential up - never the reverse."""
        out = al.probe_all(self.OK(), self.STACKS, {"a": {"token": "t"}, "departed": {"token": "t"}})
        self.assertNotIn("departed", out)

    def test_one_failing_stack_does_not_fail_the_sweep(self):
        class Boom:
            def __init__(self):
                self.n = 0

            def get(self, url, **kw):
                self.n += 1
                if "a.grafana.net" in url:
                    raise TimeoutError("boom")

                class R:
                    status = 200
                    ok = True

                    def json(self):
                        return []
                return R()
        seen = []
        out = al.probe_all(Boom(), [self.STACKS[0], {"slug": "b", "url": "https://b.grafana.net"}],
                           {"a": {"token": "t"}, "b": {"token": "t"}},
                           on_error=lambda s, m: seen.append(s))
        self.assertEqual(out["a"]["reason"], al.TRANSPORT_ERROR)
        self.assertTrue(out["b"]["available"])
        self.assertEqual(seen, ["a"])


if __name__ == "__main__":
    unittest.main()
