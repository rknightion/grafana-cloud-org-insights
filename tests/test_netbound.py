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


@pytest.mark.parametrize("mode", ["get", "guarded", "label_get", "profile", "rpc", "legacy_query"])
def test_never_returning_resolver_has_total_wall_time_bound(mode):
    script = textwrap.dedent("""
        import socket
        import threading
        import time
        from collector.httpclient import ReadOnlyClient
        from collector.sources.label_risk import bounded_transport, profile_read
        from collector.sources.dataplane import _connect_rpc
        from collector.sources.usage_insights import _query

        entered = threading.Event()
        def resolver(*args, **kwargs):
            entered.set()
            threading.Event().wait()  # never returns, including after caller timeout
        socket.getaddrinfo = resolver
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
        except (RuntimeError, TimeoutError):
            assert entered.is_set(), 'did not exercise DNS'
            assert time.monotonic() - started < 1, 'caller exceeded wall budget'
        else:
            raise AssertionError('blocked resolver did not fail the call')
    """)
    run_probe("MODE = " + repr(mode) + "\n" + script)


@pytest.mark.parametrize("mode", ["rpc", "legacy_query"])
def test_legacy_complete_transport_body_read_has_wall_time_bound(mode):
    script = textwrap.dedent("""
        import threading
        import time
        from unittest import mock
        from collector.sources.dataplane import _connect_rpc
        from collector.sources.usage_insights import _query

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
        from collector.netbound import MAX_WORKERS

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
