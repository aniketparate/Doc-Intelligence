# from __future__ import annotations

# from typing import Literal

# from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

# from app.config import settings


# async def send_otp_email(to_email: str, code: str, purpose: Literal["verify_email", "login"]) -> None:
#     if purpose not in {"verify_email", "login"}:
#         raise ValueError("purpose must be 'verify_email' or 'login'")
#     if len(code) != 6 or not code.isdigit():
#         raise ValueError("code must be a 6-digit string")

#     subject = (
#         "Your verification code — Ultra Doc-Intelligence"
#         if purpose == "verify_email"
#         else "Your login code — Ultra Doc-Intelligence"
#     )
#     body = (
#         f"Your code: {code}\n"
#         "Expires in 10 minutes. Do not share this code."
#     )

#     conf = ConnectionConfig(
#         MAIL_USERNAME=settings.SMTP_USER,
#         MAIL_PASSWORD=settings.SMTP_PASSWORD,
#         MAIL_FROM=settings.EMAIL_FROM,
#         MAIL_PORT=settings.SMTP_PORT,
#         MAIL_SERVER=settings.SMTP_HOST,
#         MAIL_STARTTLS=True,
#         MAIL_SSL_TLS=False,
#         USE_CREDENTIALS=True,
#         VALIDATE_CERTS=True,
#     )

#     message = MessageSchema(
#         subject=subject,
#         recipients=[to_email],
#         body=body,
#         subtype=MessageType.plain,
#     )

#     await FastMail(conf).send_message(message)

import logging
from app.config import settings

logger = logging.getLogger(__name__)


async def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    subject = (
        "Your verification code — Ultra Doc-Intelligence"
        if purpose == "verify_email"
        else "Your login code — Ultra Doc-Intelligence"
    )
    body = f"Your code: {code}\nExpires in 10 minutes. Do not share this code."

    # If SMTP is not configured, just log the OTP to terminal
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("=" * 50)
        logger.warning(f"[DEV MODE] OTP email not sent — no SMTP configured")
        logger.warning(f"[DEV MODE] To: {to_email}")
        logger.warning(f"[DEV MODE] Subject: {subject}")
        logger.warning(f"[DEV MODE] OTP CODE: {code}")
        logger.warning("=" * 50)
        return

    # Real SMTP sending (only runs when SMTP_USER and SMTP_PASSWORD are set)
    try:
        from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

        conf = ConnectionConfig(
            MAIL_USERNAME=settings.SMTP_USER,
            MAIL_PASSWORD=settings.SMTP_PASSWORD,
            MAIL_FROM=settings.EMAIL_FROM,
            MAIL_PORT=settings.SMTP_PORT,
            MAIL_SERVER=settings.SMTP_HOST,
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
        )
        message = MessageSchema(
            subject=subject,
            recipients=[to_email],
            body=body,
            subtype=MessageType.plain,
        )
        fm = FastMail(conf)
        await fm.send_message(message)
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        raise