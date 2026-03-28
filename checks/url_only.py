"""Check for messages that are just a link with minimal text."""

import re

_URL_PATTERN = re.compile(r"https?://\S+")

# Messages with this many non-URL words or fewer are considered link-only.
_MAX_NON_URL_WORDS = 5


def check_url_only(body: str) -> dict | None:
    """Hold messages that are just a URL with minimal surrounding text.

    Returns {"decision": "hold", "reason": "..."} if the message has
    at least one URL and <=5 non-URL words, or None if it passes through.
    """
    stripped = body.strip()
    if not stripped:
        return None

    urls = _URL_PATTERN.findall(stripped)
    if not urls:
        return None

    # Remove URLs from text and count remaining words
    text_without_urls = _URL_PATTERN.sub("", stripped)
    non_url_words = text_without_urls.split()

    if len(non_url_words) <= _MAX_NON_URL_WORDS:
        return {"decision": "hold", "reason": "Link-only message with minimal text"}

    return None
