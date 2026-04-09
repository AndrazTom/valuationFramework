"""Scaled-number helpers for valuation code."""

from __future__ import annotations

import re
from typing import Union

THOUSAND = 1_000
MILLION = 1_000_000
BILLION = 1_000_000_000
TRILLION = 1_000_000_000_000

_SCALE_MAP = {
    "K": THOUSAND,
    "THOUSAND": THOUSAND,
    "M": MILLION,
    "MM": MILLION,
    "MILLION": MILLION,
    "B": BILLION,
    "BN": BILLION,
    "BILLION": BILLION,
    "T": TRILLION,
    "TN": TRILLION,
    "TRILLION": TRILLION,
}


def parse_scaled_number(value: Union[str, int, float]) -> float:
    """Parse inputs like `100B`, `2.5M`, or plain numbers into a float."""
    if isinstance(value, (int, float)):
        return float(value)

    cleaned = value.strip().upper().replace(",", "")
    match = re.fullmatch(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Z]+)?", cleaned)
    if match is None:
        raise ValueError(f"Could not parse scaled number: {value}")

    number = float(match.group(1))
    scale = match.group(2)
    if scale is None:
        return number
    if scale not in _SCALE_MAP:
        raise ValueError(f"Unknown scale suffix: {scale}")
    return number * _SCALE_MAP[scale]
