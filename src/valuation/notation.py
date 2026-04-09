"""Valuation-friendly number notation helpers.

Use this module when code or tests need large financial values. It avoids
spreading raw eleven- and twelve-digit literals across the repo.
"""

from __future__ import annotations

import re
from numbers import Real
from typing import Any, Union

THOUSAND = 1_000
MILLION = 1_000_000
BILLION = 1_000_000_000
TRILLION = 1_000_000_000_000

K = THOUSAND
M = MILLION
B = BILLION
T = TRILLION

_DISPLAY_SCALES = (
    (TRILLION, "T"),
    (BILLION, "B"),
    (MILLION, "M"),
    (THOUSAND, "K"),
)

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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
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


def format_scaled_number(value: Any) -> Any:
    """Render a number using valuation-friendly scale suffixes."""
    if not _is_number(value):
        return value
    return _format_scaled(value)


def format_scaled_currency(value: Any) -> Any:
    """Render a number using valuation-friendly currency notation."""
    if not _is_number(value):
        return value
    return _format_scaled(value, prefix="$")


def _format_scaled(value: Any, prefix: str = "") -> str:
    numeric = float(value)
    negative = numeric < 0
    absolute = abs(numeric)

    for scale, suffix in _DISPLAY_SCALES:
        if absolute >= scale:
            rendered = _trimmed_decimal(absolute / scale)
            return _with_sign(prefix, rendered + suffix, negative)

    if float(absolute).is_integer():
        rendered = f"{absolute:,.0f}"
    else:
        rendered = _trimmed_decimal(absolute)
    return _with_sign(prefix, rendered, negative)


def _trimmed_decimal(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _with_sign(prefix: str, rendered: str, negative: bool) -> str:
    if negative:
        return f"-{prefix}{rendered}"
    return f"{prefix}{rendered}"


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)
