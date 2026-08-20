from __future__ import annotations

from django.conf import settings
from django.utils.html import escape

from apps.common.mailer import send_email
from apps.eprescriptions.services.qr import prescription_qr_svg, prescription_url


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


def send_prescription_email(prescription, *, secret: str, pin: str) -> None:
    """
    Sends the prescription as a QR code. In the POC the console email backend prints it;
    point EMAIL_* settings at a real SMTP host and nothing else changes.
    """
    url = prescription_url(prescription.code, secret)
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
