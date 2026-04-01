"""Two-layer message classifier for Google Groups moderation.

Layer 1: Pattern-matching checks (checks/ package) for obvious violations.
Layer 2: LLM classification via Anthropic API for judgment calls.

Standalone module — imports only checks/ from this project. Has its own
AsyncAnthropic client and retry logic. Fails open on all exceptions.
"""

import asyncio
import json
import logging
import os
import re

from anthropic import AsyncAnthropic, APIStatusError
from openai import AsyncOpenAI

from checks import run_all_checks
from config import DEFAULT_MODEL, resolve_model

log = logging.getLogger("classifier")

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

SYSTEM_PROMPT = """\
You are a Google Groups message moderator for a forecasting/predictions discussion group.

Your job is to classify pending messages as either APPROVE or HOLD.

HOLD messages that violate any of these rules:

1. **Hostile or mean-spirited** — aggressive tone, ranting, insults
2. **Personal attacks** — attacking a person rather than their ideas (public figures included)
3. **Bigotry** — racist, sexist, or discriminatory content
4. **Off-topic chatter** — does not advance a forecasting discussion, even if tangentially related to the thread subject

Bright-line test for off-topic: does the message make, discuss, question, or provide evidence for a prediction or forecast? Sharing a funny link or casual remark in a forecasting thread is NOT on-topic.

When genuinely uncertain, APPROVE.

Respond with EXACTLY this JSON format (no markdown, no extra text):
{"decision": "approve" or "hold", "reason": "brief 5-10 word reason"}
"""


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from API response text."""
    text = re.sub(r"^```(?:json|JSON)?[ \t]*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text


async def classify_message(
    subject: str,
    body: str,
    sender: str = "",
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Classify a message as approve or hold.

    Runs Layer 1 checks first. If a check catches the message, returns
    immediately without an API call. Otherwise, calls the Anthropic API
    with a tightened prompt for LLM judgment.

    Always returns {"decision": "approve"|"hold", "reason": "..."}.
    Fails open — returns approve on any exception.
    """
    # Layer 1: pattern-matching checks
    check_result = run_all_checks(subject, body, sender=sender)
    if check_result is not None:
        return check_result

    # Layer 2: LLM classification
    try:
        user_content = f"Subject: {subject}\nFrom: {sender}\n\nMessage body:\n{body}"
        if model == "slm":
            client = AsyncOpenAI(base_url="https://litellm.neurometric.ai/v1", api_key=os.environ.get("LITELLM_API_KEY", ""))
            response = await client.chat.completions.create(model=resolve_model(model), max_tokens=150, 
                                messages=[{"role": "system", "content": SYSTEM_PROMPT},{"role": "user", "content": user_content}])
            result_text = _strip_markdown_fences(response.choices[0].message.content.strip())
        else:
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            client = AsyncAnthropic(api_key=key)

            response = await _api_call_with_retry(
                client,
                model=resolve_model(model),
                max_tokens=150,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            result_text = _strip_markdown_fences(response.content[0].text.strip())

        try:
            result = json.loads(result_text)
            return {
                "decision": result.get("decision", "approve"),
                "reason": result.get("reason", ""),
            }
        except json.JSONDecodeError:
            # Fallback parsing
            lower = result_text.lower()
            if "hold" in lower:
                return {"decision": "hold", "reason": result_text[:80]}
            return {"decision": "approve", "reason": result_text[:80]}

    except Exception as e:
        log.debug(f"Classification failed: {type(e).__name__}: {e}")
        return {"decision": "approve", "reason": f"(classification failed: {type(e).__name__})"}


async def _api_call_with_retry(client, **kwargs):
    """Call the Anthropic API with retry on 500/529 errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return await client.messages.create(**kwargs)
        except APIStatusError as e:
            if e.status_code in (500, 529) and attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (attempt + 1)
                log.debug(f"API {e.status_code}, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
            else:
                raise
