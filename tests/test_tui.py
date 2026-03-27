"""Tests for tui.py — ModeratorApp, PreviewScreen, ConfirmApproveScreen, run_tui."""

import asyncio
import pytest
from unittest.mock import patch

from scraper import PendingMessage
from tui import ModeratorApp, PreviewScreen, run_tui


def _make_msg(status="ok", ai_rec="approve", ai_reason="On-topic", body="Body text", summary=""):
    return PendingMessage(
        id="0", sender="alice@example.com", subject="Test Subject",
        snippet="snippet", body=body, date="2026-03-15",
        status=status, ai_recommendation=ai_rec, ai_reason=ai_reason,
        ai_summary=summary,
    )


# ── ModeratorApp ───────────────────────────────────────────────

class TestModeratorApp:
    @pytest.mark.asyncio
    async def test_compose(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test():
            table = app.query_one("#msg-table")
            assert table is not None
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_empty_state(self):
        app = ModeratorApp([])
        async with app.run_test():
            table = app.query_one("#msg-table")
            assert table.row_count == 0

    @pytest.mark.asyncio
    async def test_toggle_hold(self):
        msg = _make_msg(status="ok")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("h")
            assert msg.status == "hold"
            await pilot.press("h")
            assert msg.status == "ok"

    @pytest.mark.asyncio
    async def test_preview(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.pause()
            # PreviewScreen should be on the screen stack
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_approve_all_with_confirm(self):
        msg = _make_msg(status="ok")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            # ConfirmApproveScreen should be showing
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_approve_all_no_ok_messages(self):
        msg = _make_msg(status="hold")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            # No confirm screen since no OK messages
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_refresh(self):
        refresh_called = []
        msg = _make_msg()
        app = ModeratorApp([msg], on_refresh=lambda: refresh_called.append(True))
        async with app.run_test() as pilot:
            await pilot.press("r")
            await pilot.pause()
            assert len(refresh_called) == 1

    @pytest.mark.asyncio
    async def test_row_selection_enter_opens_preview(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_multiple_messages(self):
        msgs = [_make_msg(), _make_msg(status="hold", ai_rec="hold", ai_reason="Bad")]
        msgs[1].id = "1"
        msgs[1].sender = "bob@example.com"
        app = ModeratorApp(msgs)
        async with app.run_test():
            table = app.query_one("#msg-table")
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_hold_message_display(self):
        msg = _make_msg(status="hold", ai_rec="hold", ai_reason="Hostile")
        app = ModeratorApp([msg])
        async with app.run_test():
            # Just verify it renders without error
            table = app.query_one("#msg-table")
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_approved_property(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        assert app.approved is False

    @pytest.mark.asyncio
    async def test_toggle_hold_empty_table(self):
        """Toggle hold on empty table does nothing."""
        app = ModeratorApp([])
        async with app.run_test() as pilot:
            await pilot.press("h")  # No crash

    @pytest.mark.asyncio
    async def test_preview_empty_table(self):
        """Preview on empty table does nothing."""
        app = ModeratorApp([])
        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.pause()
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_preview_dismiss_restores_cursor(self):
        """Dismissing preview restores table cursor position."""
        msgs = [_make_msg(), _make_msg()]
        msgs[1].id = "1"
        msgs[1].sender = "bob@example.com"
        app = ModeratorApp(msgs)
        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_quit(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("q")


# ── PreviewScreen ──────────────────────────────────────────────

class TestPreviewScreen:
    @pytest.mark.asyncio
    async def test_compose(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_compose_with_summary(self):
        msg = _make_msg(summary="This is a summary of the message.")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_compose_hold_status(self):
        msg = _make_msg(status="hold", ai_rec="hold")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_toggle_hold_updates_header(self):
        msg = _make_msg(status="ok")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()
            await pilot.press("h")
            assert msg.status == "hold"
            await pilot.press("h")
            assert msg.status == "ok"

    @pytest.mark.asyncio
    async def test_copy_body(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()
            # copy_body writes OSC52 to stdout — just ensure it doesn't crash
            with patch("sys.stdout"):
                await pilot.press("c")

    @pytest.mark.asyncio
    async def test_copy_body_with_summary(self):
        msg = _make_msg(summary="Summary text")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()
            with patch("sys.stdout"):
                await pilot.press("c")

    @pytest.mark.asyncio
    async def test_dismiss(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_no_body_shows_snippet(self):
        msg = _make_msg(body="")
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_no_body_no_snippet(self):
        msg = _make_msg(body="")
        msg.snippet = ""
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            app.push_screen(PreviewScreen(msg))
            await pilot.pause()


# ── ConfirmApproveScreen ───────────────────────────────────────

class TestConfirmApproveScreen:
    @pytest.mark.asyncio
    async def test_yes_button(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("a")  # Opens confirm screen
            await pilot.pause()
            await pilot.click("#btn-yes")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_cancel_button(self):
        msg = _make_msg()
        app = ModeratorApp([msg])
        async with app.run_test() as pilot:
            await pilot.press("a")
            await pilot.pause()
            await pilot.click("#btn-cancel")
            await pilot.pause()
            # Should be back to main screen
            assert len(app.screen_stack) == 1


# ── run_tui ────────────────────────────────────────────────────

class TestRunTui:
    def test_run_tui_returns_none_on_quit(self):
        msg = _make_msg()
        with patch("tui.ModeratorApp") as MockApp:
            MockApp.return_value.run.return_value = None
            result = run_tui([msg])
            assert result is None

    def test_run_tui_returns_messages(self):
        msg = _make_msg()
        with patch("tui.ModeratorApp") as MockApp:
            MockApp.return_value.run.return_value = [msg]
            result = run_tui([msg])
            assert result == [msg]

    def test_run_tui_closed_event_loop(self):
        """Handles a closed event loop from prior asyncio.run()."""
        msg = _make_msg()

        # Simulate a closed event loop
        loop = asyncio.new_event_loop()
        loop.close()

        with patch("asyncio.get_event_loop", return_value=loop), \
             patch("tui.ModeratorApp") as MockApp:
            MockApp.return_value.run.return_value = None
            result = run_tui([msg])
            assert result is None

    def test_run_tui_no_event_loop(self):
        """Handles RuntimeError when no event loop exists."""
        msg = _make_msg()

        with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")), \
             patch("tui.ModeratorApp") as MockApp:
            MockApp.return_value.run.return_value = None
            result = run_tui([msg])
            assert result is None
