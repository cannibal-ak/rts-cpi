"""SMTP delivery + connection test, backed by the smtp_config row.

Single source of truth: the smtp_config table. This module reads it,
decrypts the password via core.encryption, and uses plain smtplib to
deliver messages.

Templates are kept inline (single template — the password reset
email). When a second template lands, factor templates into a
sibling module rather than growing this one.
"""

import logging
import smtplib
import socket
import time
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.orm import Session

from app.core.encryption import decrypt_secret
from app.models.smtp_config import SmtpConfig

logger = logging.getLogger("uvicorn.error")

# smtplib socket timeout for connect / handshake / auth. Short enough
# that the Test Connection button doesn't hang the admin UI, long
# enough to tolerate slow upstream auth.
CONNECT_TIMEOUT_SECONDS = 10


def get_smtp_config(db: Session) -> Optional[SmtpConfig]:
    """Return the single smtp_config row, or None if not yet configured."""
    return db.query(SmtpConfig).first()


def _build_message(
    *,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return msg


def _open_smtp(
    *,
    host: str,
    port: int,
    encryption: str,
    username: str,
    password: str,
) -> smtplib.SMTP:
    """Open an authenticated SMTP connection matching the encryption mode.

    Caller is responsible for closing the returned client.
    """
    if encryption == "SSL_TLS":
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=CONNECT_TIMEOUT_SECONDS)
    else:
        client = smtplib.SMTP(host, port, timeout=CONNECT_TIMEOUT_SECONDS)

    try:
        client.ehlo()
        if encryption == "STARTTLS":
            client.starttls()
            client.ehlo()
        client.login(username, password)
    except Exception:
        # Ensure we don't leak the socket on auth/handshake failure.
        try:
            client.close()
        finally:
            raise
    return client


def send_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Send an email using the saved smtp_config. Returns True on success.

    Never raises — every failure path is logged and returns False so
    callers can decide whether to leak the error to the user.
    """
    config = get_smtp_config(db)
    if config is None:
        logger.warning(
            "send_email: no smtp_config row — refusing to send to %s", to_email
        )
        return False

    try:
        password = decrypt_secret(config.password_encrypted)
    except Exception as e:
        logger.exception("send_email: failed to decrypt SMTP password: %s", e)
        return False

    msg = _build_message(
        from_email=config.from_email,
        from_name=config.from_name,
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )

    try:
        client = _open_smtp(
            host=config.host,
            port=config.port,
            encryption=config.encryption,
            username=config.username,
            password=password,
        )
    except (smtplib.SMTPException, socket.error, OSError) as e:
        logger.error(
            "send_email: SMTP connect/auth failed (%s:%s): %s",
            config.host, config.port, e,
        )
        return False

    try:
        client.send_message(msg)
        return True
    except smtplib.SMTPException as e:
        logger.error("send_email: SMTP send failed to %s: %s", to_email, e)
        return False
    finally:
        try:
            client.quit()
        except Exception:
            pass


def test_smtp_connection(
    *,
    host: str,
    port: int,
    encryption: str,
    username: str,
    password: str,
    from_email: str,
    from_name: str,
    to_email: str,
) -> dict:
    """Validate an SMTP config by connecting, authenticating, and
    sending one short message to ``to_email``.

    Returns ``{success, message, latency_ms}``. Never raises — failures
    are reported via the response so the admin sees a useful error
    instead of a 500.
    """
    start = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - start) * 1000)

    msg = _build_message(
        from_email=from_email,
        from_name=from_name,
        to_email=to_email,
        subject="RTS CPI — SMTP test message",
        body_text=(
            "This is a test message sent from the RTS CPI platform's "
            "admin Settings → Email page. If you received this, your "
            "SMTP configuration is working."
        ),
    )

    try:
        client = _open_smtp(
            host=host,
            port=port,
            encryption=encryption,
            username=username,
            password=password,
        )
    except Exception as e:
        return {
            "success": False,
            "message": f"Connect/auth failed: {e}",
            "latency_ms": _elapsed_ms(),
        }

    try:
        client.send_message(msg)
    except Exception as e:
        try:
            client.quit()
        except Exception:
            pass
        return {
            "success": False,
            "message": f"Send failed: {e}",
            "latency_ms": _elapsed_ms(),
        }

    try:
        client.quit()
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Test message delivered to {to_email}.",
        "latency_ms": _elapsed_ms(),
    }


def _reset_email_bodies(code: str, expiry_minutes: int) -> tuple[str, str]:
    plain = (
        f"Your RTS CPI password reset code is: {code}\n\n"
        f"This code expires in {expiry_minutes} minutes. "
        f"If you did not request a password reset, you can ignore this email."
    )
    html = (
        "<p>Your RTS CPI password reset code is:</p>"
        f"<p style=\"font-size:22px;font-weight:700;letter-spacing:4px;"
        f"font-family:'Courier New',monospace\">{code}</p>"
        f"<p>This code expires in <strong>{expiry_minutes} minutes</strong>. "
        "If you did not request a password reset, you can ignore this email.</p>"
    )
    return plain, html


def send_password_reset_email(
    db: Session,
    *,
    to_email: str,
    code: str,
    expiry_minutes: int,
) -> bool:
    """Specialised wrapper around send_email for the forgot-password flow."""
    plain, html = _reset_email_bodies(code, expiry_minutes)
    return send_email(
        db,
        to_email=to_email,
        subject="RTS CPI password reset code",
        body_text=plain,
        body_html=html,
    )
