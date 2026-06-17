"""
Email provider — sends via Gmail SMTP (primary) or Resend (fallback).
"""
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings
from app.integrations.base import IntegrationError, IntegrationNotConfiguredError


class EmailProvider:
    """Sends email via Gmail SMTP. Falls back to Resend if SMTP not configured."""

    def is_configured(self) -> bool:
        return bool(settings.SMTP_USER and settings.SMTP_PASS) or bool(settings.RESEND_API_KEY)

    def send(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str,
        from_email: str = None,
        from_name: str = None,
    ) -> dict:
        if not self.is_configured():
            raise IntegrationNotConfiguredError(
                "Neither SMTP nor RESEND_API_KEY configured"
            )

        f_email = from_email or settings.SMTP_USER or settings.FROM_EMAIL
        f_name = from_name or settings.FROM_NAME or "Creator Forge Team"

        # ── Try SMTP first ──────────────────────────────────────────────
        if settings.SMTP_USER and settings.SMTP_PASS:
            try:
                return self._send_smtp(
                    to_email, subject, body_html, body_text, f_email, f_name
                )
            except Exception as e:
                print(f"[SMTP] Send failed: {e}")
                # Fall through to Resend if configured
                if not settings.RESEND_API_KEY:
                    return {
                        "message_id": f"smtp_err_{uuid.uuid4().hex[:8]}",
                        "status": "failed",
                        "error": str(e),
                    }

        # ── Fallback: Resend ────────────────────────────────────────────
        if settings.RESEND_API_KEY:
            try:
                return self._send_resend(
                    to_email, subject, body_html, body_text, f_email, f_name
                )
            except Exception as e:
                print(f"[Resend] Send failed: {e}")
                return {
                    "message_id": f"resend_err_{uuid.uuid4().hex[:8]}",
                    "status": "failed",
                    "error": str(e),
                }

        raise IntegrationNotConfiguredError("No email provider available")

    # ── SMTP via Gmail ──────────────────────────────────────────────────
    def _send_smtp(
        self, to_email, subject, body_html, body_text, from_email, from_name
    ) -> dict:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        host = settings.SMTP_HOST or "smtp.gmail.com"
        port = settings.SMTP_PORT or 587

        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.sendmail(from_email, [to_email], msg.as_string())

        msg_id = f"smtp_{uuid.uuid4().hex[:12]}"
        print(f"[SMTP] Sent to {to_email} — {subject}")
        return {"message_id": msg_id, "status": "sent"}

    # ── Resend fallback ─────────────────────────────────────────────────
    def _send_resend(
        self, to_email, subject, body_html, body_text, from_email, from_name
    ) -> dict:
        import resend  # type: ignore[import-untyped]

        resend.api_key = settings.RESEND_API_KEY
        sender = f"{from_name} <{from_email}>"

        r = resend.Emails.send(
            {
                "from": sender,
                "to": [to_email],
                "subject": subject,
                "html": body_html,
                "text": body_text,
            }
        )
        print(f"[Resend] Sent to {to_email} — {subject}")
        return {"message_id": r.get("id"), "status": "sent"}

    def check_bounce_status(self, email: str) -> bool:
        return False


email_provider = EmailProvider()

