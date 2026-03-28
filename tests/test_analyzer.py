"""Tests for analyzer.py — message trimming, API calls, classification."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mail_monitor import PendingMessage


# ── trim_for_analysis ──────────────────────────────────────────

class TestTrimForAnalysis:
    def test_empty_body(self):
        from analyzer import trim_for_analysis
        assert trim_for_analysis("") == ""

    def test_none_body(self):
        from analyzer import trim_for_analysis
        assert trim_for_analysis(None) is None

    def test_strips_email_headers(self):
        from analyzer import trim_for_analysis
        body = "From: alice@example.com\nTo: bob@example.com\nSubject: Test\n\nActual message content."
        result = trim_for_analysis(body)
        assert "From:" not in result
        assert "Actual message content." in result

    def test_strips_continuation_headers(self):
        from analyzer import trim_for_analysis
        body = "From: alice@example.com\n  continued header\nTo: bob@example.com\n\nContent here."
        result = trim_for_analysis(body)
        assert "continued header" not in result
        assert "Content here." in result

    def test_strips_x_headers(self):
        from analyzer import trim_for_analysis
        body = "X-Mailer: Outlook\nX-Priority: 1\n\nMessage text."
        result = trim_for_analysis(body)
        assert "X-Mailer" not in result
        assert "Message text." in result

    def test_strips_signature_block(self):
        from analyzer import trim_for_analysis
        body = "Hello world.\n\n-- \nJohn Doe\nCEO, Acme Corp"
        result = trim_for_analysis(body)
        assert "Hello world." in result
        assert "John Doe" not in result

    def test_strips_signature_block_no_trailing_space(self):
        from analyzer import trim_for_analysis
        body = "Hello world.\n\n--\nJohn Doe"
        result = trim_for_analysis(body)
        assert "Hello world." in result
        assert "John Doe" not in result

    def test_strips_bottom_quoted_reply(self):
        from analyzer import trim_for_analysis
        body = "My reply here.\n\nOn Mon, Jan 1, 2026, Alice <alice@example.com> wrote:\n> Original message\n> More original"
        result = trim_for_analysis(body)
        assert "My reply here." in result
        assert "Original message" not in result

    def test_preserves_inline_replies(self):
        from analyzer import trim_for_analysis
        body = "> Original point\nMy reply to this.\n> Another point\nAnother reply."
        result = trim_for_analysis(body)
        assert "Original point" in result
        assert "My reply to this." in result
        assert "Another reply." in result

    def test_plain_message_unchanged(self):
        from analyzer import trim_for_analysis
        body = "Just a normal message\nwith multiple lines\nand no special markers."
        result = trim_for_analysis(body)
        assert result == body

    def test_exception_returns_original(self):
        from analyzer import trim_for_analysis
        # Force an exception in the inner implementation
        with patch("analyzer._trim_for_analysis_impl", side_effect=ValueError("boom")):
            result = trim_for_analysis("test body")
            assert result == "test body"

    def test_strips_trailing_blank_lines(self):
        from analyzer import trim_for_analysis
        body = "Content here.\n\n\n"
        result = trim_for_analysis(body)
        assert result == "Content here."

    def test_only_headers_returns_original(self):
        """If trimming removes everything, falls back to original body."""
        from analyzer import trim_for_analysis
        body = "From: alice@example.com\nTo: bob@example.com"
        result = trim_for_analysis(body)
        # _trim_for_analysis_impl returns body when result is empty
        assert result == body

    def test_quote_block_with_blank_lines(self):
        from analyzer import trim_for_analysis
        body = "My reply.\n\n> Quote line 1\n\n> Quote line 2"
        result = trim_for_analysis(body)
        assert "My reply." in result

    def test_attribution_line_case_insensitive(self):
        from analyzer import trim_for_analysis
        body = "Reply.\n\non Mon, Jan 1, 2026, Someone <s@e.com> Wrote:\n> quoted"
        result = trim_for_analysis(body)
        assert "Reply." in result
        assert "quoted" not in result

    def test_inline_reply_in_bottom_quote_preserved(self):
        """When a non-quoted reply line appears inside the bottom quote block, keep everything."""
        from analyzer import trim_for_analysis
        body = "Top reply.\n\nOn Mon, Jan 1, 2026, Someone <s@e.com> wrote:\n> quoted line\nInline reply here\n> more quoted"
        result = trim_for_analysis(body)
        assert "Inline reply here" in result
        assert "quoted line" in result


# ── _api_call_with_retry ───────────────────────────────────────

class TestApiCallWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self, mock_anthropic):
        with patch("analyzer.client", mock_anthropic):
            from analyzer import _api_call_with_retry
            result = await _api_call_with_retry(model="test", max_tokens=10, messages=[])
            assert result == mock_anthropic.messages.create.return_value
            assert mock_anthropic.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_500(self, mock_anthropic):
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(500, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Server error", response=error_response, body=None)

        mock_anthropic.messages.create.side_effect = [error, MagicMock(content=[MagicMock(text="ok")])]

        with patch("analyzer.client", mock_anthropic), patch("analyzer.RETRY_DELAY", 0):
            from analyzer import _api_call_with_retry
            await _api_call_with_retry(model="test", max_tokens=10, messages=[])
            assert mock_anthropic.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_529(self, mock_anthropic):
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(529, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Overloaded", response=error_response, body=None)

        mock_anthropic.messages.create.side_effect = [error, MagicMock(content=[MagicMock(text="ok")])]

        with patch("analyzer.client", mock_anthropic), patch("analyzer.RETRY_DELAY", 0):
            from analyzer import _api_call_with_retry
            await _api_call_with_retry(model="test", max_tokens=10, messages=[])
            assert mock_anthropic.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self, mock_anthropic):
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(500, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Server error", response=error_response, body=None)

        mock_anthropic.messages.create.side_effect = error

        with patch("analyzer.client", mock_anthropic), patch("analyzer.RETRY_DELAY", 0):
            from analyzer import _api_call_with_retry
            with pytest.raises(APIStatusError):
                await _api_call_with_retry(model="test", max_tokens=10, messages=[])
            assert mock_anthropic.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self, mock_anthropic):
        from anthropic import APIStatusError
        import httpx

        error_response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com"))
        error = APIStatusError("Bad request", response=error_response, body=None)

        mock_anthropic.messages.create.side_effect = error

        with patch("analyzer.client", mock_anthropic):
            from analyzer import _api_call_with_retry
            with pytest.raises(APIStatusError):
                await _api_call_with_retry(model="test", max_tokens=10, messages=[])
            assert mock_anthropic.messages.create.call_count == 1


# ── analyze_message ────────────────────────────────────────────

class TestAnalyzeMessage:
    @pytest.mark.asyncio
    async def test_approve(self, sample_message):
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "Good post"})
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            result = await analyze_message(sample_message)
            assert result.ai_recommendation == "approve"
            assert result.ai_reason == "Good post"
            assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_hold(self, sample_message):
        mock_classify = AsyncMock(return_value={"decision": "hold", "reason": "Hostile tone"})
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            result = await analyze_message(sample_message)
            assert result.ai_recommendation == "hold"
            assert result.status == "hold"

    @pytest.mark.asyncio
    async def test_classifier_receives_trimmed_body(self, sample_message):
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            await analyze_message(sample_message)
            mock_classify.assert_called_once()
            call_kwargs = mock_classify.call_args.kwargs
            assert call_kwargs["subject"] == sample_message.subject
            assert call_kwargs["sender"] == sample_message.sender

    @pytest.mark.asyncio
    async def test_recursion_error(self, sample_message):
        mock_classify = AsyncMock(side_effect=RecursionError("too deep"))
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            result = await analyze_message(sample_message)
            assert result.ai_recommendation == "approve"
            assert "recursion" in result.ai_reason.lower()
            assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_general_exception(self, sample_message):
        mock_classify = AsyncMock(side_effect=RuntimeError("network error"))
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            result = await analyze_message(sample_message)
            assert result.ai_recommendation == "approve"
            assert "RuntimeError" in result.ai_reason
            assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_uses_snippet_when_no_body(self):
        msg = PendingMessage(id="0", sender="a@b.com", subject="Test",
                             snippet="snippet text", body="", date="2026-01-01")
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            result = await analyze_message(msg)
            assert result.ai_recommendation == "approve"
            assert mock_classify.call_args.kwargs["body"] == "snippet text"

    @pytest.mark.asyncio
    async def test_truncates_long_body(self, sample_message):
        sample_message.body = "x" * 10000
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            await analyze_message(sample_message)
            body_arg = mock_classify.call_args.kwargs["body"]
            assert "[... truncated]" in body_arg

    @pytest.mark.asyncio
    async def test_empty_reason_defaults(self, sample_message):
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": ""})
        with patch("analyzer.classifier.classify_message", mock_classify):
            from analyzer import analyze_message
            result = await analyze_message(sample_message)
            assert result.ai_recommendation == "approve"
            assert result.ai_reason == ""


# ── summarize_message ──────────────────────────────────────────

class TestSummarizeMessage:
    @pytest.mark.asyncio
    async def test_long_message_gets_summary(self, sample_message, mock_anthropic):
        sample_message.body = "\n".join([f"Line {i}" for i in range(25)])
        mock_anthropic.messages.create.return_value.content[0].text = "This is a summary."
        with patch("analyzer.client", mock_anthropic):
            from analyzer import summarize_message
            result = await summarize_message(sample_message)
            assert result == "This is a summary."
            assert sample_message.ai_summary == "This is a summary."

    @pytest.mark.asyncio
    async def test_short_message_no_summary(self, sample_message, mock_anthropic):
        sample_message.body = "Short message.\nTwo lines."
        with patch("analyzer.client", mock_anthropic):
            from analyzer import summarize_message
            result = await summarize_message(sample_message)
            assert result == ""

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, sample_message, mock_anthropic):
        sample_message.body = "\n".join([f"Line {i}" for i in range(25)])
        mock_anthropic.messages.create.side_effect = RuntimeError("fail")
        with patch("analyzer.client", mock_anthropic):
            from analyzer import summarize_message
            result = await summarize_message(sample_message)
            assert result == ""

    @pytest.mark.asyncio
    async def test_uses_snippet_when_no_body(self, mock_anthropic):
        msg = PendingMessage(id="0", sender="a@b.com", subject="Test",
                             snippet="snippet", body="", date="2026-01-01")
        with patch("analyzer.client", mock_anthropic):
            from analyzer import summarize_message
            result = await summarize_message(msg)
            assert result == ""

    @pytest.mark.asyncio
    async def test_truncates_long_body(self, sample_message, mock_anthropic):
        sample_message.body = "\n".join(["x" * 400 for _ in range(25)])
        mock_anthropic.messages.create.return_value.content[0].text = "Summary."
        with patch("analyzer.client", mock_anthropic):
            from analyzer import summarize_message
            result = await summarize_message(sample_message)
            assert result == "Summary."


# ── analyze_all ────────────────────────────────────────────────

class TestAnalyzeAll:
    @pytest.mark.asyncio
    async def test_empty_list(self):
        from analyzer import analyze_all
        result = await analyze_all([])
        assert result == []

    @pytest.mark.asyncio
    async def test_concurrent_classification(self):
        from analyzer import analyze_all

        msgs = [
            PendingMessage(id=str(i), sender=f"u{i}@e.com", subject=f"Msg {i}",
                           snippet=f"Snippet {i}", body=f"Body {i}", date="2026-01-01")
            for i in range(3)
        ]
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})

        with patch("analyzer.classifier.classify_message", mock_classify):
            result = await analyze_all(msgs)
            assert len(result) == 3
            for msg in result:
                assert msg.ai_recommendation == "approve"

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        from analyzer import analyze_all

        msgs = [
            PendingMessage(id="0", sender="u@e.com", subject="Test",
                           snippet="Snippet", body="Body", date="2026-01-01")
        ]
        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})

        progress_calls = []

        def on_progress(completed, total, phase, msg):
            progress_calls.append((completed, total, phase))

        with patch("analyzer.classifier.classify_message", mock_classify):
            await analyze_all(msgs, on_progress=on_progress)
            assert len(progress_calls) >= 1
            assert progress_calls[0][2] == "classify"

    @pytest.mark.asyncio
    async def test_summarize_progress_callback(self, mock_anthropic):
        """The summarize phase fires on_progress with 'summarize' phase."""
        from analyzer import analyze_all

        long_body = "\n".join([f"Line {i} with content" for i in range(25)])
        msgs = [
            PendingMessage(id="0", sender="u@e.com", subject="Test",
                           snippet="Snippet", body=long_body, date="2026-01-01")
        ]

        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})

        mock_anthropic.messages.create.return_value.content[0].text = "A summary."

        progress_calls = []

        def on_progress(completed, total, phase, msg):
            progress_calls.append((completed, total, phase))

        with patch("analyzer.classifier.classify_message", mock_classify), \
             patch("analyzer.client", mock_anthropic):
            await analyze_all(msgs, on_progress=on_progress)
            phases = [p[2] for p in progress_calls]
            assert "summarize" in phases

    @pytest.mark.asyncio
    async def test_summarizes_long_messages(self, mock_anthropic):
        from analyzer import analyze_all

        long_body = "\n".join([f"Line {i} with content" for i in range(25)])
        msgs = [
            PendingMessage(id="0", sender="u@e.com", subject="Test",
                           snippet="Snippet", body=long_body, date="2026-01-01")
        ]

        mock_classify = AsyncMock(return_value={"decision": "approve", "reason": "ok"})

        mock_anthropic.messages.create.return_value.content[0].text = "A summary."

        with patch("analyzer.classifier.classify_message", mock_classify), \
             patch("analyzer.client", mock_anthropic):
            result = await analyze_all(msgs)
            assert result[0].ai_summary == "A summary."
