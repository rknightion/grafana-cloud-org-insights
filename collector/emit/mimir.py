"""Mimir remote_write emitter - protobuf + snappy, hand-rolled on the stdlib (PLAN 5.1).

**Never the OTLP gateway.** Routing our own telemetry through the org's gateway would inflate their
request counts and corrupt the protocol-adoption numbers this platform reports on. Native remote_write
is the only correct path.

The collector is stdlib-only, so both wire formats are implemented here rather than imported.

## protobuf - `prometheus.WriteRequest` (remote write 1.0)

    message WriteRequest { repeated TimeSeries timeseries = 1; }
    message TimeSeries   { repeated Label labels = 1; repeated Sample samples = 2; }
    message Label        { string name = 1; string value = 2; }
    message Sample       { double value = 1; int64 timestamp = 2; }

Only four messages and three wire types (varint, length-delimited, fixed64), so encoding it by hand is
a few dozen lines and no dependency. The field numbers are load-bearing: remote write 2.0 `reserved 1
to 3` in its `Request` precisely because 1.0 used field 1 for `timeseries`, which is what pins them.

## snappy - block format, literals only

Mimir wants snappy **block** format (not the framed variant). A valid snappy block may consist entirely
of literal runs with no back-references, so this emits exactly that: the uncompressed length as a
varint, one extended-length literal tag, then the payload verbatim.

**It is therefore valid snappy that does not compress.** Overhead is ~6 bytes against a ~150KB body, so
the trade is a dependency-free encoder for a payload that does not shrink. If body size ever matters,
the upgrade is `python3-snappy` and `compress()` becomes one line - the rest of this module is unchanged.

## The GET-only invariant

`ReadOnlyClient` refuses any method but GET, by construction, and that stays true: it is what guarantees
the collector cannot mutate any stack it scans. This module does its own POST, and to keep the guarantee
meaningful it refuses to post anywhere except a configured remote_write endpoint - see `RemoteWriter`.
"""

from __future__ import annotations

import base64
import datetime as dt
import struct
import urllib.error
import urllib.request
from typing import Iterable, Mapping, Sequence

from collector import identity
from collector.emit import guard

WRITE_PATH = "/api/prom/push"
CONTENT_TYPE = "application/x-protobuf"
# 0.1.0 is mandatory when talking to a 1.x receiver, which Mimir is on this path.
WRITE_VERSION = "0.1.0"
USER_AGENT = identity.env("GCINSIGHT_USER_AGENT", "gcinsight-collector/1 (+grafana-ps)")

MAX_LABEL_NAME = 128
MAX_LABEL_VALUE = 2048


class InvalidSeries(ValueError):
    """A series that Mimir would reject, caught before the request rather than as a 400."""


class RemoteWriteRefused(RuntimeError):
    """The writer was pointed at something that is not its configured remote_write endpoint."""


class RemoteWriteFailed(RuntimeError):
    pass


# --- protobuf primitives -------------------------------------------------------------------------

def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint is unsigned here; Sample.timestamp uses _varint_signed")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _varint_signed(value: int) -> bytes:
    """protobuf int64 is NOT zigzag - negatives sign-extend to a full 10-byte varint."""
    return _varint(value & (2**64 - 1))


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _len_delimited(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def _string_field(field: int, text: str) -> bytes:
    return _len_delimited(field, text.encode("utf-8"))


def _double_field(field: int, value: float) -> bytes:
    return _tag(field, 1) + struct.pack("<d", value)


def _int64_field(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint_signed(value)


# --- WriteRequest --------------------------------------------------------------------------------

def validate(name: str, labels: Mapping[str, str]) -> None:
    """Reject what Mimir would 400 on, plus what the cardinality guard forbids."""
    guard.check(name, labels)
    if not name:
        raise InvalidSeries("metric name is empty")
    if "__name__" in labels:
        raise InvalidSeries(f"{name}: pass the metric name as `name`, not as a __name__ label")
    for key, value in labels.items():
        if not key:
            raise InvalidSeries(f"{name}: empty label name")
        # Mimir drops empty label values; a series that silently loses a label is worse than an error.
        if value == "":
            raise InvalidSeries(f"{name}: label {key!r} has an empty value")
        if key.startswith("__"):
            raise InvalidSeries(f"{name}: label {key!r} uses the reserved __ prefix")
        if len(key) > MAX_LABEL_NAME:
            raise InvalidSeries(f"{name}: label name {key!r} is {len(key)} chars")
        if len(value) > MAX_LABEL_VALUE:
            raise InvalidSeries(f"{name}: label {key!r} value is {len(value)} chars")


def encode_timeseries(name: str, labels: Mapping[str, str], value: float, timestamp_ms: int) -> bytes:
    validate(name, labels)
    # __name__ first, then the rest lexicographically. The spec requires sorted labels, and `__name__`
    # sorts before any legal label name anyway, so this IS lexicographic order.
    pairs = [("__name__", name)] + sorted(labels.items())
    body = b"".join(
        _len_delimited(1, _string_field(1, key) + _string_field(2, val)) for key, val in pairs
    )
    body += _len_delimited(2, _double_field(1, float(value)) + _int64_field(2, timestamp_ms))
    return body


def encode_write_request(
    metrics: Iterable[tuple[str, Mapping[str, str], float]], timestamp_ms: int
) -> bytes:
    """Serialise a whole batch as one `prometheus.WriteRequest`."""
    return b"".join(
        _len_delimited(1, encode_timeseries(name, labels, value, timestamp_ms))
        for name, labels, value in metrics
    )


# --- snappy block, literals only -----------------------------------------------------------------

def snappy_compress(data: bytes) -> bytes:
    """Valid snappy block format containing a single literal run. See the module docstring."""
    if not data:
        # An empty block is just the length preamble.
        return _varint(0)
    out = bytearray(_varint(len(data)))
    length_minus_one = len(data) - 1
    if length_minus_one < 60:
        out.append(length_minus_one << 2)
    else:
        # Extended literal length: tag (59 + n) << 2, then (len-1) little-endian in n bytes.
        width = (length_minus_one.bit_length() + 7) // 8
        out.append((59 + width) << 2)
        out.extend(length_minus_one.to_bytes(width, "little"))
    out.extend(data)
    return bytes(out)


def snappy_decompress(block: bytes) -> bytes:
    """Decoder for the literals-only subset, so the encoder is verifiable without a dependency.

    Deliberately NOT a general snappy decoder - it raises on back-references rather than pretending to
    handle them, because its only job is to prove what `snappy_compress` produced.
    """
    pos = 0
    expected = 0
    shift = 0
    while True:
        byte = block[pos]
        pos += 1
        expected |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
    out = bytearray()
    while pos < len(block):
        tag = block[pos]
        pos += 1
        if tag & 0x03:
            raise ValueError("back-reference found; this decoder handles literals only")
        run = tag >> 2
        if run < 60:
            length = run + 1
        else:
            width = run - 59
            length = int.from_bytes(block[pos:pos + width], "little") + 1
            pos += width
        out.extend(block[pos:pos + length])
        pos += length
    if len(out) != expected:
        raise ValueError(f"snappy length mismatch: preamble {expected}, got {len(out)}")
    return bytes(out)


# --- the writer ----------------------------------------------------------------------------------

class RemoteWriter:
    """POSTs to exactly one configured remote_write endpoint and nowhere else.

    The read client is GET-only by construction; this is the one component that writes, so it is
    deliberately narrow. `url` is fixed at construction and `push` cannot be redirected.
    """

    def __init__(self, base_url: str, tenant: str, token: str, *, dry_run: bool = False,
                 timeout: float = 60.0) -> None:
        base = base_url.rstrip("/")
        if not base.startswith("https://"):
            raise RemoteWriteRefused(f"remote_write must be https, got {base_url!r}")
        if not base.endswith(WRITE_PATH):
            base = base + WRITE_PATH
        self.url = base
        self.tenant = str(tenant)
        self._token = token
        self.dry_run = dry_run
        self.timeout = timeout
        self.samples_written = 0

    def _headers(self, body_len: int) -> dict[str, str]:
        auth = base64.b64encode(f"{self.tenant}:{self._token}".encode()).decode()
        return {
            "Authorization": f"Basic {auth}",
            "Content-Type": CONTENT_TYPE,
            "Content-Encoding": "snappy",
            "X-Prometheus-Remote-Write-Version": WRITE_VERSION,
            "User-Agent": USER_AGENT,
            "Content-Length": str(body_len),
        }

    def push(
        self,
        metrics: Sequence[tuple[str, Mapping[str, str], float]],
        *,
        timestamp: dt.datetime | None = None,
    ) -> int:
        """Encode, compress and POST one batch. Returns the sample count written."""
        if not metrics:
            return 0
        # Duplicate series in one batch would publish whichever sample encoded last.
        guard.check_no_duplicates(metrics)
        stamp = timestamp or dt.datetime.now(dt.timezone.utc)
        timestamp_ms = int(stamp.timestamp() * 1000)

        external = identity.externalize_metrics(metrics)
        body = snappy_compress(encode_write_request(external, timestamp_ms))
        if self.dry_run:
            self.samples_written += len(metrics)
            return len(metrics)

        request = urllib.request.Request(
            self.url, data=body, headers=self._headers(len(body)), method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status not in (200, 204):
                    raise RemoteWriteFailed(f"{self.url}: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read(500).decode("utf-8", "replace")
            raise RemoteWriteFailed(f"{self.url}: HTTP {exc.code} {detail}") from exc
        self.samples_written += len(metrics)
        return len(metrics)
