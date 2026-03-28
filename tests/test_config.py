"""Tests for config.py — env var loading and path constants."""

import importlib
from pathlib import Path


def test_env_vars_loaded(monkeypatch):
    """Config exports env vars from .env."""
    monkeypatch.setenv("GOOGLE_EMAIL", "user@test.com")
    monkeypatch.setenv("GOOGLE_PASSWORD", "secret123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("GROUP_URL", "https://groups.google.com/g/my-group")

    import config
    importlib.reload(config)

    assert config.GOOGLE_EMAIL == "user@test.com"
    assert config.GOOGLE_PASSWORD == "secret123"
    assert config.ANTHROPIC_API_KEY == "sk-test-key"
    assert config.GROUP_URL == "https://groups.google.com/g/my-group"


def test_default_group_url(monkeypatch):
    """GROUP_URL has a default when env var is unset."""
    monkeypatch.delenv("GROUP_URL", raising=False)
    import config
    importlib.reload(config)

    assert "groups.google.com" in config.GROUP_URL


def test_base_dir_is_project_root():
    """BASE_DIR points to the directory containing config.py."""
    import config
    assert config.BASE_DIR == Path(config.__file__).parent


def test_empty_env_vars_default_to_empty_string(monkeypatch):
    """Missing env vars default to empty strings."""
    monkeypatch.delenv("GOOGLE_EMAIL", raising=False)
    monkeypatch.delenv("GOOGLE_PASSWORD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)

    import config
    importlib.reload(config)

    assert config.GOOGLE_EMAIL == ""
    assert config.GOOGLE_PASSWORD == ""
    assert config.ANTHROPIC_API_KEY == ""


def test_email_config_defaults(monkeypatch):
    """Email config vars have sensible defaults."""
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("GROUP_EMAIL", raising=False)

    import config
    importlib.reload(config)

    assert config.IMAP_HOST == "imap.gmail.com"
    assert config.SMTP_HOST == "smtp.gmail.com"
    assert config.SMTP_PORT == 587
    assert config.GROUP_EMAIL == ""


def test_email_config_from_env(monkeypatch):
    """Email config vars can be set via environment."""
    monkeypatch.setenv("IMAP_HOST", "imap.custom.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.custom.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("GROUP_EMAIL", "mygroup@googlegroups.com")

    import config
    importlib.reload(config)

    assert config.IMAP_HOST == "imap.custom.com"
    assert config.SMTP_HOST == "smtp.custom.com"
    assert config.SMTP_PORT == 465
    assert config.GROUP_EMAIL == "mygroup@googlegroups.com"
