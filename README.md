# Google Groups Moderator

Automates Google Groups message moderation. Reads moderation notification emails via IMAP, classifies them with a two-layer system (pattern checks + Claude API), presents a terminal UI for human review, and approves by replying via SMTP.

## Prerequisites

- Python 3.12+
- A Gmail account with [2-Step Verification](https://myaccount.google.com/security) enabled
- An [App Password](https://myaccount.google.com/apppasswords) for the Gmail account
- Moderator or owner role on the Google Group you want to moderate
- An [Anthropic API key](https://console.anthropic.com/) for AI classification

## Installation

```bash
git clone <repo-url>
cd ggroups-auto-approve-test
bin/dependencies
```

`bin/dependencies` creates a virtual environment and installs all packages from `requirements.txt`.

## Gmail Setup

1. **Enable IMAP**: Gmail Settings > See all settings > Forwarding and POP/IMAP > Enable IMAP
2. **Create an App Password**: Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create a new app password, and copy the 16-character code

## Configuration

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_EMAIL` | Your Gmail address | (required) |
| `GOOGLE_PASSWORD` | Gmail App Password (16-char code from step above) | (required) |
| `ANTHROPIC_API_KEY` | Claude API key for AI classification | (required) |
| `GROUP_EMAIL` | Google Groups address (e.g. `mygroup@googlegroups.com`) | (required) |
| `IMAP_HOST` | IMAP server hostname | `imap.gmail.com` |
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |

## Usage

```bash
# Normal run: fetch pending messages, classify with AI, review in TUI, approve
python main.py

# Auto-approve AI-approved messages without TUI
python main.py --auto-approve

# Only fetch emails from the last 7 days (default: 2)
python main.py --days 7

# Enable debug logging
python main.py --debug

# Combine flags
python main.py --auto-approve --days 5 --debug
```

## TUI Keybindings

### Main View

| Key | Action |
|-----|--------|
| `q` | Quit without approving |
| `h` | Toggle Hold/OK for selected message |
| `a` | Approve all messages marked OK |
| `p` / `Enter` | Preview full message |
| `r` | Refresh |

### Preview

| Key | Action |
|-----|--------|
| `Escape` | Back to main view |
| `h` | Toggle Hold/OK |
| `c` | Copy message to clipboard |

## How It Works

### Three-Phase Flow

The tool runs in three separate phases (each with its own `asyncio.run()` call, since Textual manages its own event loop):

1. **Fetch + Analyze** -- Connects to IMAP, searches for unread moderation emails from the last N days, parses them, and runs concurrent AI classification
2. **TUI Review** -- Textual terminal app for reviewing messages, toggling hold/ok, and previewing full message bodies
3. **Approve** -- Opens a fresh SMTP connection, replies "Approve" to each approved moderation email, and marks originals as read

### Two-Layer Classification

1. **Layer 1 -- Pattern checks** (no API calls): Detects spam, URL-only messages, and low-substance reactions (e.g. "+1", "thanks")
2. **Layer 2 -- Claude API**: If pattern checks pass, sends the message to Claude for nuanced classification

The system is **fail-open**: any exception during classification results in an "approve" recommendation, so messages are never silently dropped.

## Development

### Running Tests

```bash
# Full CI pipeline (lint + tests with 100% coverage requirement)
bin/ci

# Run a specific test file
bin/test tests/test_classifier.py

# Interactive TUI diagnostics (manual, not automated)
python test_tui.py [1-5]
```

### Project Structure

```
main.py              # CLI entry point, three-phase orchestration
config.py            # Environment configuration via .env
mail_monitor.py      # IMAP/SMTP operations, email parsing
analyzer.py          # AI analysis (classification + summarization)
classifier.py        # Two-layer classification (pattern checks + LLM)
tui.py               # Textual terminal UI
checks/              # Layer 1 pattern-matching checks
  spam.py            #   Spam detection
  url_only.py        #   URL-only message detection
  no_substance.py    #   Low-substance reaction detection
tests/               # Automated test suite (100% coverage)
bin/                  # Helper scripts (ci, test, dependencies)
```
