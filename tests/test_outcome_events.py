"""Typed attempt records refuse content outside the approved event contract."""
import datetime as dt
import hashlib
import json
from unittest import mock

from collector import outcome_events as events
from collector.emit import s3

NOW = dt.datetime(2026, 10, 13, 12, tzinfo=dt.timezone.utc)


def records():
    wire = []
    recorder = events.Recorder.start('t2', 900, emit=wire.append, clock=lambda: NOW)
    recorder.inventory('success', count=5, read_started_at=NOW, read_completed_at=NOW)
    return recorder, wire


def test_contract_and_fail_closed_parser():
    recorder, wire = records()
    recorder.finish(0)
    assert [e['event'] for e in wire] == ['attempt_started', 'inventory_result', 'attempt_finished']
    assert wire[0]['source_revision'] is None
    for event in wire:
        assert events.parse_event(json.dumps(event), now=NOW) == event
    for change in ({'source_revision': 'unverified'}, {'sequence': True}, {'private': 'canary'},
                   {'at': '2026-10-14T00:00:00Z'}, {'version': 2}):
        assert events.validate_event({**wire[0], **change}, now=NOW) is None
    raw = json.dumps(wire[0])
    assert events.parse_event(raw[:-1] + ',"sequence":1}', now=NOW) is None
    assert events.parse_event(raw + '{}', now=NOW) is None
    assert events.parse_event(b'x' * 2049, now=NOW) is None


def test_recording_failure_consumes_sequence_and_never_changes_scan():
    wire = []
    def sink(event):
        if event['sequence'] == 2:
            raise OSError('private canary')
        wire.append(event)
    with mock.patch.object(events, '_diagnostic') as diagnostic:
        recorder = events.Recorder.start('t1', 10, emit=sink, clock=lambda: NOW)
        recorder.inventory('success', count=1, read_started_at=NOW, read_completed_at=NOW)
        recorder.finish(0)
    assert [e['sequence'] for e in wire] == [1, 3]
    diagnostic.assert_called_once_with()


def test_s3_receipt_binds_exact_bytes_and_excludes_protected_views(tmp_path):
    recorder, wire = records()
    uploaded = []
    def put(local, key, bucket, dry_run):
        uploaded.append((key, local.read_bytes()))
        return key
    views = {name: [{'count': 1}] for name in events.RECEIPT_VIEWS}
    views.update(risk_label_hygiene=[{'private': 'canary'}], labelling_metrics=[{'name': 'canary'}])
    with events.recording(recorder), mock.patch.object(s3, '_put', side_effect=put):
        s3.write_views(views, {'tier': 't2', 'generated_at': NOW.isoformat()})
    receipts = [e for e in wire if e['event'] == 'view_write_result']
    assert {e['payload']['view'] for e in receipts} == set(events.RECEIPT_VIEWS)
    for event in receipts:
        data = dict(uploaded)['views/' + event['payload']['view'] + '.json']
        assert event['payload']['sha256'] == hashlib.sha256(data).hexdigest()
    assert 'canary' not in json.dumps(wire)


def test_s3_failure_preserves_exception_and_records_failed_receipt():
    recorder, wire = records()
    failure = s3.S3WriteFailed('private canary')
    import pytest
    with events.recording(recorder), mock.patch.object(s3, '_put', side_effect=failure):
        with pytest.raises(s3.S3WriteFailed) as caught:
            s3.write_views({'cost_summary': []}, {'tier': 't2', 'generated_at': NOW.isoformat()})
    assert caught.value is failure
    assert wire[-1]['payload']['state'] == 'failed'
    assert 'canary' not in json.dumps(wire)


def test_timestamp_requires_rfc3339_and_t4_never_claims_fresh_inventory():
    recorder, wire = records()
    assert events.parse_timestamp('2026-10-13 12:00:00+00:00') is None
    assert events.parse_timestamp('2026-10-13T12:00:00Z') == NOW
    invalid = {**wire[1], 'tier': 't4'}
    assert events.validate_event(invalid, now=NOW) is None


def test_digest_recording_failure_does_not_block_view_publisher():
    recorder, wire = records()
    with events.recording(recorder), mock.patch.object(s3.hashlib, 'sha256', side_effect=OSError('digest failed')), \
            mock.patch.object(s3, '_put', return_value='published') as put:
        assert s3.write_views({'cost_summary': []}, {'tier': 't2', 'generated_at': NOW.isoformat()}) == ['published']
    put.assert_called_once()


def test_clock_failure_at_receipt_seam_leaves_gap_and_preserves_upload():
    recorder, wire = records()
    with events.recording(recorder), mock.patch.object(recorder, 'clock', side_effect=OSError('clock failed')), \
            mock.patch.object(s3, '_put', return_value='published'):
        assert s3.write_views({'cost_summary': []}, {'tier': 't2', 'generated_at': NOW.isoformat()}) == ['published']
    recorder.finish(0)
    assert [e['sequence'] for e in wire] == [1, 2, 4]
