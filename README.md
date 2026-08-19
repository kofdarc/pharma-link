# PharmaLink

A pharmacy operations platform for Lebanon: stock and invoicing for pharmacies, unified
medicine search and delivery for the public, QR prescriptions for doctors, and a smart
multi-pickup delivery router underneath it all.

- `apps/api` — Django + Django REST Framework
- `apps/web` — Next.js + TypeScript
- `tools/connector` — the agent that runs inside the pharmacy, bridging their existing software
- `docs/` — [architecture](docs/ARCHITECTURE.md) · [demo script](docs/DEMO.md) · [API](docs/API.md) · [setup](docs/SETUP.md) · [deploying to AWS](docs/DEPLOY_AWS.md)

## What it does

**For pharmacies** — batch-level stock with FEFO and expiry risk, invoicing, client records
with an account ledger, CSV/Excel import, and analytics built on the metrics operators
actually review (turnover, DIO, GMROI, ABC classification, dead stock, reorder points,
and demand they *missed*).

**Onboarding without migration** — pharmacies keep their existing software and their own
product codes. A stdlib-only connector reads whatever their POS can already export and
pushes only what changed, over signed requests. Unknown codes are parked for a one-time
mapping, never rejected.

**For the public** — one search across every connected pharmacy, ranked by distance, other
shoppers' experience, reliability and price. Order across several pharmacies at once, or
schedule repeat refills for chronic medication. Pharmacies never expose their true stock
depth: shoppers see an orderable ceiling only.

**For doctors** — the Order of Physicians roster is pre-loaded, so activation is a one-minute
claim, not an onboarding. Prescriptions are emailed as secure QR codes.

**For any pharmacy, with no account** — scan a patient's QR (or type the code and PIN) at
`/rx`, see the items, and dispense in full or in part. The remainder stays claimable
elsewhere, exactly once.

**Delivery that isn't naive** — an order sourced from three pharmacies does not mean one
driver touring three shops for one customer. Orders are batched into routes that *share*
pharmacy visits, under real precedence, capacity and time-window constraints. On the seeded
demo: **6 orders, 1 driver, 13.7 km against a 38.9 km naive baseline — 65% less driving and
5 pharmacy visits avoided.** See [the routing section](docs/ARCHITECTURE.md#3-delivery-routing--deliveryservicesroutingpy).

Medicine prices set by the Ministry of Public Health are enforced everywhere a price can be
written; supplements and parapharmacy stay freely priced.

## Quick start

```powershell
Copy-Item .env.example .env
docker compose up -d postgres          # or set DJANGO_TEST_SQLITE=1 to skip Postgres

cd apps/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_poc
.\.venv\Scripts\python.exe manage.py runserver 8000
```

```powershell
cd apps/web
pnpm install
pnpm dev
```

Open http://localhost:3000 and follow [docs/DEMO.md](docs/DEMO.md).

`seed_poc` builds a full Beirut scenario — 5 pharmacies with deliberately fragmented stock,
3 doctors, 6 shoppers with orders clustered in two neighbourhoods, and 3 drivers — and prints
every login plus a live prescription code and PIN.

### Demo accounts

All use `Password123!`:
`admin@pharmalink.test` · `owner@cedarcare.test` · `rima.khalil@doctors.test` (doctor) ·
`shopper1@pharmalink.test` · `karim@pharmalink.test` (driver)

## Verification

```powershell
cd apps/api
$env:DJANGO_TEST_SQLITE='1'
.\.venv\Scripts\python.exe manage.py test       # 110 tests

cd ../web
pnpm exec tsc --noEmit
pnpm build
```

## Background jobs

```powershell
# Release stale stock holds, generate recurring orders, release scheduled orders,
# and re-plan delivery routes.
.\.venv\Scripts\python.exe manage.py run_scheduler --loop --every 300 --plan
```

## Non-goals

No diagnosis or treatment advice, no automatic substitution recommendations, no payment
processing or insurance claims, no native mobile app, and no microservices/Kafka/Kubernetes.
Known limitations are listed honestly at the end of [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#known-limitations).
