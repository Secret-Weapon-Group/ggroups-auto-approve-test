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

    # ── realistic edge-case corpus (Task 2) ──────────────────────

    def test_full_realistic_email(self):
        """Headers + body + signature + bottom-quoted reply — strips all non-body content."""
        from analyzer import trim_for_analysis
        body = (
            "From: alice@example.com\n"
            "To: forecast-chat@googlegroups.com\n"
            "Subject: Re: Q3 GDP forecast\n"
            "Date: Mon, 15 Mar 2026 10:30:00 -0700\n"
            "\n"
            "I think the probability of recession in Q3 is around 25%.\n"
            "Leading indicators from PMI and jobless claims both suggest\n"
            "slowing growth, but consumer spending remains resilient.\n"
            "\n"
            "-- \n"
            "Alice Johnson\n"
            "Senior Economist, Acme Research\n"
            "\n"
            "On Sun, 14 Mar 2026, Bob <bob@example.com> wrote:\n"
            "> What's everyone's take on Q3? The latest PMI numbers\n"
            "> look concerning but I'm not sure they're predictive.\n"
        )
        result = trim_for_analysis(body)
        assert "From:" not in result
        assert "I think the probability" in result
        assert "consumer spending remains resilient" in result
        assert "Alice Johnson" not in result
        assert "What's everyone's take" not in result

    def test_multi_level_inline_reply_thread(self):
        """Interleaved > and >> quotes with replies preserved as inline discussion."""
        from analyzer import trim_for_analysis
        body = (
            "> Alice wrote: I think recession odds are 30%\n"
            "I disagree — the labor market is too strong.\n"
            "\n"
            ">> Bob originally said: PMI is dropping fast\n"
            "> Alice replied: But services PMI is stable\n"
            "Both of you are ignoring the yield curve inversion.\n"
        )
        result = trim_for_analysis(body)
        assert "I disagree" in result
        assert "labor market is too strong" in result
        assert "Both of you are ignoring" in result
        assert "Alice wrote" in result

    def test_forwarded_message_preserved(self):
        """Forwarded message separator is not a header — body content preserved."""
        from analyzer import trim_for_analysis
        body = (
            "FYI, relevant to our recession forecast discussion.\n"
            "\n"
            "---------- Forwarded message ----------\n"
            "From: economist@reuters.com\n"
            "Date: Fri, 12 Mar 2026\n"
            "Subject: Q3 outlook report\n"
            "\n"
            "Our models show a 22% chance of recession by Q3.\n"
        )
        result = trim_for_analysis(body)
        assert "FYI, relevant" in result
        # Forwarded separator is preserved (not a recognized header)
        assert "Forwarded message" in result
        assert "22% chance of recession" in result

    def test_very_long_email_signature_near_middle(self):
        """Signature marker near the middle strips from that point (known limitation)."""
        from analyzer import trim_for_analysis
        top_lines = [f"Analysis point {i}: data looks stable." for i in range(1, 51)]
        bottom_lines = [f"Additional note {i}: more supporting data." for i in range(1, 51)]
        body = "\n".join(top_lines) + "\n\n-- \nDr. Smith\nChief Analyst\n\n" + "\n".join(bottom_lines)
        result = trim_for_analysis(body)
        assert "Analysis point 1" in result
        assert "Analysis point 50" in result
        # Everything after "-- " is treated as signature
        assert "Dr. Smith" not in result
        assert "Additional note 1" not in result

    def test_double_dash_in_body_text(self):
        """Bare '--' in body treated as signature marker (scans backward for last occurrence)."""
        from analyzer import trim_for_analysis
        body = (
            "The range is 20--30% based on historical data.\n"
            "\n"
            "My final estimate: 25% probability.\n"
        )
        result = trim_for_analysis(body)
        # No bare "-- " or "--" on its own line, so nothing stripped
        assert "20--30%" in result
        assert "My final estimate" in result

    def test_bottom_quote_without_attribution(self):
        """Bottom-quoted block without 'On ... wrote:' attribution is still trimmed."""
        from analyzer import trim_for_analysis
        body = (
            "I agree with the 30% estimate.\n"
            "\n"
            "> The latest PMI data suggests a slowdown.\n"
            "> Consumer confidence is also declining.\n"
            "> I'd put recession odds at 30%.\n"
        )
        result = trim_for_analysis(body)
        assert "I agree with the 30% estimate" in result
        assert "PMI data" not in result

    def test_multiple_bottom_quoted_sections(self):
        """Reply-to-a-reply: nested quoting treated as single bottom-quote block."""
        from analyzer import trim_for_analysis
        body = (
            "Good points from both of you.\n"
            "\n"
            "On Tue, 16 Mar 2026, Alice <alice@example.com> wrote:\n"
            "> I'm revising my estimate to 28%.\n"
            ">\n"
            "> On Mon, 15 Mar 2026, Bob <bob@example.com> wrote:\n"
            ">> The PMI numbers are really concerning.\n"
            ">> I think 35% is more realistic.\n"
        )
        result = trim_for_analysis(body)
        assert "Good points from both" in result
        assert "revising my estimate" not in result
        assert "PMI numbers" not in result

    def test_encoding_artifacts_preserved(self):
        """QP encoding artifacts in body text are preserved (not stripped by trimmer)."""
        from analyzer import trim_for_analysis
        body = (
            "The probability is=20around 25% based on current data.\n"
            "Temperature will be =3D 15=C2=B0C tomorrow.\n"
            "Full analysis at https://example.com/report?q=3Dforecast\n"
        )
        result = trim_for_analysis(body)
        assert "probability is=20around" in result
        assert "=3D 15" in result
        assert "q=3Dforecast" in result

    def test_all_quoted_text_preserved(self):
        """Body consisting entirely of quoted text is preserved (falls back to original)."""
        from analyzer import trim_for_analysis
        body = (
            "> First quoted line about the forecast.\n"
            "> Second quoted line with more data.\n"
            "> Third quoted line concluding analysis.\n"
        )
        result = trim_for_analysis(body)
        # Trimming would remove everything, so falls back to original
        assert "First quoted line" in result
        assert "Third quoted line" in result

    def test_realistic_google_groups_moderation_email(self):
        """Full Google Groups moderation notification format."""
        from analyzer import trim_for_analysis
        body = (
            "From: noreply@googlegroups.com\n"
            "Reply-To: forecast-chat+approve-abc123@googlegroups.com\n"
            "X-Google-Group-Id: abc123\n"
            "Content-Type: text/plain; charset=utf-8\n"
            "\n"
            "A message by alice@example.com requires your approval.\n"
            "\n"
            "From: alice@example.com\n"
            "Subject: My Q3 recession forecast\n"
            "\n"
            "I've been tracking the Sahm Rule indicator and it just hit 0.43.\n"
            "Combined with the inverted yield curve, I'm putting recession\n"
            "probability at 35% for the next 12 months.\n"
        )
        result = trim_for_analysis(body)
        # Outer headers stripped; inner "From:" also matches header pattern
        assert "noreply@googlegroups.com" not in result
        assert "X-Google-Group-Id" not in result
        # The inner message content should be preserved
        assert "Sahm Rule indicator" in result


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
