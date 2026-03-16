#!/usr/bin/env python3
"""Targeted TUI diagnostics — run each test until one hangs."""

import sys

from scraper import PendingMessage

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
    print("Test 5: After real scraper session (full login check)")
    import asyncio
    from scraper import GoogleGroupsScraper

    async def real_scraper():
        s = GoogleGroupsScraper(headless=True)
        await s.start()
        logged_in = await s.ensure_logged_in()
        print(f"  Logged in: {logged_in}")
        msgs = await s.fetch_pending_messages()
        print(f"  Found {len(msgs)} messages")
        await s.stop()
        print("  Scraper stopped OK")
        return msgs

    messages = asyncio.run(real_scraper())
    # Use test message if no real messages
    if not messages:
        messages = [msg]
    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui(messages)
    print(f"PASSED - result: {result}")

elif test == "6":
    print("Test 6: Scraper + Anthropic analyzer, then TUI")
    import asyncio
    from scraper import GoogleGroupsScraper
    from analyzer import analyze_all

    async def full_flow():
        s = GoogleGroupsScraper(headless=True)
        await s.start()
        await s.ensure_logged_in()
        msgs = await s.fetch_pending_messages()
        print(f"  Found {len(msgs)} messages")
        if msgs:
            await s.fetch_all_message_bodies(msgs)
            await analyze_all(msgs)
            print(f"  Analysis done")
        await s.stop()
        return msgs if msgs else [msg]

    messages = asyncio.run(full_flow())
    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui(messages)
    print(f"PASSED - result: {result}")

elif test == "7":
    print("Test 7: Two asyncio.run() calls (like main_flow), then TUI")
    import asyncio
    from scraper import GoogleGroupsScraper

    async def phase1():
        s = GoogleGroupsScraper(headless=True)
        await s.start()
        await s.ensure_logged_in()
        msgs = await s.fetch_pending_messages()
        print(f"  Phase 1: Found {len(msgs)} messages")
        return s, msgs if msgs else [msg]

    scraper, messages = asyncio.run(phase1())

    print("  Phase 2: Stopping scraper in separate asyncio.run()...")
    asyncio.run(scraper.stop())

    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui(messages)
    print(f"PASSED - result: {result}")

elif test == "8":
    print("Test 8: Exact main_flow replica")
    import asyncio
    import time
    from scraper import GoogleGroupsScraper
    from analyzer import analyze_all
    import config

    async def fetch_and_analyze():
        s = GoogleGroupsScraper(headless=True)
        await s.start()
        await s.ensure_logged_in()
        msgs = await s.fetch_pending_messages()
        print(f"  Found {len(msgs)} messages")
        if msgs:
            await s.fetch_all_message_bodies(msgs)
        if msgs and config.ANTHROPIC_API_KEY:
            await analyze_all(msgs)
            print(f"  Analysis done")
        return msgs if msgs else [msg], s

    messages, scraper = asyncio.run(fetch_and_analyze())
    asyncio.run(scraper.stop())
    print("  Launching TUI...")
    from tui import run_tui
    result = run_tui(messages)
    print(f"PASSED - result: {result}")

else:
    print(f"Usage: python3 test_tui.py [1-8]")
