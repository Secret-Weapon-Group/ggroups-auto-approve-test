"""Check for obvious spam keyword patterns."""

import re

# Patterns that indicate spam — checked against combined subject + body
_SPAM_PATTERNS = [
    re.compile(r"\bbuy\s+(bitcoin|crypto|ethereum|nft)", re.IGNORECASE),
    re.compile(r"\bguaranteed\s+returns?\b", re.IGNORECASE),
    re.compile(r"\bclick\s+here\b", re.IGNORECASE),
    re.compile(r"\bact\s+now\b", re.IGNORECASE),
    re.compile(r"\blimited\s+time\s+offer\b", re.IGNORECASE),
    re.compile(r"\bmake\s+money\s+fast\b", re.IGNORECASE),
    re.compile(r"\bfree\s+(?:gift|prize|money)\b", re.IGNORECASE),
    re.compile(r"\bSEO\s+services?\b", re.IGNORECASE),
    re.compile(r"\bboost\s+your\s+(?:website|ranking|traffic)\b", re.IGNORECASE),
    re.compile(r"\bunsubscribe\s+(?:here|now|below)\b", re.IGNORECASE),
    re.compile(r"\bcongratulations[!,]?\s+you(?:'ve)?\s+(?:won|been\s+selected)\b", re.IGNORECASE),
]


def check_spam(subject: str, body: str) -> dict | None:
    """Hold messages with obvious spam keyword patterns.

    Returns {"decision": "hold", "reason": "..."} if spam patterns
    are found in the subject or body, or None if it passes through.
    """
    combined = f"{subject} {body}"
    if not combined.strip():
        return None

    for pattern in _SPAM_PATTERNS:
        match = pattern.search(combined)
        if match:
            return {"decision": "hold", "reason": f"Spam pattern detected: {match.group()[:40]}"}

    return None
