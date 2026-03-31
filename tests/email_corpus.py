"""Typed email test corpus for realistic content testing.

Each EmailCase declares which checks/rules it exercises via tags.
The structural coverage test in test_checks.py enforces that every
check module has at least 2 corpus entries (1 catch, 1 pass-through).
"""

from collections import namedtuple

EmailCase = namedtuple("EmailCase", [
    "subject", "body", "sender", "expected_decision",
    "reason_substr", "tags", "description",
])

# Corpus entries are added by Tasks 2-5. Each entry's tags field
# declares which checks/rules it exercises.
CORPUS: list[EmailCase] = [
    # ── no_substance: catch ──────────────────────────────────────
    EmailCase(
        subject="Re: Q3 GDP forecast",
        body="+1",
        sender="lurker@example.com",
        expected_decision="hold",
        reason_substr="Low-substance",
        tags=["no_substance"],
        description="Bare +1 reply to a forecast thread",
    ),
    # ── no_substance: pass-through ───────────────────────────────
    EmailCase(
        subject="Re: Q3 GDP forecast",
        body=(
            "I think the probability of a GDP contraction in Q3 is around 25%. "
            "The leading indicators from the PMI survey and initial jobless claims "
            "both suggest slowing growth, but consumer spending remains resilient. "
            "My base case is a soft landing with 1.2% annualized growth."
        ),
        sender="analyst@example.com",
        expected_decision=None,
        reason_substr="",
        tags=["no_substance"],
        description="Substantive forecast with evidence passes no_substance check",
    ),
    # ── url_only: catch ──────────────────────────────────────────
    EmailCase(
        subject="Interesting article",
        body="Check this out https://www.economist.com/finance/2026/03/recession-forecast",
        sender="sharer@example.com",
        expected_decision="hold",
        reason_substr="Link-only",
        tags=["url_only"],
        description="Link with minimal commentary held by url_only check",
    ),
    # ── url_only: pass-through ───────────────────────────────────
    EmailCase(
        subject="Re: Recession probability models",
        body=(
            "The latest Sahm Rule indicator just ticked up to 0.43 according to "
            "this FRED data https://fred.stlouisfed.org/series/SAHMREALTIME — "
            "still below the 0.50 threshold but trending in the wrong direction. "
            "I'm revising my recession probability from 15% to 22% for the next 12 months."
        ),
        sender="datahead@example.com",
        expected_decision=None,
        reason_substr="",
        tags=["url_only"],
        description="Link with substantial analysis passes url_only check",
    ),
    # ── spam: catch ──────────────────────────────────────────────
    EmailCase(
        subject="GUARANTEED RETURNS on Bitcoin investment",
        body=(
            "Buy Bitcoin now and get guaranteed returns of 500% in just 30 days! "
            "Limited time offer — act now before this opportunity disappears!"
        ),
        sender="scammer@shady-domain.com",
        expected_decision="hold",
        reason_substr="Spam pattern",
        tags=["spam"],
        description="Obvious crypto spam caught by spam check",
    ),
    # ── spam: pass-through ───────────────────────────────────────
    EmailCase(
        subject="Re: Crypto market forecast for Q4",
        body=(
            "I've been tracking Bitcoin's correlation with M2 money supply growth "
            "and I think the market is overestimating the probability of a sustained "
            "rally. My model puts BTC at 60% chance of being below $40K by year-end "
            "based on tightening liquidity conditions and declining retail flows."
        ),
        sender="crypto-analyst@example.com",
        expected_decision=None,
        reason_substr="",
        tags=["spam"],
        description="Legitimate crypto discussion passes spam check",
    ),
]
