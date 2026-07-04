# MediSync MVP

MediSync is a pharmacy-focused medication availability and inventory management platform for Lebanon. This repository implements the PRD as a modular monorepo:

- `apps/api`: Django + Django REST Framework API
- `apps/web`: Next.js + TypeScript frontend
- `docker-compose.yml`: local PostgreSQL
- `docs`: setup and API notes

## Local Setup

1. Copy environment defaults:

```powershell
Copy-Item .env.example .env
```

2. Start PostgreSQL:

```powershell
docker compose up -d postgres
```

3. Install backend dependencies:

```powershell
cd apps/api
python -m pip install -r requirements.txt
```

4. Run migrations and seed demo data:

```powershell
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 8000
```

5. Install and run the frontend:

```powershell
cd apps/web
pnpm install
pnpm dev
```

Open `http://localhost:3000`.

Demo credentials after `seed_demo`:

- Admin: `admin@medisync.test` / `Password123!`
- Owner: `owner@cedarcare.test` / `Password123!`
- Staff: `staff@cedarcare.test` / `Password123!`

## Verification

Backend focused tests can run without PostgreSQL by using SQLite:

```powershell
cd apps/api
$env:DJANGO_TEST_SQLITE='1'
python manage.py test apps.accounts apps.inventory apps.sales apps.prescriptions
```

For production-like local testing, use PostgreSQL through Docker and run `python manage.py migrate`.

