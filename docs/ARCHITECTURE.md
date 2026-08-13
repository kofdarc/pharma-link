# PharmaLink architecture

A Django REST API plus a Next.js frontend in a pnpm monorepo. Everything below is
implemented and covered by tests; nothing here is aspirational.

```
apps/api          Django + DRF
apps/web          Next.js (App Router, TypeScript)
tools/connector   Standalone agent that runs inside the pharmacy
```

## Domain apps

| App | Owns |
|---|---|
| `accounts` | Users and roles: platform admin, pharmacy owner/staff, doctor, customer, driver |
| `pharmacies` | Pharmacy profile, geolocation, opening hours, reputation counters |
| `medicines` | Catalog, aliases, **MoPH price regime** |
| `inventory` | Batches, FEFO stock, movements, reservations |
| `imports` | CSV/Excel preview → confirm |
| `customers` | Per-pharmacy client records (CRM) and an append-only account ledger |
| `sales` | Invoices, line items, channels (counter / platform / POS sync) |
| `prescriptions` | Scanned paper prescriptions a pharmacy uploads (pre-existing) |
| `eprescriptions` | Doctor-issued QR prescriptions consumable by **any** pharmacy |
| `orders` | Shopper baskets, multi-pharmacy sourcing, reservations, schedules, reviews |
| `payments` | Order payments: provider-agnostic charge interface, cash-on-delivery + mock gateway adapters |
| `billing` | Pharmacy revenue: subscription plans, per-request service fees |
| `delivery` | Drivers, the routing solver, routes, stops, driver operations |
| `analytics` | Read-only KPI projections (owns no tables) |
| `integrations` | Signed machine API, SKU mapping, sync runs, webhooks |
| `audit` | Append-only audit trail |

## Cross-cutting decisions

**Services, not fat views.** Business rules live in `apps/<app>/services/`. Views validate
input and translate errors into HTTP. This is what let the routing solver be tested as
pure functions with no database.

**Append-only where it matters.** `AuditLog`, `ClientLedgerEntry` and
`PrescriptionAccessLog` refuse to be updated — corrections are new entries. A dispensing
record you can silently edit is worth nothing.

**Transactions are scoped deliberately.** Two bugs found during development came from
wrapping too much in `transaction.atomic`: a raise rolled back the failure log and the
brute-force counter on prescriptions, and separately rolled back the unmet-demand signal
when a basket could not be filled. Both are now fixed and pinned by tests — the rule is
that **anything you want to survive a raise must be committed outside the block that
raises.** See the comments in `eprescriptions/services/access.py` and
`orders/services/placement.py`.

---

## 1. Pricing: MoPH-regulated vs free

Medicine prices in Lebanon are set by the Ministry of Public Health; supplements and
parapharmacy are priced freely. `Medicine` carries `price_regime` and `regulated_price`,
and `validate_selling_price()` is enforced on every path that sets a price: stock entry,
the inventory serializer, counter sales, POS sync, and the consumer quote.

The MoPH price is treated as **the** price, not a ceiling — undercutting is rejected too.
The one exception is imports: a stale price in a pharmacy's spreadsheet is snapped to the
official price with a note on the row, because failing an entire onboarding import over a
price the pharmacy does not control would be hostile.

## 2. Sourcing a basket — `orders/services/sourcing.py`

Deciding *which* pharmacies fill a basket is the first half of the delivery problem: every
extra pharmacy is another pickup stop, so the cheapest way to keep routes short is not to
create the stop at all.

Modelled as **weighted set-cover**. Per-pharmacy cost:

```
STOP_PENALTY + DISTANCE_WEIGHT·detour_km + goods_cost
             + RATING_WEIGHT·(5 − rating) + RELIABILITY_WEIGHT·shortfall%
```

- If any single pharmacy can cover the whole basket, it wins outright — no split.
- Otherwise greedy set-cover on cost-per-unit (1+ln n approximation), then a **drop pass**
  that removes any pharmacy whose items the others can absorb.
- The shopper is shown the resulting plan *and the reasoning* before committing.

## 3. Delivery routing — `delivery/services/routing.py`

**The problem.** An order with items from 3 pharmacies naively means one driver visiting
3 pharmacies then 1 customer: 4 stops to serve 1 person.

**The model.** A Pickup-and-Delivery Problem with Time Windows, plus the twist that makes
it worth doing: **pickups consolidate**. Stops are keyed by location and serve a *set* of
jobs, so two orders needing something from the same pharmacy share one visit.

Constraints (all hard):
- precedence — every pickup of an order precedes its dropoff, on the same route
- capacity — load never exceeds the vehicle
- time windows — pharmacy opening/prep time, and the customer's promised window

Objective: `total_distance + DRIVER_FIXED_COST_KM × routes_used`. The per-route fixed cost
is what makes the solver stack work onto an existing driver rather than waking a new one.

**The algorithm.**
1. **Regret-ordered insertion.** Hardest jobs first (tightest window, most pickups). For
   each job, enumerate every dropoff position × every pickup ordering; each pickup either
   *merges* into an existing stop at that pharmacy or is inserted at its cheapest position
   before the dropoff.
2. **Or-opt relocation.** Repeatedly remove a whole job and re-insert it wherever it is now
   cheapest, including on another driver. Strict improvements only, bounded passes.

> **Subtle point, learned the hard way.** Feasibility is checked only on the *completed*
> candidate route. A half-built candidate is always infeasible by construction — the dropoff
> needs the job's full unit count, which is not collected until the last pickup is placed —
> so checking mid-way rejected every multi-pharmacy order. Partial states are scored on
> distance alone. This is pinned by `test_multi_pharmacy_job_is_assignable`.

**Honest measurement.** `summarise()` compares against a naive baseline of one dedicated
trip per order — computed over the **assigned jobs only**, so the "saving" can never be
inflated by orders the plan failed to serve.

On the seeded demo: 6 orders, 3 drivers → **1 route, 13.7 km vs 38.9 km naive (−65%), 4
shared pickup stops, 5 pharmacy visits avoided.**

**Driver-facing.** `marginal_cost_for_driver()` returns the true insertion delta, so an
order that fits a corridor a driver is already on reads as near-zero. `reoptimise_remaining()`
re-sequences only unvisited stops from the driver's live GPS position — completed stops are
frozen, so it is safe mid-shift.

## 4. E-prescriptions — `eprescriptions/`

Doctors are pre-loaded from the Order of Physicians roster, so activation is a *claim*:
prove control of the licence + registered email pair, set a password, done. No forms, no
approval queue.

Security model for a document any pharmacy can consume without an account:

| Value | Storage | Purpose |
|---|---|---|
| `code` (RX-XXXX-XXXX) | plain | human-typeable identifier, **never sufficient alone** |
| QR key | SHA-256 hash only | high-entropy secret embedded in the QR link |
| PIN (6 digits) | SHA-256 hash only | manual-entry path when no camera is available |

So a database leak exposes no prescription content. Failed attempts are counted per
prescription and lock it briefly, defeating PIN brute force. Every access — success or
failure — lands in an append-only log. Dispensing uses a short-lived signed **ticket**
issued at lookup, so the long-lived secret is never re-sent.

Partial dispensing across pharmacies is first-class: quantities decrement per item, the
prescribed amount is a hard ceiling, and the remainder stays claimable elsewhere exactly
once.

## 5. Stock reservations

A confirmed order **holds** stock rather than deducting it: `InventoryBatch.reserved_quantity`
rises, `available_quantity = current_quantity − reserved_quantity` falls out of public search
and sourcing. Reservations are FEFO (earliest expiry first) and taken under `select_for_update`,
so two shoppers cannot claim the same box.

Stock actually leaves the shelf at **handover**, against a 6-digit code the pharmacist reads
to the driver — and that is also when the pharmacy's invoice is written. Holds expire on a
timer so an abandoned order cannot strand inventory.

## 6. Integration bridge — `integrations/`

The onboarding thesis: pharmacies keep their software and their product codes.

- **`SkuMapping`** maps the pharmacy's own code to our catalog, once. Obvious names
  auto-match; the rest are *parked, not rejected*, so a first sync never fails wholesale.
- **Absolute levels, not deltas.** The POS is the source of truth for its own shelf; we
  reconcile to the number it reports and write a `CORRECTION` movement for the difference,
  so the ledger still explains every change.
- **Idempotent.** Same key → first result returned, never double-applied.
- **Signed requests**, not sessions:
  `HMAC-SHA256(secret, method\npath\ntimestamp\nnonce\nsha256(body))`. The secret never
  travels; method/path/body are bound into the signature; timestamp + single-use nonce kill
  replay. Because HMAC is symmetric the server must recover the secret, so it is stored
  **encrypted** (Fernet, key derived from `DJANGO_SECRET_KEY`) — not hashed — and never
  returned by any endpoint. `secret_fingerprint` lets support identify a key safely.
- **The connector** (`tools/connector/`) is stdlib-only Python that runs on the counter PC,
  reads a CSV export or a read-only SQLite query, sends only rows whose quantity or price
  changed, retries with backoff, and drops incoming orders into a CSV the staff already watch.

## 7. Analytics — `analytics/services/kpis.py`

Owns no tables; every number is derived from the stock and sales ledgers, so no aggregate
can drift from its source. Metrics chosen from what pharmacy operators and wholesalers
actually review: inventory turnover, DIO, **GMROI**, ABC/Pareto classification, dead stock,
expiry exposure at 30/60/90 days, reorder point with safety stock
(`ROP = μ·L + z·σ·√L`, z = 1.645 for 95% service), margin split between regulated and
free-priced lines, and **unmet demand** — searches and baskets nobody nearby could fill,
which is data a till system structurally cannot produce.

## Testing

129 tests, all passing. The ones that carry weight:

- `delivery/tests/test_routing.py` — precedence, capacity, infeasible windows left
  unassigned rather than violated, pickup consolidation, marginal cost falling on an
  established corridor, baseline honesty, determinism
- `delivery/tests/test_dispatch.py` — DB → solver → driver → delivered stock + invoice
- `eprescriptions/tests/` — leaked code is useless, tampered key rejected, brute force
  locks out, over-dispense refused, partial dispense across two pharmacies, patient contact
  details withheld from the dispensing pharmacy
- `orders/tests/test_sourcing.py` — no needless splits, FEFO holds, cap enforcement,
  unmet demand recorded
- `medicines/tests/test_pricing.py` — MoPH price enforced on every write path
- `integrations/tests/test_bridge.py` — signature, tamper, replay, scope, idempotency
- `payments/tests/test_payments.py` — every order gets exactly one payment, cash on
  delivery only settles at actual handover, the mock gateway charges synchronously, a
  shopper cannot see or pay another shopper's order
- `billing/tests/test_billing.py` — a subscribed pharmacy is charged per accepted request,
  an unsubscribed or zero-fee pharmacy is not, accepting twice never double-charges

## Known limitations

Honest list, since this is a POC:

- Travel time is haversine × 1.4 at a fixed average speed. Real traffic needs a routing API;
  `apps/common/geo.py` is the single seam to swap.
- Opening stock for turnover is approximated from current stock + period COGS. A real
  deployment wants a nightly inventory snapshot table.
- Payments use a provider-agnostic interface (`apps/payments`) with cash-on-delivery and a
  mock gateway adapter; no real Lebanese payment platform is wired in yet (none chosen).
  Real money only moves for cash on delivery, and only in the trivial sense of a status
  flip at handover — no bank/wallet settlement exists.
- Route re-planning is triggered manually or by the scheduler; there is no live push to
  drivers (no WebSocket layer).
- The connector's `--check` verifies credentials and the export file, but there is no
  installer or service wrapper.
- Auth tokens (`ExpiringTokenAuthentication`) expire after `AUTH_TOKEN_TTL_HOURS` (24h
  default) and login is rate-limited; e-prescription PINs are salted/iterated (PBKDF2, not
  raw SHA-256); prescription files are encrypted at rest (`apps/prescriptions/storage.py`).
  Not yet done: encrypting other PII columns (patient/doctor names, phone numbers, addresses)
  at the database level, and real disk/volume-level encryption for Postgres itself — both
  are infra-level concerns this POC's `docker-compose.yml` doesn't configure.
