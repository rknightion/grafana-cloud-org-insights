"""Structural fence for the explicitly approved count-only product resources.

Only field names and JSON structure are examined, never string value semantics.
This cannot undo receipt into memory, detect all secrets, or authorize other routes.
"""
from __future__ import annotations

import math

MAX_NODES = 100_000
MAX_DEPTH = 32
MAX_KEY_LENGTH = 256
CREDENTIAL_FIELDS = frozenset({
    "apikey", "grafanaapikey", "clientsecret", "password", "authorization",
    "accesstoken", "refreshtoken", "secretkey", "privatekey",
})


class UnsafeSchema(ValueError):
    """A resource must be deferred; the exception never includes upstream content."""


def guard_resource(body):
    """Bound traversal, rejecting known credential fields and malformed structures."""
    pending = [(body, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise UnsafeSchema("unsafe_schema")
        if isinstance(value, dict):
            if nodes + len(pending) + len(value) > MAX_NODES:
                raise UnsafeSchema("unsafe_schema")
            for key, child in value.items():
                if (not isinstance(key, str) or len(key) > MAX_KEY_LENGTH
                        or key.replace("_", "").replace("-", "").lower() in CREDENTIAL_FIELDS):
                    raise UnsafeSchema("unsafe_schema")
                pending.append((child, depth + 1))
        elif isinstance(value, list):
            if nodes + len(pending) + len(value) > MAX_NODES:
                raise UnsafeSchema("unsafe_schema")
            pending.extend((child, depth + 1) for child in value)
        elif value is not None and not isinstance(value, (str, bool, int, float)):
            raise UnsafeSchema("unsafe_schema")
        elif isinstance(value, float) and not math.isfinite(value):
            raise UnsafeSchema("unsafe_schema")
    return body
