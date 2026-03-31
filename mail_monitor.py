"""Email-based Google Groups moderation via IMAP/SMTP."""

import email as email_lib
import email.utils
import logging
import quopri
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from config import DEFAULT_FETCH_DAYS

import aioimaplib
import aiosmtplib
from email.mime.text import MIMEText

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
    mod_subject: str = ""  # original moderation email subject (contains confirmation code)
    message_uid: str = ""  # IMAP UID for post-processing


# Pattern to strip Google Groups moderation subject prefix
# e.g. "parisposse - Google Groups: Message Pending [{...}]"
# or   "[forecast-chat] Please approve or reject: My forecast for Q3"
_SUBJECT_PREFIX_RE = re.compile(
    r"^(?:.*?Google Groups:\s*Message Pending\s*|"
    r"\[.*?\]\s*Please approve(?:\s+or\s+reject)?:\s*)",
    re.IGNORECASE,
)

# Pattern to extract original sender from moderation email body
_SENDER_RE = re.compile(r"From:\s*(\S+@\S+)")

# Pattern to extract the message body section
_MESSAGE_BODY_RE = re.compile(
    r"Message:\s*\n(.*?)(?:\nTo approve|$)",
    re.DOTALL,
)


def _extract_inner_message(raw_email: bytes):
    """Extract the original message from a moderation email's message/rfc822 part.

    Python's email parser doesn't properly decode QP-encoded message/rfc822
    attachments, so we split on the MIME boundary and QP-decode manually.
    """
    msg = email_lib.message_from_bytes(raw_email)
    boundary = msg.get_boundary()
    if not boundary:
        return None

    parts = raw_email.split(b"--" + boundary.encode())
    for part in parts:
        # Find header/body separator (CRLF or LF)
        for sep in (b"\r\n\r\n", b"\n\n"):
            header_end = part.find(sep)
            if header_end != -1:
                break
        if header_end == -1:
            continue
        part_header = part[:header_end]
        if b"message/rfc822" not in part_header:
            continue
        inner_raw = part[header_end + len(sep):]
        # Check if QP-encoded by inspecting MIME headers of this part
        if b"quoted-printable" in part_header.lower():
            inner_raw = quopri.decodestring(inner_raw)
        return email_lib.message_from_bytes(inner_raw)
    return None


def _get_plain_text(msg) -> str:
    """Extract plain text body from an email Message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace") if payload else ""


class MailMonitor:
    """Monitors email for Google Groups moderation notifications."""

    def __init__(self, *, imap_host: str, email_address: str, password: str,
                 group_email: str, imap_port: int = 993,
                 smtp_host: str = "smtp.gmail.com", smtp_port: int = 587):
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._email = email_address
        self._password = password
        print(f'{self._email} = {self._password}')
        self._group_email = group_email
        self._imap = None

    async def connect(self):
        """Connect and authenticate to the IMAP server."""
        self._imap = aioimaplib.IMAP4_SSL(host=self._imap_host, port=self._imap_port)
        await self._imap.wait_hello_from_server()
        result, _ = await self._imap.login(self._email, self._password)
        if result != "OK":
            raise ConnectionError("IMAP login failed")
        await self._imap.select("INBOX")

    async def disconnect(self):
        """Logout from the IMAP server."""
        if self._imap:
            await self._imap.logout()
            self._imap = None

    async def fetch_pending(self, *, days: int = DEFAULT_FETCH_DAYS) -> list[PendingMessage]:
        """Fetch unread moderation emails and return as PendingMessage list."""
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        # Google Groups sends moderation emails from group+msgappr@googlegroups.com
        mod_from = self._group_email.replace("@", "+msgappr@")
        search_criteria = (
            f'UNSEEN FROM "{mod_from}" SUBJECT "Message Pending"'
            f' SINCE {since_date}'
        )
        response = await self._imap.uid_search(search_criteria)

        if response.result != "OK":
            log.warning("IMAP search failed: %s", response.lines)
            return []

        uid_line = response.lines[0] if response.lines else b""
        if isinstance(uid_line, bytes):
            uid_line = uid_line.decode("utf-8", errors="replace")
        uids = uid_line.split()
        if not uids or uids == [""]:
            return []

        messages = []
        for uid in uids:
            resp = await self._imap.uid("fetch", uid, "(BODY.PEEK[])")
            if resp.result != "OK" or len(resp.lines) < 2:
                log.warning("Failed to fetch UID %s", uid)
                continue
            raw_email = resp.lines[1]
            msg = self._parse_moderation_email(raw_email, uid=uid)
            messages.append(msg)

        return messages

    async def approve_messages(self, messages: list[PendingMessage]) -> dict[str, bool]:
        """Approve messages by replying to their moderation emails via SMTP.

        Returns dict mapping message id -> success boolean.
        """
        if not messages:
            return {}

        results = {}
        smtp = aiosmtplib.SMTP(hostname=self._smtp_host, port=self._smtp_port,
                               use_tls=False, start_tls=True)
        await smtp.connect()
        await smtp.login(self._email, self._password)

        try:
            for msg in messages:
                try:
                    reply = MIMEText("Approve", "plain", "utf-8")
                    reply["To"] = msg.reply_to
                    reply["From"] = self._email
                    reply["Subject"] = f"Re: {msg.mod_subject}"
                    reply["In-Reply-To"] = msg.id
                    reply["References"] = msg.id

                    await smtp.sendmail(
                        self._email,
                        [msg.reply_to],
                        reply.as_string(),
                    )

                    # Mark original moderation email as read
                    if self._imap and msg.message_uid:
                        await self._imap.uid("store", msg.message_uid,
                                             "+FLAGS", r"(\Seen)")

                    results[msg.id] = True
                    log.info("Approved: %s", msg.subject)
                except Exception:
                    log.exception("Failed to approve: %s", msg.subject)
                    results[msg.id] = False
        finally:
            await smtp.quit()

        return results

    async def mark_seen(self, messages: list[PendingMessage]) -> None:
        """Mark messages as \\Seen in IMAP without sending any email."""
        for msg in messages:
            if not self._imap or not msg.message_uid:
                continue
            try:
                await self._imap.uid("store", msg.message_uid,
                                     "+FLAGS", r"(\Seen)")
            except Exception:
                log.exception("Failed to mark as seen: %s", msg.subject)

    @staticmethod
    def _parse_moderation_email(raw_email: bytes, *, uid: str = "") -> PendingMessage:
        """Parse a raw moderation email into a PendingMessage."""
        msg = email_lib.message_from_bytes(raw_email)

        # Extract moderation envelope headers
        reply_to_raw = msg.get("Reply-To", "") or msg.get("From", "")
        _, reply_to = email.utils.parseaddr(reply_to_raw)
        message_id = msg.get("Message-ID", "")
        mod_subject = msg.get("Subject", "")

        # Extract the original message from the attached message/rfc822 part.
        # Google Groups embeds the original post as a QP-encoded attachment.
        inner = _extract_inner_message(raw_email)

        if inner:
            sender = inner.get("From", "")
            subject = inner.get("Subject", "")
            date = inner.get("Date", "")
            body_text = _get_plain_text(inner)
        else:
            # Fallback: parse from the moderation email itself
            raw_subject = msg.get("Subject", "")
            subject = _SUBJECT_PREFIX_RE.sub("", raw_subject)
            date = msg.get("Date", "")
            body_text = _get_plain_text(msg)
            sender_match = _SENDER_RE.search(body_text)
            sender = sender_match.group(1) if sender_match else ""
            message_match = _MESSAGE_BODY_RE.search(body_text)
            if message_match:
                body_text = message_match.group(1).strip()

        snippet = body_text[:100] if body_text else ""

        return PendingMessage(
            id=message_id,
            sender=sender,
            subject=subject,
            snippet=snippet,
            body=body_text,
            date=date,
            reply_to=reply_to,
            mod_subject=mod_subject,
            message_uid=uid,
        )
