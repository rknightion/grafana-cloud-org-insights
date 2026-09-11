"""Explicitly bounded combinatorial helpers for contract tests."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Iterator
from typing import TypeVar


T = TypeVar("T")


def subsets_up_to(
    items: Iterable[T], *, max_size: int, max_subsets: int
) -> Iterator[frozenset[T]]:
    """Yield subsets only after proving the complete search fits the caller's budget."""
    values = tuple(items)
    if max_size < 0:
        return
    capped_size = min(max_size, len(values))
    count = sum(math.comb(len(values), size) for size in range(capped_size + 1))
    if count > max_subsets:
        raise AssertionError(
            f"combinatorial proof needs {count} subsets, above its {max_subsets} cap"
        )
    for size in range(capped_size + 1):
        for subset in itertools.combinations(values, size):
            yield frozenset(subset)
