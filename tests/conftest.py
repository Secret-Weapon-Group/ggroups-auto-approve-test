"""Shared test fixtures for Google Groups moderator tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def pytest_configure(config):
    """Suppress AsyncMock internal coroutine GC warnings.

    Python's AsyncMock creates internal coroutines via _execute_mock_call
    that get garbage-collected without being awaited. This is a stdlib
    limitation — not fixable in test code. The warnings appear
    non-deterministically under pytest-xdist parallel execution.
    """
    config.addinivalue_line(
        "filterwarnings",
        "ignore:coroutine.*was never awaited:RuntimeWarning",
    )
    config.addinivalue_line(
        "filterwarnings",
        "ignore::pytest.PytestUnraisableExceptionWarning",
    )


@pytest.fixture(autouse=True)
def env_vars(tmp_path, monkeypatch):
    """Set required env vars before any module imports them at load time."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
    monkeypatch.setenv("GOOGLE_EMAIL", "test@example.com")
    monkeypatch.setenv("GOOGLE_PASSWORD", "testpass")
    monkeypatch.setenv("GROUP_URL", "https://groups.google.com/g/test-group")


@pytest.fixture
def sample_message():
    """A PendingMessage instance for testing."""
    from mail_monitor import PendingMessage
    return PendingMessage(
        id="0",
        sender="alice@example.com",
        subject="Test forecast discussion",
        snippet="I think the probability is around 30%",
        body="Full body of the test message.\nLine 2.\nLine 3.",
        date="2026-03-15",
        status="ok",
        ai_recommendation="approve",
        ai_reason="On-topic, substantive",
        ai_summary="",
    )


@pytest.fixture
def hold_message():
    """A PendingMessage marked as hold."""
    from mail_monitor import PendingMessage
    return PendingMessage(
        id="1",
        sender="bob@example.com",
        subject="Angry rant",
        snippet="This is terrible",
        body="This is a hostile message body.",
        date="2026-03-16",
        status="hold",
        ai_recommendation="hold",
        ai_reason="Hostile tone",
        ai_summary="",
    )


@pytest.fixture
def mock_anthropic():
    """Mock AsyncAnthropic client."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "On-topic"}')]
    mock_client.messages.create.return_value = mock_response
    return mock_client


def make_realistic_body(
    *,
    greeting="",
    content="",
    signature="",
    bottom_quote="",
):
    """Compose an email body from parts for testing.

    Each part is optional. Parts are joined with blank-line separators.
    """
    parts = []
    if greeting:
        parts.append(greeting)
    if content:
        parts.append(content)
    if signature:
        parts.append(f"-- \n{signature}")
    if bottom_quote:
        parts.append(bottom_quote)
    return "\n\n".join(parts)


@pytest.fixture
def mock_mail_monitor():
    """Mock MailMonitor with all async methods."""
    monitor = MagicMock()
    monitor.connect = AsyncMock()
    monitor.disconnect = AsyncMock()
    monitor.fetch_pending = AsyncMock(return_value=[])
    monitor.approve_messages = AsyncMock(return_value={})
    return monitor
