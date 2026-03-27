# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Google Groups pending message moderator. Scrapes pending messages from a Google Groups group via Playwright, classifies them with Claude API (approve/hold), and presents a Textual TUI for human review before approving.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# First-time login (opens visible browser for Google OAuth)
python main.py --login

# Normal run: fetch -> AI classify -> TUI -> approve
python main.py

# Auto-approve without TUI
python main.py --auto-approve

# Debug mode (screenshots saved to debug/)
python main.py --debug

# Manual TUI diagnostics (not automated tests — each test is interactive)
python test_tui.py [1-8]
```

## Configuration

Copy `.env.example` to `.env` and fill in:
- `GOOGLE_EMAIL` / `GOOGLE_PASSWORD` — Google account
- `ANTHROPIC_API_KEY` — Claude API key
- `GROUP_URL` — Google Groups URL to moderate

Browser session is persisted in `.browser_profile/` (gitignored).

## Architecture

Three-phase flow in `main.py` using separate `asyncio.run()` calls (Textual and Playwright each need their own event loop):

1. **Fetch + Analyze** (`fetch_and_analyze`) — starts Playwright, scrapes pending messages, fetches bodies by click-expand on each row, runs concurrent Claude API classification, stops browser
2. **TUI** (`run_tui`) — Textual app for reviewing messages, toggling hold/ok, previewing full bodies
3. **Approve** — fresh Playwright session clicks approve buttons and confirms dialogs

Key modules:
- `scraper.py` — `GoogleGroupsScraper` (Playwright automation), `PendingMessage` dataclass. Selector probing with caching for Google Groups' dynamic DOM.
- `analyzer.py` — `analyze_all` runs classification + summarization concurrently. `trim_for_analysis` strips email headers, signatures, and bottom-quoted replies while preserving inline replies.
- `tui.py` — `ModeratorApp` (main table), `PreviewScreen` (modal message view), `ConfirmApproveScreen`. Keybindings: h=toggle hold, a=approve all OK, p=preview, q=quit.
- `config.py` — loads `.env` via python-dotenv, exposes constants.

<!-- FLOW:BEGIN -->

# Python Conventions

## Architecture Patterns

- **Module structure** — Read the full module and its imports before modifying.
  Check for circular import risks and module-level state.
- **Function signatures** — If modifying a function signature, grep for all
  callers to ensure compatibility.
- **Scripts** — Check argument parsing, error handling, and exit codes. Verify
  the script is registered in any entry points or `bin/` wrappers.

## Test Conventions

- Check `conftest.py` for existing fixtures before creating new ones.
- Never duplicate fixture logic — reuse existing fixtures.
- Follow existing test patterns in the project.
- Targeted test command: `bin/test <tests/path/to/test_file.py>`

## CI Failure Fix Order

1. Lint violations — read the lint output carefully, fix the code
2. Test failures — understand the root cause, fix the code not the test
3. Coverage gaps — write the missing test

## Hard Rules

- Always read module imports before modifying any module.
- Always check `conftest.py` for existing fixtures before creating new ones.
- Never add lint exclusions — fix the code, not the linter configuration.
- After creating new files, verify they appear in `git status`. If missing, check `.git/info/exclude` and `.gitignore` for rules hiding them.
- Always run `bin/ci` and verify clean output before asking the user to check. Never ask the user to verify what you can verify yourself.

## Dependency Management

- Run `bin/dependencies` to update packages.

<!-- FLOW:END -->
