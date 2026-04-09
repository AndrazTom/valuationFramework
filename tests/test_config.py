from valuation.config import (
    DEFAULT_SEC_USER_AGENT,
    get_sec_user_agent,
    using_default_sec_user_agent,
)


def test_default_sec_user_agent(monkeypatch):
    monkeypatch.delenv("VALUATION_SEC_USER_AGENT", raising=False)

    assert get_sec_user_agent() == DEFAULT_SEC_USER_AGENT
    assert using_default_sec_user_agent() is True


def test_custom_sec_user_agent(monkeypatch):
    monkeypatch.setenv(
        "VALUATION_SEC_USER_AGENT",
        "valuationFramework/0.1 test@example.com",
    )

    assert get_sec_user_agent() == "valuationFramework/0.1 test@example.com"
    assert using_default_sec_user_agent() is False
