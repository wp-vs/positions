"""Send position report via email using SMTP.

Configure via environment variables:
    SMTP_HOST      - SMTP server (default: 127.0.0.1 for ProtonMail Bridge)
    SMTP_PORT      - SMTP port (default: 1025 for ProtonMail Bridge)
    SMTP_USER      - SMTP username / login email
    SMTP_PASS      - SMTP password / app password
    SMTP_USE_TLS   - "true" for STARTTLS, "false" for SSL (default: true)
    EMAIL_FROM     - Sender address (defaults to SMTP_USER)
    EMAIL_TO       - Recipient address
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def _get_config(recipient_override: str | None = None) -> dict:
    """Load SMTP config from environment variables."""
    config = {
        "host": os.environ.get("SMTP_HOST", "127.0.0.1"),
        "port": int(os.environ.get("SMTP_PORT", "1025")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
        "from_addr": os.environ.get("EMAIL_FROM", ""),
        "to_addr": recipient_override or os.environ.get("EMAIL_TO", ""),
    }

    # Default from_addr to user if not set
    if not config["from_addr"]:
        config["from_addr"] = config["user"]

    return config


def send_report(html_body: str, recipient: str | None = None) -> None:
    """Send the HTML report via email.

    Args:
        html_body: The HTML content to send as the email body.
        recipient: Override recipient address (otherwise uses EMAIL_TO env var).

    Raises:
        ValueError: If required config is missing.
        smtplib.SMTPException: If sending fails.
    """
    config = _get_config(recipient)

    if not config["to_addr"]:
        raise ValueError(
            "No recipient address configured.\n"
            "Set EMAIL_TO environment variable or pass --email-to <address>"
        )
    if not config["user"]:
        raise ValueError(
            "No SMTP credentials configured.\n"
            "Set SMTP_USER and SMTP_PASS environment variables.\n"
            "See .env.example for all available settings."
        )

    # Build the email
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Position DMA Report - {timestamp}"
    msg["From"] = config["from_addr"]
    msg["To"] = config["to_addr"]

    # Plain text fallback
    plain = (
        f"Position DMA Report - {timestamp}\n\n"
        "This report is best viewed in an email client that supports HTML.\n"
        "Alternatively, run with --html to save as a file."
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # Send
    if config["use_tls"]:
        # STARTTLS (ProtonMail Bridge, Gmail, most providers)
        with smtplib.SMTP(config["host"], config["port"]) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], config["to_addr"], msg.as_string())
    else:
        # Direct SSL (port 465)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(config["host"], config["port"], context=context) as server:
            server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], config["to_addr"], msg.as_string())
