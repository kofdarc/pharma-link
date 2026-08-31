from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.utils.html import escape

from apps.common.mailer import send_email
from apps.eprescriptions.services import fax
from apps.eprescriptions.services.qr import prescription_qr_png, prescription_url

logger = logging.getLogger(__name__)

LOGO_CONTENT_ID = "healthconnect-logo"
QR_CONTENT_ID = "prescription-qr"


# The brand mark shown in the dark email header - the same asset the web app renders via
# <BrandMark tone="on-dark"> (apps/web/components/ui/BrandMark.tsx). Kept as a PNG sibling of
# the .webp the site uses because Gmail/Outlook/Apple Mail do not render WebP.
_LOGO_RELATIVE_PATH = "brand/mark-on-dark.png"


def _logo_bytes() -> bytes | None:
    logo_path = Path(settings.REPO_ROOT) / "apps" / "web" / "public" / _LOGO_RELATIVE_PATH
    try:
        return logo_path.read_bytes()
    except OSError:
        # The API container is built from apps/api and does not include the web bundle.
        # Fetching the public asset here still embeds it into the email. The recipient's
        # client never has to make an external image request.
        try:
            import requests

            response = requests.get(f"{settings.PUBLIC_WEB_BASE_URL.rstrip('/')}/{_LOGO_RELATIVE_PATH}", timeout=5)
            response.raise_for_status()
            return response.content
        except Exception:
            logger.warning("Email logo could not be loaded locally or from the public site")
            return None


def _html_body(prescription, url: str, pin: str, *, include_logo: bool = True) -> str:
    rows = "".join(
        f"<tr><td style='padding:14px 12px;border-top:1px solid #e2e8f0;color:#0f172a'>{escape(item.medicine_text)}</td>"
        f"<td style='padding:14px 12px;border-top:1px solid #e2e8f0;color:#334155'>{item.quantity_prescribed} {escape(item.unit)}</td>"
        f"<td style='padding:14px 12px;border-top:1px solid #e2e8f0;color:#334155'>{escape(item.dosage_instructions or 'As directed')}</td></tr>"
        for item in prescription.items.all()
    )
    logo_cell = (
        f'<td><img src="cid:{LOGO_CONTENT_ID}" width="44" alt="HealthConnect" '
        'style="display:block;width:44px;height:auto"></td>'
        if include_logo
        else ""
    )
    wordmark_padding = "12px" if include_logo else "0"
    return f"""
    <!doctype html><html><body style="margin:0;padding:0;background:#f1f5f9">
      <div style="display:none;max-height:0;overflow:hidden;color:transparent">Your secure prescription is ready to use at any pharmacy.</div>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f1f5f9">
        <tr><td align="center" style="padding:32px 12px">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:620px;background:#ffffff;border-radius:18px;overflow:hidden;font-family:Arial,sans-serif;color:#0f172a;box-shadow:0 8px 30px rgba(15,23,42,.08)">
            <tr><td style="padding:22px 28px;background:#073763">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
                {logo_cell}
                <td style="padding-left:{wordmark_padding};color:#ffffff;font-size:21px;font-weight:700;letter-spacing:-.3px">HealthConnect</td>
              </tr></table>
            </td></tr>
            <tr><td style="padding:32px 28px 12px">
              <div style="color:#0a8f68;font-size:12px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase">Secure e-prescription</div>
              <h1 style="margin:8px 0 10px;font-size:26px;line-height:1.25">Your prescription is ready</h1>
              <p style="margin:0;color:#475569;font-size:16px;line-height:1.6">Dr. {escape(prescription.doctor.full_name)} issued this prescription for <strong style="color:#0f172a">{escape(prescription.patient_name)}</strong>.</p>
            </td></tr>
            <tr><td align="center" style="padding:20px 28px">
              <div style="display:inline-block;padding:16px;background:#ffffff;border:1px solid #dbe5ee;border-radius:16px">
                <a href="{escape(url)}"><img src="cid:{QR_CONTENT_ID}" width="240" height="240" alt="Scan prescription QR code" style="display:block;width:240px;height:240px;border:0"></a>
              </div>
              <p style="margin:14px 0 0;color:#475569;font-size:14px;line-height:1.5">Show this QR code at any pharmacy, or tap it to open your prescription.</p>
            </td></tr>
            <tr><td style="padding:4px 28px 24px">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#effaf6;border-radius:12px">
                <tr><td align="center" style="padding:16px 8px;border-right:1px solid #d4eee5;color:#475569;font-size:12px;text-transform:uppercase;letter-spacing:.8px">Prescription code<br><strong style="display:inline-block;margin-top:5px;color:#073763;font-size:20px;letter-spacing:1px">{escape(prescription.code)}</strong></td>
                <td align="center" style="padding:16px 8px;color:#475569;font-size:12px;text-transform:uppercase;letter-spacing:.8px">Private PIN<br><strong style="display:inline-block;margin-top:5px;color:#073763;font-size:20px;letter-spacing:2px">{escape(pin)}</strong></td></tr>
              </table>
            </td></tr>
            <tr><td style="padding:0 28px 28px">
              <h2 style="margin:0 0 10px;font-size:17px">Prescription details</h2>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e2e8f0;border-radius:10px;border-collapse:separate;border-spacing:0;font-size:14px">
                <thead><tr><th align="left" style="padding:11px 12px;background:#f8fafc;color:#475569">Medicine</th><th align="left" style="padding:11px 12px;background:#f8fafc;color:#475569">Quantity</th><th align="left" style="padding:11px 12px;background:#f8fafc;color:#475569">Instructions</th></tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </td></tr>
            <tr><td align="center" style="padding:0 28px 30px">
              <a href="{escape(url)}" style="display:inline-block;padding:14px 24px;background:#0a8f68;color:#ffffff;text-decoration:none;border-radius:9px;font-weight:700;font-size:15px">Open prescription</a>
            </td></tr>
            <tr><td style="padding:20px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;line-height:1.6">
              Valid until <strong>{prescription.valid_until:%d %b %Y at %H:%M}</strong>. Keep your PIN private. A pharmacy can use it to access this prescription. If images are hidden, use the code and PIN at <a href="{escape(settings.PUBLIC_WEB_BASE_URL)}/rx" style="color:#0a6f57">{escape(settings.PUBLIC_WEB_BASE_URL)}/rx</a>.
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body></html>
    """


def send_prescription_email(prescription, *, secret: str, pin: str) -> bool:
    """
    Sends the prescription as a QR code. In the POC the console email backend prints it;
    point EMAIL_* settings at a real SMTP host and nothing else changes. Returns whether the
    send succeeded so the caller can fall back to the fax back-up (see send_prescription_fax)
    on failure, per PrescribeIT's guaranteed-delivery model.
    """
    url = prescription_url(prescription.code, secret)
    try:
        qr_png = prescription_qr_png(prescription.code, secret)
        inline_images = [
            (f"prescription-{prescription.code}.png", qr_png, "image/png", QR_CONTENT_ID),
        ]
        logo = _logo_bytes()
        if logo:
            inline_images.append(("healthconnect-logo.png", logo, "image/png", LOGO_CONTENT_ID))
        send_email(
            to=[prescription.patient_email],
            subject=f"Prescription {prescription.code} from Dr. {prescription.doctor.full_name}",
            text_body=(
                f"Prescription {prescription.code} for {prescription.patient_name}.\n"
                f"Open: {url}\nOr enter code {prescription.code} with PIN {pin} at {settings.PUBLIC_WEB_BASE_URL}/rx\n"
                f"Valid until {prescription.valid_until:%d %b %Y %H:%M}.\n"
            ),
            html_body=_html_body(prescription, url, pin, include_logo=logo is not None),
            inline_images=inline_images,
            attachments=[(f"prescription-{prescription.code}.png", qr_png, "image/png")],
        )
    except Exception:
        logger.exception("Failed to email prescription %s to %s", prescription.code, prescription.patient_email)
        return False
    return True


def send_prescription_sms(prescription, *, secret: str, pin: str) -> bool:
    """
    Texts the prescription to the patient's phone at issue time, alongside the email (not a
    fallback for it - a patient who gave both a phone and an email gets both).

    The body is deliberately short and link-light: mobile carriers in several markets
    (Lebanon among them) silently drop SMS that carry a long URL with a query string,
    especially from a shared/unregistered originator. So the text carries only the code +
    PIN for the manual-entry flow and a bare short domain - never the `?k=<secret>` deep
    link (that lives in the email and WhatsApp, where it is also safer to expose). `secret`
    is accepted for signature symmetry with the other channels but not sent.
    Returns whether the send succeeded so the caller can record sms_sent_at.
    """
    del secret  # intentionally not included in SMS - see docstring
    doctor_last = prescription.doctor.full_name.split()[-1] if prescription.doctor.full_name else prescription.doctor.full_name
    short_domain = settings.PUBLIC_WEB_BASE_URL.split("://", 1)[-1].rstrip("/")
    body = (
        f"HealthConnect: Rx {prescription.code} from Dr {doctor_last}. "
        f"PIN {pin}. Give the code and PIN at any pharmacy, or at {short_domain}/rx. "
        f"Valid to {prescription.valid_until:%d %b %Y}."
    )
    try:
        from apps.messaging.sms.service import send_sms

        result = send_sms(to=prescription.patient_phone, body=body)
    except Exception:
        logger.exception("Failed to text prescription %s to %s", prescription.code, prescription.patient_phone)
        return False
    if result.status == "FAILED":
        logger.warning("SMS delivery of prescription %s failed: %s", prescription.code, result.failure_reason)
        return False
    return True


def send_prescription_whatsapp(prescription, *, secret: str, pin: str) -> bool:
    """
    Sends the prescription to the patient's phone over WhatsApp at issue time, alongside the
    email and the SMS (each channel is independent - the patient gets it on every contact
    detail they gave). Goes through the same apps.messaging.services.send_whatsapp_text
    chokepoint the rest of the app uses; the console provider logs it in dev/test. Returns
    whether the send succeeded so the caller can record whatsapp_sent_at.
    """
    url = prescription_url(prescription.code, secret)
    items = "\n".join(
        f"- {item.medicine_text}: {item.quantity_prescribed} {item.unit}"
        f" ({item.dosage_instructions or 'as directed'})"
        for item in prescription.items.all()
    )
    body = (
        f"Prescription {prescription.code} from Dr. {prescription.doctor.full_name}, "
        f"for {prescription.patient_name}.\n\n"
        f"{items}\n\n"
        f"Show this at any pharmacy: open {url}, or give them code {prescription.code} "
        f"with PIN {pin} at {settings.PUBLIC_WEB_BASE_URL}/rx.\n"
        f"Valid until {prescription.valid_until:%d %b %Y %H:%M}. Keep the PIN private."
    )
    try:
        from apps.messaging.services import send_whatsapp_text

        result = send_whatsapp_text(to=prescription.patient_phone, body=body)
    except Exception:
        logger.exception("Failed to WhatsApp prescription %s to %s", prescription.code, prescription.patient_phone)
        return False
    if result.status == "FAILED":
        logger.warning("WhatsApp delivery of prescription %s failed: %s", prescription.code, result.failure_reason)
        return False
    return True


def send_prescription_fax(prescription, *, pin: str) -> bool:
    """
    Back-up delivery channel used when the prescription has no email on file, or the email
    send failed - PrescribeIT documents this as its guaranteed-delivery path. Fax is a
    plain-text medium (no QR rendering), so the pharmacy on the other end falls back to the
    code+PIN manual-entry flow rather than scanning.
    """
    text_body = (
        f"Prescription {prescription.code} from Dr. {prescription.doctor.full_name}, "
        f"for {prescription.patient_name}.\n\n"
        + "\n".join(
            f"- {item.medicine_text}: {item.quantity_prescribed} {item.unit} ({item.dosage_instructions or 'as directed'})"
            for item in prescription.items.all()
        )
        + f"\n\nEnter code {prescription.code} with PIN {pin} at {settings.PUBLIC_WEB_BASE_URL}/rx to dispense.\n"
        f"Valid until {prescription.valid_until:%d %b %Y %H:%M}.\n"
    )
    try:
        provider = fax.get_provider(settings.FAX_PROVIDER)
        result = provider.send_fax(
            to=prescription.patient_fax,
            subject=f"Prescription {prescription.code}",
            text_body=text_body,
        )
    except Exception:
        logger.exception("Failed to fax prescription %s to %s", prescription.code, prescription.patient_fax)
        return False
    return result.status == "SENT"
