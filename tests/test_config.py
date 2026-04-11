from valuation.config import (
    DEFAULT_SEC_USER_AGENT,
    get_sec_user_agent,
    load_project_env,
    using_default_sec_user_agent,
)


def test_default_sec_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("VALUATION_SEC_USER_AGENT", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("valuation.config._LOADED_ENV_FILES", set())
    monkeypatch.setattr("valuation.config._candidate_env_paths", lambda: [tmp_path / ".env"])

    assert get_sec_user_agent() == DEFAULT_SEC_USER_AGENT
    assert using_default_sec_user_agent() is True


def test_custom_sec_user_agent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("valuation.config._LOADED_ENV_FILES", set())
    monkeypatch.setattr("valuation.config._candidate_env_paths", lambda: [tmp_path / ".env"])
    monkeypatch.setenv(
        "VALUATION_SEC_USER_AGENT",
        "valuationFramework/0.1 test@example.com",
    )

    assert get_sec_user_agent() == "valuationFramework/0.1 test@example.com"
    assert using_default_sec_user_agent() is False


def test_load_project_env_reads_local_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("VALUATION_SEC_USER_AGENT", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("valuation.config._LOADED_ENV_FILES", set())
    monkeypatch.setattr("valuation.config._candidate_env_paths", lambda: [tmp_path / ".env"])
    (tmp_path / ".env").write_text(
        "VALUATION_SEC_USER_AGENT=valuationFramework/0.1 local@example.com\n",
        encoding="utf-8",
    )

    load_project_env()

    assert get_sec_user_agent() == "valuationFramework/0.1 local@example.com"


def test_load_project_env_does_not_override_exported_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("valuation.config._LOADED_ENV_FILES", set())
    monkeypatch.setattr("valuation.config._candidate_env_paths", lambda: [tmp_path / ".env"])
    monkeypatch.setenv(
        "VALUATION_SEC_USER_AGENT",
        "valuationFramework/0.1 exported@example.com",
    )
    (tmp_path / ".env").write_text(
        "VALUATION_SEC_USER_AGENT=valuationFramework/0.1 local@example.com\n",
        encoding="utf-8",
    )

    load_project_env()

    assert get_sec_user_agent() == "valuationFramework/0.1 exported@example.com"
