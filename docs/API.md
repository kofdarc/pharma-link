# API

Base path: `/api`. Protected requests use `Authorization: Token <token>`.

## Authentication

| Endpoint | Notes |
|---|---|
| `POST /auth/login/` | Returns `{token, user}` |
| `POST /auth/logout/` | |
| `GET /auth/me/` | |
| `POST /auth/register/` | Shopper self-signup. Only the `CUSTOMER` role can be self-assigned. |

Roles: `PLATFORM_ADMIN`, `PHARMACY_OWNER`, `PHARMACY_STAFF`, `DOCTOR`, `CUSTOMER`, `DRIVER`.

---

## Public (no authentication)

| Endpoint | Notes |
|---|---|
| `GET /public/search/?q=&area=&lat=&lng=&sort=` | Unified availability. `sort` = `best` (default), `distance`, `price`, `rating`. |
| `GET /public/pharmacies/:id/` | |
| `GET /public/pharmacy-directory/?q=` | Lets a walk-in pharmacy identify itself when dispensing. |
| `POST /public/rx/lookup/` | `{code, key?, pin?}` → prescription + short-lived `dispense_ticket`. |
| `POST /public/rx/dispense/` | `{ticket, pharmacy_name, pharmacist_name, items[]}` |

**Search never returns** exact stock depth, purchase cost, supplier, staff, sales or
prescription data. It returns `available_up_to` — an orderable ceiling clamped to
`PUBLIC_MAX_QUANTITY_PER_ITEM` (per-pharmacy override available) — plus a status band,
`unit_price` with `is_price_regulated`, `distance_km` when coordinates are supplied, and the
confirmation disclaimer. Searches that match nothing are recorded as unmet demand.

**Prescription endpoints** are throttled (`rx_lookup` 30/min, `rx_dispense` 12/min) on top of
per-prescription lockout. The `code` alone is never sufficient — the QR key or PIN is always
required, and both are stored only as SHA-256 hashes.

---

## Doctors

| Endpoint | Notes |
|---|---|
| `POST /doctors/activate/` | `{license_number, email, password}`. Claims a pre-loaded roster record. |
| `GET /doctor/profile/` | |
| `GET/POST /doctor/prescriptions/` | Creating one returns `one_time_secrets` (PIN, QR URL, QR SVG) — **shown once**. |
| `POST /doctor/prescriptions/:id/cancel/` | |
| `GET /doctor/prescriptions/:id/qr.svg?k=<key>` | Re-renders the QR only while the caller still holds the key. |

---

## Shopper

| Endpoint | Notes |
|---|---|
| `/shop/addresses/` | CRUD. Coordinates drive ranking and routing. |
| `POST /shop/quote/` | `{items[], latitude, longitude}` → sourcing plan **without** holding stock. |
| `GET/POST /shop/orders/` | Placing an order reserves stock across the chosen pharmacies. |
| `POST /shop/orders/:id/cancel/` | Releases all holds. |
| `POST /shop/orders/:id/review/` | `{pharmacy, rating, comment}` — feeds search ranking. |
| `/shop/recurring-orders/` | Repeat refills; re-sourced fresh each cycle. |

---

## Pharmacy workspace

Requires `PHARMACY_OWNER` or `PHARMACY_STAFF`; all querysets are scoped to the user's active
pharmacy.

| Endpoint | Notes |
|---|---|
| `GET /pharmacy/dashboard/` · `GET/PATCH /pharmacy/profile/` | |
| `/pharmacy/inventory/` · `POST /pharmacy/inventory/:id/adjust/` | |
| `/pharmacy/stock-movements/` | |
| `/pharmacy/imports/` · `POST /pharmacy/imports/upload/` · `POST /pharmacy/imports/:id/confirm/` | |
| `/pharmacy/sales/` · `/pharmacy/invoices/:id/` | Accepts `client` and `payment_method=ON_ACCOUNT` |
| `/pharmacy/clients/` | CRM |
| `GET /pharmacy/clients/:id/history/` | Visits, spend, top products, balance |
| `GET/POST /pharmacy/clients/:id/ledger/` | Append-only account entries |
| `/pharmacy/orders/` | Incoming platform orders |
| `POST /pharmacy/orders/:id/{accept,reject,ready,handover}/` | `handover` deducts stock and writes the invoice |
| `POST /pharmacy/rx/scan/` | Same as public lookup, attributed to this pharmacy |
| `/pharmacy/prescriptions/` · `GET /pharmacy/prescriptions/:id/download/` | Uploaded paper scans |
| `/pharmacy/staff/` · `/pharmacy/audit-logs/` | |

### Analytics

| Endpoint | Returns |
|---|---|
| `GET /pharmacy/analytics/overview/` | Stock, 7d/30d sales, turnover, platform performance, revenue series |
| `GET /pharmacy/analytics/inventory/?days=` | Stock snapshot, turnover/GMROI, ABC classification, dead stock |
| `GET /pharmacy/analytics/sales/?days=` | Sales snapshot, daily series, top movers |
| `GET /pharmacy/analytics/replenishment/?days=&lead_time_days=` | Reorder points with safety stock |
| `GET /pharmacy/analytics/demand/?days=` | Unmet demand in the pharmacy's area |

### Integration setup

| Endpoint | Notes |
|---|---|
| `GET /pharmacy/onboarding/` | Checklist derived from real data |
| `/pharmacy/integration-keys/` | Owner only. Create returns `secret` **once**. |
| `/pharmacy/sku-mappings/?unmapped=true` | Map the pharmacy's own product codes |
| `/pharmacy/sync-runs/` · `/pharmacy/webhooks/` | |

---

## Dispatch (platform admin)

| Endpoint | Notes |
|---|---|
| `GET /dispatch/board/` | Waiting orders, drivers online, committed routes |
| `GET /dispatch/preview/` | Dry run — solves and reports savings, writes nothing |
| `POST /dispatch/plan/` | Solves and commits. Never touches an `ACTIVE` route. |
| `GET /dispatch/orders/:id/offers/` | Marginal insertion cost per online driver |
| `POST /dispatch/routes/:id/reoptimise/` | Re-sequences unvisited stops only |
| `/admin/drivers/` | |

## Driver

| Endpoint | Notes |
|---|---|
| `GET/PATCH /driver/me/` | `is_online` toggles inclusion in planning |
| `POST /driver/ping/` | `{latitude, longitude}` — plans start from the live position |
| `GET /driver/routes/` · `GET /driver/routes/current/` | |
| `POST /driver/routes/:id/accept/` · `POST /driver/routes/:id/reoptimise/` | |
| `POST /driver/stops/:id/{arrive,pickup,deliver,fail}/` | `pickup` takes `{handover_codes: {fulfillment_id: code}}` |

---

## Integration bridge (machine-to-machine)

Signed with HMAC-SHA256; no session, no password.

```
canonical = method + "\n" + path + "\n" + timestamp + "\n" + nonce + "\n" + sha256(body)
signature = hex(hmac_sha256(secret, canonical))

X-PharmaLink-Key:        <key id>
X-PharmaLink-Timestamp:  <unix seconds>      # ±300s window
X-PharmaLink-Nonce:      <unique per request> # single use
X-PharmaLink-Signature:  <signature>
```

`401` means the credentials are wrong — stop retrying. `403` means authenticated but the key
lacks the required scope.

| Endpoint | Scope |
|---|---|
| `GET /integration/v1/ping/` | `orders:read` |
| `POST /integration/v1/stock/sync/` | `stock:write` |
| `POST /integration/v1/sales/sync/` | `sales:write` |
| `GET /integration/v1/orders/?open=true` | `orders:read` |
| `POST /integration/v1/orders/:id/{accept,reject,ready}/` | `orders:write` |

Stock sync takes **absolute levels**, not deltas, and is idempotent on `idempotency_key`.
Unmapped product codes are reported, not rejected. MoPH-regulated prices always override
whatever the POS sends.

```json
POST /integration/v1/stock/sync/
{
  "idempotency_key": "2026-07-30T14:00-a1b2c3",
  "rows": [
    {"external_code": "POS-1001", "name": "PANADOL 500 TAB", "quantity": 42, "selling_price": "2.25"}
  ]
}
```

---

## Medicines

- `GET /medicines/search/?q=` — brand, generic, alias, partial and fuzzy matching
- `GET /medicines/:id/` — includes `price_regime`, `regulated_price`, `is_price_regulated`,
  `requires_prescription`
