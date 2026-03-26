#!/usr/bin/env python3
"""Google Groups Pending Message Moderator.

Usage:
    python main.py              # Fetch pending, analyze, launch TUI
    python main.py --login      # Force re-login (opens visible browser)
    python main.py --auto-approve  # (Future) Auto-approve AI-approved messages
"""

import argparse
import asyncio
import logging
import sys
import time

import config
from scraper import GoogleGroupsScraper, PendingMessage
from analyzer import analyze_all, MODEL_MAP, DEFAULT_MODEL
from tui import run_tui


async def do_login():
    """Open visible browser for manual Google login (fresh profile, no prior account)."""
    print("Opening browser for Google login (fresh profile)...")
    print(f"Group: {config.GROUP_URL}")
    print(f"Account: {config.GOOGLE_EMAIL}\n")

    scraper = GoogleGroupsScraper(headless=False, fresh_profile=True)
    await scraper.start()
    try:
        logged_in = await scraper.ensure_logged_in()
        if not logged_in:
            print("\nLogin failed or was not completed.")
            sys.exit(1)

        # Verify we can actually access the pending-messages page
        print("Verifying access to pending messages...")
        pending_url = f"{scraper.group_url}/pending-messages"
        await scraper._navigate_and_wait(pending_url)
        if scraper._is_login_page():
            print("\nLogin succeeded but pending-messages page requires re-auth.")
            print("Please log in again in the browser window...")
            try:
                await scraper._page.wait_for_url(
                    "**/groups.google.com/**", timeout=300000
                )
                await asyncio.sleep(2)
            except Exception:
                print("\nLogin timed out.")
                sys.exit(1)

        print("\nLogin successful! Session saved.")
        print("You can now run without --login.")
    finally:
        await scraper.stop()


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed time concisely."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.1f}s"


async def fetch_and_analyze(debug: bool = False, model: str = DEFAULT_MODEL) -> list[PendingMessage]:
    """Fetch pending messages, run AI analysis, and close the browser.

    The scraper is started and stopped within a single asyncio.run() call
    because Playwright objects are bound to the event loop that created them.
    """
    t_total = time.time()

    scraper = GoogleGroupsScraper(headless=True, debug=debug)

    t0 = time.time()
    await scraper.start()
    print(f"Browser started ({_fmt_elapsed(time.time() - t0)})")

    try:
        t0 = time.time()
        logged_in = await scraper.ensure_logged_in()
        if not logged_in:
            print("Not logged in. Run with --login first:")
            print("  python main.py --login")
            sys.exit(1)
        print(f"Session verified ({_fmt_elapsed(time.time() - t0)})")

        t0 = time.time()
        print("Fetching pending messages...")
        messages = await scraper.fetch_pending_messages()

        if not messages:
            print(f"No pending messages found. ({_fmt_elapsed(time.time() - t0)})")
            return []

        print(f"Found {len(messages)} pending message(s) ({_fmt_elapsed(time.time() - t0)})")

        # Fetch message bodies (batch — uses back-navigation instead of full reloads)
        t0 = time.time()

        def on_body_progress(i, total, msg):
            subj = msg.subject[:40] + "..." if len(msg.subject) > 40 else msg.subject
            print(f"  [{i}/{total}] {subj}", flush=True)

        print("Fetching message bodies...")
        await scraper.fetch_all_message_bodies(messages, on_progress=on_body_progress)
        print(f"Bodies fetched ({_fmt_elapsed(time.time() - t0)})")

        # Run AI analysis
        if config.ANTHROPIC_API_KEY:
            t0 = time.time()

            def on_ai_progress(i, total, phase, msg):
                subj = msg.subject[:40] + "..." if len(msg.subject) > 40 else msg.subject
                label = "Classified" if phase == "classify" else "Summarized"
                result = ""
                if phase == "classify":
                    result = f" -> {msg.ai_recommendation}"
                print(f"  [{i}/{total}] {label}: {subj}{result}", flush=True)

            print(f"Running AI analysis (model: {model})...")
            await analyze_all(messages, on_progress=on_ai_progress, model=model)
            hold_count = sum(1 for m in messages if m.ai_recommendation == "hold")
            print(f"AI done: {len(messages) - hold_count} approve, {hold_count} hold ({_fmt_elapsed(time.time() - t0)})")
        else:
            print("Warning: ANTHROPIC_API_KEY not set. Skipping AI analysis.")
            for msg in messages:
                msg.ai_recommendation = "approve"
                msg.ai_reason = "(no API key)"
                msg.status = "ok"

        print(f"\nTotal load time: {_fmt_elapsed(time.time() - t_total)}")
        return messages

    finally:
        await scraper.stop()


async def approve_messages(scraper: GoogleGroupsScraper, messages: list[PendingMessage]):
    """Approve the given messages via Playwright."""
    ids = [m.id for m in messages]
    print(f"\nApproving {len(ids)} message(s)...")
    results = await scraper.approve_messages(ids)
    ok = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    if failed == 0:
        print(f"All {ok} message(s) approved and verified!")
    else:
        if ok > 0:
            print(f"Approved {ok}, failed {failed}.")
        else:
            print(f"Approval failed for all {failed} message(s).")
        print("Failed messages (check Google Groups manually):")
        for mid, success in results.items():
            if not success:
                msg = next((m for m in messages if m.id == mid), None)
                subj = msg.subject if msg else mid
                print(f"  FAILED: {subj}")
        print("\nTip: Run with --debug for screenshots and logs to diagnose.")


def main_flow(debug: bool = False, model: str = DEFAULT_MODEL):
    """Main flow: fetch -> analyze -> TUI -> approve.

    Split into separate asyncio.run() calls because Textual's app.run()
    manages its own event loop and can't be nested inside another.
    Scraper is fully stopped before TUI launches (Playwright objects
    can't cross event loop boundaries).
    """
    # Phase 1: async fetch + analyze (scraper starts and stops here)
    messages = asyncio.run(fetch_and_analyze(debug=debug, model=model))
    if not messages:
        return

    # Phase 2: Synchronous TUI (runs its own event loop)
    to_approve = run_tui(messages, model=model)

    # Phase 3: async approve (fresh scraper session)
    if to_approve:
        async def do_approve():
            s = GoogleGroupsScraper(headless=True, debug=debug)
            await s.start()
            try:
                logged_in = await s.ensure_logged_in()
                if not logged_in:
                    print("Session expired. Run with --login first.")
                    return
                await approve_messages(s, to_approve)
            finally:
                await s.stop()

        asyncio.run(do_approve())
    else:
        print("No messages approved. Exiting.")


async def auto_approve_flow(model: str = DEFAULT_MODEL):
    """Auto-approve all AI-approved messages without TUI."""
    messages = await fetch_and_analyze(model=model)
    if not messages:
        return

    ok_messages = [m for m in messages if m.ai_recommendation == "approve"]
    hold_messages = [m for m in messages if m.ai_recommendation == "hold"]

    if hold_messages:
        print(f"\nHeld {len(hold_messages)} message(s):")
        for m in hold_messages:
            print(f"  - [{m.sender}] {m.subject}: {m.ai_reason}")

    if ok_messages:
        scraper = GoogleGroupsScraper(headless=True)
        await scraper.start()
        try:
            logged_in = await scraper.ensure_logged_in()
            if not logged_in:
                print("Session expired. Run with --login first.")
                return
            await approve_messages(scraper, ok_messages)
        finally:
            await scraper.stop()
    else:
        print("No messages to approve.")


def main():
    parser = argparse.ArgumentParser(description="Google Groups Pending Message Moderator")
    parser.add_argument("--login", action="store_true", help="Open browser for manual login")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve AI-approved messages")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and screenshots to debug/")
    parser.add_argument("--model", choices=list(MODEL_MAP.keys()), default=DEFAULT_MODEL,
                        help=f"AI model for analysis (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(message)s",
            datefmt="%H:%M:%S",
        )
        print("Debug mode ON — logs and screenshots will be saved to debug/")

    if args.login:
        asyncio.run(do_login())
    elif args.auto_approve:
        asyncio.run(auto_approve_flow(model=args.model))
    else:
        main_flow(debug=args.debug, model=args.model)


if __name__ == "__main__":
    main()
