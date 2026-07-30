from __future__ import annotations

from urllib.parse import quote

from django.conf import settings


def prescription_url(code: str, secret: str) -> str:
    """The URL encoded in the QR code. Any phone camera opens it; no MediSync account is involved."""
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
