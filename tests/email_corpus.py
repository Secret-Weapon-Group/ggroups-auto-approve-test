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
    # ── classifier: should approve (pass Layer 1, reach LLM) ────
    EmailCase(
        subject="Re: Q3 recession probability",
        body=(
            "I'd give this a 30% chance based on recent polling data and "
            "historical trends. The leading indicators from the Conference "
            "Board's composite index are still positive, though the margin "
            "is shrinking. I'm watching initial jobless claims closely — "
            "if they break above 250K sustained, I'd revise upward to 40%."
        ),
        sender="forecaster@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Clear probability forecast with numerical estimates",
    ),
    EmailCase(
        subject="Re: PMI and recession timing",
        body=(
            "The manufacturing PMI has been below 50 for three consecutive "
            "months now. Historically, when this coincides with an inverted "
            "yield curve (which we've had since Q1), recession follows within "
            "6-12 months about 70% of the time. I'm using a simple base rate "
            "model and getting 35% for H2 2026."
        ),
        sender="evidence@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Evidence-based analysis with leading indicators",
    ),
    EmailCase(
        subject="Re: Election forecast methodology",
        body=(
            "I think your 60% estimate is too high. The base rate for "
            "incumbent party retention when real GDP growth exceeds 2% is "
            "closer to 70%, which gives the challenger only 30%. What's "
            "your adjustment factor for the approval rating differential?"
        ),
        sender="contrarian@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Questioning a forecast with alternative base rates",
    ),
    EmailCase(
        subject="New BLS jobs report data",
        body=(
            "The March jobs report just dropped — 287K vs 180K expected. "
            "This is a significant upside surprise. Here's the FRED link "
            "for the full dataset https://fred.stlouisfed.org/series/PAYEMS "
            "and my interpretation: this pushes my recession probability "
            "down from 30% to about 20%. The labor market is clearly "
            "stronger than the PMI surveys suggested."
        ),
        sender="datanerd@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Link to evidence with substantive commentary",
    ),
    EmailCase(
        subject="Multi-factor recession model update",
        body=(
            "Updated my model with the latest data. Key inputs:\n"
            "- Yield curve: still inverted, -0.3% spread\n"
            "- PMI: 48.2\n"
            "- Jobless claims: 215K, stable\n"
            "- Consumer confidence: 98.7, declining\n\n"
            "Blended probability: 28% for recession starting in next "
            "6 months. This is down from my 32% estimate last month, "
            "mostly due to the strong labor market data."
        ),
        sender="modeler@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Long substantive post with multiple forecasts and data",
    ),
    EmailCase(
        subject="Re: China GDP growth forecast",
        body=(
            "I strongly disagree with the 6% estimate. The property sector "
            "is in structural decline and local government debt is at "
            "unsustainable levels. My model, which accounts for shadow "
            "banking exposure and demographic headwinds, puts real GDP "
            "growth at 3.8% for 2027. The official statistics are likely "
            "overstating growth by 1-2 percentage points."
        ),
        sender="chinabull@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Strong disagreement with evidence and alternative forecast",
    ),
    EmailCase(
        subject="Bayesian updating for geopolitical risk",
        body=(
            "I've been applying Bayesian updating to the Taiwan Strait "
            "conflict probability. Starting from Metaculus's 4% base rate "
            "for 2026, I update on three signals: increased military "
            "exercises (+2%), diplomatic rhetoric shift (+1%), and US "
            "carrier group deployment (-1%). Posterior: ~6%. Interested "
            "in how others are structuring their priors here."
        ),
        sender="bayesian@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier"],
        description="Technical forecasting methodology discussion",
    ),
    # ── classifier: should hold (pass Layer 1, caught by LLM) ────
    EmailCase(
        subject="Re: This group is terrible",
        body=(
            "I can't believe the quality of analysis in this group has "
            "fallen so far. Every single forecast posted here in the last "
            "month has been laughably wrong. You people clearly have no "
            "idea what you're doing and should stop pretending to be "
            "analysts. This is embarrassing for everyone involved."
        ),
        sender="angry@example.com",
        expected_decision="hold",
        reason_substr="",
        tags=["classifier"],
        description="Hostile rant against the group (passes Layer 1, >20 words)",
    ),
    EmailCase(
        subject="Re: Weekend plans",
        body=(
            "Did anyone catch the game last night? That fourth quarter "
            "comeback was insane! I was at the bar with some friends and "
            "we couldn't believe what happened. Anyway, great weekend "
            "everyone, see you all at the next meetup."
        ),
        sender="offtopic@example.com",
        expected_decision="hold",
        reason_substr="",
        tags=["classifier"],
        description="Off-topic chatter with no forecasting content",
    ),
    EmailCase(
        subject="Re: The economy is fine because reasons",
        body=(
            "The Democrats have completely ruined this country and anyone "
            "who thinks otherwise is delusional. Everything Biden has "
            "touched has turned to garbage. Inflation is out of control "
            "and the media won't report it. WAKE UP PEOPLE! This is all "
            "going to crash and burn because of their incompetent policies."
        ),
        sender="ranter@example.com",
        expected_decision="hold",
        reason_substr="",
        tags=["classifier"],
        description="Political rant disguised as economic commentary, no forecast",
    ),
    # ── classifier: should hold (caught by Layer 1) ──────────────
    EmailCase(
        subject="Re: Great forecast on the GDP numbers",
        body="lol nice call",
        sender="casual@example.com",
        expected_decision="hold",
        reason_substr="",
        tags=["classifier"],
        description="Casual reaction — passes Layer 1 (not full-string match), needs LLM",
    ),
    EmailCase(
        subject="Re: Someone posted this",
        body="https://www.nytimes.com/2026/03/31/economy/recession-indicators.html",
        sender="linkdropper@example.com",
        expected_decision="hold",
        reason_substr="Link-only",
        tags=["classifier", "url_only"],
        description="Bare news link with zero commentary caught by url_only",
    ),
    # ── classifier: borderline/adversarial ───────────────────────
    EmailCase(
        subject="Re: Q3 outlook",
        body="60% by Q3. Base rate from 2019 data.",
        sender="terse@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier", "adversarial"],
        description="Short but substantive — terse forecast with base rate reference",
    ),
    EmailCase(
        subject="Re: Weekend forecast meetup",
        body=(
            "Had a great time at the bar last night watching the game. "
            "Anyway, on the actual topic — I've been running the numbers "
            "on housing starts and my model now gives a 45% probability "
            "of a construction sector downturn by Q4. The permit data "
            "is really concerning."
        ),
        sender="pivoter@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier", "adversarial"],
        description="Looks off-topic but pivots to substantive forecast mid-message",
    ),
    EmailCase(
        subject="Re: Yield curve analysis",
        body=(
            "Interesting use of forecasting methodology there. The approach "
            "reminds me of what we discussed at the conference about "
            "predictive modeling frameworks and their applications in "
            "various analytical contexts. Really good stuff from the "
            "research community lately."
        ),
        sender="vague@example.com",
        expected_decision="hold",
        reason_substr="",
        tags=["classifier", "adversarial"],
        description="Uses forecasting vocabulary without making any prediction",
    ),
    EmailCase(
        subject="Re: Your inflation model is naive",
        body=(
            "Oh sure, just ignore the supply-side constraints like everyone "
            "else. Here's what your 'model' misses: shipping costs are up "
            "40% YoY, container availability is at 2021 crisis levels, and "
            "the Suez disruptions haven't even hit consumer prices yet. My "
            "estimate: CPI will average 4.2% for H2, not your rosy 2.8%."
        ),
        sender="snarky@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier", "adversarial"],
        description="Snarky tone but substantive with data and counter-forecast",
    ),
    EmailCase(
        subject="ALL CAPS FORECAST",
        body=(
            "I AM PUTTING MY RECESSION PROBABILITY AT 45% FOR Q4 BASED "
            "ON THE LATEST EMPLOYMENT DATA AND THE FACT THAT EVERY MAJOR "
            "LEADING INDICATOR IS NOW FLASHING WARNING SIGNS. THE FED IS "
            "BEHIND THE CURVE AND WE ALL KNOW IT."
        ),
        sender="capslock@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier", "adversarial"],
        description="All-caps but substantive forecasting message with data",
    ),
    EmailCase(
        subject="Re: Your recession call is wrong",
        body=(
            "You're being completely irresponsible with that 15% estimate. "
            "The yield curve has been inverted for 14 months — the longest "
            "inversion since 1980. Every single time this has happened, a "
            "recession followed within 18 months. The base rate is 100%. "
            "Your model is broken if it's giving you 15%."
        ),
        sender="hostile-but-data@example.com",
        expected_decision="approve",
        reason_substr="",
        tags=["classifier", "adversarial"],
        description="Hostile tone but backed by historical evidence and data",
    ),
]
