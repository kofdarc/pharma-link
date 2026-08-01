# PharmaLink POC — demo script

About 15 minutes end to end. Every step below works against seeded data.

## Setup

```powershell
# Backend
cd apps/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DJANGO_TEST_SQLITE='1'          # or start Postgres: docker compose up -d postgres
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_poc
.\.venv\Scripts\python.exe manage.py runserver 8000
```

```powershell
# Frontend, in a second terminal
cd apps/web
pnpm install
pnpm dev
```

Open http://localhost:3000.

`seed_poc` prints the demo prescription code, PIN and QR link — **copy them**, they are
shown once by design.

### Accounts (password `Password123!` for all)

| Role | Email |
|---|---|
| Platform admin | `admin@pharmalink.test` |
| Pharmacy owner (Cedar Care, Hamra) | `owner@cedarcare.test` |
| Pharmacy owner (Achrafieh Health) | `owner@achrafiehhealth.test` |
| Doctor (already activated) | `rima.khalil@doctors.test` |
| Shopper | `shopper1@pharmalink.test` |
| Driver | `karim@pharmalink.test` |

Not activated, to demo the zero-onboarding claim: licence `LB-MD-20876` /
`samir.aoun@doctors.test`, and `LB-MD-30155` / `lina.nassar@doctors.test`.

---

## Act 1 — Doctor issues a prescription (2 min)

1. Go to **/activate**. Enter licence `LB-MD-20876`, email `samir.aoun@doctors.test`, pick a
   password. → *No profile form. The Order of Physicians roster already had him; he only
   claimed the account, and is signed straight in.*
2. **Write a prescription** → patient name, an email, two items (try Augmentin and Panadol).
3. Issue it. The QR renders on screen with a code and PIN.
   > **Point to make:** the PIN and QR key are shown once and stored only as SHA-256 hashes.
   > A database leak exposes no prescription content.
4. Look at the terminal running Django — the patient's email is printed there, QR attached
   (console email backend; point `EMAIL_*` at real SMTP and nothing else changes).

## Act 2 — Any pharmacy dispenses it, with no account (3 min)

1. Open **/rx** in a *private window* — you are nobody, not logged in.
2. Enter the code and PIN (or scan the QR with a phone camera).
3. The prescription opens: items, quantities, dosage, prescriber and licence.
   > **Point to make:** the patient's email and phone are deliberately **not** shown. The
   > pharmacist gets what they need to dispense, nothing more.
4. Dispense **part** of it — say 6 of 14 Augmentin. Enter a pharmacy name and pharmacist.
5. Reload and open the same prescription again: the remaining 8 are still claimable, and the
   earlier dispense is listed as history from another pharmacy.
6. Try to dispense more than remains → refused. Try a wrong PIN 5 times → the prescription
   locks out.

## Act 3 — Shopper orders across multiple pharmacies (4 min)

1. Sign in as `shopper1@pharmalink.test`, go to **/shop**.
2. Search `paracetamol`. Results are ranked by distance, rating and reliability, with prices
   labelled **"Price set by the Ministry of Public Health"** or **"Price set by the pharmacy"**.
   > **Point to make:** quantities show only an *orderable ceiling* (`available_up_to`), never
   > the pharmacy's true stock depth.
3. Add a couple of items that no single pharmacy stocks — e.g. Panadol (Cedar Care) and
   Nexium (Achrafieh Health).
4. Go to the **basket**. The sourcing plan appears before you commit: which pharmacies,
   how far, their rating, and an expandable **"Why these pharmacies?"**.
   > **Point to make:** the planner tries hard *not* to split. It splits here only because no
   > one pharmacy has both.
5. Optionally tick **"Repeat this order automatically"** to create a chronic-medication schedule.
6. Place the order. Stock is now *held* at both pharmacies — not deducted.

## Act 4 — Pharmacies accept (1 min)

1. Sign in as `owner@cedarcare.test` → **Online orders**.
2. The order shows *"part of a multi-pharmacy order"*, so staff prepare only their items.
3. Accept it, mark ready. Note the **handover code**.
4. Repeat as `owner@achrafiehhealth.test` for the other half.

## Act 5 — The routing engine (4 min) ← *the centrepiece*

1. Sign in as `admin@pharmalink.test` → **Dispatch board**.
2. Look at the tiles:
   - **Naive distance** — one dedicated trip per order
   - **Optimised distance** — the batched plan
   - **Distance saved** and **Pharmacy visits avoided**
   > On seeded data: **6 orders, 13.7 km vs 38.9 km, −65%, 4 shared pickup stops, 5 visits
   > avoided.** The baseline covers only the orders actually assigned, so the number is not
   > flattering itself.
3. Scroll the proposed plan. Stops marked **shared** are one pharmacy visit serving several
   different customers — that is the whole trick.
4. Click **Plan routes now** to commit.
5. Sign in as `karim@pharmalink.test` → the **driver console**.
   - One next action at a time, never a map to interpret.
   - At a pharmacy, *every* order to collect there is listed together, each with its own
     handover code.
6. Enter the handover codes, confirm collection. Watch the pharmacy's stock finally decrement
   and an invoice appear under **Sales** — an online order lands in their books like a
   counter sale.
7. Confirm the delivery. The order closes; the shopper can now rate each pharmacy, which
   feeds straight back into search ranking.

## Act 6 — Analytics and onboarding (3 min)

1. As `owner@cedarcare.test` → **Analytics**.
   - *Overview*: revenue, margin, turnover, **GMROI**, expiry exposure at 30/60/90 days.
   - *Inventory health*: **ABC/Pareto** classification and cash trapped in dead stock.
   - *What to reorder*: reorder points with safety stock at a 95% service level.
   - *Demand you missed*: searches and baskets in the area nobody could fill.
     > **Point to make:** this is the one number a till system can never produce — demand
     > that walked away before it reached a counter.
2. → **Connect software**.
   - The onboarding checklist is derived from real data, not tick boxes.
   - Issue an integration key (secret shown once).
   - **Your product codes**: one deliberately unmapped code is waiting. Map it in one click.
     > **Point to make:** the pharmacy never renames anything. They keep their codes; we map.
3. Optionally run the connector against the API:
   ```powershell
   cd tools/connector
   python pharmalink_connector.py --config connector.config.json --check
   ```

---

## Verification

```powershell
cd apps/api
$env:DJANGO_TEST_SQLITE='1'
.\.venv\Scripts\python.exe manage.py test          # 110 tests

cd ../web
pnpm exec tsc --noEmit
pnpm build
```

## Background jobs

```powershell
# Releases stale stock holds, generates recurring orders, releases scheduled
# orders into the dispatch pool, and re-plans routes.
.\.venv\Scripts\python.exe manage.py run_scheduler --plan
.\.venv\Scripts\python.exe manage.py run_scheduler --loop --every 300 --plan
```
