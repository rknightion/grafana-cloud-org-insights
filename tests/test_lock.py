"""Single-run lock (PLAN 1.7).

Written before `collector/emit/lock.py`. The acceptance criterion the plan names is test 2: a second
concurrent run refuses to start. The rest of this file exists because a lock that only does that is
worse than no lock - a Fargate task killed mid-scan (OOM, spot reclaim, `StopTask`) leaves the object
behind and every later scan of that tier refuses forever. So staleness and release-safety are pinned
just as hard as mutual exclusion.
"""

from __future__ import annotations

import json
import unittest

from collector.emit import lock


class FakeS3:
    """In-memory stand-in with S3's real conditional semantics.

    Models the two primitives the lock relies on, both verified present in aws-cli 2.36.24:
    `put-object --if-none-match '*'` (atomic create) and `delete-object --if-match <etag>`
    (compare-and-delete).
    """

    def __init__(self) -> None:
        self.objects: dict[str, tuple[str, str]] = {}  # key -> (body, etag)
        self._etag = 0
        self.calls: list[str] = []

    def _next_etag(self) -> str:
        self._etag += 1
        return f'"etag{self._etag}"'

    def put_if_absent(self, key: str, body: str) -> str:
        self.calls.append(f"put_if_absent {key}")
        if key in self.objects:
            raise lock.PreconditionFailed(key)
        etag = self._next_etag()
        self.objects[key] = (body, etag)
        return etag

    def get(self, key: str) -> tuple[str, str] | None:
        self.calls.append(f"get {key}")
        return self.objects.get(key)

    def delete_if_match(self, key: str, etag: str) -> bool:
        self.calls.append(f"delete_if_match {key}")
        held = self.objects.get(key)
        if held is None or held[1] != etag:
            return False
        del self.objects[key]
        return True


def make_lock(backend: FakeS3, *, tier: str = "t1", holder: str = "task-a", now: float = 1_000.0,
              ttl: float = 900.0, dry_run: bool = False) -> lock.ScanLock:
    return lock.ScanLock(
        tier=tier,
        ttl_seconds=ttl,
        holder=holder,
        backend=backend,
        now=lambda: now,
        dry_run=dry_run,
    )


class TestAcquire(unittest.TestCase):
    def test_free_lock_is_acquired(self):
        s3 = FakeS3()
        lk = make_lock(s3)
        lk.acquire()
        self.assertIn("locks/t1.lock", s3.objects)
        self.assertTrue(lk.held)

    def test_second_concurrent_run_refuses_to_start(self):
        """The PLAN 1.7 acceptance criterion."""
        s3 = FakeS3()
        first = make_lock(s3, holder="task-a")
        first.acquire()

        second = make_lock(s3, holder="task-b", now=1_060.0)  # 60s later, well inside the 900s TTL
        with self.assertRaises(lock.LockHeld) as ctx:
            second.acquire()

        self.assertIn("task-a", str(ctx.exception))
        self.assertFalse(second.held)
        # The incumbent's lock is untouched - a refused run must not disturb the running one.
        self.assertEqual(json.loads(s3.objects["locks/t1.lock"][0])["holder"], "task-a")

    def test_locks_are_per_tier(self):
        """T1 hourly and T3 weekly overlap by design; they must not block each other."""
        s3 = FakeS3()
        make_lock(s3, tier="t1").acquire()
        t3 = make_lock(s3, tier="t3", holder="task-c")
        t3.acquire()  # must not raise
        self.assertEqual(sorted(s3.objects), ["locks/t1.lock", "locks/t3.lock"])

    def test_lock_body_records_who_and_until_when_and_no_credential(self):
        s3 = FakeS3()
        make_lock(s3, holder="task-a", now=1_000.0, ttl=900.0).acquire()
        body = json.loads(s3.objects["locks/t1.lock"][0])
        self.assertEqual(body["holder"], "task-a")
        self.assertEqual(body["tier"], "t1")
        self.assertEqual(body["expires_at"], 1_900.0)
        # The lock object lands in the same bucket as the scans and is readable by anything with
        # GetObject on the prefix. It carries identity, never authority.
        self.assertNotIn("cap", {k.lower() for k in body})
        self.assertNotIn("token", json.dumps(body).lower())


class TestStaleness(unittest.TestCase):
    def test_expired_lock_is_broken_and_taken_over(self):
        s3 = FakeS3()
        dead = make_lock(s3, holder="killed-task", now=1_000.0, ttl=900.0)
        dead.acquire()

        # 1901s: one second past the incumbent's expiry.
        fresh = make_lock(s3, holder="task-b", now=1_901.0)
        fresh.acquire()

        self.assertTrue(fresh.held)
        self.assertTrue(fresh.broke_stale_lock)
        self.assertEqual(json.loads(s3.objects["locks/t1.lock"][0])["holder"], "task-b")

    def test_lock_is_not_broken_at_the_instant_it_expires(self):
        """Exactly-at-expiry stays held. An off-by-one here permits the double run the lock exists
        to prevent, and it would only ever show up as two scans racing on `latest.json`."""
        s3 = FakeS3()
        make_lock(s3, holder="task-a", now=1_000.0, ttl=900.0).acquire()
        contender = make_lock(s3, holder="task-b", now=1_900.0)
        with self.assertRaises(lock.LockHeld):
            contender.acquire()

    def test_unparseable_lock_is_broken_rather_than_deadlocking_the_tier(self):
        """A truncated or hand-edited lock object must not wedge a tier permanently."""
        s3 = FakeS3()
        s3.objects["locks/t1.lock"] = ("{not json", '"etagX"')
        lk = make_lock(s3, holder="task-b")
        lk.acquire()
        self.assertTrue(lk.held)
        self.assertTrue(lk.broke_stale_lock)

    def test_lock_vanishing_between_the_412_and_the_read_is_retried(self):
        """The incumbent released in the window between our failed put and our read. That is a free
        lock, not an error."""
        s3 = FakeS3()

        class Vanishing(FakeS3):
            def __init__(self) -> None:
                super().__init__()
                self.first = True

            def put_if_absent(self, key: str, body: str) -> str:
                if self.first:
                    self.first = False
                    raise lock.PreconditionFailed(key)
                return super().put_if_absent(key, body)

        s3 = Vanishing()
        lk = make_lock(s3, holder="task-b")
        lk.acquire()
        self.assertTrue(lk.held)


class TestRelease(unittest.TestCase):
    def test_release_deletes_our_own_lock(self):
        s3 = FakeS3()
        lk = make_lock(s3)
        lk.acquire()
        lk.release()
        self.assertNotIn("locks/t1.lock", s3.objects)
        self.assertFalse(lk.held)

    def test_release_after_being_broken_does_not_delete_the_new_holders_lock(self):
        """The overrun case. Our task was declared stale and another run took the lock; when we
        finally finish, deleting `locks/t1.lock` would hand a third run a green light while the
        second is still scanning. The ETag guard is what makes this safe."""
        s3 = FakeS3()
        overrunning = make_lock(s3, holder="task-a", now=1_000.0, ttl=900.0)
        overrunning.acquire()
        taker = make_lock(s3, holder="task-b", now=1_901.0)
        taker.acquire()

        overrunning.release()

        self.assertIn("locks/t1.lock", s3.objects)
        self.assertEqual(json.loads(s3.objects["locks/t1.lock"][0])["holder"], "task-b")

    def test_release_without_acquire_is_a_noop(self):
        s3 = FakeS3()
        make_lock(s3).release()
        self.assertEqual(s3.calls, [])

    def test_context_manager_releases_on_exception(self):
        """The whole point: a scan that raises must not leave the tier locked for the TTL."""
        s3 = FakeS3()
        lk = make_lock(s3)
        with self.assertRaises(ValueError):
            with lk:
                raise ValueError("scan blew up")
        self.assertNotIn("locks/t1.lock", s3.objects)


class TestDryRun(unittest.TestCase):
    def test_dry_run_takes_no_lock(self):
        """`--dry-run` writes nothing anywhere, so it cannot collide with a real run and must not be
        able to block one."""
        s3 = FakeS3()
        lk = make_lock(s3, dry_run=True)
        with lk:
            pass
        self.assertEqual(s3.objects, {})
        self.assertEqual(s3.calls, [])

    def test_dry_run_is_not_blocked_by_a_held_lock(self):
        s3 = FakeS3()
        make_lock(s3, holder="task-a").acquire()
        make_lock(s3, holder="dry", dry_run=True).acquire()  # must not raise


class TestTTL(unittest.TestCase):
    def test_ttl_exceeds_the_tier_deadline_so_a_live_run_is_never_declared_stale(self):
        """A scan is killed by its own deadline at `deadline_seconds`. If the lock expired first, a
        still-running scan would be overtaken. The grace period is what keeps the ordering."""
        for tier, deadline in (("t1", 900), ("t2", 3600), ("t3", 21600), ("t4", 900)):
            with self.subTest(tier=tier):
                self.assertGreater(lock.ttl_for(deadline), deadline)


if __name__ == "__main__":
    unittest.main()
