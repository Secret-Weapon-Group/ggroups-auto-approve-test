"""AI message analyzer using Claude for approve/hold recommendations."""

import asyncio
import logging
import re
import sys
from anthropic import AsyncAnthropic, APIStatusError

# Google Groups pages can produce huge scraped text that triggers
# recursion limits in regex or JSON parsing
sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))

import config
from scraper import PendingMessage

log = logging.getLogger("analyzer")

client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


async def _api_call_with_retry(**kwargs):
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


def trim_for_analysis(body: str) -> str:
    """Trim message body for AI analysis.

    Removes:
    - Email headers (From:, To:, Date:, Subject:, Cc:, etc.)
    - Trailing quoted previous messages (bottom-quoted replies)
    - Signature blocks ("--" separator and below)
    - "On ... wrote:" attribution lines preceding bottom quotes

    Preserves:
    - Inline responses (interleaved > quotes with replies) since
      the context is needed to detect snarky/mean responses
    """
    if not body:
        return body
    try:
        return _trim_for_analysis_impl(body)
    except Exception as e:
        log.debug(f"trim_for_analysis failed: {e}")
        return body


def _trim_for_analysis_impl(body: str) -> str:
    """Inner implementation of trim_for_analysis."""

    lines = body.split("\n")

    # Strip leading email headers
    start = 0
    header_re = re.compile(
        r"^(From|To|Cc|Bcc|Date|Subject|Reply-To|Message-ID|"
        r"Content-Type|MIME-Version|Delivered-To|Received|"
        r"Return-Path|X-\S+)\s*:", re.IGNORECASE
    )
    while start < len(lines):
        line = lines[start].strip()
        if not line:
            start += 1  # skip blank lines between headers
            continue
        if header_re.match(line):
            start += 1
            # skip continuation lines (indented)
            while start < len(lines) and lines[start].startswith((" ", "\t")):
                start += 1
            continue
        break
    lines = lines[start:]

    # Remove signature block ("-- " followed by signature lines at end)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() in ("--", "-- "):
            lines = lines[:i]
            break

    # Detect and trim trailing bottom-quoted block.
    # A bottom-quote is a contiguous block of ">" lines at the end,
    # possibly preceded by an "On ... wrote:" attribution line.
    # But if there are non-quoted reply lines interleaved with quoted lines,
    # that's an inline reply — keep it all.
    #
    # Strategy: walk backwards from end. If we find a contiguous block of
    # quoted lines (and blank lines) that reaches back to an attribution
    # or the start of the quote block, trim it. Stop if we hit a non-blank
    # non-quoted line (that means it's an inline reply).
    end = len(lines)
    i = end - 1

    # Skip trailing blank lines
    while i >= 0 and not lines[i].strip():
        i -= 1

    # Walk back through quoted lines
    quote_start = None
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith(">"):
            quote_start = i
            i -= 1
        elif not stripped:
            # blank line inside quote block, keep going
            i -= 1
        else:
            break

    if quote_start is not None:
        # Check if the line before the quote block is an attribution
        # like "On Mon, Jan 1, 2026, John <john@example.com> wrote:"
        attr_line = i
        if attr_line >= 0:
            s = lines[attr_line].strip()
            if re.match(r"^On .{1,500} wrote:\s*$", s, re.IGNORECASE):
                quote_start = attr_line

        # Only trim if the quote block is at the bottom (no reply lines after it)
        # Check there's no non-quoted content between quote_start and end
        has_inline_reply = False
        for j in range(quote_start, end):
            stripped = lines[j].strip()
            if stripped and not stripped.startswith(">"):
                # Check if it's the attribution line
                if j == attr_line:
                    continue
                has_inline_reply = True
                break

        if not has_inline_reply:
            lines = lines[:quote_start]

    # Strip trailing blank lines
    while lines and not lines[-1].strip():
        lines.pop()

    result = "\n".join(lines).strip()
    return result if result else body  # fall back to original if trimming removed everything

SYSTEM_PROMPT = """\
You are a Google Groups message moderator for a forecasting/predictions discussion group.

Your job is to classify pending messages as either APPROVE or HOLD.

99% of messages are fine. You should HOLD only messages that clearly violate these rules:

1. **Angry or mean-spirited** — hostile tone, ranting, aggressive language
2. **Personal attacks** — against anyone, including public figures (criticism of ideas is fine; attacking the person is not)
3. **Racist, sexist, or discriminatory** — any bigotry or hate speech
4. **No new information** — messages that are just "+1", "I agree", "This is wrong", "Thanks", simple agreement/disagreement without adding substance
5. **Off-topic** — content that has nothing to do with the subject line or forecasting/predictions in general

When in doubt, APPROVE. The group is about open discussion of forecasts and predictions.

Respond with EXACTLY this JSON format (no markdown, no extra text):
{"decision": "approve" or "hold", "reason": "brief 5-10 word reason"}
"""

SUMMARY_PROMPT = """\
Summarize this message in 2-3 concise sentences. Focus on the key points and any predictions or forecasts mentioned.
"""


async def analyze_message(msg: PendingMessage) -> PendingMessage:
    """Analyze a single message and set its AI recommendation."""
    try:
        trimmed = trim_for_analysis(msg.body) if msg.body else msg.snippet
        # Cap body size to avoid blowing up the API call (Google Groups
        # expansion can include huge footers/subscription text)
        if len(trimmed) > 8000:
            log.debug(f"Trimming body from {len(trimmed)} to 8000 chars for API")
            trimmed = trimmed[:8000] + "\n\n[... truncated]"
        user_content = f"Subject: {msg.subject}\nFrom: {msg.sender}\n\nMessage body:\n{trimmed}"

        response = await _api_call_with_retry(
            model="claude-opus-4-0",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        result_text = response.content[0].text.strip()

        # Parse JSON response
        import json
        try:
            result = json.loads(result_text)
            msg.ai_recommendation = result.get("decision", "approve")
            msg.ai_reason = result.get("reason", "")
        except json.JSONDecodeError:
            # Fallback parsing
            lower = result_text.lower()
            if "hold" in lower:
                msg.ai_recommendation = "hold"
                msg.ai_reason = result_text[:80]
            else:
                msg.ai_recommendation = "approve"
                msg.ai_reason = result_text[:80]

        # Set initial status based on AI recommendation
        msg.status = "hold" if msg.ai_recommendation == "hold" else "ok"

    except RecursionError:
        log.debug(f"RecursionError analyzing '{msg.subject}', body size={len(msg.body or '')}")
        msg.ai_recommendation = "approve"
        msg.ai_reason = "(analysis failed: recursion limit)"
        msg.status = "ok"
    except Exception as e:
        log.debug(f"Error analyzing '{msg.subject}': {type(e).__name__}: {e}")
        msg.ai_recommendation = "approve"
        msg.ai_reason = f"(analysis failed: {type(e).__name__})"
        msg.status = "ok"

    return msg


async def summarize_message(msg: PendingMessage) -> str:
    """Generate a summary for a long message (>20 lines)."""
    trimmed = trim_for_analysis(msg.body) if msg.body else msg.snippet
    if len(trimmed) > 8000:
        trimmed = trimmed[:8000] + "\n\n[... truncated]"
    lines = trimmed.split("\n")
    if len(lines) <= 20:
        return ""

    try:
        response = await _api_call_with_retry(
            model="claude-opus-4-0",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"{SUMMARY_PROMPT}\n\n---\nSubject: {msg.subject}\n\n{trimmed}",
            }],
        )
        msg.ai_summary = response.content[0].text.strip()
        return msg.ai_summary
    except Exception:
        return ""


async def analyze_all(messages: list[PendingMessage], on_progress=None) -> list[PendingMessage]:
    """Analyze all messages concurrently with progress tracking."""
    if not messages:
        return messages

    total = len(messages)
    completed = 0

    async def classify_with_progress(msg):
        nonlocal completed
        await analyze_message(msg)
        completed += 1
        if on_progress:
            on_progress(completed, total, "classify", msg)

    # Run classification concurrently
    classify_tasks = [classify_with_progress(msg) for msg in messages]
    await asyncio.gather(*classify_tasks)

    # Generate summaries for long messages
    long_msgs = [msg for msg in messages if msg.body and len(msg.body.split("\n")) > 20]
    if long_msgs:
        summary_done = 0

        async def summarize_with_progress(msg):
            nonlocal summary_done
            await summarize_message(msg)
            summary_done += 1
            if on_progress:
                on_progress(summary_done, len(long_msgs), "summarize", msg)

        await asyncio.gather(*[summarize_with_progress(msg) for msg in long_msgs])

    return messages
