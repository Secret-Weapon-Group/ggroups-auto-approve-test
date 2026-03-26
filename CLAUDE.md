# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Google Groups pending message moderator. Scrapes pending messages from a Google Groups group via Playwright browser automation, classifies them with Claude AI (approve/hold), presents a Textual TUI for human review, then approves selected messages back through the browser.

## Commands

```bash
# Install dependencies (prefer uv)
uv pip install -r requirements.txt
uv run playwright install chromium

# Or with plain pip
pip install -r requirements.txt
playwright install chromium

# First run: authenticate with Google (opens visible browser)
uv run python main.py --login

# Normal use: fetch, analyze, review in TUI, approve
uv run python main.py

# Auto-approve without TUI
uv run python main.py --auto-approve

# Debug mode (saves screenshots to debug/, verbose logging)
uv run python main.py --debug

# Manual TUI diagnostic tests (1-8, interactive)
uv run python test_tui.py 1
```

## Architecture

Three-phase flow in `main.py`, split into separate `asyncio.run()` calls because Textual manages its own event loop and Playwright objects can't cross loop boundaries:

1. **Phase 1** (`fetch_and_analyze`): Start headless Playwright → verify login → scrape pending messages → fetch bodies by click-expand → run AI classification/summarization → stop browser
2. **Phase 2** (`run_tui`): Textual TUI for human review — user toggles hold/approve per message
3. **Phase 3** (`do_approve`): Fresh headless Playwright session → click approve buttons → verify removal

### Key modules

- **`scraper.py`** — `GoogleGroupsScraper` uses a persistent Chromium profile (`.browser_profile/`) for session reuse. Selector discovery is cached and uses multiple fallback strategies since Google Groups DOM varies. `PendingMessage` dataclass is the shared data model across all modules.
- **`analyzer.py`** — Calls Claude API (`claude-opus-4-0`) concurrently for classification, then summarizes long messages (>20 lines). `trim_for_analysis()` strips email headers, signatures, and bottom-quoted replies while preserving inline replies. Retries on 500/529.
- **`tui.py`** — `ModeratorApp` with `DataTable` list view, `PreviewScreen` modal for full message, `ConfirmApproveScreen` dialog. Keybindings: `h` toggle hold, `p`/Enter preview, `a` approve all OK, `q` quit.
- **`config.py`** — Loads `.env` via python-dotenv. Required vars: `GOOGLE_EMAIL`, `ANTHROPIC_API_KEY`, `GROUP_URL`.

## Environment

Requires a `.env` file (see `.env.example`). The `.browser_profile/` directory stores Chromium session state and is gitignored.
