"""Tests for classifier.py — two-layer message classification."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── _strip_markdown_fences ───────────────────────────────────

class TestStripMarkdownFences:
    def test_clean_json_passthrough(self):
        """Clean JSON string passes through unchanged."""
        from classifier import _strip_markdown_fences

        text = '{"decision":"approve","reason":"ok"}'
        assert _strip_markdown_fences(text) == text

    def test_fenced_with_json_tag(self):
        """Strips ```json and ``` fences."""
        from classifier import _strip_markdown_fences

        text = '```json\n{"decision":"approve","reason":"ok"}\n```'
        assert _strip_markdown_fences(text) == '{"decision":"approve","reason":"ok"}'

    def test_fenced_without_tag(self):
        """Strips bare ``` fences."""
        from classifier import _strip_markdown_fences

        text = '```\n{"decision":"hold","reason":"Off-topic"}\n```'
        assert _strip_markdown_fences(text) == '{"decision":"hold","reason":"Off-topic"}'

    def test_fenced_with_uppercase_json_tag(self):
        """Strips ```JSON fences."""
        from classifier import _strip_markdown_fences

        text = '```JSON\n{"decision":"approve","reason":"ok"}\n```'
        assert _strip_markdown_fences(text) == '{"decision":"approve","reason":"ok"}'

    def test_whitespace_around_fences(self):
        """Handles whitespace inside fences."""
        from classifier import _strip_markdown_fences

        text = '```json\n  {"decision":"approve","reason":"ok"}  \n```'
        assert _strip_markdown_fences(text) == '  {"decision":"approve","reason":"ok"}  '

    def test_non_json_passthrough(self):
        """Non-JSON text passes through unchanged."""
        from classifier import _strip_markdown_fences

        text = "I think we should hold this"
        assert _strip_markdown_fences(text) == text


# ── classify_message ──────────────────────────────────────────

class TestClassifyMessage:
    @pytest.mark.asyncio
    async def test_checks_short_circuit(self):
        """When a check catches the message, returns immediately without API call."""
        from classifier import classify_message

        with patch("classifier.run_all_checks", return_value={"decision": "hold", "reason": "Low-substance reaction: +1"}):
            with patch("classifier.AsyncAnthropic") as mock_cls:
                result = await classify_message("Subject", "+1")
                assert result["decision"] == "hold"
                assert result["reason"] == "Low-substance reaction: +1"
                mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_call_when_checks_pass(self):
        """When all checks pass, makes API call and returns its verdict."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "On-topic forecast"}')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Forecast discussion", "I think the probability is 30%")
                assert result["decision"] == "approve"
                assert result["reason"] == "On-topic forecast"
                mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_call_hold_verdict(self):
        """API returns hold for off-topic messages."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "hold", "reason": "Off-topic chatter"}')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Re: forecast", "Today's xkcd is funny")
                assert result["decision"] == "hold"

    @pytest.mark.asyncio
    async def test_fail_open_on_exception(self):
        """On any exception, returns approve (fail-open)."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_client.messages.create.side_effect = RuntimeError("network error")

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Subject", "Body text")
                assert result["decision"] == "approve"
                assert "reason" in result

    @pytest.mark.asyncio
    async def test_fail_open_on_json_parse_error(self):
        """Malformed JSON from API results in approve."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Subject", "Body")
                assert result["decision"] in ("approve", "hold")

    @pytest.mark.asyncio
    async def test_prompt_includes_tangentially_related(self):
        """Prompt includes 'even if tangentially related'."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "ok"}')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                await classify_message("Subject", "Body")
                call_kwargs = mock_client.messages.create.call_args.kwargs
                system_prompt = call_kwargs["system"]
                assert "even if tangentially related" in system_prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_bright_line_test(self):
        """Prompt includes the bright-line forecasting test."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "ok"}')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                await classify_message("Subject", "Body")
                call_kwargs = mock_client.messages.create.call_args.kwargs
                system_prompt = call_kwargs["system"]
                assert "does the message make, discuss, question, or provide evidence for a prediction or forecast" in system_prompt

    @pytest.mark.asyncio
    async def test_prompt_no_bias(self):
        """Prompt does NOT include '99% of messages are fine' or similar bias."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "ok"}')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                await classify_message("Subject", "Body")
                call_kwargs = mock_client.messages.create.call_args.kwargs
                system_prompt = call_kwargs["system"]
                assert "99%" not in system_prompt

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """Retries on 500 error, succeeds on second attempt."""
        from classifier import classify_message
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(500, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Server error", response=error_response, body=None)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "ok"}')]
        mock_client.messages.create.side_effect = [error, mock_response]

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                with patch("classifier.RETRY_DELAY", 0):
                    result = await classify_message("Subject", "Body")
                    assert result["decision"] == "approve"
                    assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_529(self):
        """Retries on 529 error, succeeds on second attempt."""
        from classifier import classify_message
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(529, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Overloaded", response=error_response, body=None)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "ok"}')]
        mock_client.messages.create.side_effect = [error, mock_response]

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                with patch("classifier.RETRY_DELAY", 0):
                    result = await classify_message("Subject", "Body")
                    assert result["decision"] == "approve"
                    assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_fail_open(self):
        """After exhausting retries, fails open with approve."""
        from classifier import classify_message
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(500, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Server error", response=error_response, body=None)

        mock_client = AsyncMock()
        mock_client.messages.create.side_effect = error

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                with patch("classifier.RETRY_DELAY", 0):
                    result = await classify_message("Subject", "Body")
                    assert result["decision"] == "approve"

    @pytest.mark.asyncio
    async def test_api_key_parameter(self):
        """When api_key is provided, it's passed to AsyncAnthropic."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"decision": "approve", "reason": "ok"}')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client) as mock_cls:
                await classify_message("Subject", "Body", api_key="test-key")
                mock_cls.assert_called_once_with(api_key="test-key")

    @pytest.mark.asyncio
    async def test_sender_passed_to_checks(self):
        """Sender parameter is forwarded to run_all_checks."""
        from classifier import classify_message

        with patch("classifier.run_all_checks", return_value={"decision": "hold", "reason": "test"}) as mock_checks:
            with patch("classifier.AsyncAnthropic"):
                await classify_message("Subject", "Body", sender="alice@example.com")
                mock_checks.assert_called_once_with("Subject", "Body", sender="alice@example.com")

    @pytest.mark.asyncio
    async def test_fenced_json_approve(self):
        """API response wrapped in markdown fences is parsed correctly (approve)."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='```json\n{"decision": "approve", "reason": "On-topic"}\n```')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Forecast discussion", "I think 30%")
                assert result["decision"] == "approve"
                assert result["reason"] == "On-topic"

    @pytest.mark.asyncio
    async def test_fenced_json_hold(self):
        """API response wrapped in markdown fences is parsed correctly (hold)."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='```json\n{"decision": "hold", "reason": "Off-topic"}\n```')]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Re: forecast", "Today's xkcd")
                assert result["decision"] == "hold"
                assert result["reason"] == "Off-topic"

    @pytest.mark.asyncio
    async def test_fallback_parse_hold(self):
        """Non-JSON response containing 'hold' is parsed as hold."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I think we should HOLD this message")]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Subject", "Body")
                assert result["decision"] == "hold"

    @pytest.mark.asyncio
    async def test_fallback_parse_approve(self):
        """Non-JSON response without 'hold' is parsed as approve."""
        from classifier import classify_message

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This looks fine to approve")]
        mock_client.messages.create.return_value = mock_response

        with patch("classifier.run_all_checks", return_value=None):
            with patch("classifier.AsyncAnthropic", return_value=mock_client):
                result = await classify_message("Subject", "Body")
                assert result["decision"] == "approve"
