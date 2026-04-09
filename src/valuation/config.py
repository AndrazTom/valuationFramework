"""Project configuration helpers."""

from __future__ import annotations

import os

DEFAULT_SEC_USER_AGENT = "valuationFramework/0.1 (set VALUATION_SEC_USER_AGENT)"


def get_sec_user_agent() -> str:
    """Return the SEC-compliant user agent string."""
    return os.getenv("VALUATION_SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT)


def using_default_sec_user_agent() -> bool:
    """Whether the SEC user agent is still the placeholder value."""
    return get_sec_user_agent() == DEFAULT_SEC_USER_AGENT
