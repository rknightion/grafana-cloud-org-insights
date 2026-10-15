"""Explicit Loki-read policy, never inferred from a URL or applied to publishers.

The owner accepts wrapper bypass semantics. Sending this upstream header does not
prove that a deployed proxy forwards it or that Cloud suppresses usage tracking.
"""
from types import MappingProxyType

LOKI_READ_HEADERS = MappingProxyType({"X-Loki-Disable-Pipeline-Wrappers": "true"})
