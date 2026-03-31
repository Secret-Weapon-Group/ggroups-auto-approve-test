"""Tests for checks/ package — pattern-matching message classification."""

from checks import run_all_checks, ALL_CHECKS
from checks.no_substance import check_no_substance
from checks.url_only import check_url_only
from checks.spam import check_spam
from tests.email_corpus import CORPUS


# ── check_no_substance ─────��──────────────────────────────────

class TestCheckNoSubstance:
    def test_plus_one(self):
        result = check_no_substance("+1")
        assert result is not None
        assert result["decision"] == "hold"

    def test_thanks(self):
        result = check_no_substance("Thanks")
        assert result is not None
        assert result["decision"] == "hold"

    def test_thanks_exclamation(self):
        result = check_no_substance("Thanks!")
        assert result is not None
        assert result["decision"] == "hold"

    def test_i_agree(self):
        result = check_no_substance("I agree")
        assert result is not None
        assert result["decision"] == "hold"

    def test_me_too(self):
        result = check_no_substance("Me too")
        assert result is not None
        assert result["decision"] == "hold"

    def test_lol(self):
        result = check_no_substance("lol")
        assert result is not None
        assert result["decision"] == "hold"

    def test_this_is_wrong(self):
        result = check_no_substance("This is wrong")
        assert result is not None
        assert result["decision"] == "hold"

    def test_long_message_with_thanks_prefix(self):
        body = "Thanks, but here's my detailed forecast about the upcoming election results based on recent polling data and established historical trends in the region"
        result = check_no_substance(body)
        assert result is None

    def test_normal_substantive_message(self):
        body = "I think the probability of this event occurring is around 30% based on the current data"
        result = check_no_substance(body)
        assert result is None

    def test_empty_body(self):
        result = check_no_substance("")
        assert result is not None
        assert result["decision"] == "hold"

    def test_whitespace_only(self):
        result = check_no_substance("   ")
        assert result is not None
        assert result["decision"] == "hold"

    def test_short_non_reaction_message(self):
        result = check_no_substance("What about the GDP forecast?")
        assert result is None

    def test_reason_present(self):
        result = check_no_substance("+1")
        assert "reason" in result
        assert len(result["reason"]) > 0


# ── check_url_only ───────────���─────────────────────────��──────

class TestCheckUrlOnly:
    def test_bare_url(self):
        result = check_url_only("https://example.com/article")
        assert result is not None
        assert result["decision"] == "hold"

    def test_url_with_few_words(self):
        result = check_url_only("Check this out https://example.com")
        assert result is not None
        assert result["decision"] == "hold"

    def test_url_with_five_words(self):
        result = check_url_only("Here is a good link https://example.com")
        assert result is not None
        assert result["decision"] == "hold"

    def test_url_with_many_words(self):
        body = "I found this really interesting article about forecasting methodology that discusses Bayesian approaches https://example.com"
        result = check_url_only(body)
        assert result is None

    def test_no_url(self):
        result = check_url_only("This is a normal message with no links at all")
        assert result is None

    def test_multiple_urls_few_words(self):
        result = check_url_only("https://example.com https://other.com")
        assert result is not None
        assert result["decision"] == "hold"

    def test_empty_body(self):
        result = check_url_only("")
        assert result is None

    def test_reason_present(self):
        result = check_url_only("https://example.com")
        assert "reason" in result
        assert len(result["reason"]) > 0


# ── check_spam ──────────────────��─────────────────────────────

class TestCheckSpam:
    def test_crypto_promotion(self):
        result = check_spam("Make money fast", "Buy Bitcoin now for guaranteed returns")
        assert result is not None
        assert result["decision"] == "hold"

    def test_click_here(self):
        result = check_spam("Special offer", "Click here to claim your prize")
        assert result is not None
        assert result["decision"] == "hold"

    def test_seo_spam(self):
        result = check_spam("SEO services", "Boost your website ranking with our SEO services")
        assert result is not None
        assert result["decision"] == "hold"

    def test_normal_message(self):
        result = check_spam("Forecast discussion", "I think the probability is about 40% based on recent trends")
        assert result is None

    def test_empty_body(self):
        result = check_spam("Subject", "")
        assert result is None

    def test_both_empty(self):
        result = check_spam("", "")
        assert result is None

    def test_spam_in_subject(self):
        result = check_spam("Buy crypto now", "Here is some text")
        assert result is not None
        assert result["decision"] == "hold"

    def test_reason_present(self):
        result = check_spam("Offer", "Click here now")
        assert "reason" in result
        assert len(result["reason"]) > 0


# ── run_all_checks ────────────��───────────────────────────────

class TestRunAllChecks:
    def test_returns_first_hit(self):
        result = run_all_checks("Subject", "+1")
        assert result is not None
        assert result["decision"] == "hold"

    def test_returns_none_when_all_pass(self):
        result = run_all_checks(
            "Forecast discussion",
            "I believe the probability is around 30% based on recent polling data and historical trends",
        )
        assert result is None

    def test_url_only_caught(self):
        result = run_all_checks("Link", "https://example.com")
        assert result is not None
        assert result["decision"] == "hold"

    def test_spam_caught(self):
        result = run_all_checks("Buy crypto", "Click here for guaranteed returns on Bitcoin investment")
        assert result is not None
        assert result["decision"] == "hold"

    def test_sender_parameter_accepted(self):
        result = run_all_checks("Subject", "Normal substantive message about forecasting trends", sender="user@example.com")
        assert result is None


# ── boundary tests (Task 4) ──────────────────────────────────────

class TestNoSubstanceBoundaries:
    """Boundary tests for _WORD_THRESHOLD=20 and reaction pattern matching."""

    def test_reaction_single_word_held(self):
        """Single reaction word is held (1 word ≤20, matches pattern)."""
        assert check_no_substance("Thanks")["decision"] == "hold"
        assert check_no_substance("+1")["decision"] == "hold"
        assert check_no_substance("Agreed")["decision"] == "hold"

    def test_20_word_message_with_reaction_prefix_passes(self):
        """20-word message starting with 'Thanks' passes — pattern requires full-string match."""
        body = "Thanks " + " ".join(["word"] * 19)  # 20 words total
        assert len(body.split()) == 20
        result = check_no_substance(body)
        assert result is None  # no full-string pattern match

    def test_21_word_message_skips_pattern_check(self):
        """21-word message skips pattern check entirely (>20 early return)."""
        body = "Thanks " + " ".join(["word"] * 20)  # 21 words total
        assert len(body.split()) == 21
        result = check_no_substance(body)
        assert result is None

    def test_exactly_20_non_reaction_words_passes(self):
        """20 non-reaction words: reaches pattern check, no match, passes."""
        body = " ".join(["forecast"] * 20)
        assert len(body.split()) == 20
        result = check_no_substance(body)
        assert result is None

    def test_exactly_21_non_reaction_words_passes(self):
        """21 non-reaction words: >20 early return, passes."""
        body = " ".join(["forecast"] * 21)
        assert len(body.split()) == 21
        result = check_no_substance(body)
        assert result is None

    def test_emoji_only_passes(self):
        """Emoji-only '👍' is not in the reaction patterns — passes through."""
        result = check_no_substance("👍")
        # 1 word ≤20, but "👍" doesn't match any reaction pattern
        assert result is None

    def test_reaction_with_trailing_whitespace(self):
        """Reaction with trailing whitespace/newlines still matches after strip()."""
        result = check_no_substance("  Thanks!  \n\n")
        assert result is not None
        assert result["decision"] == "hold"

    def test_case_insensitive_thanks_uppercase(self):
        """THANKS! matches case-insensitively (re.IGNORECASE)."""
        result = check_no_substance("THANKS!")
        assert result is not None
        assert result["decision"] == "hold"

    def test_case_insensitive_thanks_mixed(self):
        """tHaNkS matches case-insensitively."""
        result = check_no_substance("tHaNkS")
        assert result is not None
        assert result["decision"] == "hold"


class TestUrlOnlyBoundaries:
    """Boundary tests for _MAX_NON_URL_WORDS=5."""

    def test_url_plus_exactly_5_non_url_words_held(self):
        """URL + exactly 5 non-URL words → hold (5 ≤ 5)."""
        body = "Here are five good words https://example.com/forecast"
        # Remove URL, count remaining: "Here are five good words" = 5 words
        result = check_url_only(body)
        assert result is not None
        assert result["decision"] == "hold"

    def test_url_plus_exactly_6_non_url_words_passes(self):
        """URL + exactly 6 non-URL words → pass (6 > 5)."""
        body = "Here are now six good words https://example.com/forecast"
        result = check_url_only(body)
        assert result is None

    def test_url_with_fragment_captured_fully(self):
        """URL with fragment (#section) is captured by \\S+ regex."""
        body = "See https://example.com/report#methodology"
        result = check_url_only(body)
        assert result is not None  # "See" = 1 non-URL word ≤ 5
        assert result["decision"] == "hold"

    def test_url_with_query_string_captured(self):
        """URL with query params captured by \\S+ regex."""
        body = "Look https://example.com/data?year=2026&metric=gdp"
        result = check_url_only(body)
        assert result is not None  # "Look" = 1 non-URL word ≤ 5
        assert result["decision"] == "hold"

    def test_multiple_urls_5_non_url_words_held(self):
        """Multiple URLs with 5 non-URL words total → hold."""
        result = check_url_only("Check these out now please https://a.com https://b.com")
        # Non-URL: "Check these out now please" = 5 words ≤ 5
        assert result is not None
        assert result["decision"] == "hold"

    def test_url_zero_non_url_words_held(self):
        """Bare URL with zero non-URL words → hold."""
        result = check_url_only("https://example.com/recession-forecast")
        assert result is not None
        assert result["decision"] == "hold"


class TestSpamBoundaries:
    """Edge cases for spam pattern matching."""

    def test_spam_keyword_in_legitimate_context(self):
        """'buy crypto' in legitimate analysis context — still caught (known false positive).

        The spam regex matches 'buy crypto' regardless of surrounding context.
        """
        body = "I wouldn't buy crypto at this valuation given the macro headwinds"
        result = check_spam("Market analysis", body)
        assert result is not None
        assert result["decision"] == "hold"

    def test_multiple_spam_patterns_returns_first_match(self):
        """Multiple spam patterns in one message — first pattern match returned."""
        body = "Buy Bitcoin now and click here for guaranteed returns"
        result = check_spam("Special offer", body)
        assert result is not None
        assert result["decision"] == "hold"
        # The first matching pattern in _SPAM_PATTERNS order is returned
        assert "Spam pattern" in result["reason"]

    def test_spam_pattern_split_across_subject_and_body(self):
        """Spam pattern spanning subject + body — caught because combined = subject + body."""
        result = check_spam("Buy", "crypto now for amazing profits")
        # combined = "Buy crypto now for amazing profits", matches "buy crypto"
        assert result is not None
        assert result["decision"] == "hold"

    def test_partial_spam_keyword_not_matched(self):
        """'buying' doesn't match '\\bbuy\\s+crypto' — no whitespace after 'buy' in 'buying'."""
        body = "I've been buying cryptocurrency ETFs as a hedge against inflation"
        result = check_spam("Portfolio update", body)
        # "buying" starts with "buy" but the regex needs \s+ after "buy",
        # and the next char in "buying" is "i" not whitespace
        assert result is None

    def test_spam_keyword_case_insensitive(self):
        """Spam patterns are case-insensitive (re.IGNORECASE)."""
        result = check_spam("GREAT DEAL", "BUY BITCOIN NOW!!!")
        assert result is not None
        assert result["decision"] == "hold"


# ── corpus coverage enforcement ──────────────────────────────────

class TestCorpusCoverage:
    def test_every_check_has_corpus_entries(self):
        """Every check module must have at least 2 corpus entries (1 catch, 1 pass-through)."""
        for check_name in ALL_CHECKS:
            tagged = [c for c in CORPUS if check_name in c.tags]
            assert len(tagged) >= 2, f"checks/{check_name}.py needs at least 2 corpus entries in tests/email_corpus.py"
            catches = [c for c in tagged if c.expected_decision is not None]
            passthru = [c for c in tagged if c.expected_decision is None]
            assert len(catches) >= 1, f"checks/{check_name}.py needs at least 1 catch corpus entry"
            assert len(passthru) >= 1, f"checks/{check_name}.py needs at least 1 pass-through corpus entry"

    def test_all_checks_matches_check_modules(self):
        """ALL_CHECKS must list every check module in checks/ directory."""
        import pkgutil
        import checks
        module_names = [
            name for _, name, _ in pkgutil.iter_modules(checks.__path__)
        ]
        for name in module_names:
            assert name in ALL_CHECKS, f"checks/{name}.py exists but is not in ALL_CHECKS"
        for name in ALL_CHECKS:
            assert name in module_names, f"ALL_CHECKS lists '{name}' but checks/{name}.py does not exist"
