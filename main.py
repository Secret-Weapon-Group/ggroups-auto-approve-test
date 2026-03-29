#!/usr/bin/env python3
"""Google Groups Pending Message Moderator (email-based).

Usage:
    python main.py              # Fetch pending, analyze, launch TUI
    python main.py --auto-approve  # Auto-approve AI-approved messages
    python main.py --debug      # Enable debug logging
"""

import argparse
import asyncio
import logging
import time

import config
from config import DEFAULT_FETCH_DAYS, DEFAULT_MODEL, MODEL_MAP
from mail_monitor import MailMonitor, PendingMessage
from analyzer import analyze_all
from tui import run_tui


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed time concisely."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.1f}s"


def _make_monitor() -> MailMonitor:
    """Create a MailMonitor from config settings."""
    return MailMonitor(
        imap_host=config.IMAP_HOST,
        email_address=config.GOOGLE_EMAIL,
        password=config.GOOGLE_PASSWORD,
        group_email=config.GROUP_EMAIL,
        smtp_host=config.SMTP_HOST,
        smtp_port=config.SMTP_PORT,
    )


async def fetch_and_analyze(*, days: int = DEFAULT_FETCH_DAYS, model: str = DEFAULT_MODEL) -> list[PendingMessage]:
    """Fetch pending moderation emails, run AI analysis, return messages."""
    t_total = time.time()

    monitor = _make_monitor()

    t0 = time.time()
    await monitor.connect()
    print(f"Connected to IMAP ({_fmt_elapsed(time.time() - t0)})")

    try:
        t0 = time.time()
        print(f"Fetching pending moderation emails (last {days} days)...")
        messages = await monitor.fetch_pending(days=days)

        if not messages:
            print(f"No pending messages found. ({_fmt_elapsed(time.time() - t0)})")
            return []

        print(f"Found {len(messages)} pending message(s) ({_fmt_elapsed(time.time() - t0)})")

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
        await monitor.disconnect()


async def approve_messages(monitor: MailMonitor, messages: list[PendingMessage]):
    """Approve the given messages via email reply."""
    print(f"\nApproving {len(messages)} message(s)...")
    results = await monitor.approve_messages(messages)
    ok = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    if failed == 0:
        print(f"All {ok} message(s) approved!")
    else:
        if ok > 0:
            print(f"Approved {ok}, failed {failed}.")
        else:
            print(f"Approval failed for all {failed} message(s).")
        print("Failed messages:")
        for mid, success in results.items():
            if not success:
                msg = next((m for m in messages if m.id == mid), None)
                subj = msg.subject if msg else mid
                print(f"  FAILED: {subj}")


def main_flow(debug: bool = False, days: int = DEFAULT_FETCH_DAYS, model: str = DEFAULT_MODEL):
    """Main flow: fetch -> analyze -> TUI -> approve.

    Split into separate asyncio.run() calls because Textual's app.run()
    manages its own event loop and can't be nested inside another.
    """
    # Phase 1: async fetch + analyze
    messages = asyncio.run(fetch_and_analyze(days=days, model=model))
    if not messages:
        return

    # Phase 2: Synchronous TUI (runs its own event loop)
    to_approve = run_tui(messages)

    # Phase 3: async approve (fresh monitor connection)
    if to_approve:
        async def do_approve():
            monitor = _make_monitor()
            await monitor.connect()
            try:
                await approve_messages(monitor, to_approve)
            finally:
                await monitor.disconnect()

        asyncio.run(do_approve())
    else:
        print("No messages approved. Exiting.")


async def auto_approve_flow(*, days: int = DEFAULT_FETCH_DAYS, model: str = DEFAULT_MODEL):
    """Auto-approve all AI-approved messages without TUI."""
    messages = await fetch_and_analyze(days=days, model=model)
    if not messages:
        return

    ok_messages = [m for m in messages if m.ai_recommendation == "approve"]
    hold_messages = [m for m in messages if m.ai_recommendation == "hold"]

    if hold_messages:
        print(f"\nHeld {len(hold_messages)} message(s):")
        for m in hold_messages:
            print(f"  - [{m.sender}] {m.subject}: {m.ai_reason}")

    if ok_messages:
        monitor = _make_monitor()
        await monitor.connect()
        try:
            await approve_messages(monitor, ok_messages)
        finally:
            await monitor.disconnect()
    else:
        print("No messages to approve.")


def main():
    parser = argparse.ArgumentParser(description="Google Groups Pending Message Moderator")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve AI-approved messages")
    parser.add_argument("--days", type=int, default=DEFAULT_FETCH_DAYS,
                        help=f"Only fetch emails from the last N days (default: {DEFAULT_FETCH_DAYS})")
    parser.add_argument("--model", choices=MODEL_MAP.keys(), default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(message)s",
            datefmt="%H:%M:%S",
        )
        print("Debug mode ON")

    if args.auto_approve:
        asyncio.run(auto_approve_flow(days=args.days, model=args.model))
    else:
        main_flow(debug=args.debug, days=args.days, model=args.model)


if __name__ == "__main__":
    main()
