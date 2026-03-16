"""Terminal UI for Google Groups message moderation using Textual."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    Label,
    Button,
)
from textual.css.query import NoMatches

from scraper import PendingMessage


class PreviewScreen(ModalScreen[None]):
    """Modal screen to preview a full message."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("h", "toggle_hold", "Toggle Hold"),
        Binding("c", "copy_body", "Copy"),
    ]

    DEFAULT_CSS = """
    PreviewScreen {
        align: center middle;
    }
    #preview-container {
        width: 95%;
        height: 90%;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    #preview-header {
        height: auto;
        margin-bottom: 1;
        color: $text;
    }
    #preview-header .label {
        color: $accent;
        text-style: bold;
    }
    #ai-box {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        border: round $warning;
        background: $surface-darken-1;
    }
    #ai-box.approve {
        border: round $success;
    }
    #ai-box.hold {
        border: round $error;
    }
    #summary-box {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        border: round $primary;
        background: $surface-darken-1;
    }
    #message-body {
        height: 1fr;
        padding: 1;
        border: round $primary-background;
        overflow-y: auto;
    }
    #preview-footer {
        height: auto;
        dock: bottom;
        margin-top: 1;
    }
    #preview-status {
        text-style: bold;
    }
    """

    def __init__(self, msg: PendingMessage):
        super().__init__()
        self.msg = msg

    def compose(self) -> ComposeResult:
        status_text = "HOLD" if self.msg.status == "hold" else "OK"
        status_color = "red" if self.msg.status == "hold" else "green"

        ai_text = f"AI: {self.msg.ai_recommendation.upper()}"
        if self.msg.ai_reason:
            ai_text += f" — {self.msg.ai_reason}"

        ai_class = "hold" if self.msg.ai_recommendation == "hold" else "approve"

        with Vertical(id="preview-container"):
            yield Static(
                f"[bold]From:[/bold] {self.msg.sender}\n"
                f"[bold]Subject:[/bold] {self.msg.subject}\n"
                f"[bold]Date:[/bold] {self.msg.date}\n"
                f"[bold]Status:[/bold] [{status_color}]{status_text}[/{status_color}]",
                id="preview-header",
            )
            yield Static(ai_text, id="ai-box", classes=ai_class)

            if self.msg.ai_summary:
                yield Static(
                    f"[bold]Summary:[/bold] {self.msg.ai_summary}",
                    id="summary-box",
                )

            body = self.msg.body or self.msg.snippet or "(no content)"
            with VerticalScroll(id="message-body"):
                yield Static(body, id="body-text")

            yield Static(
                "[bold]h[/bold] Toggle Hold  [bold]c[/bold] Copy  [bold]Esc[/bold] Back  [dim](Option+drag to select text)[/dim]",
                id="preview-footer",
            )

    def action_copy_body(self):
        """Copy the full preview (headers + AI + body) to clipboard."""
        import base64, sys
        m = self.msg
        status = "HOLD" if m.status == "hold" else "OK"
        ai = f"{m.ai_recommendation.upper()}: {m.ai_reason}" if m.ai_reason else m.ai_recommendation.upper()
        parts = [
            f"From: {m.sender}",
            f"Subject: {m.subject}",
            f"Date: {m.date}",
            f"Status: {status}",
            f"AI: {ai}",
        ]
        if m.ai_summary:
            parts.append(f"Summary: {m.ai_summary}")
        parts.append("")
        parts.append(m.body or m.snippet or "(no content)")
        text = "\n".join(parts)
        # OSC 52 clipboard escape sequence (works in iTerm2, most modern terminals)
        encoded = base64.b64encode(text.encode()).decode()
        sys.stdout.write(f"\033]52;c;{encoded}\a")
        sys.stdout.flush()
        self.notify("Copied to clipboard")

    def action_toggle_hold(self):
        self.msg.status = "ok" if self.msg.status == "hold" else "hold"
        # Update the header status display in place (don't dismiss)
        status_text = "HOLD" if self.msg.status == "hold" else "OK"
        status_color = "red" if self.msg.status == "hold" else "green"
        try:
            header = self.query_one("#preview-header", Static)
            header.update(
                f"[bold]From:[/bold] {self.msg.sender}\n"
                f"[bold]Subject:[/bold] {self.msg.subject}\n"
                f"[bold]Date:[/bold] {self.msg.date}\n"
                f"[bold]Status:[/bold] [{status_color}]{status_text}[/{status_color}]"
            )
        except NoMatches:
            pass


class ConfirmApproveScreen(ModalScreen[bool]):
    """Confirmation dialog for approving messages."""

    DEFAULT_CSS = """
    ConfirmApproveScreen {
        align: center middle;
    }
    #confirm-container {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $accent;
        padding: 2 4;
    }
    #confirm-buttons {
        height: auto;
        margin-top: 2;
        align: center middle;
    }
    #confirm-buttons Button {
        margin: 0 2;
    }
    """

    def __init__(self, count: int):
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Label(
                f"Approve {self.count} message(s) marked OK?\n\n"
                "Messages marked HOLD will remain pending.",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes, Approve", variant="success", id="btn-yes")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "btn-yes")


class ModeratorApp(App):
    """Main TUI application for Google Groups moderation."""

    TITLE = "Google Groups Moderator"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("h", "toggle_hold", "Toggle Hold"),
        Binding("a", "approve_all", "Approve All OK"),
        Binding("p", "preview", "Preview"),
        Binding("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    Screen {
        width: 100%;
    }
    #title-bar {
        width: 100%;
        height: auto;
        padding: 1 2;
        background: $accent;
        color: $text;
        text-style: bold;
        text-align: center;
    }
    DataTable {
        width: 100%;
        height: 1fr;
    }
    DataTable > .datatable--cursor {
        background: $accent 40%;
    }
    """

    def __init__(
        self,
        messages: list[PendingMessage],
        on_approve: callable = None,
        on_refresh: callable = None,
    ):
        super().__init__()
        self.messages = messages
        self.on_approve = on_approve
        self.on_refresh = on_refresh
        self._approved = False

    @property
    def approved(self) -> bool:
        return self._approved

    def compose(self) -> ComposeResult:
        group_name = "forecast-chat"  # TODO: extract from URL
        ok_count = sum(1 for m in self.messages if m.status == "ok")
        hold_count = sum(1 for m in self.messages if m.status == "hold")
        yield Static(
            f"Google Groups Moderator — {group_name}  "
            f"({len(self.messages)} pending, {ok_count} OK, {hold_count} HOLD)",
            id="title-bar",
        )
        yield DataTable(id="msg-table")
        yield Footer()

    def on_mount(self):
        self._refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Open preview when Enter is pressed on a row."""
        self.action_preview()

    def _refresh_table(self):
        table = self.query_one("#msg-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Status", "From", "Subject", "AI Recommendation")
        table.cursor_type = "row"

        for msg in self.messages:
            status = "[red]HOLD[/red]" if msg.status == "hold" else "[green] OK [/green]"
            ai_text = msg.ai_recommendation.upper()
            if msg.ai_reason:
                ai_text += f": {msg.ai_reason}"
            if msg.ai_recommendation == "hold":
                ai_text = f"[red]{ai_text}[/red]"
            else:
                ai_text = f"[green]{ai_text}[/green]"

            table.add_row(status, msg.sender, msg.subject, ai_text)

        self._update_title()

    def _update_title(self):
        ok_count = sum(1 for m in self.messages if m.status == "ok")
        hold_count = sum(1 for m in self.messages if m.status == "hold")
        try:
            title = self.query_one("#title-bar", Static)
            title.update(
                f"Google Groups Moderator — forecast-chat  "
                f"({len(self.messages)} pending, {ok_count} OK, {hold_count} HOLD)"
            )
        except NoMatches:
            pass

    def _get_selected_index(self) -> int | None:
        table = self.query_one("#msg-table", DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.messages):
            return table.cursor_row
        return None

    def action_toggle_hold(self):
        idx = self._get_selected_index()
        if idx is None:
            return
        msg = self.messages[idx]
        msg.status = "ok" if msg.status == "hold" else "hold"
        self._refresh_table()
        # Restore cursor position
        table = self.query_one("#msg-table", DataTable)
        table.move_cursor(row=idx)

    def action_preview(self):
        idx = self._get_selected_index()
        if idx is None:
            return
        msg = self.messages[idx]

        def on_dismiss(_result):
            self._refresh_table()
            table = self.query_one("#msg-table", DataTable)
            table.move_cursor(row=idx)

        self.push_screen(PreviewScreen(msg), callback=on_dismiss)

    def action_approve_all(self):
        ok_messages = [m for m in self.messages if m.status == "ok"]
        if not ok_messages:
            self.notify("No messages marked OK to approve.", severity="warning")
            return

        def on_confirm(confirmed: bool):
            if confirmed:
                self.exit(result=[m for m in self.messages if m.status == "ok"])

        self.push_screen(ConfirmApproveScreen(len(ok_messages)), callback=on_confirm)

    def action_refresh(self):
        if self.on_refresh:
            self.notify("Refreshing...", severity="information")
            self.on_refresh()


def run_tui(
    messages: list[PendingMessage],
    on_approve: callable = None,
    on_refresh: callable = None,
) -> list[PendingMessage] | None:
    """Run the TUI and return messages to approve, or None if quit."""
    import asyncio

    # Clear any stale event loop left by prior asyncio.run() calls,
    # so Textual can create its own cleanly.
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = ModeratorApp(messages, on_approve=on_approve, on_refresh=on_refresh)
    result = app.run()
    return result
