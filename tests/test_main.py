"""Tests for main.py — CLI dispatch, fetch/analyze, approve, orchestration."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mail_monitor import PendingMessage


def _make_msg(id="0", status="ok", ai_rec="approve"):
    return PendingMessage(
        id=id, sender="alice@example.com", subject="Test Subject",
        snippet="snippet", body="Body text.\nLine 2.", date="2026-03-15",
        status=status, ai_recommendation=ai_rec, ai_reason="reason",
        ai_summary="",
    )


# ── _fmt_elapsed ───────────────────────────────────────────────

class TestFmtElapsed:
    def test_sub_second(self):
        from main import _fmt_elapsed
        assert _fmt_elapsed(0.5) == "500ms"

    def test_zero(self):
        from main import _fmt_elapsed
        assert _fmt_elapsed(0) == "0ms"

    def test_seconds(self):
        from main import _fmt_elapsed
        assert _fmt_elapsed(2.3) == "2.3s"

    def test_one_second(self):
        from main import _fmt_elapsed
        assert _fmt_elapsed(1.0) == "1.0s"


# ── do_login ───────────────────────────────────────────────────

class TestDoLogin:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            MockScraper.return_value = mock_instance

            with patch("builtins.print"):
                from main import do_login
                await do_login()
                mock_instance.start.assert_awaited_once()
                mock_instance.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure(self):
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = False
            MockScraper.return_value = mock_instance

            with patch("builtins.print"), pytest.raises(SystemExit) as exc_info:
                from main import do_login
                await do_login()
            assert exc_info.value.code == 1


# ── fetch_and_analyze ──────────────────────────────────────────

class TestFetchAndAnalyze:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        msgs = [_make_msg()]
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            mock_instance.fetch_pending_messages.return_value = msgs
            MockScraper.return_value = mock_instance

            with patch("main.analyze_all", new_callable=AsyncMock, return_value=msgs), \
                 patch("main.config") as mock_config, \
                 patch("builtins.print"):
                mock_config.ANTHROPIC_API_KEY = "test-key"
                from main import fetch_and_analyze
                result = await fetch_and_analyze()
                assert len(result) == 1

    @pytest.mark.asyncio
    async def test_no_messages(self):
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            mock_instance.fetch_pending_messages.return_value = []
            MockScraper.return_value = mock_instance

            with patch("builtins.print"):
                from main import fetch_and_analyze
                result = await fetch_and_analyze()
                assert result == []

    @pytest.mark.asyncio
    async def test_not_logged_in(self):
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = False
            MockScraper.return_value = mock_instance

            with patch("builtins.print"), pytest.raises(SystemExit):
                from main import fetch_and_analyze
                await fetch_and_analyze()

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        msgs = [_make_msg()]
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            mock_instance.fetch_pending_messages.return_value = msgs
            MockScraper.return_value = mock_instance

            with patch("main.config") as mock_config, \
                 patch("builtins.print"):
                mock_config.ANTHROPIC_API_KEY = ""
                from main import fetch_and_analyze
                result = await fetch_and_analyze()
                assert result[0].ai_recommendation == "approve"
                assert result[0].ai_reason == "(no API key)"

    @pytest.mark.asyncio
    async def test_debug_mode(self):
        msgs = [_make_msg()]
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            mock_instance.fetch_pending_messages.return_value = msgs
            MockScraper.return_value = mock_instance

            with patch("main.analyze_all", new_callable=AsyncMock, return_value=msgs), \
                 patch("main.config") as mock_config, \
                 patch("builtins.print"):
                mock_config.ANTHROPIC_API_KEY = "test-key"
                from main import fetch_and_analyze
                await fetch_and_analyze(debug=True)
                MockScraper.assert_called_with(headless=True, debug=True)

    @pytest.mark.asyncio
    async def test_progress_callbacks(self):
        msgs = [_make_msg()]
        msgs[0].subject = "A very long subject that is over forty characters long for testing"
        with patch("main.GoogleGroupsScraper") as MockScraper:
            mock_instance = AsyncMock()
            mock_instance.ensure_logged_in.return_value = True
            mock_instance.fetch_pending_messages.return_value = msgs

            async def mock_fetch_bodies(messages, on_progress=None):
                if on_progress:
                    on_progress(1, 1, messages[0])

            mock_instance.fetch_all_message_bodies.side_effect = mock_fetch_bodies
            MockScraper.return_value = mock_instance

            async def mock_analyze(messages, on_progress=None):
                if on_progress:
                    on_progress(1, 1, "classify", messages[0])
                return messages

            with patch("main.analyze_all", side_effect=mock_analyze), \
                 patch("main.config") as mock_config, \
                 patch("builtins.print"):
                mock_config.ANTHROPIC_API_KEY = "test-key"
                from main import fetch_and_analyze
                result = await fetch_and_analyze()
                assert len(result) == 1


# ── approve_messages ───────────────────────────────────────────

class TestApproveMessages:
    @pytest.mark.asyncio
    async def test_all_success(self):
        msgs = [_make_msg(id="0"), _make_msg(id="1")]
        mock_scraper = AsyncMock()
        mock_scraper.approve_messages.return_value = {"0": True, "1": True}

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_scraper, msgs)
            mock_scraper.approve_messages.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        msgs = [_make_msg(id="0"), _make_msg(id="1")]
        mock_scraper = AsyncMock()
        mock_scraper.approve_messages.return_value = {"0": True, "1": False}

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_scraper, msgs)

    @pytest.mark.asyncio
    async def test_all_failure(self):
        msgs = [_make_msg(id="0")]
        mock_scraper = AsyncMock()
        mock_scraper.approve_messages.return_value = {"0": False}

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_scraper, msgs)

    @pytest.mark.asyncio
    async def test_failed_message_not_found(self):
        """When a failed msg_id doesn't match any message."""
        msgs = [_make_msg(id="0")]
        mock_scraper = AsyncMock()
        mock_scraper.approve_messages.return_value = {"99": False}

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_scraper, msgs)


# ── main_flow ──────────────────────────────────────────────────

class TestMainFlow:
    def test_three_phase_orchestration(self):
        msgs = [_make_msg()]

        with patch("main.asyncio") as mock_asyncio, \
             patch("main.fetch_and_analyze"), \
             patch("main.run_tui", return_value=msgs) as mock_tui, \
             patch("main.GoogleGroupsScraper"), \
             patch("builtins.print"):

            mock_asyncio.run.side_effect = [msgs, None]  # fetch_and_analyze, do_approve

            from main import main_flow
            main_flow()
            assert mock_asyncio.run.call_count == 2
            mock_tui.assert_called_once()

    def test_do_approve_inner_function(self):
        """Test the do_approve inner async function in main_flow."""
        msgs = [_make_msg()]

        with patch("main.run_tui", return_value=msgs), \
             patch("main.GoogleGroupsScraper") as MockScraper, \
             patch("main.approve_messages", new_callable=AsyncMock) as mock_approve, \
             patch("main.fetch_and_analyze"), \
             patch("builtins.print"):

            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.ensure_logged_in = AsyncMock(return_value=True)
            MockScraper.return_value = mock_instance

            captured_coro = []
            original_run = asyncio.run

            def capture_run(coro):
                if not captured_coro:
                    captured_coro.append(True)
                    return msgs
                else:
                    return original_run(coro)

            with patch("main.asyncio.run", side_effect=capture_run):
                from main import main_flow
                main_flow()
                mock_approve.assert_awaited_once()

    def test_do_approve_session_expired(self):
        """Test do_approve when session has expired."""
        msgs = [_make_msg()]

        with patch("main.run_tui", return_value=msgs), \
             patch("main.GoogleGroupsScraper") as MockScraper, \
             patch("main.fetch_and_analyze"), \
             patch("builtins.print"):

            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.ensure_logged_in = AsyncMock(return_value=False)
            MockScraper.return_value = mock_instance

            captured_coro = []
            original_run = asyncio.run

            def capture_run(coro):
                if not captured_coro:
                    captured_coro.append(True)
                    return msgs
                else:
                    return original_run(coro)

            with patch("main.asyncio.run", side_effect=capture_run):
                from main import main_flow
                main_flow()

    def test_no_messages(self):
        with patch("main.asyncio") as mock_asyncio, \
             patch("main.fetch_and_analyze"), \
             patch("builtins.print"):
            mock_asyncio.run.return_value = []

            from main import main_flow
            main_flow()
            assert mock_asyncio.run.call_count == 1

    def test_tui_returns_none(self):
        msgs = [_make_msg()]

        with patch("main.asyncio") as mock_asyncio, \
             patch("main.fetch_and_analyze"), \
             patch("main.run_tui", return_value=None), \
             patch("builtins.print"):
            mock_asyncio.run.return_value = msgs

            from main import main_flow
            main_flow()
            # Should not call asyncio.run a second time for approval
            assert mock_asyncio.run.call_count == 1


# ── auto_approve_flow ──────────────────────────────────────────

class TestAutoApproveFlow:
    @pytest.mark.asyncio
    async def test_approve_and_hold(self):
        ok_msg = _make_msg(id="0", ai_rec="approve")
        hold_msg = _make_msg(id="1", ai_rec="hold")
        hold_msg.status = "hold"

        with patch("main.fetch_and_analyze", new_callable=AsyncMock, return_value=[ok_msg, hold_msg]), \
             patch("main.GoogleGroupsScraper") as MockScraper, \
             patch("main.approve_messages", new_callable=AsyncMock) as mock_approve, \
             patch("builtins.print"):
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.ensure_logged_in = AsyncMock(return_value=True)
            MockScraper.return_value = mock_instance

            from main import auto_approve_flow
            await auto_approve_flow()
            mock_approve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_messages(self):
        with patch("main.fetch_and_analyze", new_callable=AsyncMock, return_value=[]), \
             patch("builtins.print"):
            from main import auto_approve_flow
            await auto_approve_flow()

    @pytest.mark.asyncio
    async def test_all_hold(self):
        hold_msg = _make_msg(ai_rec="hold")

        with patch("main.fetch_and_analyze", new_callable=AsyncMock, return_value=[hold_msg]), \
             patch("builtins.print"):
            from main import auto_approve_flow
            await auto_approve_flow()

    @pytest.mark.asyncio
    async def test_session_expired(self):
        ok_msg = _make_msg(ai_rec="approve")

        with patch("main.fetch_and_analyze", new_callable=AsyncMock, return_value=[ok_msg]), \
             patch("main.GoogleGroupsScraper") as MockScraper, \
             patch("builtins.print"):
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.ensure_logged_in = AsyncMock(return_value=False)
            MockScraper.return_value = mock_instance

            from main import auto_approve_flow
            await auto_approve_flow()


# ── main() CLI dispatch ───────────────────────────────────────

class TestMain:
    def test_login_dispatch(self):
        with patch("sys.argv", ["main.py", "--login"]), \
             patch("main.asyncio") as mock_asyncio, \
             patch("main.do_login"), \
             patch("builtins.print"):
            from main import main
            main()
            mock_asyncio.run.assert_called_once()

    def test_auto_approve_dispatch(self):
        with patch("sys.argv", ["main.py", "--auto-approve"]), \
             patch("main.asyncio") as mock_asyncio, \
             patch("main.auto_approve_flow"), \
             patch("builtins.print"):
            from main import main
            main()
            mock_asyncio.run.assert_called_once()

    def test_default_dispatch(self):
        with patch("sys.argv", ["main.py"]), \
             patch("main.main_flow") as mock_flow, \
             patch("builtins.print"):
            from main import main
            main()
            mock_flow.assert_called_once_with(debug=False)

    def test_debug_flag(self):
        with patch("sys.argv", ["main.py", "--debug"]), \
             patch("main.main_flow") as mock_flow, \
             patch("main.logging") as mock_logging, \
             patch("builtins.print"):
            from main import main
            main()
            mock_flow.assert_called_once_with(debug=True)
            mock_logging.basicConfig.assert_called_once()
