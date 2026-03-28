"""Check for messages with no substantive content."""

import re

# Short reaction patterns — case-insensitive
_REACTIONS = [
    r"^\+1$",
    r"^thanks[!.]*$",
    r"^thank you[!.]*$",
    r"^i agree[!.]*$",
    r"^me too[!.]*$",
    r"^same[!.]*$",
    r"^lol[!.]*$",
    r"^haha[!.]*$",
    r"^this[!.]*$",
    r"^yes[!.]*$",
    r"^no[!.]*$",
    r"^this is wrong[!.]*$",
    r"^exactly[!.]*$",
    r"^agreed[!.]*$",
    r"^nice[!.]*$",
    r"^great[!.]*$",
    r"^interesting[!.]*$",
    r"^wow[!.]*$",
]

_REACTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _REACTIONS]

# Messages under this word count are checked against reaction patterns.
# Longer messages are assumed to have substance even if they start with
# a reaction word (e.g. "Thanks, but here's my forecast...").
_WORD_THRESHOLD = 20


def check_no_substance(body: str) -> dict | None:
    """Hold short messages that add no substance to the discussion.

    Returns {"decision": "hold", "reason": "..."} if the message is
    a low-substance reaction, or None if it passes through.
    """
    stripped = body.strip()
    if not stripped:
        return {"decision": "hold", "reason": "Empty or whitespace-only message"}

    words = stripped.split()
    if len(words) > _WORD_THRESHOLD:
        return None

    for pattern in _REACTION_PATTERNS:
        if pattern.match(stripped):
            return {"decision": "hold", "reason": f"Low-substance reaction: {stripped[:40]}"}

    return None
