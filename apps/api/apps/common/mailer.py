from __future__ import annotations

from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_email(
    *,
    to: list[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
    attachments: list[tuple] | None = None,
    inline_images: list[tuple[str, bytes, str, str]] | None = None,
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
    if inline_images:
        # A multipart/related message lets HTML clients resolve cid: images without making
        # an external request. This is more dependable for email than data URLs or SVG.
        message.mixed_subtype = "related"
        for filename, content, mime_type, content_id in inline_images:
            _type, subtype = mime_type.split("/", 1)
            image = MIMEImage(content, _subtype=subtype)
            image.add_header("Content-ID", f"<{content_id}>")
            image.add_header("Content-Disposition", "inline", filename=filename)
            message.attach(image)
    for attachment in attachments or []:
        message.attach(*attachment)
    message.send(fail_silently=False)
