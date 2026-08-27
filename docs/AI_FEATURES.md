# Smart & AI features

A living catalog of every "smart" capability in PharmaLink — implemented today, whether or
not it uses AI, plus every AI feature that has been proposed but not built. The point of
including non-AI entries is to be honest about what already exists (a lot of this platform's
intelligence is deterministic optimization, not ML) and to flag which of those pieces are a
natural AI upgrade path versus ones that should probably stay deterministic on purpose
(compliance, pricing, audit).

**Hard boundary, from `docs/PRD.md`:** no diagnosis, no treatment advice, no automatic
substitution recommendations. Any proposal below that brushes against that line is flagged
explicitly — it should ship as pharmacist-facing decision support at most, never a
consumer-facing recommendation.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ Built · deterministic | Shipped today, rule-based/statistical, no ML |
| ✅ Built · AI-ready seam | Shipped today, deterministic, but the codebase already marks it as the swap point for a model |
| 💡 Proposed · AI | Not built. Genuinely needs a model (embeddings, LLM, forecasting) |
| 💡 Proposed · smart, non-AI | Not built. Achievable with rules/statistics alone — AI would be a nice-to-have upgrade, not a requirement |
| ⚠️ Boundary | Sits near the "no diagnosis/treatment advice" non-goal — needs deliberate scoping |

---

## 1. Search & catalog (`apps/medicines`)

This is the section we're starting with, so it gets the deepest treatment.

### Current state

`apps/medicines/services/search.py` already does two-stage matching:

1. **Direct substring match** (`icontains`) across `brand_name`, `generic_name`, and
   `MedicineAlias.alias`.
2. **Fuzzy fallback** — if fewer than `limit` results, it pulls up to 500 remaining active
   medicines and scores each against the query with `difflib.SequenceMatcher`, keeping
   anything ≥ 0.68 similarity. `best_catalog_match()` (used by imports/POS sync to resolve a
   free-text product name to a catalog row) does the same thing over up to 1000 candidates at
   a 0.78 threshold.

So **typo tolerance already exists** — it's real, but has two structural limits worth naming:
- It's an **O(n) Python scan** capped at 500–1000 rows, not an index — fine at today's catalog
  size, won't scale past a few thousand SKUs without either a real trigram/vector index or a
  pre-filtered candidate set.
- `SequenceMatcher` is **character-edit-distance style**, not semantic or phonetic — it
  catches "parasetamol" but won't connect "panadol" → "paracetamol" (different words
  entirely) or an Arabic-script query to a Latin-script catalog. That's a different problem:
  *alias coverage*, not *typo tolerance*.
- There is no language/script field anywhere in the schema — `MedicineAlias` has no way to
  say "this is the Arabic name" or "this is a transliteration."

### Proposed upgrades

| Feature | Status | Approach | Notes |
|---|---|---|---|
| Brand↔generic alias search ("panadol" → paracetamol) | ✅ Built · deterministic | Works **if** the alias exists as a row. Search also matches `generic_name` directly, which the MoPH catalog populates for every product. | Coverage is only as good as the imported alias set. `seed_poc` no longer writes aliases: it now selects real MoPH products rather than creating a fictional catalog, and inventing transliterations for real registered brands would be putting made-up data in the catalogue. An alias-coverage pass over the synced catalog is the open follow-up. |
| Unicode-aware fuzzy matching (was ASCII-only, silently stripped Arabic/accented text to nothing) | ✅ Built · deterministic | `normalize_name()` in `apps/medicines/services/search.py` now uses `\w` (Unicode-aware) instead of `[a-z0-9]`. | Bug fix uncovered while scoping this section — the fuzzy fallback couldn't have matched any non-Latin script before this. |
| Arabic-script alias support | ⚠️ Partly built · deterministic | `MedicineAlias.AliasType.TRANSLITERATION` exists (migration `0005`) and both exact and fuzzy search read aliases through the existing `icontains`/`SequenceMatcher` paths. | The matching side is done; the **data** side is not. The demo aliases this row used to describe were attached to a fictional seed catalog that no longer exists. Transliterations for the real MoPH catalog have to come from a real source, not from the seed command. |
| Replace the O(n) scan with a real fuzzy index | ✅ Built · deterministic (Postgres only) | `pg_trgm` GIN indexes on `brand_name`/`generic_name`/`alias` (migration `0006_trigram_search_indexes`) + a `TrigramSimilarity`-based fast path in `search_medicines()`/`best_catalog_match()`, used automatically when `connection.vendor == "postgresql"`. | Every operation in the migration is guarded to no-op on non-Postgres backends (verified against a scratch SQLite DB) since this repo's dev/test DB is SQLite (`apps/api/test.sqlite3` — never touched by this work) while production is Postgres. The SQLite dev path still uses the original Python scan, now capped/named via `FUZZY_SCAN_LIMIT`/`FUZZY_MATCH_THRESHOLD` constants. Alias fuzzy-matching (as opposed to brand/generic) still falls back to the Python scan on every backend — a real trigram query aggregated across the alias table's related rows is a known follow-up, not solved here. |
| Semantic/embedding search (catches unlisted brand↔generic pairs without a manual alias row) | 💡 Proposed · AI | Embed `brand_name + generic_name + aliases` per medicine once (small local model, e.g. a sentence-transformer, or an API embedding call), store the vector, cosine-similarity at query time. | Needs a vector column/index (pgvector on Postgres) or an external vector store. Bigger infra lift than alias-seeding/trigram — worth doing once the catalog is large enough that manual aliasing can't keep up. |
| LLM-assisted query normalization for transliterated/Arabizi queries beyond the seeded alias list | 💡 Proposed · AI | Send the raw query to a model, get back a canonical drug name guess, then run it through existing search. | Recommend this only as a **zero-result fallback**, not the default path — adds latency + an external call cost per query otherwise. The rules-based alias seeding above already covers the head of the distribution for free. |
| Voice/speech search entry | 💡 Proposed · AI | Off-the-shelf speech-to-text (browser Web Speech API client-side, or a hosted STT call) feeding the existing search box. | Pure UX add-on, no new backend logic — the hard part is already the query-understanding above. |
| Query autocomplete / did-you-mean | 💡 Proposed · smart, non-AI | Prefix index over `brand_name`/`generic_name`/alias, ranked by search-frequency (which `analytics`'s unmet-demand tracking already gives a hook into). | No model required; standard search-UX feature. |
| Alias-aware trigram matching (aggregate similarity across `MedicineAlias` rows on Postgres) | 💡 Proposed · smart, non-AI | Extend the `_trigram_search`/`best_catalog_match` fast path to also rank by best-matching alias, not just `brand_name`/`generic_name`. | Flagged as a known gap above — the straightforward per-column `TrigramSimilarity` doesn't extend cleanly across a reverse FK without an aggregate subquery. |

**Status:** steps 1–2 of the original recommended order (alias-coverage pass, scale fix) are
done. Remaining: embeddings once catalog volume justifies it, LLM query normalization as a
zero-result fallback, and the alias-aware trigram follow-up.

---

## 2. Prescription intake (`apps/prescriptions`, `apps/eprescriptions`)

| Feature | Status | Notes |
|---|---|---|
| QR/PIN-secured e-prescription lookup, partial dispensing across pharmacies, brute-force lockout, append-only access log | ✅ Built · deterministic | Security model, not AI — see `docs/ARCHITECTURE.md` §4. Left here for completeness since it's the most "smart" thing in the app today. |
| PrescribeIT-style guaranteed delivery: direct-to-pharmacy "Create Rx", deferred transmission (patient carries the QR/PIN barcode to any pharmacy), fax back-up when email is missing or fails | ✅ Built · deterministic | `apps/eprescriptions/services/issue.py` tries email first (`send_prescription_email`); if there's no `patient_email` or the send raises, and a `patient_fax` was captured, `send_prescription_fax` (`apps/eprescriptions/services/fax.py`, provider-agnostic like `apps.messaging.providers`, console-only today) sends a text-only fax with the code/PIN. `email_sent_at`/`fax_sent_at` record which channel actually delivered. The e-signed paper copy (QR code) handed to the patient at issue time remains the authoritative record regardless of whether either digital channel succeeds. |
| OCR + structured extraction from uploaded paper prescriptions (drug/dose/qty pre-fill) | ✅ Built · pluggable (deterministic default, two optional upgrades) | `apps/prescriptions/services/ocr/` (provider interface mirroring `apps.payments.providers`/`apps.messaging.providers`), `apps/prescriptions/services/extraction.py` (regex dose/qty parsing + catalog matching via the same `best_catalog_match()` search uses), `POST /api/pharmacy/prescriptions/{id}/extract/`, "Extract with OCR" action on the pharmacy prescriptions page. Candidates are never persisted as an order or dispensed automatically — a pharmacist reviews and selects lines, which prefill (not auto-submit) the new-sale form. | **Answers "do we need an external provider":** not by default, and there's now a free *self-hosted* upgrade path before reaching for one — see the three-tier quality comparison in the next two rows. `settings.PRESCRIPTION_OCR_PROVIDER` defaults to `"tesseract"` (zero external account — the Dockerfile installs the `tesseract-ocr` system package). It handles **printed** prescriptions reasonably; handwriting is a known weak spot for it specifically. JPG/PNG and PDF are both supported: Tesseract and EasyOCR both render PDF pages via `pdf2image`/`poppler-utils` (added to the Dockerfile) before OCR-ing each page; the Anthropic provider reads PDF natively as a `document` content block, no rendering step needed. Tesseract loads `eng+fra+ara` language data (previously English-only, which silently produced garbage on French or Arabic prescriptions — the majority script mix in Lebanon) and applies grayscale/autocontrast preprocessing before OCR-ing a phone-photo-quality scan. `extraction.py`'s regex layer recognises French posology unit words (cp/comprimé, gél/gélule, sachet) and skips French/Arabic metadata lines (nom, docteur, اسم, الطبيب, ...) in addition to English, and disambiguates same-brand strength variants (e.g. "Panadol 500mg" vs a "Panadol 1g" catalog row) by preferring the sibling whose `strength` matches the dose written on the line, since `best_catalog_match()` itself only matches on name/alias text. `OcrResult` now carries an optional `confidence` score (mean word confidence for Tesseract/EasyOCR; `None` for the Anthropic provider, which doesn't expose an equivalent) — not yet wired to anything, but the intended foundation for a future low-confidence-triggers-escalation gate rather than a global provider switch. Full posology parsing (per-dose × frequency × duration, e.g. "1 cp x 3/j pendant 7j" → total 21) is still out of scope — the quantity regex only catches an explicit total. |
| Free, still-self-hosted quality upgrade over Tesseract | ✅ Built · optional, no external account | `PRESCRIPTION_OCR_PROVIDER=easyocr` → `EasyOcrProvider`. A real detection+recognition deep-learning pipeline (CRAFT+CRNN) instead of Tesseract's classical glyph matching, so it generalises better to varied fonts, lighting, and moderately messy handwriting — genuinely the best *free* option, per the ranked comparison worked out in conversation: Anthropic vision > EasyOCR ≈ PaddleOCR > TrOCR (recognition-only, no detection, no Arabic) > Tesseract. Heavier than Tesseract: pulls in PyTorch, downloads model weights on first use per process, and is slower per request — kept out of `requirements.txt` and the default Dockerfile entirely — it lives in `requirements-easyocr.txt` as an explicit opt-in cost, not a replacement default, because torch/torchvision/opencv add several GB to an image that is pulled on every task start for a provider that is off unless selected. Selecting the provider without installing those extras raises a clear `OcrProviderError` telling you which file to install, not a bare `ModuleNotFoundError`. Same inert-until-selected pattern as the other adapters. Two real integration bugs found and fixed while wiring this in, both worth knowing about if this provider is touched again: (1) EasyOCR rejects `Reader(["en","fr","ar"])` outright ("Arabic is only compatible with English" — verified against the installed package, unlike Tesseract's `eng+fra+ara` which works fine together), so `easyocr_provider.py` runs two compatible readers (`en+fr` and `en+ar`) over the same image and merges detections by matching bbox position, keeping only the higher-confidence transcription per region — needed because naively concatenating both readers' output duplicated every line and kept the losing reader's garbage (English text forced through the Arabic recognizer produced `"P٥٧A٥٥L5٥٥MIG"` for `"PANADOL 500MG"` instead of failing loudly). (2) Installing `torch` alone from PyPI's default index pulls a multi-GB CUDA/GPU build nobody asked for (inference always runs `gpu=False`), and installing it from the CPU-only index *without* `torchvision` alongside it lets `easyocr` pull a mismatched `torchvision` from the default index afterward, which fails to import with `"operator torchvision::nms does not exist"` — both packages have to be installed together, from the same CPU index, in one command (see the Dockerfile and the header comment in `requirements-easyocr.txt`). |
| Handwriting-specialized transcription via a real vision-language model | ✅ Built · optional (needs `ANTHROPIC_API_KEY`) | `AnthropicOcrProvider` — a real vision model prompted to transcribe only ("no summary, no interpretation, no added dosage/medical advice beyond what is literally written"), deliberately kept a pure OCR step rather than an "interpret this prescription" request, to stay clear of the diagnosis/treatment-advice non-goal. Still the clear quality leader on genuinely bad handwriting — neither free option has its drug-name world knowledge or language-model context to disambiguate an illegible stroke. Off by default; sends the prescription image externally when enabled, so it's a compliance decision, not just a cost one. |
| Anomalous access-pattern detection on the append-only access log | 💡 Proposed · smart, non-AI (start), AI (later) | Simple threshold rules first (N failed lookups from one IP/pharmacy in a window); ML anomaly scoring is a later refinement once there's enough log volume to train on. |

---

## 3. Sourcing a basket (`apps/orders/services/sourcing.py`)

| Feature | Status | Notes |
|---|---|---|
| Weighted set-cover sourcing (`STOP_PENALTY + DISTANCE_WEIGHT·detour + goods_cost + RATING_WEIGHT·(5−rating) + RELIABILITY_WEIGHT·shortfall%`), greedy cost-per-unit with a drop pass | ✅ Built · deterministic | `docs/ARCHITECTURE.md` §2. A real optimization algorithm, not ML — and arguably shouldn't become one; it's explainable by construction, which the product relies on (shopper sees the plan *and the reasoning*). |
| Freshness-weighted stale-POS penalty | ✅ Built · AI-ready seam | Already a place where a smarter reliability signal could plug in without touching the cost-function shape. |
| ML-predicted `shortfall%` replacing/augmenting the static reliability counter | 💡 Proposed · AI | Feed the same weight slot with a model trained on historical fulfillment-vs-promised data instead of (or blended with) the current counter. Low blast radius — one input to an existing formula. |
| Natural-language plan explanation for the shopper | 💡 Proposed · AI | The structured reasoning already exists (which pharmacies, why, cost breakdown); an LLM turning that into one plain sentence is a thin wrapper, not new logic. |

---

## 4. Delivery routing (`apps/delivery/services/routing.py`)

| Feature | Status | Notes |
|---|---|---|
| Pickup-and-Delivery Problem with Time Windows solver: regret-ordered insertion, pickup consolidation, or-opt relocation, marginal-cost-for-driver, live re-optimization from GPS position | ✅ Built · deterministic | `docs/ARCHITECTURE.md` §3. A real OR solver with tests pinning correctness (precedence, capacity, feasibility). This is core IP — not something to replace with a black box. |
| `haversine × 1.4` fixed-speed travel time | ✅ Built · AI-ready seam | Explicitly called out in ARCHITECTURE.md as a known limitation with `apps/common/geo.py` as "the single seam to swap." |
| Learned/real travel-time model | 💡 Proposed · AI | Historical route data (or a routing API) → predicted ETA, feeding the existing solver's cost function through that one seam. Doesn't touch the solver itself. |
| Demand-clustering-based driver pre-positioning | 💡 Proposed · AI | Predict where orders will cluster by time/area to suggest driver staging before orders land — extends `marginal_cost_for_driver()`'s "near-zero cost on an established corridor" logic proactively instead of reactively. |
| Live push to drivers (WebSocket) | ✅/💡 Not AI at all | Called out in ARCHITECTURE.md's known limitations. Listed here only because it's a prerequisite for the pre-positioning idea above to be actionable in real time. |

---

## 5. Inventory & analytics (`apps/inventory`, `apps/analytics/services/kpis.py`)

| Feature | Status | Notes |
|---|---|---|
| FEFO stock allocation under `select_for_update` | ✅ Built · deterministic | Correctness-critical rule (earliest-expiry-first); should stay deterministic. |
| Reorder point with safety stock, `ROP = μ·L + z·σ·√L` (z=1.645, 95% service) | ✅ Built · deterministic | `docs/ARCHITECTURE.md` §7. Statistical, auditable formula. |
| Inventory turnover, DIO, GMROI, ABC/Pareto classification, dead-stock and 30/60/90-day expiry exposure, margin split, unmet demand | ✅ Built · deterministic | All derived read-only from the sales/stock ledgers — "no aggregate can drift from its source." |
| `ReservationShortfall` flagging when POS reconciliation lands below what shoppers already hold | ✅ Built · deterministic | `inventory/services/stock.py`. Correctly *not* silently absorbed. |
| ML demand forecasting feeding μ/σ into the existing ROP formula | 💡 Proposed · AI | Seasonality, local outbreak/flu signals, promotions → better inputs to the *same* auditable formula, rather than a opaque forecast replacing it. Keeps the "z=1.645, 95% service" logic legible to pharmacy operators. |
| Expiry-exposure markdown/reallocation advisor | 💡 Proposed · AI (or rules) | Analytics already computes 30/60/90-day exposure; turning that into proactive discount or cross-pharmacy reallocation suggestions can start as threshold rules, upgrade to a model later. |
| **Smart Insights** — plain-language digest synthesizing stock/replenishment/movement/demand/platform KPIs into prioritized cards (critical/warning/opportunity/info) | ✅ Built · deterministic (no external provider) | `apps/analytics/services/insights.py`, `GET /api/pharmacy/analytics/insights/`, "Insights" tab in the pharmacy analytics UI (en/ar/fr). Templated from numbers `kpis.py` already computes — expiry exposure, reorder-now count, dead-stock value, unmet demand for unstocked items, low stock, regulated-revenue mix, GMROI, order acceptance rate. | This is the answer to "do we need an external provider": **not for v1.** A rule-based digest covers the concrete, numeric insights pharmacy owners actually asked for at zero per-request cost, zero external data egress, and zero risk of a model inventing a figure. It supersedes the two rows below for the cases it covers. |
| Free-form natural-language digest / narrative trend summary (e.g. "your Panadol sales dipped 12% vs last month, likely tied to the Doliprane stockout on the 14th") | 💡 Proposed · AI | This is the point where an LLM genuinely earns its cost — connecting multiple metrics into prose/causal narration isn't a template. Would need an external provider (Anthropic Claude API is the natural fit given no local GPU infra exists here) since a model of that quality isn't self-hostable cheaply. Build this only if pharmacy owners ask for more than the Smart Insights cards give them. |
| Natural-language KPI queries ("show me dead stock over 90 days") | 💡 Proposed · AI | A constrained text-to-query layer over the existing read-only `analytics` service, not free-form SQL generation against the DB. Needs an external LLM provider for the query-understanding step; the query *execution* stays the existing deterministic `kpis.py` functions. |

---

## 6. POS integration bridge (`apps/integrations`)

| Feature | Status | Notes |
|---|---|---|
| HMAC-signed sync API, idempotent absolute-level reconciliation with `CORRECTION` movements, "obvious names auto-match, rest parked (not rejected)" SKU mapping | ✅ Built · deterministic | `docs/ARCHITECTURE.md` §6. Security and correctness properties are load-bearing (replay/tamper resistance) — not AI candidates. |
| "Obvious name" SKU auto-matching | ✅ Built · deterministic, AI-ready seam | The current matcher's threshold for "obvious" is a natural spot for an upgrade. |
| Embedding-based SKU auto-matching for the parked queue | 💡 Proposed · AI | Semantic similarity over product name + brand + pack size to shrink the manually-parked backlog, surfaced as confidence-scored suggestions staff confirm — fits the existing "parked, not rejected" philosophy exactly rather than replacing it. |
| Connector-drift anomaly detection | 💡 Proposed · AI (start with rules) | Distinguish "genuine `ReservationShortfall`" from "this pharmacy's connector has silently stopped syncing" — start with a staleness threshold (the sourcing penalty already has one), graduate to pattern-based detection if false positives are a problem. |
| AI-assisted onboarding for a future SoftPharm/NIT connector | 💡 Proposed · AI | See `project-softpharm-integration` memory — mapping SoftPharm's schema/exports to PharmaLink's canonical catalog (GTIN/batch/expiry) is exactly the kind of fuzzy schema-mapping problem an LLM assist helps with, once there's a real data sample to work from. |

---

## 7. Imports (`apps/imports`)

| Feature | Status | Notes |
|---|---|---|
| CSV/Excel preview → confirm, MoPH price snapping with a note on stale rows | ✅ Built · deterministic | Deliberately fails soft on price (snap + note) rather than rejecting the whole import. |
| AI-assisted column mapping detection | 💡 Proposed · AI | Pharmacies' spreadsheets won't share a schema; auto-detecting "this column is generic name, this one is pack size" from header text + sample values (LLM or heuristic classifier) instead of manual column selection would directly reduce onboarding friction. |
| Row-level product matching via `best_catalog_match()` | ✅ Built · deterministic, AI-ready seam | Same fuzzy-match function used by search (§1) — any upgrade there (embeddings, `pg_trgm`) benefits imports for free. |

---

## 8. Trust, fraud, compliance

| Feature | Status | Notes |
|---|---|---|
| Insurance claim manual adjudication tracker (`SUBMITTED → APPROVED/REJECTED → PAID`) | ✅ Built · deterministic | `apps/insurance` — deliberately manual since Lebanon's TPAs (GlobeMed, LibanCard, NexCare, MedNet…) have no shared API. |
| Insurance claim anomaly flagging (unusual billed/covered ratios) | 💡 Proposed · AI | Flags for staff review only, never auto-decision — adjudication stays human. |
| Pharmacy reputation counters | ✅ Built · deterministic | Simple counters today (`apps/pharmacies`). |
| Review/rating fraud detection | 💡 Proposed · AI | Coordinated or fake review detection once review volume exists to make it worth building. |
| MediTrack compliance mapping assist (MoPH Decision 412/1) | 💡 Proposed · AI | See `project-softpharm-integration` memory — mapping PharmaLink's medication master to MediTrack's is a schema-alignment task an LLM can accelerate once that integration is actually scoped. |
| Append-only audit log (`apps/audit`) | ✅ Built · deterministic | Correctness/compliance-critical — should never be non-deterministic. |
| Plain-language audit trail summarization for investigations | 💡 Proposed · AI | Summarize a raw audit trail into a human-readable narrative for a specific investigation — read-only convenience layer on top of, never a replacement for, the raw log. |

---

## 9. Pharmacy & platform operations

| Feature | Status | Notes |
|---|---|---|
| Messaging channels/providers (`apps/messaging`) | ✅ Built · not AI | Delivery mechanism only today. |
| Suggested-reply / auto-draft copilot for pharmacy↔customer↔driver messaging | 💡 Proposed · AI | Draft only, human sends — same "assistive, not autonomous" pattern as the prescription OCR idea. |
| Customer CRM + append-only account ledger (`apps/customers`) | ✅ Built · deterministic | |
| Purchase-pattern-based reorder reminders / collections prioritization | 💡 Proposed · AI (or rules) | Could start as simple recency/frequency rules before reaching for a model. |
| Subscription plans + per-request service fees (`apps/billing`) | ✅ Built · deterministic | |
| Subscription churn-risk scoring | 💡 Proposed · AI | Early-warning for account managers from usage/fee patterns — a fairly standard churn model, no domain-specific risk. |
| Provider-agnostic payments (cash-on-delivery + mock gateway) (`apps/payments`) | ✅ Built · deterministic | No real gateway wired in yet (`docs/PRD.md`). |
| Online-payment fraud scoring | 💡 Proposed · AI | Only relevant once a real payment gateway replaces the mock adapter — no live money movement to protect yet. |

---

## 10. The boundary case

| Feature | Status | Notes |
|---|---|---|
| Drug interaction / duplicate-therapy flags at basket build time | ⚠️ Boundary · Proposed · AI | Cross-references a shopper's active orders/prescriptions for interaction warnings. Directly adjacent to the "no treatment advice" non-goal from `docs/PRD.md`. If built, it should surface **only to the pharmacist at fulfillment**, framed as a flag for their judgment, never as a consumer-facing recommendation or an automatic block/substitution. Needs a deliberate scoping conversation, including whether it needs a licensed drug-interaction database (not something to freehand with an LLM given the safety stakes) before any implementation work starts. |

---

## Notes on maintaining this doc

- When a 💡 item gets built, move its row's status to ✅ and note which app/service it landed
  in, the same way `docs/ARCHITECTURE.md` only documents what's actually shipped.
- If a proposal turns out to be infeasible or explicitly rejected, keep the row with a status
  of "Rejected" and the reason — same spirit as `docs/PRD.md`'s "Non-goals preserved" section
  — so the same idea doesn't get re-proposed without context next time.
