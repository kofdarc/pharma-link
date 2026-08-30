<div align="center">

<img src="apps/web/public/brand/mark-primary.webp" alt="HealthConnect" width="104">

# HealthConnect

**Healthcare, *finally* connected.**

HealthConnect lets patients search connected pharmacies across Lebanon. It also gives
doctors a quick way to issue QR prescriptions, helps pharmacies manage stock and
invoicing, and combines deliveries into efficient routes.

### [**healthconnect.dev →**](https://healthconnect.dev)

[![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.15-A30000)](https://www.django-rest-framework.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PWA](https://img.shields.io/badge/PWA-ready-00BF63)](apps/web/public/manifest.json)
![Tests](https://img.shields.io/badge/tests-322%20passing-00BF63)

[Architecture](docs/ARCHITECTURE.md) · [Demo script](docs/DEMO.md) · [API](docs/API.md) · [Setup](docs/SETUP.md) · [Smart features](docs/AI_FEATURES.md) · [Deploy](docs/DEPLOY_AWS.md)

</div>

<br>

<img src="docs/screenshots/landing.png" alt="HealthConnect landing page">

<br>

## The problem

Finding a medicine in Beirut can take several phone calls. Pharmacies cannot see what
nearby pharmacies have in stock, and patients still rely on paper prescriptions. Orders
that span several pharmacies can also result in separate delivery trips.

HealthConnect brings patients, pharmacies, physicians, and drivers together. Pharmacies
can continue using their existing software.

<br>

## For patients

Search once by brand or generic name and see what is genuinely available across connected
pharmacies, ranked by distance, other shoppers' experience, reliability, and price. Order
across several pharmacies at once, track it to the door, or schedule repeat refills for
chronic medication.

Pharmacies do not expose their exact stock levels. Shoppers only see how much they can
order.

| Search across every pharmacy | Availability, pharmacy by pharmacy |
|---|---|
| <img src="docs/screenshots/search.png" alt="Medicine search results"> | <img src="docs/screenshots/medication-detail.png" alt="Medication detail with availability"> |

| Orders, tracked to the door | |
|---|---|
| <img src="docs/screenshots/shopper-orders.png" alt="Shopper order tracking"> | Orders from multiple pharmacies arrive in **one** delivery, with live status updates and an arrival window. |

<br>

## For pharmacies

Pharmacies can manage stock by batch using FEFO, monitor expiry risk, create invoices,
maintain client ledgers, and import CSV or Excel files. Analytics cover turnover, DIO,
GMROI, ABC classification, dead stock, reorder points, and unmet demand.

| Dashboard | Analytics |
|---|---|
| <img src="docs/screenshots/pharmacy-dashboard.png" alt="Pharmacy dashboard"> | <img src="docs/screenshots/pharmacy-analytics.png" alt="Pharmacy analytics"> |

<img src="docs/screenshots/pharmacy-inventory.png" alt="Pharmacy inventory with batches and expiry">

### Onboarding without migration

Pharmacies keep their existing software and product codes. A connector built with the
Python standard library reads existing POS exports and sends only changed records through
signed requests. Staff can map unknown codes once and reuse those mappings afterward.

For the safe export-based SoftPharm workflow, see the
[SoftPharm connector setup](docs/SOFTPHARM_CONNECTOR.md).

<br>

## For doctors

The Order of Physicians roster is already loaded, which allows doctors to claim their
account quickly. Prescriptions are emailed to patients as secure QR codes.

| Write a prescription | Everything you have issued |
|---|---|
| <img src="docs/screenshots/doctor-new-rx.png" alt="Write a prescription"> | <img src="docs/screenshots/doctor-rx-list.png" alt="Issued prescriptions"> |

<br>

## For any pharmacy, with no account

At `/rx`, a pharmacist can scan the patient's QR code or enter the code and PIN. The
prescription can be dispensed in full or in part, and any remaining items can be claimed
once at another pharmacy.

<img src="docs/screenshots/rx-dispense.png" alt="Dispense a prescription without an account">

<br>

## Delivery routing

Orders are grouped into routes that share pharmacy visits where possible. The routing
logic accounts for visit order, driver capacity, and delivery time windows.

| Dispatch board | Driver console |
|---|---|
| <img src="docs/screenshots/admin-dispatch.png" alt="Admin dispatch board"> | <img src="docs/screenshots/driver.png" alt="Driver route console"> |

In the full `seed_poc` scenario, **6 orders require 1 driver and 13.7 km of travel, compared
with a 38.9 km baseline. This reduces driving by 65% and avoids 5 pharmacy visits.** The
board above shows a smaller live batch, so its numbers differ. See
[the routing section](docs/ARCHITECTURE.md#3-delivery-routing--deliveryservicesroutingpy).

Medicine prices set by the Ministry of Public Health are enforced everywhere a price can be
written; supplements and parapharmacy stay freely priced.

<br>

## Built with

| Layer | Stack |
|---|---|
| **API** | Django 5 · Django REST Framework · PostgreSQL (SQLite for dev) |
| **Web** | Next.js 14 (App Router) · TypeScript · React 18 · PWA |
| **Connector** | Python standard library only; runs on the pharmacy's existing system |
| **i18n** | English · Arabic · French, with RTL |
| **Deploy** | Docker Compose · AWS Amplify ([guide](docs/DEPLOY_AWS.md)) |

<br>

## Quick start

```bash
cp .env.example .env
docker compose up -d postgres          # or set DJANGO_TEST_SQLITE=1 to skip Postgres
```

**API**

```bash
cd apps/api
python -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py seed_poc
./.venv/bin/python manage.py runserver 8000
```

**Web**

```bash
cd apps/web
pnpm install
pnpm dev
```

Open <http://localhost:3000> and follow [docs/DEMO.md](docs/DEMO.md).

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
Copy-Item .env.example .env
docker compose up -d postgres

cd apps/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_poc
.\.venv\Scripts\python.exe manage.py runserver 8000
```

</details>

`seed_poc` builds a Beirut scenario with 5 pharmacies whose stock is deliberately
fragmented, 3 doctors, 6 shoppers, refill schedules, electronic prescriptions, saved
payment methods, and 3 drivers. The orders cover every lifecycle state. The command also
prints each login and a working prescription code and PIN.

The demo catalogue uses real products registered by the MoPH. `seed_poc` selects 20 products
loaded by `sync_moph_catalog`, with one product for each active ingredient listed in
`SEED_INGREDIENTS`, and uses their published prices. Run the catalogue sync first. The seed
command exits with an explanation if the required data is missing.

### Demo accounts

All use `Password123!`

| Role | Email |
|---|---|
| Platform admin | `admin@pharmalink.test` |
| Pharmacy owner | `owner@cedarcare.test` |
| Pharmacy staff | `staff@cedarcare.test` |
| Doctor | `rima.khalil@doctors.test` |
| Shopper | `shopper1@pharmalink.test` |
| Driver | `karim@pharmalink.test` |

Two more physicians (`samir.aoun@doctors.test`, `lina.nassar@doctors.test`) are left
unactivated so the account claim flow can be demonstrated.

<br>

## Repository layout

```
apps/api            Django + Django REST Framework
apps/web            Next.js + TypeScript
tools/connector     The agent that runs inside the pharmacy
docs/               Architecture, API, setup, demo script, deployment
```

<br>

## Verification

```bash
cd apps/api
DJANGO_TEST_SQLITE=1 ./.venv/bin/python manage.py test    # 322 tests

cd ../web
pnpm exec tsc --noEmit
pnpm build
```

Django's SQLite backend always runs tests against an in-memory database, so this never
touches your dev data.

## Background jobs

```bash
# Release stale stock holds, generate recurring orders, release scheduled orders,
# and re-plan delivery routes.
./.venv/bin/python manage.py run_scheduler --loop --every 300 --plan
```

<br>

## Non-goals

No diagnosis or treatment advice, no automatic substitution recommendations, no payment
processing or insurance claims, no native mobile app, and no microservices/Kafka/Kubernetes.
Known limitations are listed honestly at the end of
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#known-limitations).

<br>

<div align="center">

A student project built at the American University of Beirut.

**HealthConnect does not provide medical advice.**

</div>
