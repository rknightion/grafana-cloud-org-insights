"""Network-edge probes use child processes so a broken bound cannot hang pytest."""
import subprocess
import sys
import textwrap

import pytest


def run_probe(script, *, timeout=3):
    try:
        result = subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pytest.fail("blocked network edge exceeded the caller/process wall-time bound")
    assert result.returncode == 0, result.stderr
    if result.stdout:
        print(result.stdout, end="")


@pytest.mark.parametrize("phase", ["pool_start", "dns"])
@pytest.mark.parametrize("mode", ["get", "guarded", "label_get", "profile", "rpc", "legacy_query"])
def test_never_returning_resolver_has_total_wall_time_bound(mode, phase):
    script = textwrap.dedent("""
        import socket
        import threading
        import time
        from collector.httpclient import ReadOnlyClient
        from collector.sources.label_risk import bounded_transport, profile_read
        from collector.sources.dataplane import _connect_rpc
        from collector.sources.usage_insights import _query
        from collector.netbound import MAX_WORKERS, _WORKERS, bounded_call

        entered = threading.Event()
        def resolver(*args, **kwargs):
            entered.set()
            threading.Event().wait()  # never returns, including after caller timeout
        socket.getaddrinfo = resolver
        if PHASE == 'pool_start':
            # Hold the lazy-start lock at the process edge: admission must expire
            # before a job can be submitted or any resolver can be entered.
            assert not _WORKERS.threads
            _WORKERS.lock.acquire()
        else:
            # Pool construction is setup, not DNS evidence. Prove readiness before
            # starting the unchanged short caller deadline and wall-time clock.
            bounded_call(lambda: None, timeout=1)
            assert len(_WORKERS.threads) == MAX_WORKERS
            assert all(thread.is_alive() for thread in _WORKERS.threads)
        assert not entered.is_set()
        client = ReadOnlyClient(timeout=0.1, max_attempts=1, deadline=0.2)
        started = time.monotonic()
        try:
            if MODE == 'rpc':
                _connect_rpc('https://example.test/collector.v1.CollectorService/ListCollectors',
                             '1', 'synthetic-cap', timeout=0.1)
            elif MODE == 'legacy_query':
                _query('https://example.test', 'synthetic-token',
                       'sum(count_over_time({instance_type="grafana",instance_id="1"}[1h]))',
                       expected_instance_id='1', timeout=0.1)
            elif MODE == 'profile':
                profile_read({'hpInstanceUrl': 'https://example.test', 'hpInstanceId': 1},
                             'synthetic-cap', '/querier.v1.QuerierService/LabelNames',
                             {'start': 1, 'end': 2}, timeout=0.1,
                             transport=bounded_transport(100))
            elif MODE == 'label_get':
                ReadOnlyClient(timeout=0.1, max_attempts=1,
                               transport=bounded_transport(100)).get('https://example.test/x')
            else:
                client.get('https://example.test/x', guarded=MODE == 'guarded')
        except (RuntimeError, TimeoutError) as exc:
            elapsed = time.monotonic() - started
            if PHASE == 'pool_start':
                assert _WORKERS.lock.locked() and not _WORKERS.threads
                assert not entered.is_set(), 'resolver entered before pool startup'
                # Guarded GET intentionally replaces the underlying timeout with
                # its public deadline error; phase evidence above is independent.
                expected = ('guarded GET deadline' if MODE == 'guarded'
                            else 'HTTP worker admission deadline')
                assert expected in str(exc), str(exc)
            else:
                assert entered.is_set(), 'did not exercise DNS'
            assert elapsed < 1, 'caller exceeded wall budget'
            print(f'{MODE}: phase={PHASE}, resolver_entered={entered.is_set()}, '
                  f'workers={len(_WORKERS.threads)}, elapsed={elapsed:.3f}s')
        else:
            raise AssertionError('blocked resolver did not fail the call')
    """)
    run_probe("MODE = " + repr(mode) + "\nPHASE = " + repr(phase) + "\n" + script)


@pytest.mark.parametrize("mode", ["rpc", "legacy_query"])
def test_legacy_complete_transport_body_read_has_wall_time_bound(mode):
    script = textwrap.dedent("""
        import threading
        import time
        from unittest import mock
        from collector.sources.dataplane import _connect_rpc
        from collector.sources.usage_insights import _query
        from collector.netbound import bounded_call

        bounded_call(lambda: None, timeout=1)  # startup is outside the body-read clock
        entered = threading.Event()
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                entered.set()
                threading.Event().wait()  # body read never returns after open succeeds
        started = time.monotonic()
        open_boundary = ('urllib.request.OpenerDirector.open'
                         if MODE == 'rpc' else 'urllib.request.urlopen')
        with mock.patch(open_boundary, return_value=Response()):
            try:
                if MODE == 'rpc':
                    _connect_rpc('https://example.test/collector.v1.CollectorService/ListCollectors',
                                 '1', 'synthetic-cap', timeout=0.1)
                else:
                    _query('https://example.test', 'synthetic-token',
                           'sum(count_over_time({instance_type="grafana",instance_id="1"}[1h]))',
                           expected_instance_id='1', timeout=0.1)
            except TimeoutError:
                assert entered.is_set(), 'did not exercise body read'
                assert time.monotonic() - started < 1
            else:
                raise AssertionError('blocked body read returned successfully')
    """)
    run_probe("MODE = " + repr(mode) + "\n" + script)


def test_surviving_dns_work_is_bounded_and_admission_fails_closed():
    run_probe("""
        import socket
        import threading
        import time
        from collector.httpclient import ReadOnlyClient
        from collector.netbound import MAX_WORKERS, _WORKERS, bounded_call

        # Separate lazy pool setup from the short per-call DNS budget.
        bounded_call(lambda: None, timeout=1)
        assert len(_WORKERS.threads) == MAX_WORKERS
        assert all(thread.is_alive() for thread in _WORKERS.threads)
        calls = []
        def resolver(*args, **kwargs):
            calls.append(1)
            threading.Event().wait()
        socket.getaddrinfo = resolver
        client = ReadOnlyClient(timeout=0.02, host_concurrency=MAX_WORKERS + 8, max_attempts=1)
        started = time.monotonic()
        for _ in range(MAX_WORKERS + 8):
            try:
                client.get('https://example.test/x')
            except RuntimeError:
                pass
            else:
                raise AssertionError('blocked resolver returned successfully')
        assert len(calls) == MAX_WORKERS, (len(calls), MAX_WORKERS)
        assert threading.active_count() <= MAX_WORKERS + 1, 'unbounded survivor threads'
        assert time.monotonic() - started < 2, 'saturated pool did not bound admission'
    """, timeout=5)


def test_survivor_keeps_host_slot_then_releases_it_for_recovery():
    run_probe("""
        import threading
        from collector.httpclient import ReadOnlyClient, Response
        from collector.netbound import bounded_call

        bounded_call(lambda: None, timeout=1)  # startup is outside the transport budget
        entered = threading.Event()
        release = threading.Event()
        calls = []
        def transport(req, timeout):
            calls.append(1)
            entered.set()
            release.wait(2)
            return Response(200, b'{}', req.full_url)
        client = ReadOnlyClient(timeout=0.1, host_concurrency=1, max_attempts=1,
                                transport=transport)
        for _ in range(2):
            try:
                client.get('https://example.test/x')
            except RuntimeError:
                pass
            else:
                raise AssertionError('blocked transport returned successfully')
        assert entered.is_set()
        assert len(calls) == 1, 'timed-out read lost its per-host concurrency slot'
        release.set()
        assert client.get('https://example.test/x').ok
        assert len(calls) == 2
    """)
