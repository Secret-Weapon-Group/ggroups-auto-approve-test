"""Email-based Google Groups moderation via IMAP/SMTP."""

import email as email_lib
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("mail_monitor")


@dataclass
class PendingMessage:
    """A pending message from Google Groups."""
    id: str  # Message-ID header from the moderation email
    sender: str
    subject: str
    snippet: str  # short preview text
    body: str  # full message body
    date: str
    status: str = "ok"  # "ok" or "hold"
    ai_recommendation: str = ""  # "approve" or "hold"
    ai_reason: str = ""
    ai_summary: str = ""  # summary for long messages
    reply_to: str = ""  # approval reply address from moderation email
    message_uid: str = ""  # IMAP UID for post-processing


# Pattern to strip Google Groups moderation subject prefix
# e.g. "[forecast-chat] Please approve or reject: My forecast for Q3"
_SUBJECT_PREFIX_RE = re.compile(
    r"^\[.*?\]\s*Please approve(?:\s+or\s+reject)?:\s*",
    re.IGNORECASE,
)

# Pattern to extract original sender from moderation email body
_SENDER_RE = re.compile(r"From:\s*(\S+@\S+)")

# Pattern to extract the message body section
_MESSAGE_BODY_RE = re.compile(
    r"Message:\s*\n(.*?)(?:\nTo approve|$)",
    re.DOTALL,
)


class MailMonitor:
    """Monitors email for Google Groups moderation notifications."""

    @staticmethod
    def _parse_moderation_email(raw_email: bytes, *, uid: str = "") -> PendingMessage:
        """Parse a raw moderation email into a PendingMessage."""
        msg = email_lib.message_from_bytes(raw_email)

        # Extract headers
        reply_to = msg.get("Reply-To", "")
        date = msg.get("Date", "")
        message_id = msg.get("Message-ID", "")

        # Strip subject prefix
        raw_subject = msg.get("Subject", "")
        subject = _SUBJECT_PREFIX_RE.sub("", raw_subject)

        # Get plain text body
        if msg.is_multipart():
            body_text = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode("utf-8", errors="replace")
                    break
        else:
            payload = msg.get_payload(decode=True)
            body_text = payload.decode("utf-8", errors="replace") if payload else ""

        # Extract original sender from body
        sender_match = _SENDER_RE.search(body_text)
        sender = sender_match.group(1) if sender_match else ""

        # Extract the actual message content
        message_match = _MESSAGE_BODY_RE.search(body_text)
        message_body = message_match.group(1).strip() if message_match else body_text

        # Build snippet from first line of body
        snippet = message_body[:100] if message_body else ""

        return PendingMessage(
            id=message_id,
            sender=sender,
            subject=subject,
            snippet=snippet,
            body=message_body,
            date=date,
            reply_to=reply_to,
            message_uid=uid,
        )
