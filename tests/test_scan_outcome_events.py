"""Exercise admitted public scan execution, keeping I/O at its existing process edge."""
import contextlib
import io
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector import config, outcome_events
from collector.httpclient import ReadOnlyClient, Response


def cfg(tier='t1', **changes):
    value = config.Config(cap='read', write_token='write', org_id='1', tier=tier, dry_run=False,
                          limit=None, stack=None, concurrency=1, deadline_seconds=900,
                          write_stack='target', mimir_url='https://mimir.invalid', mimir_tenant='1',
                          loki_url='https://loki.invalid', loki_tenant='2')
    return replace(value, **changes)


def typed(stderr):
    return [json.loads(line) for line in stderr.getvalue().splitlines()
            if line.startswith('{') and json.loads(line).get('kind') == outcome_events.EVENT_KIND]


def test_real_inventory_failure_records_closed_failure_and_preserves_refusal():
    stderr = io.StringIO()
    failure = RuntimeError('identity-canary@example.test')
    with (mock.patch.dict('os.environ', {'GCINSIGHT_OUTCOME_OBSERVER_ENABLED': '1'}),
          mock.patch.object(scan, '_verified_ecs_runtime', return_value=True),
          mock.patch.object(scan.s3emit, 'write_views') as views,
          mock.patch.object(scan.s3emit, 'write_scan') as scans,
          mock.patch.object(scan.mimir, 'RemoteWriter') as mimir,
          mock.patch.object(scan.loki, 'LokiWriter') as loki,
          contextlib.redirect_stderr(stderr)):
        with pytest.raises(RuntimeError) as caught:
            scan.run(ReadOnlyClient(transport=lambda request, timeout: (_ for _ in ()).throw(failure),
                                    max_attempts=1), cfg(), SimpleNamespace(out=None))
    assert str(failure) in str(caught.value)
    assert "outcome" not in str(caught.value)
    events = typed(stderr)
    assert [e['event'] for e in events] == ['attempt_started', 'inventory_result', 'attempt_finished']
    assert events[1]['payload']['reason'] == 'read_failed'
    assert events[1]['payload']['count'] is None
    assert events[-1]['payload'] == {'state': 'failed', 'reason': 'exception', 'exit_code': None}
    assert 'identity-canary' not in json.dumps(events)
    for boundary in (views, scans, mimir, loki):
        boundary.assert_not_called()


def test_no_records_for_diagnostic_or_unverified_public_run():
    for changes, verified in [({'dry_run': True}, True), ({'limit': 1}, True), ({}, False)]:
        stderr = io.StringIO()
        with (mock.patch.dict('os.environ', {'GCINSIGHT_OUTCOME_OBSERVER_ENABLED': '1'}),
              mock.patch.object(scan, '_verified_ecs_runtime', return_value=verified),
              contextlib.redirect_stderr(stderr)):
            if verified:
                with pytest.raises(RuntimeError):
                    scan.run(ReadOnlyClient(transport=lambda request, timeout: (_ for _ in ()).throw(RuntimeError('stop')),
                                            max_attempts=1), cfg(**changes), SimpleNamespace(out=None))
            else:
                assert scan.run(ReadOnlyClient(transport=lambda request, timeout: (_ for _ in ()).throw(RuntimeError('stop')),
                                            max_attempts=1), cfg(**changes), SimpleNamespace(out=None)) == 2
        assert typed(stderr) == []


def test_recorder_failure_does_not_replace_original_scan_exception():
    failure = RuntimeError('original failure')
    with (mock.patch.dict('os.environ', {'GCINSIGHT_OUTCOME_OBSERVER_ENABLED': '1'}),
          mock.patch.object(scan, '_verified_ecs_runtime', return_value=True),
          mock.patch.object(outcome_events.Recorder, '_record', side_effect=OSError('sink failed'))):
        with pytest.raises(RuntimeError) as caught:
            scan.run(ReadOnlyClient(transport=lambda request, timeout: (_ for _ in ()).throw(failure),
                                    max_attempts=1), cfg(), SimpleNamespace(out=None))
    assert str(failure) in str(caught.value)
    assert "outcome" not in str(caught.value)


@pytest.mark.parametrize('inventory', [[], [{'id': 1, 'slug': 'synthetic', 'orgId': 1, 'status': 'paused'}]])
def test_full_t1_scan_produces_records_at_actual_network_and_publisher_boundaries(inventory):
    """Real source, composer, orchestration and serialization; fake only HTTP/AWS process I/O."""
    import pathlib
    import subprocess
    uploaded = {}
    stderr = io.StringIO()
    def transport(request, timeout):
        body = {'items': inventory if request.full_url.split('?')[0].endswith('/instances') else []}
        return Response(200, json.dumps(body).encode(), request.full_url)
    def cli(argv, **kwargs):
        if argv[1:3] == ['s3', 'cp'] and argv[3].endswith('/scans/t3/latest.json'):
            body = {'meta': {'generated_at': outcome_events.utcnow().isoformat()},
                    'data': {'dataplane': {'synthetic': {}}}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(body), '')
        if argv[1:3] == ['s3', 'cp'] and not argv[3].startswith('s3://'):
            uploaded[argv[4]] = pathlib.Path(argv[3]).read_bytes()
            return subprocess.CompletedProcess(argv, 0, '', '')
        return subprocess.CompletedProcess(argv, 1, '', 'NoSuchKey (404)')
    def http(request, **kwargs):
        response = mock.MagicMock()
        if request == 'http://169.254.170.2/v4/fixture':
            response.__enter__.return_value.read.return_value = b'{"ContainerARN":"arn:aws:ecs:region:1:container/task"}'
        else:
            response.__enter__.return_value.status = 204
        return response
    with (mock.patch.dict('os.environ', {'GCINSIGHT_OUTCOME_OBSERVER_ENABLED': '1',
                                        'ECS_CONTAINER_METADATA_URI_V4': 'http://169.254.170.2/v4/fixture'}),
          mock.patch('subprocess.run', side_effect=cli),
          mock.patch.dict(scan.load_ratecard.__kwdefaults__, {'runner': cli}),
          mock.patch.dict(scan.gapstate.load.__kwdefaults__, {'runner': cli}),
          mock.patch('urllib.request.urlopen', side_effect=http),
          contextlib.redirect_stderr(stderr)):
        result = scan.run(ReadOnlyClient(transport=transport, max_attempts=1), cfg(), SimpleNamespace(out=None))
    events = typed(stderr)
    assert all(outcome_events.validate_event(e) == e for e in events)
    assert events[0]['event'] == 'attempt_started'
    assert events[-1]['event'] == 'attempt_finished'
    assert events[-1]['payload']['exit_code'] == result
    if not inventory:
        assert result == 1
        assert events[1]['payload']['state'] == 'failed'
        assert events[1]['payload']['reason'] == 'empty'
        assert events[1]['payload']['count'] is None
        assert uploaded == {}
        assert [e['event'] for e in events] == ['attempt_started', 'inventory_result', 'attempt_finished']
    else:
        import hashlib
        assert result == 0
        assert events[1]['payload']['count'] == 1
        receipts = [e for e in events if e['event'] == 'view_write_result']
        assert receipts
        for event in receipts:
            payload = event['payload']
            key = f's3://{scan.s3emit.BUCKET}/views/{payload["view"]}.json'
            assert payload['sha256'] == hashlib.sha256(uploaded[key]).hexdigest()
        assert 'synthetic' not in json.dumps(events)
