"""Tests for mail_monitor.py — email-based Google Groups moderation."""

from email.mime.text import MIMEText
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


SAMPLE_MODERATION_BODY = """\
A message by alice@example.com requires your approval before being sent to
the forecast-chat group.

From: alice@example.com
Subject: My forecast for Q3

Message:
I think the probability of a recession in Q3 is around 30%.
This is based on leading indicators and recent Fed commentary.

To approve, reply to this email or visit:
https://groups.google.com/g/forecast-chat/pendingmsg/abc123
"""


def _make_moderation_email(
    *,
    subject="[forecast-chat] Please approve or reject: My forecast for Q3",
    from_addr="forecast-chat@googlegroups.com",
    reply_to="forecast-chat+approve-abc123@googlegroups.com",
    date="Mon, 15 Mar 2026 10:30:00 -0700",
    body=SAMPLE_MODERATION_BODY,
    message_id="<mod-abc123@googlegroups.com>",
):
    """Build a raw moderation email as bytes."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["Reply-To"] = reply_to
    msg["Date"] = date
    msg["Message-ID"] = message_id
    return msg.as_bytes()


class TestPendingMessage:
    """Test PendingMessage dataclass creation and defaults."""

    def test_create_with_all_fields(self):
        from mail_monitor import PendingMessage
        msg = PendingMessage(
            id="test-id",
            sender="alice@example.com",
            subject="Test",
            snippet="Preview",
            body="Full body",
            date="2026-03-15",
        )
        assert msg.id == "test-id"
        assert msg.sender == "alice@example.com"
        assert msg.status == "ok"
        assert msg.ai_recommendation == ""
        assert msg.reply_to == ""
        assert msg.message_uid == ""

    def test_new_fields_have_defaults(self):
        from mail_monitor import PendingMessage
        msg = PendingMessage(
            id="0", sender="a@b.com", subject="S",
            snippet="snip", body="body", date="d",
        )
        assert msg.reply_to == ""
        assert msg.message_uid == ""

    def test_new_fields_can_be_set(self):
        from mail_monitor import PendingMessage
        msg = PendingMessage(
            id="0", sender="a@b.com", subject="S",
            snippet="snip", body="body", date="d",
            reply_to="approve@example.com",
            message_uid="12345",
        )
        assert msg.reply_to == "approve@example.com"
        assert msg.message_uid == "12345"


class TestParseModerrationEmail:
    """Test _parse_moderation_email extracts fields correctly."""

    def test_extracts_reply_to(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert msg.reply_to == "forecast-chat+approve-abc123@googlegroups.com"

    def test_extracts_subject_strips_prefix(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert msg.subject == "My forecast for Q3"

    def test_extracts_sender_from_body(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert msg.sender == "alice@example.com"

    def test_extracts_body(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert "probability of a recession" in msg.body

    def test_extracts_date(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert "Mar 2026" in msg.date or "2026" in msg.date

    def test_sets_message_uid(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="42")
        assert msg.message_uid == "42"

    def test_sets_id_from_message_id_header(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email(message_id="<unique-id@example.com>")
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert msg.id == "<unique-id@example.com>"

    def test_malformed_email_missing_reply_to(self):
        from mail_monitor import MailMonitor
        msg_obj = MIMEText("Some body", "plain", "utf-8")
        msg_obj["Subject"] = "Test"
        msg_obj["From"] = "test@example.com"
        msg_obj["Date"] = "Mon, 15 Mar 2026 10:30:00 -0700"
        msg_obj["Message-ID"] = "<test@example.com>"
        raw = msg_obj.as_bytes()
        msg = MailMonitor._parse_moderation_email(raw, uid="1")
        assert msg.reply_to == ""

    def test_malformed_email_missing_body(self):
        from mail_monitor import MailMonitor
        msg_obj = MIMEText("", "plain", "utf-8")
        msg_obj["Subject"] = "[group] Please approve or reject: Test"
        msg_obj["From"] = "group@googlegroups.com"
        msg_obj["Reply-To"] = "approve@googlegroups.com"
        msg_obj["Date"] = "Mon, 15 Mar 2026 10:30:00 -0700"
        msg_obj["Message-ID"] = "<test@example.com>"
        raw = msg_obj.as_bytes()
        msg = MailMonitor._parse_moderation_email(raw, uid="1")
        assert msg.body == ""

    def test_subject_without_prefix_kept_as_is(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email(subject="Just a regular subject")
        msg = MailMonitor._parse_moderation_email(raw, uid="1")
        assert msg.subject == "Just a regular subject"


def _mock_imap_client(search_uids=None, fetch_data=None):
    """Build a mock aioimaplib IMAP4_SSL client.

    Args:
        search_uids: list of UID strings the search returns, e.g. ["1", "2"]
        fetch_data: dict mapping UID string -> raw email bytes
    """
    client = MagicMock()
    client.wait_hello_from_server = AsyncMock()
    client.login = AsyncMock(return_value=("OK", [b"LOGIN completed"]))
    client.select = AsyncMock(return_value=("OK", [b"EXISTS 10"]))
    client.logout = AsyncMock()

    # Search response
    uid_line = " ".join(search_uids) if search_uids else ""
    search_resp = MagicMock()
    search_resp.result = "OK"
    search_resp.lines = [uid_line.encode()] if uid_line else [b""]
    client.uid_search = AsyncMock(return_value=search_resp)

    # Fetch responses — one per UID
    if fetch_data:
        async def fake_uid(command, uid_str, *args):
            resp = MagicMock()
            if command == "fetch":
                raw = fetch_data.get(uid_str, b"")
                resp.result = "OK"
                resp.lines = [b"FETCH", raw, b")"]
                return resp
            if command == "store":
                resp.result = "OK"
                resp.lines = []
                return resp
            return resp
        client.uid = AsyncMock(side_effect=fake_uid)
    else:
        resp = MagicMock()
        resp.result = "OK"
        resp.lines = []
        client.uid = AsyncMock(return_value=resp)

    return client


class TestFetchPending:
    """Test MailMonitor.fetch_pending() IMAP fetch logic."""

    @pytest.mark.asyncio
    async def test_fetches_and_parses_emails(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        mock_client = _mock_imap_client(
            search_uids=["101"],
            fetch_data={"101": raw},
        )

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="forecast-chat@googlegroups.com",
        )
        monitor._imap = mock_client

        messages = await monitor.fetch_pending()

        assert len(messages) == 1
        assert messages[0].sender == "alice@example.com"
        assert messages[0].subject == "My forecast for Q3"
        assert messages[0].message_uid == "101"

    @pytest.mark.asyncio
    async def test_empty_inbox_returns_empty_list(self):
        from mail_monitor import MailMonitor
        mock_client = _mock_imap_client(search_uids=[])

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="forecast-chat@googlegroups.com",
        )
        monitor._imap = mock_client

        messages = await monitor.fetch_pending()
        assert messages == []

    @pytest.mark.asyncio
    async def test_multiple_emails_returned(self):
        from mail_monitor import MailMonitor
        raw1 = _make_moderation_email(message_id="<msg1@example.com>")
        raw2 = _make_moderation_email(
            message_id="<msg2@example.com>",
            subject="[forecast-chat] Please approve or reject: Another post",
        )
        mock_client = _mock_imap_client(
            search_uids=["10", "11"],
            fetch_data={"10": raw1, "11": raw2},
        )

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="forecast-chat@googlegroups.com",
        )
        monitor._imap = mock_client

        messages = await monitor.fetch_pending()
        assert len(messages) == 2
        assert messages[0].message_uid == "10"
        assert messages[1].message_uid == "11"

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        from mail_monitor import MailMonitor
        mock_client = _mock_imap_client()

        with patch("mail_monitor.aioimaplib") as mock_lib:
            mock_lib.IMAP4_SSL.return_value = mock_client
            monitor = MailMonitor(
                imap_host="imap.gmail.com",
                email_address="mod@example.com",
                password="secret",
                group_email="group@googlegroups.com",
            )
            await monitor.connect()
            mock_client.wait_hello_from_server.assert_awaited_once()
            mock_client.login.assert_awaited_once_with("mod@example.com", "secret")
            mock_client.select.assert_awaited_once_with("INBOX")

            await monitor.disconnect()
            mock_client.logout.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self):
        from mail_monitor import MailMonitor
        mock_client = _mock_imap_client()
        mock_client.login = AsyncMock(return_value=("NO", [b"LOGIN failed"]))

        with patch("mail_monitor.aioimaplib") as mock_lib:
            mock_lib.IMAP4_SSL.return_value = mock_client
            monitor = MailMonitor(
                imap_host="imap.gmail.com",
                email_address="mod@example.com",
                password="bad",
                group_email="group@googlegroups.com",
            )
            with pytest.raises(ConnectionError, match="IMAP login failed"):
                await monitor.connect()
