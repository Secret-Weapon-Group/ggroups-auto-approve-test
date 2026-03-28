"""Tests for checks/ package — pattern-matching message classification."""

from checks import run_all_checks
from checks.no_substance import check_no_substance
from checks.url_only import check_url_only
from checks.spam import check_spam


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
