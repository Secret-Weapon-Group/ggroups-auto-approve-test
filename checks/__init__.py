"""Pattern-matching checks for obvious message violations.

Layer 1 of the two-layer classification system. Each check is a pure
function — no async, no API calls, no project imports. Returns
{"decision": "hold", "reason": "..."} on match or None on pass-through.
"""

from checks.no_substance import check_no_substance
from checks.url_only import check_url_only
from checks.spam import check_spam

ALL_CHECKS = ["no_substance", "url_only", "spam"]


def run_all_checks(subject: str, body: str, sender: str = "") -> dict | None:
    """Run all checks in order and return the first hit, or None."""
    result = check_no_substance(body)
    if result is not None:
        return result

    result = check_url_only(body)
    if result is not None:
        return result

    result = check_spam(subject, body)
    if result is not None:
        return result

    return None
