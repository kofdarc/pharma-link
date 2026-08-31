from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from django.conf import settings


def prescription_url(code: str, secret: str) -> str:
    """The URL encoded in the QR code. Any phone camera opens it; no HealthConnect account is involved."""
    base = settings.PUBLIC_WEB_BASE_URL.rstrip("/")
    return f"{base}/rx/{quote(code)}?k={quote(secret)}"


def prescription_qr_svg(code: str, secret: str) -> str:
    """
    SVG QR so the POC has no native image dependency (no Pillow).
    Error correction Q tolerates a creased or partly smudged printout.
    """
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=2)
    qr.add_data(prescription_url(code, secret))
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    return image.to_string(encoding="unicode")


def prescription_qr_png(code: str, secret: str) -> bytes:
    """Return a PNG QR for email clients, many of which do not render inline SVG."""
    import qrcode

    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=4)
    qr.add_data(prescription_url(code, secret))
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(fill_color="#0f172a", back_color="white").save(output, format="PNG")
    return output.getvalue()
