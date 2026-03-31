"""Tests for the full classification pipeline using realistic email corpus.

Tests validate: (a) Layer 1 checks correctly pre-filter obvious cases,
(b) messages that pass checks have correct prompt construction for the classifier.
"""

import pytest
from unittest.mock import AsyncMock, patch

from checks import run_all_checks
from tests.email_corpus import CORPUS


# ── Layer 1 pre-filtering ────────────────────────────────────────

def _layer1_caught():
    """Corpus entries expected to be caught by Layer 1 pattern checks."""
    return [c for c in CORPUS if c.expected_decision == "hold" and c.reason_substr]


def _layer1_pass():
    """Corpus entries expected to pass Layer 1 and reach the LLM."""
    return [c for c in CORPUS if "classifier" in c.tags and not c.reason_substr]


class TestLayer1PreFilter:
    """Verify Layer 1 checks catch obvious cases from the corpus."""

    @pytest.mark.parametrize(
        "case",
        _layer1_caught(),
        ids=[c.description for c in _layer1_caught()],
    )
    def test_layer1_catches_obvious_hold(self, case):
        """Layer 1 catches this message — no LLM call needed."""
        result = run_all_checks(case.subject, case.body, sender=case.sender)
        assert result is not None, f"Expected Layer 1 to catch: {case.description}"
        assert result["decision"] == "hold"
        assert case.reason_substr in result["reason"]

    @pytest.mark.parametrize(
        "case",
        _layer1_pass(),
        ids=[c.description for c in _layer1_pass()],
    )
    def test_layer1_passes_to_classifier(self, case):
        """Layer 1 does not catch this message — it reaches the LLM."""
        result = run_all_checks(case.subject, case.body, sender=case.sender)
        assert result is None, f"Expected Layer 1 to pass: {case.description}"


# ── Prompt construction ──────────────────────────────────────────

class TestPromptConstruction:
    """Verify classify_message constructs the correct prompt for LLM entries."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "case",
        _layer1_pass(),
        ids=[c.description for c in _layer1_pass()],
    )
    async def test_prompt_includes_message_fields(self, case):
        """classify_message sends subject, sender, and body to the LLM."""
        mock_response = AsyncMock()
        mock_response.content = [
            AsyncMock(text='{"decision": "approve", "reason": "On-topic forecast"}')
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("classifier.AsyncAnthropic", return_value=mock_client):
            from classifier import classify_message
            await classify_message(
                subject=case.subject,
                body=case.body,
                sender=case.sender,
            )

        # Verify the API was called (message passed Layer 1)
        mock_client.messages.create.assert_awaited_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]

        # Verify prompt includes the message fields
        assert case.subject in user_content
        assert case.sender in user_content
        assert case.body in user_content
        # Verify system prompt is set
        assert "system" in call_kwargs
        assert "moderator" in call_kwargs["system"].lower()
