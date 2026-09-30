"""Pure generic risk classification. Raw values are returned only to the approved S3 input.

No decoded JWT claims, value hashes or unmatched values leave this classifier. Confidence describes
format/context, not proof of a person, payment card or working credential. No remediation is inferred.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import pathlib
import re
from typing import Any

PATTERNS = json.loads(pathlib.Path(__file__).with_name("pii_patterns.json").read_text())
VERSION = PATTERNS["version"]
KEYS = {kind: frozenset(names) for kind, names in PATTERNS["keys"].items()}


def key_classes(key: str) -> list[tuple[str, str]]:
    # Preserve Tempo scope in the source; classify only the attribute portion supplied by it.
    normal = re.sub(r"[.\-]", "_", key).lower()
    return [(kind, "high" if kind in {"email", "secret", "sensitive_identifier"} else "possible")
            for kind, names in KEYS.items() if normal in names]


def _luhn(digits: str) -> bool:
    total = 0
    for i, digit in enumerate(reversed(digits)):
        n = int(digit)
        if i % 2:
            n *= 2
            n = n - 9 if n > 9 else n
        total += n
    return total % 10 == 0


def _jwt(value: str) -> bool:
    if len(value) > 8192:
        return False
    parts = value.split(".")
    if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in parts):
        return False
    try:
        objects = [json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
                   for p in parts[:2]]
        return all(isinstance(obj, dict) for obj in objects) and isinstance(objects[0].get("alg"), str)
    except (ValueError, UnicodeError, RecursionError):
        return False


def value_classes(key: str, value: str) -> list[tuple[str, str]]:
    if not value or len(value) > 8192:
        return []
    out: list[tuple[str, str]] = []
    context = {kind for kind, _confidence in key_classes(key)}
    if len(value) <= 254 and re.fullmatch(PATTERNS["email"], value):
        out.append(("email", "high"))
    try:
        # Complete literals only: not addresses hidden in URLs, ports or forwarded lists.
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        out.append(("ip_address", "possible"))
    digits = re.sub(r"[ ()-]", "", value)
    if (re.fullmatch(PATTERNS["international_phone"], value)
            and digits.startswith("+") and digits[1:].isdigit() and 8 <= len(digits[1:]) <= 15):
        out.append(("phone", "high" if "phone" in context else "possible"))
    elif "phone" in context and digits.isdigit() and 8 <= len(digits) <= 15:
        out.append(("phone", "possible"))
    card = re.sub(r"[ -]", "", value)
    if card.isascii() and card.isdigit() and 13 <= len(card) <= 19 and len(set(card)) > 1 and _luhn(card):
        out.append(("card_like", "possible"))
    if _jwt(value):
        out.append(("jwt", "high"))
    elif "secret" in context and re.fullmatch(PATTERNS["token"], value) and len(set(value)) >= 10:
        out.append(("secret", "possible"))
    words = value.split()
    if "person_name" in context and 2 <= len(words) <= 4 and all(w.isalpha() for w in words):
        out.append(("person_name", "possible"))
    return out


def finding(kind: str, confidence: str, **fields: Any) -> dict[str, Any]:
    return {"class": kind, "confidence": confidence, "pattern_version": VERSION, **fields}
