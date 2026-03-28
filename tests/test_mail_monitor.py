"""Tests for mail_monitor.py — email-based Google Groups moderation."""

from email.mime.multipart import MIMEMultipart
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

    def test_mod_subject_preserves_original(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="100")
        assert msg.mod_subject == "[forecast-chat] Please approve or reject: My forecast for Q3"

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
        assert msg.reply_to == "test@example.com"

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


def _make_multipart_moderation_email(
    *,
    inner_from="Alice <alice@example.com>",
    inner_subject="My forecast for Q3",
    inner_body="I think the probability of a recession is 30%.",
    inner_date="Mon, 15 Mar 2026 10:30:00 -0700",
    mod_from="group+msgappr@googlegroups.com",
    reply_to="",
    message_id="<mod-abc123@googlegroups.com>",
    qp_encode=True,
):
    """Build a multipart moderation email with an attached message/rfc822."""
    import quopri

    outer = MIMEMultipart("mixed")
    outer["From"] = mod_from
    outer["Subject"] = "group - Google Groups: Message Pending [{abc123}]"
    outer["Date"] = "Mon, 15 Mar 2026 11:00:00 -0700"
    outer["Message-ID"] = message_id
    if reply_to:
        outer["Reply-To"] = reply_to

    # Moderation notification part
    notification = MIMEText(
        "A message has been sent to the group and is awaiting approval.\n"
        "You can approve this message by replying to this email.\n",
        "plain", "utf-8",
    )
    outer.attach(notification)

    # Build the inner message as raw bytes
    inner = MIMEText(inner_body, "plain", "utf-8")
    inner["From"] = inner_from
    inner["Subject"] = inner_subject
    inner["Date"] = inner_date
    inner_bytes = inner.as_bytes()

    # Attach as message/rfc822 with QP encoding (matches real Gmail format)
    from email.mime.base import MIMEBase
    attachment = MIMEBase("message", "rfc822")
    if qp_encode:
        attachment["Content-Transfer-Encoding"] = "quoted-printable"
        attachment.set_payload(quopri.encodestring(inner_bytes).decode("ascii"))
    else:
        attachment.set_payload(inner_bytes.decode("ascii"))
    outer.attach(attachment)

    return outer.as_bytes()


class TestExtractInnerMessage:
    """Test _extract_inner_message extracts the attached original message."""

    def test_extracts_from_qp_encoded_rfc822(self):
        from mail_monitor import _extract_inner_message
        raw = _make_multipart_moderation_email()
        inner = _extract_inner_message(raw)
        assert inner is not None
        assert inner["From"] == "Alice <alice@example.com>"
        assert inner["Subject"] == "My forecast for Q3"

    def test_extracts_from_non_qp_rfc822(self):
        from mail_monitor import _extract_inner_message
        raw = _make_multipart_moderation_email(qp_encode=False)
        inner = _extract_inner_message(raw)
        assert inner is not None
        assert inner["From"] == "Alice <alice@example.com>"

    def test_returns_none_for_non_multipart(self):
        from mail_monitor import _extract_inner_message
        simple = MIMEText("Just a plain email", "plain", "utf-8")
        assert _extract_inner_message(simple.as_bytes()) is None

    def test_returns_none_when_no_rfc822_part(self):
        from mail_monitor import _extract_inner_message
        outer = MIMEMultipart("mixed")
        outer.attach(MIMEText("Part 1", "plain", "utf-8"))
        outer.attach(MIMEText("Part 2", "plain", "utf-8"))
        assert _extract_inner_message(outer.as_bytes()) is None


class TestGetPlainText:
    """Test _get_plain_text extracts body from various email formats."""

    def test_simple_message(self):
        from mail_monitor import _get_plain_text
        import email as email_lib
        msg = email_lib.message_from_bytes(
            MIMEText("Hello world", "plain", "utf-8").as_bytes()
        )
        assert _get_plain_text(msg) == "Hello world"

    def test_multipart_message(self):
        from mail_monitor import _get_plain_text
        import email as email_lib
        outer = MIMEMultipart("alternative")
        outer.attach(MIMEText("Plain text body", "plain", "utf-8"))
        outer.attach(MIMEText("<p>HTML body</p>", "html", "utf-8"))
        msg = email_lib.message_from_bytes(outer.as_bytes())
        assert _get_plain_text(msg) == "Plain text body"

    def test_multipart_no_plain_text(self):
        from mail_monitor import _get_plain_text
        import email as email_lib
        outer = MIMEMultipart("alternative")
        outer.attach(MIMEText("<p>HTML only</p>", "html", "utf-8"))
        msg = email_lib.message_from_bytes(outer.as_bytes())
        assert _get_plain_text(msg) == ""

    def test_empty_payload(self):
        from mail_monitor import _get_plain_text
        import email as email_lib
        msg = email_lib.message_from_bytes(
            MIMEText("", "plain", "utf-8").as_bytes()
        )
        assert _get_plain_text(msg) == ""


class TestParseModerationEmailWithAttachment:
    """Test _parse_moderation_email with multipart/rfc822 format."""

    def test_extracts_inner_fields(self):
        from mail_monitor import MailMonitor
        raw = _make_multipart_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="200")
        assert msg.sender == "Alice <alice@example.com>"
        assert msg.subject == "My forecast for Q3"
        assert "probability of a recession" in msg.body

    def test_subject_is_inner_mod_subject_is_outer(self):
        from mail_monitor import MailMonitor
        raw = _make_multipart_moderation_email(
            inner_subject="Q3 recession forecast",
        )
        msg = MailMonitor._parse_moderation_email(raw, uid="200")
        assert msg.subject == "Q3 recession forecast"
        assert msg.mod_subject == "group - Google Groups: Message Pending [{abc123}]"

    def test_falls_back_to_from_when_no_reply_to(self):
        from mail_monitor import MailMonitor
        raw = _make_multipart_moderation_email()
        msg = MailMonitor._parse_moderation_email(raw, uid="200")
        assert msg.reply_to == "group+msgappr@googlegroups.com"


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
    async def test_search_failure_returns_empty_list(self):
        from mail_monitor import MailMonitor
        mock_client = _mock_imap_client()
        search_resp = MagicMock()
        search_resp.result = "NO"
        search_resp.lines = [b"Search failed"]
        mock_client.uid_search = AsyncMock(return_value=search_resp)

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
    async def test_fetch_failure_skips_uid(self):
        from mail_monitor import MailMonitor
        raw = _make_moderation_email()
        mock_client = _mock_imap_client(search_uids=["10", "11"])

        async def fake_uid(command, uid_str, *args):
            resp = MagicMock()
            if command == "fetch" and uid_str == "10":
                resp.result = "NO"
                resp.lines = [b"Fetch failed"]
                return resp
            if command == "fetch" and uid_str == "11":
                resp.result = "OK"
                resp.lines = [b"FETCH", raw, b")"]
                return resp
            return resp
        mock_client.uid = AsyncMock(side_effect=fake_uid)

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="forecast-chat@googlegroups.com",
        )
        monitor._imap = mock_client

        messages = await monitor.fetch_pending()
        assert len(messages) == 1
        assert messages[0].message_uid == "11"

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


class TestApproveMessages:
    """Test MailMonitor.approve_messages() SMTP approval logic."""

    def _make_pending(self, *, msg_id="<mod-1@example.com>", uid="100",
                      reply_to="group+approve-1@googlegroups.com",
                      subject="Test subject"):
        from mail_monitor import PendingMessage
        return PendingMessage(
            id=msg_id, sender="alice@example.com", subject=subject,
            snippet="snip", body="body", date="2026-03-15",
            reply_to=reply_to, message_uid=uid,
        )

    @pytest.mark.asyncio
    async def test_sends_approval_reply(self):
        from mail_monitor import MailMonitor
        msg = self._make_pending()
        mock_client = _mock_imap_client()
        mock_smtp = AsyncMock()
        mock_smtp.sendmail = AsyncMock()

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="group@googlegroups.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
        )
        monitor._imap = mock_client

        with patch("mail_monitor.aiosmtplib") as mock_lib:
            mock_lib.SMTP.return_value = mock_smtp
            results = await monitor.approve_messages([msg])

        assert results[msg.id] is True
        mock_smtp.sendmail.assert_awaited_once()
        # Verify the reply was sent to the reply_to address
        call_args = mock_smtp.sendmail.call_args
        assert call_args[0][1] == [msg.reply_to]

    @pytest.mark.asyncio
    async def test_marks_email_as_read_after_approval(self):
        from mail_monitor import MailMonitor
        msg = self._make_pending()
        mock_client = _mock_imap_client()
        mock_smtp = AsyncMock()
        mock_smtp.sendmail = AsyncMock()

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="group@googlegroups.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
        )
        monitor._imap = mock_client

        with patch("mail_monitor.aiosmtplib") as mock_lib:
            mock_lib.SMTP.return_value = mock_smtp
            await monitor.approve_messages([msg])

        # Verify IMAP store was called to mark as read
        mock_client.uid.assert_awaited()
        store_calls = [
            c for c in mock_client.uid.call_args_list
            if c[0][0] == "store"
        ]
        assert len(store_calls) == 1
        assert store_calls[0][0][1] == "100"  # UID

    @pytest.mark.asyncio
    async def test_handles_smtp_failure_gracefully(self):
        from mail_monitor import MailMonitor
        msg = self._make_pending()
        mock_client = _mock_imap_client()
        mock_smtp = AsyncMock()
        mock_smtp.sendmail = AsyncMock(side_effect=Exception("SMTP error"))

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="group@googlegroups.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
        )
        monitor._imap = mock_client

        with patch("mail_monitor.aiosmtplib") as mock_lib:
            mock_lib.SMTP.return_value = mock_smtp
            results = await monitor.approve_messages([msg])

        assert results[msg.id] is False

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        from mail_monitor import MailMonitor
        msg1 = self._make_pending(msg_id="<m1>", uid="10",
                                  reply_to="approve-1@g.com")
        msg2 = self._make_pending(msg_id="<m2>", uid="11",
                                  reply_to="approve-2@g.com")
        mock_client = _mock_imap_client()
        call_count = 0

        async def sendmail_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("SMTP error on second")

        mock_smtp = AsyncMock()
        mock_smtp.sendmail = AsyncMock(side_effect=sendmail_side_effect)

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="group@googlegroups.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
        )
        monitor._imap = mock_client

        with patch("mail_monitor.aiosmtplib") as mock_lib:
            mock_lib.SMTP.return_value = mock_smtp
            results = await monitor.approve_messages([msg1, msg2])

        assert results["<m1>"] is True
        assert results["<m2>"] is False

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self):
        from mail_monitor import MailMonitor
        mock_client = _mock_imap_client()

        monitor = MailMonitor(
            imap_host="imap.gmail.com",
            email_address="mod@example.com",
            password="secret",
            group_email="group@googlegroups.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
        )
        monitor._imap = mock_client

        with patch("mail_monitor.aiosmtplib"):
            results = await monitor.approve_messages([])

        assert results == {}
