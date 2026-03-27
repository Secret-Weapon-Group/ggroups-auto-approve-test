"""Tests for scraper.py — PendingMessage, GoogleGroupsScraper, standalone functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from scraper import PendingMessage, GoogleGroupsScraper


# ── PendingMessage dataclass ───────────────────────────────────

class TestPendingMessage:
    def test_create_with_defaults(self):
        msg = PendingMessage(id="0", sender="a@b.com", subject="Test",
                             snippet="snip", body="body", date="2026-01-01")
        assert msg.status == "ok"
        assert msg.ai_recommendation == ""
        assert msg.ai_reason == ""
        assert msg.ai_summary == ""

    def test_create_with_all_fields(self):
        msg = PendingMessage(id="1", sender="b@c.com", subject="Sub",
                             snippet="sn", body="bd", date="2026-02-01",
                             status="hold", ai_recommendation="hold",
                             ai_reason="Bad", ai_summary="Summary")
        assert msg.status == "hold"
        assert msg.ai_recommendation == "hold"
        assert msg.ai_reason == "Bad"
        assert msg.ai_summary == "Summary"


# ── GoogleGroupsScraper ───────────────────────────────────────

class TestGoogleGroupsScraper:
    def test_init_defaults(self):
        with patch("config.GROUP_URL", "https://groups.google.com/g/test"):
            scraper = GoogleGroupsScraper()
            assert scraper.group_url == "https://groups.google.com/g/test"
            assert scraper.headless is True
            assert scraper.debug is False
            assert scraper._cached_msg_selector is None

    def test_init_custom_url(self):
        scraper = GoogleGroupsScraper(group_url="https://groups.google.com/g/custom/")
        assert scraper.group_url == "https://groups.google.com/g/custom"  # trailing slash stripped

    def test_init_debug_creates_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scraper.DEBUG_DIR", tmp_path / "debug")
        scraper = GoogleGroupsScraper(debug=True)
        assert scraper.debug is True
        assert (tmp_path / "debug").exists()

    @pytest.mark.asyncio
    async def test_start(self):
        scraper = GoogleGroupsScraper()
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

        with patch("scraper.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=mock_pw)
            await scraper.start()
            assert scraper._page == mock_page

    @pytest.mark.asyncio
    async def test_start_no_existing_pages(self):
        scraper = GoogleGroupsScraper()
        mock_pw = AsyncMock()
        mock_context = AsyncMock()
        mock_new_page = AsyncMock()
        mock_context.pages = []
        mock_context.new_page = AsyncMock(return_value=mock_new_page)
        mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

        with patch("scraper.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=mock_pw)
            await scraper.start()
            assert scraper._page == mock_new_page

    @pytest.mark.asyncio
    async def test_start_fresh_profile(self, tmp_path, monkeypatch):
        profile_dir = tmp_path / ".browser_profile"
        profile_dir.mkdir()
        (profile_dir / "test_file").write_text("data")
        monkeypatch.setattr("config.BROWSER_PROFILE_DIR", profile_dir)

        scraper = GoogleGroupsScraper(fresh_profile=True)
        mock_pw = AsyncMock()
        mock_context = AsyncMock()
        mock_context.pages = [AsyncMock()]
        mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

        with patch("scraper.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=mock_pw)
            await scraper.start()
            # fresh_profile should have cleared and recreated the dir
            assert profile_dir.exists()
            assert not (profile_dir / "test_file").exists()

    @pytest.mark.asyncio
    async def test_stop(self):
        scraper = GoogleGroupsScraper()
        scraper._context = AsyncMock()
        scraper._playwright = AsyncMock()
        await scraper.stop()
        scraper._context.close.assert_awaited_once()
        scraper._playwright.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_no_context(self):
        scraper = GoogleGroupsScraper()
        scraper._context = None
        scraper._playwright = None
        await scraper.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_ensure_logged_in_success(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.url = "https://groups.google.com/g/test"
        await scraper._dbg("test", save_screenshot=False)  # calls with no debug
        result = await scraper.ensure_logged_in()
        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_logged_in_needs_login_headless(self):
        scraper = GoogleGroupsScraper(headless=True)
        scraper._page = AsyncMock()
        scraper._page.url = "https://accounts.google.com/signin/v2"
        result = await scraper.ensure_logged_in()
        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_logged_in_visible_mode_success(self):
        scraper = GoogleGroupsScraper(headless=False)
        scraper._page = AsyncMock()
        scraper._page.url = "https://accounts.google.com/signin"
        scraper._page.wait_for_url = AsyncMock()

        with patch("builtins.print"):
            result = await scraper.ensure_logged_in()
            assert result is True

    @pytest.mark.asyncio
    async def test_ensure_logged_in_visible_mode_timeout(self):
        scraper = GoogleGroupsScraper(headless=False)
        scraper._page = AsyncMock()
        scraper._page.url = "https://accounts.google.com/signin"
        scraper._page.wait_for_url = AsyncMock(side_effect=Exception("timeout"))

        with patch("builtins.print"):
            result = await scraper.ensure_logged_in()
            assert result is False

    @pytest.mark.asyncio
    async def test_fetch_pending_messages_found(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()

        mock_elem = AsyncMock()
        mock_elem.inner_text.return_value = "Alice\nForecast topic\nSome snippet\n2026-01-15"

        with patch.object(scraper, "_find_message_elements", return_value=[mock_elem]):
            msgs = await scraper.fetch_pending_messages()
            assert len(msgs) == 1
            assert msgs[0].sender == "Alice"
            assert msgs[0].subject == "Forecast topic"

    @pytest.mark.asyncio
    async def test_fetch_pending_messages_none(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.inner_text.return_value = "no pending messages"

        with patch.object(scraper, "_find_message_elements", return_value=[]):
            msgs = await scraper.fetch_pending_messages()
            assert msgs == []

    @pytest.mark.asyncio
    async def test_fetch_pending_messages_empty_text(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.inner_text.return_value = "some other page content"

        with patch.object(scraper, "_find_message_elements", return_value=[]):
            msgs = await scraper.fetch_pending_messages()
            assert msgs == []

    @pytest.mark.asyncio
    async def test_find_message_elements_cached_selector(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._cached_msg_selector = '[role="listitem"]'
        mock_elements = [AsyncMock()]
        scraper._page.query_selector_all.return_value = mock_elements
        scraper.debug = False

        result = await scraper._find_message_elements()
        assert result == mock_elements

    @pytest.mark.asyncio
    async def test_find_message_elements_cached_selector_invalidated(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._cached_msg_selector = ".stale-selector"
        scraper._page.wait_for_selector.side_effect = [Exception("not found"), None]
        scraper._page.query_selector_all.side_effect = [[], [AsyncMock()]]
        scraper.debug = False

        await scraper._find_message_elements()
        assert scraper._cached_msg_selector is not None

    @pytest.mark.asyncio
    async def test_find_message_elements_probes_selectors(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._cached_msg_selector = None
        scraper.debug = False

        mock_elements = [AsyncMock()]
        # First call to wait_for_selector succeeds (combined), then query_selector_all
        # returns empty for first selectors, elements for a later one
        scraper._page.wait_for_selector.return_value = None
        call_count = 0

        async def mock_qsa(selector):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return mock_elements
            return []

        scraper._page.query_selector_all.side_effect = mock_qsa

        result = await scraper._find_message_elements()
        assert result == mock_elements

    @pytest.mark.asyncio
    async def test_find_message_elements_no_match(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._cached_msg_selector = None
        scraper.debug = False
        scraper._page.wait_for_selector.side_effect = Exception("timeout")

        result = await scraper._find_message_elements()
        assert result == []

    @pytest.mark.asyncio
    async def test_find_message_elements_query_exception(self):
        """query_selector_all raises on some selectors, returns empty on all."""
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._cached_msg_selector = None
        scraper.debug = False
        scraper._page.wait_for_selector.return_value = None

        # All query_selector_all calls raise exceptions
        scraper._page.query_selector_all.side_effect = Exception("query failed")

        result = await scraper._find_message_elements()
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_message_from_element(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.return_value = "Sender\nSubject Line\nPreview text\nJan 15"

        msg = await scraper._extract_message_from_element(elem, "0")
        assert msg.sender == "Sender"
        assert msg.subject == "Subject Line"
        assert msg.snippet == "Preview text"
        assert msg.date == "Jan 15"

    @pytest.mark.asyncio
    async def test_extract_message_from_element_empty(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.return_value = ""

        msg = await scraper._extract_message_from_element(elem, "0")
        assert msg is None

    @pytest.mark.asyncio
    async def test_extract_message_from_element_exception(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.side_effect = Exception("DOM error")

        msg = await scraper._extract_message_from_element(elem, "0")
        assert msg is None

    @pytest.mark.asyncio
    async def test_extract_message_minimal_lines(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.return_value = "Sender Only"

        msg = await scraper._extract_message_from_element(elem, "0")
        assert msg.sender == "Sender Only"
        assert msg.subject == "(no subject)"

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies(self, sample_message):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_elem = AsyncMock()
        mock_elem.inner_text.return_value = "Sender\nSubject\nExpanded body content here\nMore content"
        mock_elem.click = AsyncMock()

        with patch.object(scraper, "_find_message_elements", return_value=[mock_elem]), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            progress_calls = []

            def on_progress(i, total, msg):
                progress_calls.append(i)

            await scraper.fetch_all_message_bodies([sample_message], on_progress=on_progress)
            assert sample_message.body != ""
            assert len(progress_calls) == 1

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies_empty(self):
        scraper = GoogleGroupsScraper()
        await scraper.fetch_all_message_bodies([])  # Should not raise

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies_index_out_of_range(self, sample_message):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False
        sample_message.id = "5"  # Index beyond available elements

        with patch.object(scraper, "_find_message_elements", return_value=[]), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.fetch_all_message_bodies([sample_message])
            # Should skip gracefully

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies_expansion_empty(self, sample_message):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_elem = AsyncMock()
        mock_elem.inner_text.return_value = ""
        mock_elem.click = AsyncMock()

        with patch.object(scraper, "_find_message_elements", return_value=[mock_elem]), \
             patch.object(scraper, "_extract_expanded_body", return_value=""), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.fetch_all_message_bodies([sample_message])
            assert sample_message.body in (sample_message.snippet, "(could not extract body)")

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies_exception(self, sample_message):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        with patch.object(scraper, "_find_message_elements", side_effect=Exception("DOM crashed")), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.fetch_all_message_bodies([sample_message])
            assert "Could not fetch body" in sample_message.body

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies_escape_fails_after_error(self, sample_message):
        """When body fetch fails AND the escape key press also fails."""
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.keyboard.press = AsyncMock(side_effect=Exception("keyboard broken"))
        scraper.debug = False

        with patch.object(scraper, "_find_message_elements", side_effect=Exception("DOM crashed")), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.fetch_all_message_bodies([sample_message])
            assert "Could not fetch body" in sample_message.body

    @pytest.mark.asyncio
    async def test_fetch_all_message_bodies_requery_fewer_elements(self, sample_message):
        """After clicking to expand, re-query returns fewer elements."""
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False
        sample_message.id = "0"

        mock_elem = AsyncMock()
        mock_elem.inner_text.return_value = "content"
        mock_elem.click = AsyncMock()

        # First call returns element, second call (re-query after click) returns empty
        with patch.object(scraper, "_find_message_elements",
                          side_effect=[[mock_elem], []]), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.fetch_all_message_bodies([sample_message])
            assert sample_message.body in (sample_message.snippet, "(could not extract body)")

    @pytest.mark.asyncio
    async def test_extract_expanded_body(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.return_value = "Sender\nSubject\nDate\nThis is the body content\nMore body"
        result = await scraper._extract_expanded_body(elem)
        assert "body content" in result

    @pytest.mark.asyncio
    async def test_extract_expanded_body_short(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.return_value = "Short\nContent"
        result = await scraper._extract_expanded_body(elem)
        assert "Short" in result

    @pytest.mark.asyncio
    async def test_extract_expanded_body_exception(self):
        scraper = GoogleGroupsScraper()
        elem = AsyncMock()
        elem.inner_text.side_effect = Exception("fail")
        result = await scraper._extract_expanded_body(elem)
        assert result == ""

    @pytest.mark.asyncio
    async def test_dbg_no_debug(self):
        scraper = GoogleGroupsScraper(debug=False)
        scraper._page = AsyncMock()
        await scraper._dbg("test")
        scraper._page.screenshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dbg_with_debug(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scraper.DEBUG_DIR", tmp_path)
        scraper = GoogleGroupsScraper(debug=True)
        scraper._page = AsyncMock()
        scraper._page.url = "https://example.com"
        scraper._page.title.return_value = "Test"
        await scraper._dbg("test_label")
        scraper._page.screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dbg_no_screenshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scraper.DEBUG_DIR", tmp_path)
        scraper = GoogleGroupsScraper(debug=True)
        scraper._page = AsyncMock()
        scraper._page.url = "https://example.com"
        scraper._page.title.return_value = "Test"
        await scraper._dbg("test_label", save_screenshot=False)
        scraper._page.screenshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approve_messages_success(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_btn = AsyncMock()
        mock_elem = AsyncMock()

        # First call: elements list for finding idx, second call: fewer elements (verified)
        with patch.object(scraper, "_find_message_elements",
                          side_effect=[[mock_elem, mock_elem], [mock_elem]]), \
             patch.object(scraper, "_find_approve_button", return_value=mock_btn), \
             patch.object(scraper, "_handle_approve_confirm", return_value=True), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            results = await scraper.approve_messages(["0"])
            assert results["0"] is True

    @pytest.mark.asyncio
    async def test_approve_messages_empty(self):
        scraper = GoogleGroupsScraper()
        results = await scraper.approve_messages([])
        assert results == {}

    @pytest.mark.asyncio
    async def test_approve_messages_no_button(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_elem = AsyncMock()
        with patch.object(scraper, "_find_message_elements", return_value=[mock_elem]), \
             patch.object(scraper, "_find_approve_button", return_value=None), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            results = await scraper.approve_messages(["0"])
            assert results["0"] is False

    @pytest.mark.asyncio
    async def test_approve_messages_not_verified(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_btn = AsyncMock()
        mock_elem = AsyncMock()

        # Count doesn't decrease after approval
        with patch.object(scraper, "_find_message_elements",
                          side_effect=[[mock_elem], [mock_elem], [mock_elem]]), \
             patch.object(scraper, "_find_approve_button", return_value=mock_btn), \
             patch.object(scraper, "_handle_approve_confirm", return_value=True), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            results = await scraper.approve_messages(["0"])
            assert results["0"] is False

    @pytest.mark.asyncio
    async def test_approve_messages_index_out_of_range(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        with patch.object(scraper, "_find_message_elements", return_value=[]), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            results = await scraper.approve_messages(["5"])
            assert results["5"] is False

    @pytest.mark.asyncio
    async def test_approve_messages_exception_in_loop(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_elem = AsyncMock()
        with patch.object(scraper, "_find_message_elements", return_value=[mock_elem]), \
             patch.object(scraper, "_find_approve_button", side_effect=Exception("DOM error")), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            results = await scraper.approve_messages(["0"])
            assert results["0"] is False

    @pytest.mark.asyncio
    async def test_approve_messages_top_level_exception(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.goto.side_effect = Exception("Navigation failed")
        scraper.debug = False

        with patch("builtins.print"):
            results = await scraper.approve_messages(["0"])
            assert results == {}

    @pytest.mark.asyncio
    async def test_approve_messages_debug_dump(self):
        """In debug mode, approve_messages dumps row elements."""
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = True

        mock_elem = AsyncMock()
        with patch.object(scraper, "_find_message_elements",
                          side_effect=[[mock_elem], [mock_elem], [mock_elem]]), \
             patch.object(scraper, "_find_approve_button", return_value=None), \
             patch.object(scraper, "_dump_row_elements", new_callable=AsyncMock) as mock_dump, \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.approve_messages(["0"])
            mock_dump.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_messages_reverse_order(self):
        """Messages are processed in reverse index order."""
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_elem = AsyncMock()
        processed_order = []

        async def track_find(*args, **kwargs):
            return [mock_elem, mock_elem, mock_elem]

        async def track_approve(elem, msg_id):
            processed_order.append(msg_id)
            return None  # No button found, that's fine

        with patch.object(scraper, "_find_message_elements", side_effect=track_find), \
             patch.object(scraper, "_find_approve_button", side_effect=track_approve), \
             patch.object(scraper, "_dbg", new_callable=AsyncMock):
            await scraper.approve_messages(["0", "2", "1"])
            # Should be processed in reverse: 2, 1, 0
            assert processed_order == ["2", "1", "0"]

    @pytest.mark.asyncio
    async def test_find_approve_button_css_selector(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_btn = AsyncMock()
        elem = AsyncMock()
        elem.query_selector.return_value = mock_btn

        result = await scraper._find_approve_button(elem, "0")
        assert result == mock_btn

    @pytest.mark.asyncio
    async def test_find_approve_button_js_fallback(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        mock_btn = AsyncMock()
        elem = AsyncMock()
        elem.query_selector.return_value = None  # CSS selectors fail

        mock_handle = MagicMock()
        mock_handle.as_element.return_value = mock_btn
        scraper._page.evaluate_handle.return_value = mock_handle

        result = await scraper._find_approve_button(elem, "0")
        assert result == mock_btn

    @pytest.mark.asyncio
    async def test_find_approve_button_js_fallback_debug(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = True

        mock_btn = AsyncMock()
        elem = AsyncMock()
        elem.query_selector.return_value = None

        mock_handle = MagicMock()
        mock_handle.as_element.return_value = mock_btn
        scraper._page.evaluate_handle.return_value = mock_handle
        scraper._page.evaluate.return_value = {"tag": "BUTTON", "text": "check"}

        result = await scraper._find_approve_button(elem, "0")
        assert result == mock_btn

    @pytest.mark.asyncio
    async def test_find_approve_button_nothing_found(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        elem = AsyncMock()
        elem.query_selector.return_value = None
        mock_handle = MagicMock()
        mock_handle.as_element.return_value = None
        scraper._page.evaluate_handle.return_value = mock_handle

        result = await scraper._find_approve_button(elem, "0")
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_approve_confirm_role_button(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        ok_locator = MagicMock()
        ok_locator.count = AsyncMock(return_value=1)
        ok_locator.click = AsyncMock()
        # get_by_role is synchronous in Playwright — must be a regular MagicMock
        scraper._page.get_by_role = MagicMock(return_value=ok_locator)

        result = await scraper._handle_approve_confirm()
        assert result is True
        ok_locator.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_approve_confirm_css_selector(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        # Role-based fails — get_by_role is synchronous in Playwright
        ok_locator = MagicMock()
        ok_locator.count = AsyncMock(return_value=0)
        scraper._page.get_by_role = MagicMock(return_value=ok_locator)

        # CSS selector succeeds
        mock_elem = AsyncMock()
        scraper._page.wait_for_selector.return_value = mock_elem

        result = await scraper._handle_approve_confirm()
        assert result is True

    @pytest.mark.asyncio
    async def test_handle_approve_confirm_js_fallback(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        # Role-based fails — get_by_role is synchronous in Playwright
        scraper._page.get_by_role = MagicMock(side_effect=Exception("no role"))
        # CSS selectors fail
        scraper._page.wait_for_selector.side_effect = Exception("no selector")
        # JS succeeds
        scraper._page.evaluate.return_value = "clicked: OK"

        result = await scraper._handle_approve_confirm()
        assert result is True

    @pytest.mark.asyncio
    async def test_handle_approve_confirm_all_fail(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        # get_by_role is synchronous in Playwright
        scraper._page.get_by_role = MagicMock(side_effect=Exception("no role"))
        scraper._page.wait_for_selector.side_effect = Exception("no selector")
        scraper._page.evaluate.return_value = None

        with patch.object(scraper, "_dbg", new_callable=AsyncMock):
            result = await scraper._handle_approve_confirm()
            assert result is False

    @pytest.mark.asyncio
    async def test_handle_approve_confirm_js_exception(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        # get_by_role is synchronous in Playwright
        scraper._page.get_by_role = MagicMock(side_effect=Exception("no role"))
        scraper._page.wait_for_selector.side_effect = Exception("no selector")
        scraper._page.evaluate.side_effect = Exception("JS error")

        with patch.object(scraper, "_dbg", new_callable=AsyncMock):
            result = await scraper._handle_approve_confirm()
            assert result is False

    @pytest.mark.asyncio
    async def test_dump_row_elements_no_debug(self):
        scraper = GoogleGroupsScraper(debug=False)
        scraper._page = AsyncMock()
        await scraper._dump_row_elements(MagicMock(), "0")
        scraper._page.evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dump_row_elements_debug(self):
        scraper = GoogleGroupsScraper(debug=True)
        scraper._page = AsyncMock()
        scraper._page.evaluate.return_value = [
            {"tag": "BUTTON", "text": "check", "ariaLabel": "Approve",
             "tooltip": "", "jsaction": "", "role": "button", "classes": "", "id": ""}
        ]
        await scraper._dump_row_elements(AsyncMock(), "0")
        scraper._page.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dump_row_elements_exception(self):
        scraper = GoogleGroupsScraper(debug=True)
        scraper._page = AsyncMock()
        scraper._page.evaluate.side_effect = Exception("JS fail")
        await scraper._dump_row_elements(AsyncMock(), "0")  # Should not raise

    @pytest.mark.asyncio
    async def test_fetch_group_description_success(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        mock_elem = AsyncMock()
        mock_elem.inner_text.return_value = "Group description text"
        scraper._page.wait_for_selector.return_value = mock_elem

        result = await scraper.fetch_group_description()
        assert result == "Group description text"

    @pytest.mark.asyncio
    async def test_fetch_group_description_empty(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.wait_for_selector.side_effect = Exception("not found")

        result = await scraper.fetch_group_description()
        assert result == ""

    @pytest.mark.asyncio
    async def test_fetch_group_description_exception(self):
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper._page.goto.side_effect = Exception("navigation failed")

        result = await scraper.fetch_group_description()
        assert result == ""

    @pytest.mark.asyncio
    async def test_handle_approve_confirm_role_button_exception(self):
        """Role-button lookup raises, falls through to CSS selectors."""
        scraper = GoogleGroupsScraper()
        scraper._page = AsyncMock()
        scraper.debug = False

        # get_by_role is synchronous in Playwright
        scraper._page.get_by_role = MagicMock(side_effect=Exception("no match"))
        mock_elem = AsyncMock()
        scraper._page.wait_for_selector.return_value = mock_elem

        result = await scraper._handle_approve_confirm()
        assert result is True


# ── Standalone functions ───────────────────────────────────────

class TestLoginFlow:
    @pytest.mark.asyncio
    async def test_login_flow_success(self):
        with patch("scraper.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            MockScraper.return_value = mock_instance

            with patch("builtins.print"):
                from scraper import login_flow
                await login_flow()
                mock_instance.start.assert_awaited_once()
                mock_instance.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_login_flow_failure(self):
        with patch("scraper.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = False
            MockScraper.return_value = mock_instance

            with patch("builtins.print"):
                from scraper import login_flow
                await login_flow()
                mock_instance.stop.assert_awaited_once()


class TestFetchAllPending:
    @pytest.mark.asyncio
    async def test_fetch_all_pending_success(self):
        with patch("scraper.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            msg = PendingMessage(id="0", sender="a@b.com", subject="Test",
                                 snippet="snip", body="", date="2026-01-01")
            mock_instance.fetch_pending_messages.return_value = [msg]
            MockScraper.return_value = mock_instance

            from scraper import fetch_all_pending
            result = await fetch_all_pending()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fetch_all_pending_not_logged_in(self):
        with patch("scraper.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = False
            MockScraper.return_value = mock_instance

            with patch("builtins.print"):
                from scraper import fetch_all_pending
                result = await fetch_all_pending()
                assert result == []
