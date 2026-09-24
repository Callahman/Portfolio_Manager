"""Email delivery (Step 7) — SMTP summary on completed runs and on failures.

Config: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO. A missing
SMTP_HOST is a visible no-op (logged), never a crash.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from common import config

log = logging.getLogger(__name__)


def send(subject: str, body: str) -> bool:
    config.load_env()
    host = (config.get("SMTP_HOST") or "").strip()
    if not host:
        log.warning("SMTP_HOST not set — email skipped (visible no-op)")
        return False
    port = config.get_int("SMTP_PORT", 587)
    user = (config.get("SMTP_USER") or "").strip()
    pwd = config.get("SMTP_PASS") or ""
    to = (config.get("EMAIL_TO") or "").strip()
    if not to:
        log.warning("EMAIL_TO not set — email skipped")
        return False

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = user or "portfolio-manager@localhost"
    msg["To"] = to
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if port == 587:
                s.starttls()
            if user:
                s.login(user, pwd)
            s.sendmail(msg["From"], [to], msg.as_string())
        log.info("email sent: %s", subject)
        return True
    except Exception as e:  # noqa: BLE001
        log.error("email FAILED: %s", e)
        return False


def send_run_summary(report_md: str) -> bool:
    return send("Portfolio Manager — run summary", report_md[:20000])


def send_failure_summary(failures: list[dict]) -> bool:
    lines = [f"- {f.get('failure_id')}: {f.get('source')} — {f.get('message')}" for f in failures]
    return send("Portfolio Manager — failures", "\n".join(lines)[:20000])
