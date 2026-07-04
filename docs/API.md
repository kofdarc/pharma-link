# API

Base path: `/api`.

## Authentication

- `POST /auth/login/`
- `POST /auth/logout/`
- `GET /auth/me/`

Protected requests use:

```text
Authorization: Token <token>
```

## Public

- `GET /public/search/?q=&area=&medicine_id=`
- `GET /public/pharmacies/:id/`

Public search returns medicine, public pharmacy contact fields, simplified availability status, last updated timestamp, and the confirmation disclaimer. It never returns exact stock quantities, purchase cost, supplier, staff, sales, or prescription data.

## Admin

- `/admin/pharmacies/`
- `/admin/users/`
- `/admin/medicines/`
- `/admin/imports/`
- `/admin/audit-logs/`

Admin endpoints require `PLATFORM_ADMIN`.

## Pharmacy

- `GET /pharmacy/dashboard/`
- `GET/PATCH /pharmacy/profile/`
- `/pharmacy/inventory/`
- `POST /pharmacy/inventory/:id/adjust/`
- `/pharmacy/stock-movements/`
- `/pharmacy/imports/`
- `POST /pharmacy/imports/upload/`
- `POST /pharmacy/imports/:id/confirm/`
- `/pharmacy/sales/`
- `/pharmacy/invoices/:id/`
- `/pharmacy/prescriptions/`
- `GET /pharmacy/prescriptions/:id/download/`
- `/pharmacy/staff/`

Pharmacy endpoints require `PHARMACY_OWNER` or `PHARMACY_STAFF` and scope querysets to the authenticated user's active pharmacy.

## Medicines

- `GET /medicines/search/?q=`
- `GET /medicines/:id/`

Search supports brand, generic, alias, partial matches, and basic fuzzy matching.

