# Setup

## Requirements

- Python 3.12+
- Node.js 20+
- pnpm
- Docker for local PostgreSQL

## Backend

The backend defaults to PostgreSQL at:

```text
postgresql://medisync:medisync@localhost:55432/medisync
```

Use `.env` to override `DATABASE_URL`, CORS, CSRF, file-size limits, and storage settings. Prescription files are stored under private local media in development and are only served through authenticated download endpoints.

## Frontend

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api` for local development. The frontend stores the DRF token in `sessionStorage` and sends it on protected API requests.

## Demo Flow

1. Seed demo data with `python manage.py seed_demo`.
2. Log in as the owner.
3. Review dashboard alerts.
4. Add an inventory batch or import a CSV/XLSX file.
5. Record a sale.
6. Search public availability from `/search`.
7. Log in as admin to review pharmacies, users, medicines, imports, and audit logs.

