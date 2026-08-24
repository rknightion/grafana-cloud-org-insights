"""Mimir remote_write encoding (PLAN 5.1).

Both wire formats are hand-rolled, so both are decoded back here. The protobuf decoder below is
deliberately independent of the encoder - it walks tags and wire types generically rather than assuming
the layout - so a matching round-trip is real evidence about the bytes, not two copies of one mistake.
"""

from __future__ import annotations

import datetime as dt
import struct
import unittest

from collector.emit import mimir
from collector.emit.guard import DuplicateSeries, UnboundedLabel


# --- an independent, generic protobuf reader ------------------------------------------------------

def read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, pos


def parse_fields(data: bytes) -> list[tuple[int, int, bytes | int]]:
    """Generic walk: returns (field_number, wire_type, payload) for every field present."""
    out: list[tuple[int, int, bytes | int]] = []
    pos = 0
    while pos < len(data):
        key, pos = read_varint(data, pos)
        field, wire = key >> 3, key & 0x07
        if wire == 0:
            value, pos = read_varint(data, pos)
            out.append((field, wire, value))
        elif wire == 1:
            out.append((field, wire, data[pos:pos + 8]))
            pos += 8
        elif wire == 2:
            length, pos = read_varint(data, pos)
            out.append((field, wire, data[pos:pos + length]))
            pos += length
        else:
            raise AssertionError(f"unexpected wire type {wire}")
    return out


def decode_write_request(body: bytes) -> list[dict]:
    series = []
    for field, wire, payload in parse_fields(body):
        assert field == 1 and wire == 2, f"WriteRequest.timeseries must be field 1, got {field}"
        labels: dict[str, str] = {}
        samples: list[tuple[float, int]] = []
        label_order: list[str] = []
        for sub_field, _sw, sub in parse_fields(payload):  # type: ignore[arg-type]
            if sub_field == 1:
                pair = {f: p for f, _w, p in parse_fields(sub)}  # type: ignore[arg-type]
                name = pair[1].decode()  # type: ignore[union-attr]
                labels[name] = pair[2].decode()  # type: ignore[union-attr]
                label_order.append(name)
            elif sub_field == 2:
                parts = {f: p for f, _w, p in parse_fields(sub)}  # type: ignore[arg-type]
                samples.append((struct.unpack("<d", parts[1])[0], parts[2]))  # type: ignore[arg-type]
        series.append({"labels": labels, "order": label_order, "samples": samples})
    return series


class SnappyTest(unittest.TestCase):
    def test_round_trip_across_sizes_that_change_the_tag_width(self):
        for size in (0, 1, 59, 60, 61, 255, 256, 65_535, 65_536, 200_000):
            data = bytes((i * 7 + 3) & 0xFF for i in range(size))
            self.assertEqual(mimir.snappy_decompress(mimir.snappy_compress(data)), data, f"size {size}")

    def test_preamble_is_the_uncompressed_length_as_a_varint(self):
        block = mimir.snappy_compress(b"x" * 300)
        length, pos = read_varint(block, 0)
        self.assertEqual(length, 300)
        # Then an extended literal tag, since 299 >= 60.
        self.assertEqual(block[pos] & 0x03, 0, "literal tags have 00 in the low two bits")
        self.assertGreaterEqual(block[pos] >> 2, 60)

    def test_short_payload_uses_the_single_byte_literal_tag(self):
        block = mimir.snappy_compress(b"abc")
        self.assertEqual(block[0], 3)
        self.assertEqual(block[1], (3 - 1) << 2)
        self.assertEqual(block[2:], b"abc")

    def test_overhead_is_a_handful_of_bytes(self):
        """It does not compress; it must at least not bloat."""
        data = b"y" * 150_000
        self.assertLessEqual(len(mimir.snappy_compress(data)) - len(data), 8)

    def test_the_decoder_refuses_back_references_rather_than_guessing(self):
        with self.assertRaises(ValueError):
            mimir.snappy_decompress(b"\x05\x01\x00")


class ProtobufTest(unittest.TestCase):
    def test_a_single_series_round_trips(self):
        body = mimir.encode_write_request(
            [("gcinsight_estate_stacks", {"status": "total"}, 271.0)], 1_755_460_000_000
        )
        series = decode_write_request(body)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["labels"],
                         {"__name__": "gcinsight_estate_stacks", "status": "total"})
        value, timestamp = series[0]["samples"][0]
        self.assertEqual(value, 271.0)
        self.assertEqual(timestamp, 1_755_460_000_000)

    def test_metric_name_travels_as_the_name_label(self):
        body = mimir.encode_write_request([("m", {}, 1.0)], 0)
        self.assertEqual(decode_write_request(body)[0]["labels"]["__name__"], "m")

    def test_labels_are_sorted_lexicographically_with_name_first(self):
        """The spec requires sorted labels; unsorted is accepted by some receivers and not others."""
        body = mimir.encode_write_request(
            [("m", {"stack": "z", "region": "a", "kind": "m"}, 1.0)], 0
        )
        order = decode_write_request(body)[0]["order"]
        self.assertEqual(order, ["__name__", "kind", "region", "stack"])
        self.assertEqual(order, sorted(order))

    def test_float_values_survive_exactly(self):
        for value in (0.0, 1.0, -1.5, 0.446, 3_012_408.0, 1e-9, 1e18):
            body = mimir.encode_write_request([("m", {}, value)], 0)
            self.assertEqual(decode_write_request(body)[0]["samples"][0][0], value)

    def test_a_negative_timestamp_encodes_as_a_full_width_varint(self):
        """protobuf int64 is not zigzag: -1 sign-extends to ten bytes. Getting this wrong ships a
        timestamp far in the future rather than an error."""
        body = mimir.encode_write_request([("m", {}, 1.0)], -1)
        raw = decode_write_request(body)[0]["samples"][0][1]
        self.assertEqual(raw, 2**64 - 1)

    def test_a_whole_batch_round_trips_with_every_series_intact(self):
        metrics = [(f"gcinsight_m{i}", {"stack": f"s{i}"}, float(i)) for i in range(200)]
        series = decode_write_request(mimir.encode_write_request(metrics, 1_000))
        self.assertEqual(len(series), 200)
        for i, entry in enumerate(series):
            self.assertEqual(entry["labels"]["__name__"], f"gcinsight_m{i}")
            self.assertEqual(entry["samples"][0][0], float(i))

    def test_the_full_pipeline_composes(self):
        metrics = [("gcinsight_estate_stacks", {"status": "total"}, 271.0)]
        wire = mimir.snappy_compress(mimir.encode_write_request(metrics, 42))
        decoded = decode_write_request(mimir.snappy_decompress(wire))
        self.assertEqual(decoded[0]["samples"][0], (271.0, 42))


class ValidationTest(unittest.TestCase):
    def test_an_empty_label_value_is_refused_not_silently_dropped(self):
        """Mimir drops empty label values, so the series arrives missing a dimension with no error."""
        with self.assertRaises(mimir.InvalidSeries):
            mimir.validate("m", {"stack": ""})

    def test_a_reserved_double_underscore_label_is_refused(self):
        """The allow-list catches this first (UnboundedLabel); the `__` check in validate() is defence
        in depth for a future allow-listed key. Both subclass ValueError, so assert the family."""
        with self.assertRaises(ValueError):
            mimir.validate("m", {"__name__": "m"})
        with self.assertRaises(UnboundedLabel):
            mimir.validate("m", {"__name__": "m"})

    def test_the_cardinality_guard_still_applies_at_the_wire(self):
        """The emitter is the last gate. An unbounded label must not get through here either."""
        with self.assertRaises(UnboundedLabel):
            mimir.validate("m", {"dashboard_uid": "abc123"})

    def test_an_empty_metric_name_is_refused(self):
        with self.assertRaises(mimir.InvalidSeries):
            mimir.validate("", {"stack": "a"})

    def test_an_overlong_label_value_is_refused(self):
        with self.assertRaises(UnboundedLabel):
            mimir.validate("m", {"stack": "x" * 3000})


class WriterTest(unittest.TestCase):
    def test_the_write_path_is_appended_once(self):
        for base in ("https://prometheus-prod-65-prod-eu-west-2.grafana.net",
                     "https://prometheus-prod-65-prod-eu-west-2.grafana.net/",
                     "https://prometheus-prod-65-prod-eu-west-2.grafana.net/api/prom/push"):
            writer = mimir.RemoteWriter(base, "000000", "tok", dry_run=True)
            self.assertEqual(writer.url,
                             "https://prometheus-prod-65-prod-eu-west-2.grafana.net/api/prom/push")

    def test_plain_http_is_refused(self):
        with self.assertRaises(mimir.RemoteWriteRefused):
            mimir.RemoteWriter("http://example.invalid", "1", "tok")

    def test_headers_carry_snappy_protobuf_and_the_1x_version(self):
        writer = mimir.RemoteWriter("https://example.grafana.net", "000000", "tok", dry_run=True)
        headers = writer._headers(123)
        self.assertEqual(headers["Content-Encoding"], "snappy")
        self.assertEqual(headers["Content-Type"], "application/x-protobuf")
        self.assertEqual(headers["X-Prometheus-Remote-Write-Version"], "0.1.0")
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertIn("gcinsight", headers["User-Agent"])

    def test_tenant_and_token_form_the_basic_auth_pair(self):
        import base64
        writer = mimir.RemoteWriter("https://example.grafana.net", "000000", "secret", dry_run=True)
        raw = base64.b64decode(writer._headers(1)["Authorization"].split()[1]).decode()
        self.assertEqual(raw, "000000:secret")

    def test_dry_run_writes_nothing_but_still_encodes_and_validates(self):
        writer = mimir.RemoteWriter("https://example.grafana.net", "1", "tok", dry_run=True)
        self.assertEqual(writer.push([("m", {"stack": "a"}, 1.0)]), 1)
        with self.assertRaises(UnboundedLabel):
            writer.push([("m", {"login": "a@b.com"}, 1.0)])

    def test_an_empty_batch_is_a_no_op(self):
        writer = mimir.RemoteWriter("https://example.grafana.net", "1", "tok", dry_run=True)
        self.assertEqual(writer.push([]), 0)

    def test_duplicate_series_in_one_batch_are_refused(self):
        writer = mimir.RemoteWriter("https://example.grafana.net", "1", "tok", dry_run=True)
        with self.assertRaises(DuplicateSeries):
            writer.push([("m", {"stack": "a"}, 1.0), ("m", {"stack": "a"}, 2.0)])

    def test_timestamp_is_milliseconds(self):
        writer = mimir.RemoteWriter("https://example.grafana.net", "1", "tok", dry_run=True)
        stamp = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.timezone.utc)
        body = mimir.encode_write_request([("m", {}, 1.0)], int(stamp.timestamp() * 1000))
        got = decode_write_request(body)[0]["samples"][0][1]
        self.assertEqual(got, int(stamp.timestamp()) * 1000)
        self.assertGreater(got, 1_700_000_000_000, "seconds instead of ms would land in 1970")
        writer.push([("m", {}, 1.0)], timestamp=stamp)


class RealBatchTest(unittest.TestCase):
    """The actual estate batch must encode, not just a toy series."""

    def test_the_live_pillar_output_encodes_and_round_trips(self):
        import json
        import pathlib
        from collector.coverage import Coverage
        from collector.pillars import compose

        evidence = pathlib.Path(__file__).resolve().parent.parent / "testdata"
        stacks = json.loads((evidence / "gcom-instances-2026-08-17.json").read_text())["items"]
        dataplane = json.loads((evidence / "t3-dataplane-2026-08-17.json").read_text())
        coverage = Coverage(tier="t3", total=len(stacks))
        for s in stacks:
            if s.get("status") == "paused":
                coverage.record_skipped(str(s["slug"]), "paused")
            else:
                coverage.record_ok(str(s["slug"]))
        metrics, _ = compose.build_all(stacks, coverage, dataplane=dataplane)

        wire = mimir.snappy_compress(mimir.encode_write_request(metrics, 1_755_460_000_000))
        decoded = decode_write_request(mimir.snappy_decompress(wire))
        self.assertEqual(len(decoded), len(metrics))
        for entry in decoded:
            self.assertIn("__name__", entry["labels"])
            self.assertEqual(entry["order"], sorted(entry["order"]))
            self.assertEqual(len(entry["samples"]), 1)
        # A rough guard on body size, so a cardinality mistake shows up as a failing test.
        self.assertLess(len(wire), 2_000_000, f"{len(wire):,} bytes for {len(metrics)} series")


if __name__ == "__main__":
    unittest.main()
