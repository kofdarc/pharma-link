import { apiFetch } from "@/lib/api-client";
import type { Medicine, PublicAvailability } from "@/types/api";
import { MOCK_CATALOG } from "./mock-catalog";
import type { AvailabilityState, MedicineDetail, MedicineSummary, ProductType, SearchFilters, SortMode } from "./types";

/**
 * The catalogue as patients see it.
 *
 * Two things happen here that the API deliberately does not do for us:
 *
 * 1. **Medicine-first shaping.** `/public/search/` answers per (medicine,
 *    pharmacy) pair, because that is what sourcing and delivery need. Patients
 *    are choosing a *medicine*, not a pharmacy, so rows are folded into one
 *    entry per medicine and pharmacies become a count.
 * 2. **A demo fallback.** If the API is unreachable the pages fall back to
 *    `MOCK_CATALOG` rather than dead-ending, so the patient slice can be
 *    demoed, screenshotted and design-reviewed without the backend running.
 *    `usedFallback` is returned so callers can say so honestly if they want to.
 */

export interface MedicineSuggestion {
  id: string;
  brand: string;
  strength: string;
  generic: string;
  form: string;
  requiresPrescription: boolean;
}

export interface SearchOutcome {
  results: MedicineSummary[];
  usedFallback: boolean;
}

export interface MedicineOutcome {
  medicine: MedicineDetail | null;
  usedFallback: boolean;
}

const AVAILABILITY_RANK: Record<AvailabilityState, number> = { available: 0, limited: 1, unavailable: 2 };

function toAvailability(status: PublicAvailability["availability_status"]): AvailabilityState {
  if (status === "Available") return "available";
  if (status === "Low stock") return "limited";
  return "unavailable";
}

/**
 * Brand vs generic is not a field the API carries, so it is inferred: a product
 * whose brand name starts with its own active ingredient is a generic listing
 * ("Atorvastatin Sandoz"), anything else is a brand ("Lipitor").
 */
function inferProductType(brand: string, generic: string): ProductType {
  const firstIngredient = generic.split(/[/,]/)[0].trim().toLowerCase();
  return firstIngredient && brand.toLowerCase().startsWith(firstIngredient) ? "generic" : "brand";
}

function parsePrice(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Fold per-pharmacy availability rows into one entry per medicine. */
function groupByMedicine(rows: PublicAvailability[]): MedicineSummary[] {
  const grouped = new Map<string, MedicineSummary>();

  for (const row of rows) {
    const { medicine } = row;
    const availability = toAvailability(row.availability_status);
    const price = parsePrice(row.unit_price);
    const canFulfil = row.available_up_to > 0 && row.pharmacy.accepts_online_orders;
    const existing = grouped.get(medicine.id);

    if (!existing) {
      grouped.set(medicine.id, {
        id: medicine.id,
        brand: medicine.brand_name,
        strength: medicine.strength || "",
        generic: medicine.generic_name || "",
        form: medicine.form || "",
        image: medicine.image,
        requiresPrescription: Boolean(medicine.requires_prescription),
        productType: inferProductType(medicine.brand_name, medicine.generic_name || ""),
        availability,
        fromPrice: price,
        isPriceRegulated: row.is_price_regulated,
        sourcingCount: canFulfil ? 1 : 0,
        aliases: []
      });
      continue;
    }

    if (AVAILABILITY_RANK[availability] < AVAILABILITY_RANK[existing.availability]) {
      existing.availability = availability;
    }
    if (price !== null && (existing.fromPrice === null || price < existing.fromPrice)) {
      existing.fromPrice = price;
    }
    if (canFulfil) existing.sourcingCount += 1;
  }

  return [...grouped.values()];
}

// --- mock matching ---------------------------------------------------------

function matchScore(medicine: MedicineSummary, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const brand = medicine.brand.toLowerCase();
  const generic = medicine.generic.toLowerCase();

  if (brand.startsWith(q)) return 100;
  if (brand.includes(q)) return 80;
  if (generic.startsWith(q)) return 60;
  if (generic.includes(q)) return 50;
  if (medicine.aliases.some((alias) => alias.toLowerCase().includes(q))) return 40;
  if (medicine.form.toLowerCase().startsWith(q)) return 20;
  return -1;
}

function searchMock(query: string): MedicineSummary[] {
  return MOCK_CATALOG.map((medicine) => ({ medicine, score: matchScore(medicine, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || AVAILABILITY_RANK[a.medicine.availability] - AVAILABILITY_RANK[b.medicine.availability])
    .map((entry) => ({ ...entry.medicine }));
}

// --- public API ------------------------------------------------------------

export async function searchMedicines(query: string, signal?: AbortSignal): Promise<SearchOutcome> {
  const trimmed = query.trim();
  if (!trimmed) return { results: [], usedFallback: false };

  try {
    const rows = await apiFetch<PublicAvailability[]>(`/public/search/?q=${encodeURIComponent(trimmed)}`, { signal });
    return { results: groupByMedicine(rows), usedFallback: false };
  } catch (error) {
    if (signal?.aborted) throw error;
    return { results: searchMock(trimmed), usedFallback: true };
  }
}

export async function suggestMedicines(query: string, signal?: AbortSignal): Promise<MedicineSuggestion[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) return [];

  try {
    const medicines = await apiFetch<Medicine[]>(`/medicines/search/?q=${encodeURIComponent(trimmed)}`, { signal });
    return medicines.slice(0, 6).map((medicine) => ({
      id: medicine.id,
      brand: medicine.brand_name,
      strength: medicine.strength || "",
      generic: medicine.generic_name || "",
      form: medicine.form || "",
      requiresPrescription: Boolean(medicine.requires_prescription)
    }));
  } catch (error) {
    if (signal?.aborted) throw error;
    return searchMock(trimmed)
      .slice(0, 6)
      .map(({ id, brand, strength, generic, form, requiresPrescription }) => ({
        id,
        brand,
        strength,
        generic,
        form,
        requiresPrescription
      }));
  }
}

export async function getMedicine(id: string, signal?: AbortSignal): Promise<MedicineOutcome> {
  const fromMock = (): MedicineOutcome => {
    const medicine = MOCK_CATALOG.find((entry) => entry.id === id);
    return {
      medicine: medicine ? { ...medicine, related: relatedTo(medicine, MOCK_CATALOG) } : null,
      usedFallback: true
    };
  };

  try {
    const rows = await apiFetch<PublicAvailability[]>(`/public/search/?medicine_id=${encodeURIComponent(id)}`, { signal });
    const [medicine] = groupByMedicine(rows);
    if (!medicine) {
      // `/public/search/?medicine_id=` only returns rows backed by real,
      // in-stock inventory. An empty result here doesn't mean the id is
      // bogus — the medicine may still be a real catalogue entry that no
      // connected pharmacy currently stocks. Look it up directly so the page
      // can still show the product, just marked unavailable.
      const catalogueOnly = await fromCatalogueOnly(id, signal);
      return catalogueOnly.medicine ? catalogueOnly : fromMock();
    }

    // Same active ingredient, different product. One extra query, and it is the
    // only way to offer "other listed strengths" without a dedicated endpoint.
    let related: MedicineSummary[] = [];
    try {
      const siblings = await apiFetch<PublicAvailability[]>(`/public/search/?q=${encodeURIComponent(medicine.generic)}`, { signal });
      related = relatedTo(medicine, groupByMedicine(siblings));
    } catch {
      related = [];
    }

    return { medicine: { ...medicine, related }, usedFallback: false };
  } catch (error) {
    if (signal?.aborted) throw error;
    return fromMock();
  }
}

/**
 * The medicine has no live stock anywhere, so `/public/search/` won't return
 * it. Fall back to the catalogue record itself (via `/medicines/search/?id=`,
 * auth-free) so the page can still show what the product is — just marked
 * unavailable — instead of a dead end.
 */
async function fromCatalogueOnly(id: string, signal?: AbortSignal): Promise<MedicineOutcome> {
  try {
    const record = await apiFetch<Medicine>(`/medicines/search/?id=${encodeURIComponent(id)}`, { signal });
    // A MoPH-regulated price is fixed nationwide, not something an individual
    // pharmacy sets - so it's known even when no pharmacy currently stocks the
    // item. Free-priced products have no such fallback: without a stocking
    // pharmacy there's genuinely no price to show.
    const fromPrice = record.is_price_regulated ? parsePrice(record.regulated_price ?? null) : null;
    const medicine: MedicineSummary = {
      id: record.id,
      brand: record.brand_name,
      strength: record.strength || "",
      generic: record.generic_name || "",
      form: record.form || "",
      image: record.image,
      requiresPrescription: Boolean(record.requires_prescription),
      productType: inferProductType(record.brand_name, record.generic_name || ""),
      availability: "unavailable",
      fromPrice,
      isPriceRegulated: Boolean(record.is_price_regulated),
      sourcingCount: 0,
      aliases: (record.aliases ?? []).map((entry) => entry.alias)
    };

    let related: MedicineSummary[] = [];
    try {
      const siblings = await apiFetch<PublicAvailability[]>(`/public/search/?q=${encodeURIComponent(medicine.generic)}`, { signal });
      related = relatedTo(medicine, groupByMedicine(siblings));
    } catch {
      related = [];
    }

    return { medicine: { ...medicine, related }, usedFallback: false };
  } catch (error) {
    if (signal?.aborted) throw error;
    return { medicine: null, usedFallback: false };
  }
}

function relatedTo(medicine: MedicineSummary, pool: MedicineSummary[]): MedicineSummary[] {
  return pool
    .filter((entry) => entry.id !== medicine.id && entry.generic.toLowerCase() === medicine.generic.toLowerCase())
    .sort((a, b) => AVAILABILITY_RANK[a.availability] - AVAILABILITY_RANK[b.availability])
    .slice(0, 4);
}

// --- client-side refinement ------------------------------------------------

export function availableForms(results: MedicineSummary[]): string[] {
  return [...new Set(results.map((entry) => entry.form).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

export function applyFilters(results: MedicineSummary[], filters: SearchFilters): MedicineSummary[] {
  return results.filter((entry) => {
    if (filters.availability === "available" && entry.availability === "unavailable") return false;
    if (filters.prescription === "required" && !entry.requiresPrescription) return false;
    if (filters.prescription === "none" && entry.requiresPrescription) return false;
    if (filters.productType !== "any" && entry.productType !== filters.productType) return false;
    if (filters.form !== "any" && entry.form !== filters.form) return false;
    return true;
  });
}

export function applySort(results: MedicineSummary[], sort: SortMode): MedicineSummary[] {
  const sorted = [...results];
  if (sort === "price") {
    // Unpriced entries sink rather than sorting as free.
    sorted.sort((a, b) => (a.fromPrice ?? Infinity) - (b.fromPrice ?? Infinity));
  } else if (sort === "availability") {
    sorted.sort(
      (a, b) => AVAILABILITY_RANK[a.availability] - AVAILABILITY_RANK[b.availability] || b.sourcingCount - a.sourcingCount
    );
  }
  // "recommended" keeps the order the API ranked, which already accounts for
  // distance, reliability and price.
  return sorted;
}
