from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_email(
    *,
    to: list[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
    attachments: list[tuple] | None = None,
) -> None:
    """
    Builds and sends one EmailMultiAlternatives message. Every mailer in the codebase
    (prescription delivery, order/webhook/account notifications) should call this instead of
    constructing the message itself, so there is one place that knows how mail actually goes
    out. In development the console backend prints it; point EMAIL_* at a real SMTP host and
    nothing else changes.
    """
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    for attachment in attachments or []:
        message.attach(*attachment)
    message.send(fail_silently=False)
