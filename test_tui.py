#!/usr/bin/env python3
"""Targeted TUI diagnostics — run each test until one hangs."""

import sys

from mail_monitor import PendingMessage

msg = PendingMessage(
    id="0",
    sender="test@example.com",
    subject="Test message subject",
    snippet="This is a test snippet",
    body="This is the full body of the test message.\nLine 2.\nLine 3.",
    date="2026-03-13",
    status="ok",
    ai_recommendation="approve",
    ai_reason="On-topic, substantive",
    ai_summary="",
)

test = sys.argv[1] if len(sys.argv) > 1 else "1"

if test == "1":
    print("Test 1: DataTable with rich markup in rows")
    from textual.app import App, ComposeResult
    from textual.widgets import DataTable, Footer, Static
    from textual.binding import Binding

    class T(App):
        BINDINGS = [Binding("q", "quit", "Quit")]
        def compose(self) -> ComposeResult:
            yield Static("Test 1 - press q to quit")
            yield DataTable(id="t")
            yield Footer()
        def on_mount(self):
            t = self.query_one("#t", DataTable)
            t.add_columns("Status", "From", "Subject", "AI")
            t.cursor_type = "row"
            t.add_row("[green] OK [/green]", "test@example.com", "Test subject", "[green]APPROVE[/green]")
    T().run()
    print("PASSED")

elif test == "2":
    print("Test 2: Full ModeratorApp with 1 message")
    from tui import ModeratorApp
    app = ModeratorApp([msg])
    result = app.run()
    print(f"PASSED - result: {result}")

elif test == "3":
    print("Test 3: Full ModeratorApp after asyncio.run (simulates main_flow)")
    import asyncio

    async def dummy():
        await asyncio.sleep(0.01)

    asyncio.run(dummy())
    print("  asyncio.run() done, now launching TUI...")

    from tui import run_tui
    result = run_tui([msg])
    print(f"PASSED - result: {result}")

elif test == "4":
    print("Test 4: After real Playwright start/stop (no navigation)")
    import asyncio
    from playwright.async_api import async_playwright

    async def pw_start_stop():
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("about:blank")
        await browser.close()
        await pw.stop()
        print("  Playwright started and stopped OK")

    asyncio.run(pw_start_stop())
    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui([msg])
    print(f"PASSED - result: {result}")

elif test == "5":
    print("Test 5: After real mail monitor session")
    import asyncio
    from main import fetch_and_analyze

    messages = asyncio.run(fetch_and_analyze())
    if not messages:
        messages = [msg]
    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui(messages)
    print(f"PASSED - result: {result}")

elif test == "6":
    print("Test 6: Full main_flow replica")
    import asyncio
    from main import fetch_and_analyze
    from analyzer import analyze_all
    import config

    messages = asyncio.run(fetch_and_analyze())
    if not messages:
        messages = [msg]
    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui(messages)
    print(f"PASSED - result: {result}")

else:
    print(f"Usage: python3 test_tui.py [1-8]")
