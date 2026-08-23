# PRD Source

The implementation follows `C:/Users/PC/Downloads/Product Requirements Document - PharmaLink MVP.pdf`. That
document is a static snapshot; the mentorship program's live BRD is the Google Drive doc Marc maintains and
shares with the AWE mentors. This file tracks what is actually built, so it can drift from both.

Implemented MVP scope:

- Django REST backend with modular apps for accounts, pharmacies, medicines, inventory, imports, sales,
  prescriptions, orders, delivery routing, payments, billing, and audit logs.
- Next.js TypeScript frontend with public search, login, shopper checkout, pharmacy workspace, and admin workspace.
- PostgreSQL-ready configuration through Docker Compose.
- UUID primary keys, role-based permissions, pharmacy-scoped protected querysets, soft active/public flags, private prescription downloads, audit logs, import preview/confirm, and FEFO stock deduction for sales.
- Focused backend tests for permission boundaries, public search privacy, stock deduction, prescription access, payments, and billing.

## Payment processing

Decided in the 2026-08-07 BRD/HLD review: include a Lebanese payment platform (provider not yet chosen).
Built as a provider-agnostic abstraction (`apps/payments`) rather than a specific gateway integration, since
the team hasn't picked one:

- `Payment` model attached one-to-one to each shopper `Order`, tracking provider, status
  (PENDING/PAID/FAILED/REFUNDED), amount, and the provider's own transaction reference.
- Two adapters behind a common `PaymentProvider.charge()` interface: **cash on delivery** (stays PENDING
  until the order is actually delivered/collected, then auto-settles) and a **mock online gateway** (charges
  synchronously with a fake reference, so checkout can demo a full "pay online" flow today).
- Swapping in a real gateway (Whish Money, OMT, Areeba, or whichever is chosen) means adding one adapter
  class and a registry entry — checkout, the order API, and the frontend do not change.
- Shopper checkout picks a payment method (`POST /api/shop/orders/` takes `payment_method`); a dedicated
  `POST /api/shop/orders/{id}/pay/` retries/confirms an online charge.

## Revenue model

Decided in the same review: pharmacy subscriptions, with a service fee charged per request submitted
through the platform. Built as `apps/billing`:

- `SubscriptionPlan` (admin-managed: monthly fee + per-request service fee) and `PharmacySubscription`
  (one active plan per pharmacy).
- `PlatformServiceFee`: one row per order request a pharmacy accepts, charged automatically at acceptance
  from its plan's per-request fee. A pharmacy with no active subscription, or a zero-fee plan, is never charged.
- Pharmacies see their own fees and subscription (`/api/pharmacy/service-fees/`, `/api/pharmacy/subscription/`);
  admins manage plans and assignments and see collected/pending totals in one place.

## Success criteria / KPIs beyond system uptime

Flagged as missing in the review. `GET /api/admin/revenue/overview/` now reports monthly recurring revenue
(sum of active subscriptions' monthly fees), active subscriber count, and service fees collected/pending —
the first cut of the "revenue tracking, user base growth, and subscription metrics" the mentors asked for.
User growth and retention metrics are not yet built.

## Delivery

Already implemented pre-review: shared-route batching across pharmacies (`apps/delivery`), not naive
one-driver-per-order. See [ARCHITECTURE.md](ARCHITECTURE.md#3-delivery-routing--deliveryservicesroutingpy)
for the routing algorithm and the seeded-demo numbers.

Non-goals preserved:

- No diagnosis, treatment advice, automatic substitution recommendations, native mobile app, microservices,
  Kafka, Kubernetes, or blockchain. Public prescription access stays QR/code+PIN only, never a public listing.

## Insurance / copayment

Reverses the "no insurance claims" non-goal above, added 2026-08-22 at the team's request after reviewing a
competitor's copayment feature. Built as `apps/insurance`:

- `InsuranceProvider` / `InsurancePlan` (admin-managed: coverage % + a flat minimum copay floor, no
  per-medicine formulary) and `PatientInsurancePolicy` (held by either a platform shopper or a pharmacy's
  own walk-in `customers.Client`, never both).
- `InsuranceClaim`: one per dispensing event (an `orders.OrderFulfillment` or a `sales.Sale`, never per
  multi-pharmacy order), carrying `billed_amount` / `covered_amount` / `patient_copay`. Adjudication is a
  **manual tracker**, not a live TPA integration — Lebanon has multiple TPAs (GlobeMed, LibanCard, NexCare,
  MedNet, ...) with no shared API, so staff record the outcome by hand, `SUBMITTED → APPROVED/REJECTED →
  PAID`, the same way cash-on-delivery payments are manually settled.
- Insured shop checkout charges the shopper's `Payment` only the summed copay across fulfillments (delivery
  fee is never insurance-eligible); an insured `ON_ACCOUNT` counter sale charges the client ledger only the
  copay. Both are opt-in — an order or sale placed without a policy behaves exactly as before.
- Known limitation, kept deliberately out of scope: if a claim is later rejected after the patient already
  paid the estimated copay, the platform does not auto-re-charge them — that reconciliation is manual.
