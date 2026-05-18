"""Project configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SEC_USER_AGENT = "valuationFramework/0.1 (set VALUATION_SEC_USER_AGENT)"
_LOADED_ENV_FILES: set[Path] = set()


def load_project_env() -> None:
    """Load repo-local .env files without overriding explicit shell exports."""
    for path in _candidate_env_paths():
        if path in _LOADED_ENV_FILES or not path.is_file():
            continue
        _load_env_file(path)
        _LOADED_ENV_FILES.add(path)


def get_sec_user_agent() -> str:
    """Return the SEC-compliant user agent string."""
    load_project_env()
    return os.getenv("VALUATION_SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT)


def using_default_sec_user_agent() -> bool:
    """Whether the SEC user agent is still the placeholder value."""
    return get_sec_user_agent() == DEFAULT_SEC_USER_AGENT


def cache_dir() -> Path:
    """Return the persistent cache root for provider payloads."""
    load_project_env()
    configured = os.getenv("VALUATION_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "valuationFramework"
    return Path.home() / ".cache" / "valuationFramework"


def _candidate_env_paths() -> list[Path]:
    cwd_env = Path.cwd() / ".env"
    repo_env = Path(__file__).resolve().parents[2] / ".env"
    candidates = [cwd_env]
    if repo_env != cwd_env:
        candidates.append(repo_env)
    return candidates


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
