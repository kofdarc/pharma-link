from __future__ import annotations

import logging

from django.conf import settings
from django.utils.html import escape

from apps.common.mailer import send_email
from apps.eprescriptions.services import fax
from apps.eprescriptions.services.qr import prescription_qr_svg, prescription_url

logger = logging.getLogger(__name__)


def _html_body(prescription, url: str, pin: str) -> str:
    rows = "".join(
        f"<tr><td style='padding:6px 12px;border-bottom:1px solid #e5e7eb'>{escape(item.medicine_text)}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e5e7eb'>{item.quantity_prescribed} {escape(item.unit)}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e5e7eb'>{escape(item.dosage_instructions)}</td></tr>"
        for item in prescription.items.all()
    )
    return f"""
    <div style="font-family:system-ui,sans-serif;color:#0f172a;max-width:560px">
      <h2>Your prescription from Dr. {escape(prescription.doctor.full_name)}</h2>
      <p>Patient: <strong>{escape(prescription.patient_name)}</strong></p>
      <table style="border-collapse:collapse;width:100%;font-size:14px">
        <thead><tr><th align="left" style="padding:6px 12px">Item</th><th align="left" style="padding:6px 12px">Quantity</th>
        <th align="left" style="padding:6px 12px">Instructions</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:20px">Show this to <strong>any pharmacy</strong>. They scan the attached QR code, or open
        <a href="{escape(url)}">this link</a>, or type the code and PIN below on
        <strong>{escape(settings.PUBLIC_WEB_BASE_URL)}/rx</strong>.</p>
      <p style="font-size:18px">Code: <strong>{escape(prescription.code)}</strong><br/>PIN: <strong>{escape(pin)}</strong></p>
      <p style="color:#64748b;font-size:13px">Valid until {prescription.valid_until:%d %b %Y %H:%M}. Keep the PIN private:
        it lets a pharmacy consume this prescription. Each item can only be dispensed up to the prescribed quantity,
        even across different pharmacies.</p>
    </div>
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
        send_email(
            to=[prescription.patient_email],
            subject=f"Prescription {prescription.code} from Dr. {prescription.doctor.full_name}",
            text_body=(
                f"Prescription {prescription.code} for {prescription.patient_name}.\n"
                f"Open: {url}\nOr enter code {prescription.code} with PIN {pin} at {settings.PUBLIC_WEB_BASE_URL}/rx\n"
                f"Valid until {prescription.valid_until:%d %b %Y %H:%M}.\n"
            ),
            html_body=_html_body(prescription, url, pin),
            attachments=[(f"prescription-{prescription.code}.svg", prescription_qr_svg(prescription.code, secret), "image/svg+xml")],
        )
    except Exception:
        logger.exception("Failed to email prescription %s to %s", prescription.code, prescription.patient_email)
        return False
    return True


def send_prescription_sms(prescription, *, secret: str, pin: str) -> bool:
    """
    Texts the prescription to the patient's phone at issue time, alongside the email (not a
    fallback for it - a patient who gave both a phone and an email gets both). SMS is a
    plain-text medium with no QR, so it carries the deep link plus the code+PIN manual-entry
    details. Returns whether the send succeeded so the caller can record sms_sent_at.
    """
    url = prescription_url(prescription.code, secret)
    body = (
        f"Prescription {prescription.code} from Dr. {prescription.doctor.full_name}. "
        f"Open {url} or enter code {prescription.code} with PIN {pin} at "
        f"{settings.PUBLIC_WEB_BASE_URL}/rx. Valid until {prescription.valid_until:%d %b %Y}."
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
