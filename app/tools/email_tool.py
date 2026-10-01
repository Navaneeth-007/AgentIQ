"""
Email delivery tool — SMTP with HTML body and file attachments.

Used by the agent only when the user explicitly requests email delivery.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None,
) -> dict:
    """
    Send a report via email.

    Args:
        to:          Recipient email address.
        subject:     Email subject.
        body:        Email body (HTML or plain text).
        attachments: Optional list of file paths to attach.

    Returns:
        {"success": True, "to": to, "subject": subject}
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("EMAIL_FROM", smtp_user)

    if not smtp_user or not smtp_password:
        raise EnvironmentError(
            "SMTP_USER and SMTP_PASSWORD must be set in .env to use email delivery."
        )

    msg = MIMEMultipart("mixed")
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject

    # Detect HTML body
    if "<html" in body.lower() or "<p>" in body.lower():
        msg.attach(MIMEText(body, "html"))
    else:
        msg.attach(MIMEText(body, "plain"))

    # Attach files
    for path_str in (attachments or []):
        path = Path(path_str)
        if path.exists():
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={path.name}")
                msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, to, msg.as_string())

    return {"success": True, "to": to, "subject": subject}
