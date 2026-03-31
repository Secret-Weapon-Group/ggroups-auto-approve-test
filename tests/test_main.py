"""Tests for main.py — CLI dispatch, fetch/analyze, approve, orchestration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config import DEFAULT_FETCH_DAYS, DEFAULT_MODEL
from mail_monitor import PendingMessage


def _make_msg(id="0", status="ok", ai_rec="approve"):
    return PendingMessage(
        id=id, sender="alice@example.com", subject="Test Subject",
        snippet="snippet", body="Body text.\nLine 2.", date="2026-03-15",
        status=status, ai_recommendation=ai_rec, ai_reason="reason",
        ai_summary="", reply_to="approve@googlegroups.com", message_uid="100",
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


# ── fetch_and_analyze ──────────────────────────────────────────

class TestFetchAndAnalyze:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        msgs = [_make_msg()]
        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.fetch_pending = AsyncMock(return_value=msgs)

        with patch("main.MailMonitor", return_value=mock_monitor), \
             patch("main.analyze_all", new_callable=AsyncMock, return_value=msgs), \
             patch("main.config") as mock_config, \
             patch("builtins.print"):
            mock_config.ANTHROPIC_API_KEY = "test-key"
            mock_config.IMAP_HOST = "imap.gmail.com"
            mock_config.SMTP_HOST = "smtp.gmail.com"
            mock_config.SMTP_PORT = 587
            mock_config.GOOGLE_EMAIL = "test@example.com"
            mock_config.GOOGLE_PASSWORD = "secret"
            mock_config.GROUP_EMAIL = "group@googlegroups.com"
            from main import fetch_and_analyze
            result = await fetch_and_analyze()
            assert len(result) == 1
            mock_monitor.connect.assert_awaited_once()
            mock_monitor.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_messages(self):
        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.fetch_pending = AsyncMock(return_value=[])

        with patch("main.MailMonitor", return_value=mock_monitor), \
             patch("main.config") as mock_config, \
             patch("builtins.print"):
            mock_config.IMAP_HOST = "imap.gmail.com"
            mock_config.SMTP_HOST = "smtp.gmail.com"
            mock_config.SMTP_PORT = 587
            mock_config.GOOGLE_EMAIL = "test@example.com"
            mock_config.GOOGLE_PASSWORD = "secret"
            mock_config.GROUP_EMAIL = "group@googlegroups.com"
            from main import fetch_and_analyze
            result = await fetch_and_analyze()
            assert result == []

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        msgs = [_make_msg()]
        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.fetch_pending = AsyncMock(return_value=msgs)

        with patch("main.MailMonitor", return_value=mock_monitor), \
             patch("main.config") as mock_config, \
             patch("builtins.print"):
            mock_config.ANTHROPIC_API_KEY = ""
            mock_config.IMAP_HOST = "imap.gmail.com"
            mock_config.SMTP_HOST = "smtp.gmail.com"
            mock_config.SMTP_PORT = 587
            mock_config.GOOGLE_EMAIL = "test@example.com"
            mock_config.GOOGLE_PASSWORD = "secret"
            mock_config.GROUP_EMAIL = "group@googlegroups.com"
            from main import fetch_and_analyze
            result = await fetch_and_analyze()
            assert result[0].ai_recommendation == "approve"
            assert result[0].ai_reason == "(no API key)"


    @pytest.mark.asyncio
    async def test_progress_callback(self):
        msgs = [_make_msg()]
        msgs[0].subject = "A very long subject that is over forty characters long for testing"
        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.fetch_pending = AsyncMock(return_value=msgs)

        async def mock_analyze(messages, on_progress=None, model=None):
            if on_progress:
                on_progress(1, 1, "classify", messages[0])
                on_progress(1, 1, "summarize", messages[0])
            return messages

        with patch("main.MailMonitor", return_value=mock_monitor), \
             patch("main.analyze_all", side_effect=mock_analyze), \
             patch("main.config") as mock_config, \
             patch("builtins.print"):
            mock_config.ANTHROPIC_API_KEY = "test-key"
            mock_config.IMAP_HOST = "imap.gmail.com"
            mock_config.SMTP_HOST = "smtp.gmail.com"
            mock_config.SMTP_PORT = 587
            mock_config.GOOGLE_EMAIL = "test@example.com"
            mock_config.GOOGLE_PASSWORD = "secret"
            mock_config.GROUP_EMAIL = "group@googlegroups.com"
            from main import fetch_and_analyze
            result = await fetch_and_analyze()
            assert len(result) == 1


# ── approve_messages ───────────────────────────────────────────

class TestApproveMessages:
    @pytest.mark.asyncio
    async def test_all_success(self):
        msgs = [_make_msg(id="0"), _make_msg(id="1")]
        mock_monitor = MagicMock()
        mock_monitor.approve_messages = AsyncMock(return_value={"0": True, "1": True})

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_monitor, msgs)
            mock_monitor.approve_messages.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        msgs = [_make_msg(id="0"), _make_msg(id="1")]
        mock_monitor = MagicMock()
        mock_monitor.approve_messages = AsyncMock(return_value={"0": True, "1": False})

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_monitor, msgs)

    @pytest.mark.asyncio
    async def test_all_failure(self):
        msgs = [_make_msg(id="0")]
        mock_monitor = MagicMock()
        mock_monitor.approve_messages = AsyncMock(return_value={"0": False})

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_monitor, msgs)

    @pytest.mark.asyncio
    async def test_failed_message_not_found(self):
        msgs = [_make_msg(id="0")]
        mock_monitor = MagicMock()
        mock_monitor.approve_messages = AsyncMock(return_value={"99": False})

        with patch("builtins.print"):
            from main import approve_messages
            await approve_messages(mock_monitor, msgs)


# ── main_flow ──────────────────────────────────────────────────

class TestMainFlow:
    def test_three_phase_orchestration(self):
        msgs = [_make_msg()]

        with patch("main.asyncio") as mock_asyncio, \
             patch("main.fetch_and_analyze"), \
             patch("main.run_tui", return_value=msgs) as mock_tui, \
             patch("main.MailMonitor"), \
             patch("main.config"), \
             patch("builtins.print"):

            mock_asyncio.run.side_effect = [msgs, None]

            from main import main_flow
            main_flow()
            assert mock_asyncio.run.call_count == 2
            mock_tui.assert_called_once()

    def test_do_approve_phase(self):
        """Test that main_flow executes the approval phase."""
        import asyncio
        _original_run = asyncio.run
        msgs = [_make_msg()]

        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.mark_seen = AsyncMock()

        with patch("main.run_tui", return_value=msgs), \
             patch("main._make_monitor", return_value=mock_monitor), \
             patch("main.approve_messages", new_callable=AsyncMock) as mock_approve, \
             patch("main.fetch_and_analyze"), \
             patch("builtins.print"):

            call_count = []

            def run_side_effect(coro):
                call_count.append(1)
                if len(call_count) == 1:
                    return msgs
                return _original_run(coro)

            with patch("main.asyncio.run", side_effect=run_side_effect):
                from main import main_flow
                main_flow()
                mock_approve.assert_awaited_once()
                mock_monitor.connect.assert_awaited_once()
                mock_monitor.disconnect.assert_awaited_once()

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
            # 2 calls: fetch_and_analyze + do_post_tui (mark_seen even without approvals)
            assert mock_asyncio.run.call_count == 2

    def test_mark_seen_called_with_approvals(self):
        """After TUI approves some messages, mark_seen is called for ALL fetched messages."""
        import asyncio
        _original_run = asyncio.run
        msgs = [_make_msg(id="0"), _make_msg(id="1")]

        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.mark_seen = AsyncMock()

        with patch("main.run_tui", return_value=[msgs[0]]), \
             patch("main._make_monitor", return_value=mock_monitor), \
             patch("main.approve_messages", new_callable=AsyncMock), \
             patch("main.fetch_and_analyze"), \
             patch("builtins.print"):

            call_count = []

            def run_side_effect(coro):
                call_count.append(1)
                if len(call_count) == 1:
                    return msgs
                return _original_run(coro)

            with patch("main.asyncio.run", side_effect=run_side_effect):
                from main import main_flow
                main_flow()
                mock_monitor.mark_seen.assert_awaited_once_with(msgs)

    def test_mark_seen_called_no_approvals(self):
        """After TUI exits with no approvals, mark_seen is still called for all messages."""
        import asyncio
        _original_run = asyncio.run
        msgs = [_make_msg(id="0"), _make_msg(id="1")]

        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.mark_seen = AsyncMock()

        with patch("main.run_tui", return_value=None), \
             patch("main._make_monitor", return_value=mock_monitor), \
             patch("main.fetch_and_analyze"), \
             patch("builtins.print"):

            call_count = []

            def run_side_effect(coro):
                call_count.append(1)
                if len(call_count) == 1:
                    return msgs
                return _original_run(coro)

            with patch("main.asyncio.run", side_effect=run_side_effect):
                from main import main_flow
                main_flow()
                mock_monitor.mark_seen.assert_awaited_once_with(msgs)


# ── auto_approve_flow ──────────────────────────────────────────

class TestAutoApproveFlow:
    @pytest.mark.asyncio
    async def test_approve_and_hold(self):
        ok_msg = _make_msg(id="0", ai_rec="approve")
        hold_msg = _make_msg(id="1", ai_rec="hold")
        hold_msg.status = "hold"

        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.approve_messages = AsyncMock(return_value={"0": True})
        mock_monitor.mark_seen = AsyncMock()

        with patch("main.fetch_and_analyze", new_callable=AsyncMock, return_value=[ok_msg, hold_msg]), \
             patch("main.MailMonitor", return_value=mock_monitor), \
             patch("main.config") as mock_config, \
             patch("builtins.print"):
            mock_config.IMAP_HOST = "imap.gmail.com"
            mock_config.SMTP_HOST = "smtp.gmail.com"
            mock_config.SMTP_PORT = 587
            mock_config.GOOGLE_EMAIL = "test@example.com"
            mock_config.GOOGLE_PASSWORD = "secret"
            mock_config.GROUP_EMAIL = "group@googlegroups.com"
            from main import auto_approve_flow
            await auto_approve_flow()
            mock_monitor.approve_messages.assert_awaited_once()

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
    async def test_mark_seen_called_for_held_messages(self):
        """After approving ok messages, mark_seen is called for held messages."""
        ok_msg = _make_msg(id="0", ai_rec="approve")
        hold_msg = _make_msg(id="1", ai_rec="hold")
        hold_msg.status = "hold"

        mock_monitor = MagicMock()
        mock_monitor.connect = AsyncMock()
        mock_monitor.disconnect = AsyncMock()
        mock_monitor.approve_messages = AsyncMock(return_value={"0": True})
        mock_monitor.mark_seen = AsyncMock()

        with patch("main.fetch_and_analyze", new_callable=AsyncMock, return_value=[ok_msg, hold_msg]), \
             patch("main.MailMonitor", return_value=mock_monitor), \
             patch("main.config") as mock_config, \
             patch("builtins.print"):
            mock_config.IMAP_HOST = "imap.gmail.com"
            mock_config.SMTP_HOST = "smtp.gmail.com"
            mock_config.SMTP_PORT = 587
            mock_config.GOOGLE_EMAIL = "test@example.com"
            mock_config.GOOGLE_PASSWORD = "secret"
            mock_config.GROUP_EMAIL = "group@googlegroups.com"
            from main import auto_approve_flow
            await auto_approve_flow()
            mock_monitor.mark_seen.assert_awaited_once_with([hold_msg])


# ── main() CLI dispatch ───────────────────────────────────────

class TestMain:
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
            mock_flow.assert_called_once_with(debug=False, days=DEFAULT_FETCH_DAYS,
                                                 model=DEFAULT_MODEL)

    def test_debug_flag(self):
        with patch("sys.argv", ["main.py", "--debug"]), \
             patch("main.main_flow") as mock_flow, \
             patch("main.logging") as mock_logging, \
             patch("builtins.print"):
            from main import main
            main()
            mock_flow.assert_called_once_with(debug=True, days=DEFAULT_FETCH_DAYS,
                                                 model=DEFAULT_MODEL)
            mock_logging.basicConfig.assert_called_once()

    def test_model_flag(self):
        with patch("sys.argv", ["main.py", "--model", "opus"]), \
             patch("main.main_flow") as mock_flow, \
             patch("builtins.print"):
            from main import main
            main()
            mock_flow.assert_called_once_with(debug=False, days=DEFAULT_FETCH_DAYS,
                                                 model="opus")
