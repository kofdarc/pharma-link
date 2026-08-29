# WhatsApp integration

WhatsApp is a time-sensitive notification channel for Pharma Link. Search, checkout,
payments, prescriptions, clinical information and inventory operations stay inside the
authenticated web application.

## Implemented notification families

| Family | Trigger |
|---|---|
| Order updates | Placed, accepted, ready, rejected, delivered or collected |
| Refill reminders | Three-day heads-up, refill placed, or refill failed |
| Pharmacy alerts | New order slice or new targeted e-prescription |
| Prescription expiry | Once inside seven days and once inside one day |
| Renewal decision | Doctor approved or denied a renewal request |
| Payment failure | Online payment attempt failed |

System notifications are stored in `messaging.WhatsAppNotification`. Its unique
`deduplication_key` prevents the five-minute scheduler from repeating a reminder. Customer
notifications respect the existing order, refill and prescription preference switches.

Messages contain references, dates and statuses only. They never contain medication names,
diagnoses, prescription images, access secrets, PINs, payment credentials or insurance data.

## Meta templates

Create and approve these utility templates in WhatsApp Manager. Create translated variants
with the same parameter positions when Arabic and French are enabled.

| Environment setting | Default template | Suggested body |
|---|---|---|
| `WHATSAPP_TEMPLATE_ORDER_STATUS` | `pharmalink_order_status_v1` | `Order {{1}}: {{2}}` |
| `WHATSAPP_TEMPLATE_REFILL_REMINDER` | `pharmalink_refill_reminder_v1` | `Refill {{1}}: {{2}}` |
| `WHATSAPP_TEMPLATE_PHARMACY_ALERT` | `pharmalink_pharmacy_alert_v1` | `{{1}} {{2}} requires review in Pharma Link.` |
| `WHATSAPP_TEMPLATE_PRESCRIPTION_EXPIRY` | `pharmalink_prescription_expiry_v1` | `Prescription {{1}} expires on {{2}}. Review it securely in Pharma Link.` |
| `WHATSAPP_TEMPLATE_RENEWAL_DECISION` | `pharmalink_renewal_decision_v1` | `The renewal for prescription {{1}} was reviewed and {{2}}.` |
| `WHATSAPP_TEMPLATE_PAYMENT_FAILED` | `pharmalink_payment_failed_v1` | `Payment for order {{1}} was unsuccessful. Review it securely in Pharma Link.` |

Each template can define one dynamic URL button whose fixed base is
`https://healthconnect.dev/` and whose `{{1}}` suffix is supplied by the backend. Suggested
button labels are `View order`, `Review refill`, `Open Pharma Link`, `Review prescription`
and `Retry payment`.

## Configuration

The console provider is the default and makes no external request:

```text
WHATSAPP_PROVIDER=console
```

For Meta Cloud API delivery, inject the following through the deployment's existing secret
mechanism. Do not commit their values or print them in logs.

```text
WHATSAPP_PROVIDER=meta_cloud
WHATSAPP_GRAPH_API_VERSION=<supported version shown by Meta>
WHATSAPP_ACCESS_TOKEN=<runtime secret>
WHATSAPP_PHONE_NUMBER_ID=<Meta phone-number ID>
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<runtime secret>
WHATSAPP_APP_SECRET=<runtime secret>
WHATSAPP_TEMPLATE_LANGUAGE=en
```

Webhook callback:

```text
https://<api-host>/api/public/whatsapp/webhook/
```

Subscribe the Meta app to the `messages` field. The callback validates
`X-Hub-Signature-256`, accepts inbound text messages and updates sent, delivered, read and
failed states for chat messages and system notifications.

## Free demo

### Reliable offline demo

Leave `WHATSAPP_PROVIDER=console`. The complete event, preference and deduplication paths
run, messages appear as sent, and the template name and non-sensitive parameters appear in
the API log. This requires no Meta account and remains the presentation fallback.

### Real phone demo

1. Create a Meta developer app and add the WhatsApp product.
2. Use Meta's supplied test number and temporary token.
3. Verify the presenters' recipient phones in **WhatsApp > API Setup**.
4. Configure the callback above and subscribe to `messages`.
5. Create and approve the six templates, or initially test the existing human chat during
   a customer-opened 24-hour service window.
6. Inject the temporary credentials at runtime and set `WHATSAPP_PROVIDER=meta_cloud`.
7. Place and accept a seeded order whose contact phone is one of the verified recipients.

Meta's pre-approved `hello_world` template can confirm that the test number works, but the
application's six notification families require the configured template names to be
approved before Meta will deliver them.
