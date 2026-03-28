# Message Classification

Two-layer architecture for classifying pending Google Groups messages as approve or hold.

## Architecture

### Layer 1 — Pattern-Matching Checks (`checks/`)

Pure Python functions that catch obvious violations without an API call. Each check returns `{"decision": "hold", "reason": "..."}` on match or `None` on pass-through.

Checks run in order — the first hit wins:

1. **`no_substance`** — Short reaction messages: "+1", "thanks", "I agree", "me too", "lol", etc. Messages over 20 words are assumed to have substance even if they start with a reaction word.
2. **`url_only`** — Messages with at least one URL and 5 or fewer non-URL words.
3. **`spam`** — Obvious spam keyword patterns: crypto promotion, "click here", SEO services, etc. Checked against combined subject + body.

### Layer 2 — LLM Classification (`classifier.py`)

When all checks pass, the message reaches the Anthropic API with a prompt tuned for judgment calls:

- **Hostile/mean-spirited** — aggressive tone, insults
- **Personal attacks** — attacking a person rather than their ideas
- **Bigotry** — racist, sexist, discriminatory content
- **Off-topic chatter** — does not advance a forecasting discussion, even if tangentially related to the thread subject

The prompt includes a bright-line test: "does the message make, discuss, question, or provide evidence for a prediction or forecast?" This catches messages like casual xkcd links in forecasting threads that are tangentially related but add nothing to the discussion.

The prompt deliberately avoids approval bias — no "99% of messages are fine" framing.

## How to Add a New Check

1. Create `checks/your_check.py` with a function `check_your_check(body)` (or `check_your_check(subject, body)` if subject is needed).
2. Return `{"decision": "hold", "reason": "..."}` on match, `None` on pass-through.
3. Keep it pure: no async, no API calls, no imports from this project.
4. Add the import and call to `checks/__init__.py` in `run_all_checks()`, in the desired priority order.
5. Write tests in `tests/test_checks.py` following the existing class-based pattern.
6. Run `bin/ci` to verify 100% coverage.

## Prompt Rationale

**Why no "99% are fine":** The original prompt said "99% of messages are fine" and "When in doubt, APPROVE." This framing biased the model toward approval for borderline cases — exactly the messages that need the most careful judgment.

**Why "even if tangentially related":** The original off-topic rule held messages with "nothing to do with the subject line." This passed messages that were tangentially related to the thread topic but contributed nothing to a forecasting discussion. The tightened rule catches chatter that relates to the subject but doesn't make, discuss, or provide evidence for a prediction.

**Why "When genuinely uncertain, APPROVE":** We still fail open — the model should approve when it truly can't tell. The distinction from the old prompt is removing the thumb on the scale. "Genuinely uncertain" is a higher bar than "in doubt."

## `classify_message()` Contract

```python
async def classify_message(
    subject: str,
    body: str,
    sender: str = "",
    api_key: str | None = None,
) -> dict:
```

**Parameters:**
- `subject` — Message subject line
- `body` — Message body (pre-trimmed by caller)
- `sender` — Sender email address (passed to checks, included in LLM context)
- `api_key` — Anthropic API key. Falls back to `ANTHROPIC_API_KEY` env var.

**Returns:** `{"decision": "approve" | "hold", "reason": "..."}` — always. Fails open on any exception (returns approve).

**Behavior:**
1. Runs `run_all_checks(subject, body, sender=sender)`. If a check returns a verdict, returns it immediately — no API call.
2. Creates a fresh `AsyncAnthropic` client and calls the API with the tightened prompt.
3. Retries on 500/529 errors (up to 3 attempts with exponential backoff).
4. Parses JSON response. Falls back to text matching ("hold" in response → hold, otherwise approve).
5. On any exception (network, parse, timeout), returns `{"decision": "approve", "reason": "(classification failed: ...)"}`.
