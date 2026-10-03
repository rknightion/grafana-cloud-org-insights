"""Dataplane contracts whose absence can turn unknown savings into a confident zero."""

from __future__ import annotations

import base64
import io
import json
import unittest
import urllib.request
import urllib.response
from email.message import Message
from unittest import mock

import pytest

from collector.coverage import Coverage
from collector.emit import s3
from collector.pillars import compose, maturity
from collector.sources import dataplane


def _record(metric: str, current: int | None, recommended: int | None) -> dict[str, object]:
    out: dict[str, object] = {"metric": metric, "recommended_action": "add"}
    if current is not None:
        out["current_series_count"] = current
    if recommended is not None:
        out["recommended_series_count"] = recommended
    return out


class RecommendationCoverageTest(unittest.TestCase):
    def test_successful_empty_payload_is_a_complete_zero(self):
        out = dataplane.summarise_recommendations([])

        self.assertEqual(out["recommendation_records_total"], 0)
        self.assertEqual(out["recommendation_records_with_series_counts"], 0)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 0)
        self.assertTrue(out["series_counts_complete"])
        self.assertEqual(out["remediable_series"], 0)

    def test_partial_verbose_payload_reports_its_missing_counts(self):
        out = dataplane.summarise_recommendations([
            _record("complete", 100, 10),
            _record("default-shape", None, None),
        ])

        self.assertEqual(out["recommendation_records_total"], 2)
        self.assertEqual(out["recommendation_records_with_series_counts"], 1)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 1)
        self.assertFalse(out["series_counts_complete"])
        self.assertFalse(out["verbose"], "legacy consumers must not mistake partial counts for verbose")

    def test_savings_record_without_metric_identity_withholds_savings(self):
        out = dataplane.summarise_recommendations([
            _record("valid", 200, 20),
            _record("", 100, 10),
        ])

        self.assertEqual(out["recommendation_records_missing_metric_identity"], 1)
        self.assertEqual(out["recommendation_records_missing_series_counts"], 0)
        self.assertFalse(out["series_counts_complete"])
        self.assertFalse(out["verbose"])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["remediable_series_unused"], 0)
        self.assertEqual(out["sample_recommendations"], [])

    def test_duplicate_metric_identity_withholds_savings(self):
        out = dataplane.summarise_recommendations([
            _record("duplicate", 100, 10),
            _record("duplicate", 80, 20),
        ])

        self.assertEqual(out["recommendation_records_duplicate_metric_identity"], 1)
        self.assertFalse(out["series_counts_complete"])
        self.assertFalse(out["verbose"])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["remediable_series_unused"], 0)
        self.assertEqual(out["sample_recommendations"], [])

    def test_invalid_or_negative_series_counts_withhold_all_savings(self):
        for current, recommended in ((-10, -20), (50, -20), (10.5, 2), ("bad", 2)):
            with self.subTest(current=current, recommended=recommended):
                out = dataplane.summarise_recommendations([
                    _record("valid", 100, 10),
                    _record("invalid", current, recommended),
                ])

                self.assertEqual(out["recommendation_records_invalid_series_counts"], 1)
                self.assertFalse(out["series_counts_complete"])
                self.assertFalse(out["verbose"])
                self.assertEqual(out["remediable_series"], 0)
                self.assertEqual(out["remediable_series_unused"], 0)
                self.assertEqual(out["sample_recommendations"], [])

    def test_failed_recommendations_request_is_not_a_complete_empty_payload(self):
        class Response:
            def __init__(self, ok: bool, body: object, status: int) -> None:
                self.ok = ok
                self._body = body
                self.status = status

            def json(self) -> object:
                return self._body

        class Client:
            def get(self, url: str, basic: object = None) -> Response:
                if url.endswith("/aggregations/rules"):
                    return Response(True, [], 200)
                return Response(False, {}, 503)

        stack = {
            "slug": "one",
            "hmInstancePromUrl": "https://prom.example",
            "hmInstancePromId": "1",
        }
        out = dataplane.adaptive_metrics(Client(), stack, "cap")

        self.assertFalse(out["recommendations_available"])
        self.assertFalse(out["series_counts_complete"])

    def test_invalid_json_is_unavailable_instead_of_raising(self):
        class Response:
            ok = True
            status = 200

            def json(self):
                raise ValueError("bad json")

        class Client:
            def get(self, url: str, basic: object = None) -> Response:
                return Response()

        stack = {"slug": "one", "hmInstancePromUrl": "https://prom.example",
                 "hmInstancePromId": "1"}
        out = dataplane.adaptive_metrics(Client(), stack, "cap")
        self.assertFalse(out["available"])
        self.assertFalse(out["series_counts_complete"])

    def test_invalid_usage_counts_make_the_saving_incomplete_not_unused(self):
        record = _record("bad-usage", 100, 10)
        record["usages_in_rules"] = "not-a-count"
        out = dataplane.summarise_recommendations([record])
        self.assertFalse(out["series_counts_complete"])
        self.assertEqual(out["remediable_series"], 0)
        self.assertEqual(out["remediable_series_unused"], 0)

    def test_malformed_recommendations_payload_is_not_a_complete_empty_payload(self):
        class Response:
            ok = True
            status = 200

            def __init__(self, body: object) -> None:
                self._body = body

            def json(self) -> object:
                return self._body

        class Client:
            def get(self, url: str, basic: object = None) -> Response:
                return Response([] if url.endswith("/aggregations/rules") else {"items": []})

        stack = {
            "slug": "one",
            "hmInstancePromUrl": "https://prom.example",
            "hmInstancePromId": "1",
        }
        out = dataplane.adaptive_metrics(Client(), stack, "cap")

        self.assertFalse(out["recommendations_available"])
        self.assertFalse(out["series_counts_complete"])


class AdaptiveRulesAvailabilityTest(unittest.TestCase):
    def test_no_readable_payload_does_not_claim_adaptive_available(self):
        class Response:
            def __init__(self, ok, body, status):
                self.ok, self.body, self.status = ok, body, status

            def json(self):
                if isinstance(self.body, Exception):
                    raise self.body
                return self.body

        class Client:
            def get(self, url, basic=None):
                if url.endswith('/aggregations/rules'):
                    return Response(True, ValueError('invalid JSON'), 200)
                return Response(False, {}, 503)

        out = dataplane.adaptive_metrics(Client(), {
            'slug': 'synthetic', 'hmInstancePromUrl': 'https://prom.example',
            'hmInstancePromId': '1',
        }, 'cap')
        self.assertFalse(out['available'])
        self.assertFalse(out['rules_available'])
        self.assertIsNone(out['rules_applied'])
        self.assertIsNone(out['adopted'])
        self.assertFalse(out['recommendations_available'])
        self.assertFalse(out['series_counts_complete'])
        self.assertNotIn('recommendations_pending', out)

    def test_unreadable_rules_stay_unknown_through_composition(self):
        from collector.coverage import Coverage
        from collector.emit.diff import summarise
        from collector.pillars.compose import build_all

        class Response:
            def __init__(self, ok, body, status=200):
                self.ok, self.body, self.status = ok, body, status

            def json(self):
                if isinstance(self.body, Exception):
                    raise self.body
                return self.body

        class Client:
            def __init__(self, rules):
                self.rules = rules

            def get(self, url, basic=None):
                if url.endswith('/aggregations/rules/segments'):
                    return Response(True, [])
                if url.endswith('/aggregations/rules'):
                    return self.rules
                if 'verbose=true' in url:
                    return Response(True, [_record('synthetic_metric', 100, 10)])
                return Response(True, {})

        stack = {'slug': 'synthetic', 'hmInstancePromUrl': 'https://prom.example',
                 'hmInstancePromId': '1', 'hmInstancePromCurrentActiveSeries': 10000,
                 'hmInstancePromCurrentUsage': 10000, 'currentActiveUsers': 10,
                 'billingActiveUsers': 10, 'dashboardCnt': 20, 'alertCnt': 10}
        coverage = Coverage(tier='t3', total=1)
        coverage.record_ok('synthetic')
        cases = ((Response(False, {}, 503), False), (Response(True, {}), False),
                 (Response(True, ValueError('invalid JSON')), False),
                 (Response(True, []), True), (Response(True, [{}]), True))
        for response, known in cases:
            with self.subTest(status=response.status, body=response.body):
                am = dataplane.adaptive_metrics(Client(response), stack, 'cap')
                applied = len(response.body) if known else None
                self.assertEqual(am.get('rules_applied'), applied)
                self.assertEqual(am.get('adopted'), bool(applied) if known else None)
                self.assertIs(am.get('rules_available'), known)
                self.assertTrue(am['recommendations_available'])
                payload = {'synthetic': {'adaptive_metrics': am}}
                metrics, views, _ = build_all([stack], coverage, dataplane=payload)
                by = {(name, tuple(sorted(labels.items()))): value
                      for name, labels, value in metrics}
                row = views['cost'][0]
                self.assertEqual(row['Adaptive rules applied'], applied)
                self.assertEqual(row['Adaptive adopted'], bool(applied) if known else None)
                unadopted = int(known and not applied)
                if known:
                    self.assertEqual(len(views['cost_adaptive_headroom']), unadopted)
                else:
                    self.assertNotIn('cost_adaptive_headroom', views)
                self.assertIn('cost_adaptive_metric_recommendations', views)
                savings = {r[' Metric']: r['Value'] for r in views['value_savings']}
                self.assertEqual(savings['Stacks with pending recommendations and zero rules applied'],
                                 unadopted if known else None)
                benchmark = next(r for r in views['value_benchmarks']
                                 if r[' Dimension'] == 'adaptive_adoption')
                self.assertEqual(benchmark['Stacks with data'], int(known))
                self.assertEqual(benchmark['Median'], 100 * applied / (applied + 1)
                                 if known else None)
                dimension = next(r for r in views['maturity_dimensions']
                                 if r['Dimension'] == 'adaptive_adoption')
                self.assertEqual(dimension['Applicable'], known)
                self.assertEqual(dimension['Score'], round(100 * applied / (applied + 1), 1)
                                 if known else None)
                for key, expected in (
                    (('gcinsight_adaptive_recommendations',
                      (('stack', 'synthetic'), ('status', 'applied'))), applied),
                    (('gcinsight_cost_adaptive_rules_applied_total', ()), applied),
                    (('gcinsight_cost_stacks_without_adaptive', ()), unadopted),
                ):
                    if known:
                        self.assertEqual(by[key], expected)
                    else:
                        self.assertNotIn(key, by)
                summary = summarise({'data': {'stacks': [stack], 'dataplane': payload}})
                self.assertEqual(summary['adaptive_pending'], 1)
                if known:
                    self.assertEqual(summary['adaptive_applied'], applied)
                else:
                    self.assertNotIn('adaptive_applied', summary)


class AutoApplyConfigTest(unittest.TestCase):
    class Response:
        def __init__(self, ok: bool, body: object, status: int = 200) -> None:
            self.ok = ok
            self._body = body
            self.status = status

        def json(self) -> object:
            return self._body

    class Client:
        def __init__(self, response) -> None:
            self.response = response

        def get(self, url: str, basic: object = None):
            return self.response

    def test_enabled_preserves_the_whole_object_and_discards_keep_labels(self):
        out = dataplane._auto_apply_config(
            self.Client(self.Response(True, {
                "keep_labels": ["discard-me"],
                "auto_apply": {"enabled": True, "gate": {"policy": "synthetic"}},
            })),
            "https://prom.example",
            ("1", "cap"),
        )
        self.assertEqual(out, {
            "auto_apply_state": dataplane.AUTO_APPLY_ENABLED,
            "auto_apply": {"enabled": True, "gate": {"policy": "synthetic"}},
        })
        self.assertNotIn("keep_labels", out)

    def test_omitted_key_is_absent_not_false(self):
        out = dataplane._auto_apply_config(
            self.Client(self.Response(True, {"keep_labels": []})),
            "https://prom.example",
            ("1", "cap"),
        )
        self.assertEqual(out, {"auto_apply_state": dataplane.AUTO_APPLY_ABSENT})

    def test_failed_or_malformed_response_is_unreadable(self):
        for response in (self.Response(False, {}, 503), self.Response(True, [])):
            with self.subTest(status=response.status, body=response._body):
                out = dataplane._auto_apply_config(
                    self.Client(response), "https://prom.example", ("1", "cap")
                )
                self.assertEqual(out, {"auto_apply_state": dataplane.AUTO_APPLY_UNREADABLE})


class ConnectRpcTest(unittest.TestCase):
    def test_redirects_never_send_a_second_authenticated_request(self):
        url = "https://rpc.example/collector.v1.CollectorService/ListCollectors"
        target = "http://attacker.example/nonallowlisted"
        authorization = "Basic " + base64.b64encode(b"123:cap").decode()
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                requests = []

                def wire(request):
                    requests.append((
                        request.full_url, request.get_method(),
                        request.get_header("Authorization"),
                    ))
                    headers = Message()
                    if request.full_url == url:
                        headers["Location"] = target
                        status, body = code, b""
                    else:
                        status, body = 200, b"{}"
                    response = urllib.response.addinfourl(
                        io.BytesIO(body), headers, request.full_url, status,
                    )
                    response.msg = "offline response"
                    return response

                # Keep the real opener, HTTPErrorProcessor and redirect handlers;
                # replace only the wire boundary so neither origin is contacted.
                with mock.patch.object(urllib.request.HTTPSHandler, "https_open", side_effect=wire), \
                        mock.patch.object(urllib.request.HTTPHandler, "http_open", side_effect=wire):
                    out = dataplane._connect_rpc(url, "123", "cap")
                self.assertEqual(requests, [(url, "POST", authorization)])
                self.assertEqual(out, {"_http": code})

    def test_unsafe_authorities_are_refused_before_transport(self):
        route = "/collector.v1.CollectorService/ListCollectors"
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        for base in ("http://rpc.example", "https://", "https://user:pass@rpc.example"):
            with self.subTest(base=base):
                with mock.patch("urllib.request.OpenerDirector.open", return_value=response) as open_url:
                    with self.assertRaises(ValueError):
                        dataplane._connect_rpc(base + route, "123", "cap")
                    open_url.assert_not_called()

    def test_unapproved_routes_are_refused_before_transport(self):
        paths = (
            "/collector.v1.CollectorService/DeleteCollector",
            "/pipeline.v1.PipelineService/ListPipelinesX",
            "/querier.v1.QuerierService/SelectMergeStacktraces",
            "/querier.v1.QuerierService/LabelNames",
            "/collector.v1.CollectorService/ListCollectors?x=1",
            "/collector.v1.CollectorService/ListCollectors#f",
            "/collector.v1.CollectorService/ListCollectors/../Delete",
            "/collector.v1.CollectorService%2FListCollectors",
            "/other.v1.OtherService/ListAnything",
            "/prefixcollector.v1.CollectorService/ListCollectors",
            "/collector.v1.CollectorService/%4cistCollectors",
            "/querier.v1.QuerierService%2fLabelValues",
        )
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        for path in paths:
            with self.subTest(path=path):
                with mock.patch("urllib.request.OpenerDirector.open", return_value=response) as open_url:
                    with self.assertRaises(ValueError):
                        dataplane._connect_rpc("https://rpc.example" + path, "123", "cap")
                    open_url.assert_not_called()

    def test_each_exact_read_route_accepts_a_base_path_prefix(self):
        for route in (
            "/collector.v1.CollectorService/ListCollectors",
            "/pipeline.v1.PipelineService/ListPipelines",
            "/querier.v1.QuerierService/LabelValues",
        ):
            for prefix in ("", "/rpc"):
                with self.subTest(route=route, prefix=prefix):
                    response = mock.MagicMock()
                    response.__enter__.return_value.read.return_value = b'{"result":[]}'
                    url = "https://fleet-management-prod-gb-south-1.grafana.net" + prefix + route
                    with mock.patch("urllib.request.OpenerDirector.open", return_value=response) as open_url:
                        out = dataplane._connect_rpc(url, "123", "cap")
                    self.assertEqual(out, {"result": []})
                    open_url.assert_called_once()
                    request = open_url.call_args.args[0]
                    self.assertEqual(request.full_url, url)
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(json.loads(request.data), {})

    def test_http_error_keeps_the_existing_return_shape(self):
        import urllib.error

        with mock.patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.HTTPError(
            "https://rpc.example", 403, "Forbidden", {}, None,
        )):
            self.assertEqual(dataplane._connect_rpc(
                "https://rpc.example/collector.v1.CollectorService/ListCollectors", "123", "cap",
            ), {"_http": 403})

    def test_read_payload_is_sent_without_relaxing_the_path_guard(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"names":[]}'
        with mock.patch("urllib.request.OpenerDirector.open", return_value=response) as open_url:
            out = dataplane._connect_rpc(
                "https://profiles.example/querier.v1.QuerierService/LabelValues",
                "123", "cap", payload={"name": "service_name", "start": 1, "end": 2},
            )
        self.assertEqual(out, {"names": []})
        request = open_url.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"name": "service_name", "start": 1, "end": 2})

        with self.assertRaises(ValueError):
            dataplane._connect_rpc(
                "https://profiles.example/write.v1.WriterService/Push", "123", "cap",
                payload={"series": []},
            )


# Segment discovery fences whole-stack claims across the real publication boundary.
from collector.httpclient import ReadOnlyClient, Response


class Client(ReadOnlyClient):
    """Fake only the transport; preserve real status/JSON and GET-only semantics."""

    def __init__(self, segments, ok=True, empty=False, status=None):
        self.segments, self.empty, self.calls = segments, empty, []
        self.segment_status = status if status is not None else (200 if ok else 503)
        super().__init__(transport=self.transport, max_attempts=1)

    def get(self, url, basic=None):
        self.calls.append((url, basic))
        return super().get(url, basic=basic)

    def transport(self, request, timeout):
        assert request.method == 'GET'
        url = request.full_url
        status = 200
        if url.endswith('/segments'):
            body, status = self.segments, self.segment_status
        elif url.endswith('/rules'):
            body = []
        elif '?verbose=true' in url:
            body = [] if self.empty else [{
                'metric': 'synthetic_metric', 'recommended_action': 'add',
                'current_series_count': 100, 'recommended_series_count': 10,
            }]
        else:
            body = {}
        return Response(status, json.dumps(body).encode(), url)


STACK = {'slug': 'one', 'hmInstancePromUrl': 'https://inventory.example',
         'hmInstancePromId': '123', 'hmInstancePromCurrentActiveSeries': 1000}
SEGMENT = {'id': 'synthetic-segment-a', 'fallback_to_default': True,
           'name': 'PRIVATE-NAME', 'selector': 'PRIVATE-SELECTOR'}


def publish(am, stacks=None, payload=None, ratecard=None, seeded=None):
    stacks = stacks or [STACK]
    coverage = Coverage(tier='t3', total=len(stacks))
    for stack in stacks:
        if stack.get('status') == 'paused':
            coverage.record_skipped(stack['slug'], 'paused')
        else:
            coverage.record_ok(stack['slug'])
    payload = payload or {'one': {'adaptive_metrics': am}}
    metrics, views, cov = compose.build_all(stacks, coverage, dataplane=payload, ratecard=ratecard)
    published = dict(seeded or {})

    def capture(path, key, bucket, dry_run):
        published[key] = json.loads(path.read_text())
        return key

    with mock.patch.object(s3, '_put', side_effect=capture):
        s3.write_views(views, {'tier': 't3'}, bucket='offline', view_coverage=cov)
    return metrics, views, published


def test_segmented_default_saving_is_not_a_whole_stack_total():
    client = Client([SEGMENT])
    am = dataplane.adaptive_metrics(client, STACK, 'cap')
    from collector import ratecard
    card = ratecard.loads('dimension,rate,per,unit,included,currency,period,billing_basis,notes\n'
                          'metrics_series,3,1000,series,0,USD,month,base_rate_only,\n')
    metrics, views, published = publish(am, ratecard=card)
    assert not any(name.startswith('gcinsight_value_savings_') for name, _, _ in metrics)
    assert 'gcinsight_value_savings_identified_series' not in {n for n, _, _ in metrics}
    assert am['segment_coverage_state'] == 'segmented'
    assert am['series_counts_complete'] is True  # default-count validity is independent
    assert am['rules_applied'] is None
    assert am['remediable_series'] is None
    assert maturity._adaptive_adoption(STACK, {'adaptive_metrics': am}) is None
    assert published['views/value_savings.json']['meta']['rules_coverage'] == {
        'measured': 0, 'in_scope': 1, 'complete': False}
    encoded = json.dumps(published)
    assert 'segmented' in encoded
    assert 'PRIVATE-' not in encoded
    assert SEGMENT['id'] not in encoded
    assert client.calls.count(('https://inventory.example/aggregations/rules/segments',
                               ('123', 'cap'))) == 1


@pytest.mark.parametrize('segments,status,state', [
    ([], 200, 'unsegmented'), ([SEGMENT], 200, 'segmented'),
    ({}, 200, 'unknown'), ([None], 200, 'unknown'),
    ([SEGMENT, SEGMENT], 200, 'unknown'),
    ([dict(SEGMENT, id='bad/id')], 200, 'unknown'),
    ([dict(SEGMENT, fallback_to_default=1)], 200, 'unknown'),
    ([{'id': SEGMENT['id']}], 200, 'unknown'),
    ([], 503, 'unknown'),
    ([], 206, 'unknown'), ([SEGMENT], 206, 'unknown'),
    ([], 201, 'unknown'), ([], 204, 'unknown'),
])
def test_discovery_states(segments, status, state):
    am = dataplane.adaptive_metrics(Client(segments, status=status), STACK, 'cap')
    assert am['segment_coverage_state'] == state
    last_good = {'meta': {'generated_at': 'older'}, 'rows': [{'sentinel': 'last-good'}]}
    metrics, _, published = publish(am, seeded={'views/cost_summary.json': last_good})
    names = {n for n, _, _ in metrics}
    assert ('gcinsight_value_savings_identified_series' in names) == (state == 'unsegmented')
    assert am['segments_discovered'] == (len(segments) if state != 'unknown' else None)
    assert published['views/value_savings.json']['meta']['rules_coverage'] == {
        'measured': int(state == 'unsegmented'), 'in_scope': 1,
        'complete': state == 'unsegmented'}
    if state == 'unsegmented':
        assert ('gcinsight_value_savings_identified_series', {}, 90.0) in metrics
        assert published['views/cost_summary.json'] != last_good
    else:
        assert not any(name.startswith('gcinsight_value_savings_') for name in names)
        cost_rows = published['views/cost_summary.json']['rows']
        assert cost_rows[0]['Value'] == '0 of 1 scannable (1 total)'
        # Independent inventory dimensions still update; unavailable Adaptive claims stay null.
        assert all(row['Value'] is None for row in cost_rows[1:6])
        assert {'gcinsight_cost_adaptive_rules_applied_total',
                'gcinsight_cost_stacks_without_adaptive'}.isdisjoint(names)
        assert maturity._adaptive_adoption(STACK, {'adaptive_metrics': am}) is None


def test_empty_discovery_and_empty_recommendations_prove_zero():
    am = dataplane.adaptive_metrics(Client([], empty=True), STACK, 'cap')
    metrics, _, _ = publish(am)
    assert ('gcinsight_value_savings_identified_series', {}, 0.0) in metrics


def test_legacy_complete_counts_remain_unknown():
    am = dataplane.adaptive_metrics(Client([]), STACK, 'cap')
    del am['segment_coverage_state']
    metrics, _, published = publish(am)
    assert 'gcinsight_value_savings_identified_series' not in {n for n, _, _ in metrics}
    assert published['views/value_savings.json']['meta']['rules_coverage']['measured'] == 0
    assert maturity._adaptive_adoption(STACK, {'adaptive_metrics': am}) is None


def test_mixed_live_source_population_is_qualified_in_dashboard(tmp_path):
    import shutil
    from bin import dashboards
    from collector.dashboards import build
    from collector import ratecard

    normal = dataplane.adaptive_metrics(Client([]), STACK, 'cap')
    segmented = dataplane.adaptive_metrics(Client([SEGMENT]), STACK, 'cap')
    unknown = dataplane.adaptive_metrics(Client({}, False), STACK, 'cap')
    stacks = [dict(STACK, slug=slug) for slug in ('one', 'segmented', 'unknown')]
    stacks.append(dict(STACK, slug='paused', status='paused'))
    payload = {slug: {'adaptive_metrics': am} for slug, am in (
        ('one', normal), ('segmented', segmented), ('unknown', unknown),
        ('departed', normal), ('paused', normal))}
    card = ratecard.loads('dimension,rate,per,unit,included,currency,period,billing_basis,notes\n'
                          'metrics_series,3,1000,series,0,USD,month,base_rate_only,\n')
    metrics, views, published = publish(normal, stacks, payload, card)
    assert not any(name.startswith('gcinsight_value_savings_') for name, _, _ in metrics)
    envelope = published['views/value_savings.json']
    assert envelope['meta']['rules_coverage'] == {
        'measured': 1, 'in_scope': 3, 'complete': False}
    rows = {r[' Metric']: r['Value'] for r in envelope['rows']}
    assert rows['Remediable series, applying every recommendation (measured on 1 of 3 stacks)'] == 90
    priced = [v for k, v in rows.items() if 'USD/month' in k]
    assert priced[0] == 0.27
    assert '1 unsegmented; 1 segmented; 1 unknown' in rows['Adaptive segment coverage']
    benchmark = next(r for r in views['value_benchmarks'] if r[' Dimension'] == 'adaptive_adoption')
    assert benchmark['Stacks with data'] == 1
    fixtures = __import__('pathlib').Path(__file__).resolve().parents[1] / 'testdata/views'
    for existing in fixtures.glob('*.json'):
        shutil.copyfile(existing, tmp_path / existing.name)
    for key, doc in published.items():
        (tmp_path / key.rsplit('/', 1)[-1]).write_text(json.dumps(doc))
    with mock.patch.object(build, 'VIEWS_DIR', str(tmp_path)), mock.patch.object(build, 'BUCKET', 'offline'):
        _, dashboard = dashboards.assemble('value', 'infinity-offline')
    queries = [q['spec']['query']['spec'] for element in dashboard['spec']['elements'].values()
               for q in element['spec'].get('data', {}).get('spec', {}).get('queries', [])]
    savings = next(q for q in queries if q.get('url', '').endswith('/value_savings.json'))
    assert savings['root_selector'] == 'rows'
    assert ' Metric' in [c['selector'] for c in savings['columns']]


@pytest.mark.parametrize('discovery', ['legacy', 'partial-empty', 'partial-segmented'])
def test_t1_legacy_hydration_cannot_carry_complete_default_totals(discovery):
    import datetime as dt
    import scan
    from collector.emit import hydrate
    from tests.test_scan import FakeClient, cfg_for

    segments = [SEGMENT] if discovery == 'partial-segmented' else []
    am = dataplane.adaptive_metrics(
        Client(segments, status=200 if discovery == 'legacy' else 206), STACK, 'cap')
    if discovery == 'legacy':
        del am['segment_coverage_state']
    names = ['gcinsight_cost_adaptive_rules_applied_total', 'gcinsight_cost_stacks_without_adaptive',
             'gcinsight_value_savings_identified_series', 'gcinsight_value_savings_unused_series',
             'gcinsight_value_savings_identified_currency', 'gcinsight_value_savings_unused_currency']
    state = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'tier': 't3',
             'metrics': [[name, {}, 100] for name in names]}
    with (mock.patch.object(scan.gcom, 'fetch_inventory', return_value=[dict(STACK, status='active')]),
          mock.patch.object(scan.gcom, 'fetch_access_policies', return_value=[]),
          mock.patch.object(scan.gcom, 'fetch_org_members', return_value={'state': 'ok', 'members': []}),
          mock.patch.object(scan, 'gather_fleet', return_value=({}, [])),
          mock.patch.object(scan.hydrate, 'hydrate', return_value=(
              {'dataplane': {'one': {'adaptive_metrics': am}}}, hydrate.Provenance())),
          mock.patch.object(scan, 'assistant_gaps', return_value={}),
          mock.patch.object(scan, 'load_ratecard', return_value=None),
          mock.patch.object(scan.carry, 'load_state', return_value=state)):
        result = scan.run_t1(FakeClient(), cfg_for('t1'))
    assert set(names).isdisjoint(n for n, _, _ in result['_emit']['metrics'])
    assert result['_emit']['view_coverage']['cost_summary']['measured'] == 0


if __name__ == "__main__":
    unittest.main()
