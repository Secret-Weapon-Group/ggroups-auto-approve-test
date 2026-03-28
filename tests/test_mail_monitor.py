"""Tests for mail_monitor.py — email-based Google Groups moderation."""

from email.mime.text import MIMEText


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
