"""
Sends an SMS via Twilio whenever a user other than the excluded
employee ID logs in. Best-effort — failures are logged, never raised,
so a Twilio outage can't break login.
"""
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


def send_login_alert_sms(employee_name: str, employee_id: str | None) -> None:
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_FROM_NUMBER and settings.LOGIN_ALERT_PHONE):
        return

    if employee_id and employee_id == settings.LOGIN_ALERT_EXCLUDE_EMPLOYEE_ID:
        return

    body = f"iEZ login alert: {employee_name or 'Unknown user'} ({employee_id or 'N/A'}) just logged in."

    try:
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            data={
                "To": settings.LOGIN_ALERT_PHONE,
                "From": settings.TWILIO_FROM_NUMBER,
                "Body": body,
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.warning("Twilio SMS failed (%s): %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Twilio SMS exception: %s", exc)
