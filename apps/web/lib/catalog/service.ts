import { ApiError, apiFetch } from "@/lib/api-client";
import type { Medicine, PublicAvailability } from "@/types/api";
import type { AvailabilityState, MedicineDetail, MedicineSummary, ProductType, SearchFilters, SortMode } from "./types";

/**
 * The catalogue as patients see it.
 *
 * One thing happens here that the API deliberately does not do for us:
 * **medicine-first shaping**. `/public/search/` answers per (medicine, pharmacy)
 * pair, because that is what sourcing and delivery need. Patients are choosing a
 * *medicine*, not a pharmacy, so rows are folded into one entry per medicine and
 * pharmacies become a count.
 *
 * Everything returned here comes from the API. There is no local fallback
 * catalogue: if the request fails the error propagates and the page says so.
 * Showing invented medicines, prices or availability when the platform cannot
 * reach live stock would be worse than showing nothing.
 */

export interface MedicineSuggestion {
  id: string;
  brand: string;
  strength: string;
  generic: string;
  form: string;
  requiresPrescription: boolean;
}

const AVAILABILITY_RANK: Record<AvailabilityState, number> = { available: 0, limited: 1, unavailable: 2 };

function toAvailability(status: PublicAvailability["availability_status"]): AvailabilityState {
  if (status === "Available") return "available";
  if (status === "Low stock") return "limited";
  return "unavailable";
}

/**
 * Fallback brand-vs-generic guess for the rare product missing MoPH's own
 * classification: a brand name that starts with its own active ingredient reads as
 * a generic listing ("Atorvastatin Sandoz"), anything else as a brand ("Lipitor").
 */
function inferProductType(brand: string, generic: string): ProductType {
  const firstIngredient = generic.split(/[/,]/)[0].trim().toLowerCase();
  return firstIngredient && brand.toLowerCase().startsWith(firstIngredient) ? "generic" : "brand";
}

/** The shopper's position, as much of it as any of these calls needs. */
export type Near = { latitude: number; longitude: number };

function nearParams(near?: Near | null): string {
  if (!near) return "";
  return `&lat=${encodeURIComponent(near.latitude)}&lng=${encodeURIComponent(near.longitude)}`;
}

/**
 * Brand vs generic, preferring MoPH's own `brand_generic` classification (G / B /
 * BioTech / BioHuman) over the name-matching heuristic below. This matters in
 * practice: `generic_name` (what the heuristic keys off) is populated on well
 * under 1% of the production catalogue, so `inferProductType` alone silently
 * classifies almost everything as "brand".
 */
function classifyProductType(brand: string, generic: string, brandGeneric?: string): ProductType {
  const code = (brandGeneric || "").trim().toUpperCase();
  if (code === "G" || code === "BIOTECH") return "generic";
  if (code === "B" || code === "BIOHUMAN") return "brand";
  return inferProductType(brand, generic);
}

function parsePrice(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * MoPH's `presentation` field is inconsistent: some rows already carry a unit
 * ("100ml", "5ml"), others are a bare count ("30") that only reads as a pack size
 * once paired with the dosage form. `form` is populated on effectively every
 * product, so it's a reliable unit source for the bare-count case.
 */
function packSizeLabel(presentation: string | undefined, form: string): string | undefined {
  const value = (presentation || "").trim();
  if (!value) return undefined;
  if (/[a-zA-Z]/.test(value) || !form) return value;
  const unit = form.toLowerCase();
  return value === "1" ? `${value} ${unit}` : `${value} ${unit.endsWith("s") ? unit : `${unit}s`}`;
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

    const distance = typeof row.distance_km === "number" ? row.distance_km : null;

    if (!existing) {
      grouped.set(medicine.id, {
        id: medicine.id,
        brand: medicine.brand_name,
        strength: medicine.strength || "",
        generic: medicine.generic_name || "",
        activeIngredient: medicine.ingredients || medicine.generic_name || "",
        form: medicine.form || "",
        route: medicine.route || undefined,
        manufacturer: medicine.manufacturer || undefined,
        country: medicine.country || undefined,
        agent: medicine.agent || undefined,
        registrationNumber: medicine.registration_number || undefined,
        atcCode: medicine.classification || undefined,
        packSize: packSizeLabel(medicine.presentation, medicine.form || ""),
        image: medicine.image,
        requiresPrescription: Boolean(medicine.requires_prescription),
        productType: classifyProductType(medicine.brand_name, medicine.generic_name || "", medicine.brand_generic),
        availability,
        fromPrice: price,
        isPriceRegulated: row.is_price_regulated,
        sourcingCount: canFulfil ? 1 : 0,
        nearestKm: distance,
        nearestPharmacy: distance === null ? "" : row.pharmacy.name,
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
    if (distance !== null && (existing.nearestKm === null || distance < existing.nearestKm)) {
      existing.nearestKm = distance;
      existing.nearestPharmacy = row.pharmacy.name;
    }
  }

  return [...grouped.values()];
}

// --- public API ------------------------------------------------------------

/**
 * `near` is the shopper's position, when they have shared one. Passing it turns on the
 * distance figures the API can only compute if it knows where to measure from - without it
 * every row comes back with `distance_km: null` and the UI says nothing about how far,
 * rather than guessing.
 */
export async function searchMedicines(query: string, signal?: AbortSignal, near?: Near | null): Promise<MedicineSummary[]> {
  const trimmed = query.trim();
  if (!trimmed) return [];
  const rows = await apiFetch<PublicAvailability[]>(`/public/search/?q=${encodeURIComponent(trimmed)}${nearParams(near)}`, { signal });
  return groupByMedicine(rows);
}

/**
 * Type-ahead suggestions.
 *
 * The one place a failed request is swallowed: suggestions are an accelerator
 * over a search box that still works without them, so a dropdown that quietly
 * stays empty is the right failure. Nothing invented is ever shown.
 */
export async function suggestMedicines(query: string, signal?: AbortSignal): Promise<MedicineSuggestion[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) return [];

  try {
    const medicines = await apiFetch<Medicine[]>(`/medicines/search/?q=${encodeURIComponent(trimmed)}`, { signal });
    return medicines.slice(0, 6).map((medicine) => ({
      id: medicine.id,
      brand: medicine.brand_name,
      strength: medicine.strength || "",
      generic: medicine.ingredients || medicine.generic_name || "",
      form: medicine.form || "",
      requiresPrescription: Boolean(medicine.requires_prescription)
    }));
  } catch (error) {
    if (signal?.aborted) throw error;
    return [];
  }
}

/**
 * One medicine, with other products of the same composition (see `relatedTo`).
 *
 * Resolves to `null` only when the id genuinely is not in the catalogue. A
 * failed request rejects, so the page can tell "no such medicine" apart from
 * "we couldn't ask".
 */
export async function getMedicine(id: string, signal?: AbortSignal): Promise<MedicineDetail | null> {
  const rows = await apiFetch<PublicAvailability[]>(`/public/search/?medicine_id=${encodeURIComponent(id)}`, { signal });
  const [medicine] = groupByMedicine(rows);
  if (!medicine) {
    // `/public/search/?medicine_id=` only returns rows backed by real, in-stock
    // inventory. An empty result here doesn't mean the id is bogus — the
    // medicine may still be a real catalogue entry that no connected pharmacy
    // currently stocks. Look it up directly so the page can still show the
    // product, just marked unavailable.
    return fromCatalogueOnly(id, signal);
  }

  return { ...medicine, related: await relatedTo(medicine, signal) };
}

/**
 * The medicine has no live stock anywhere, so `/public/search/` won't return
 * it. Fall back to the catalogue record itself (via `/medicines/search/?id=`,
 * auth-free) so the page can still show what the product is — just marked
 * unavailable — instead of a dead end.
 */
async function fromCatalogueOnly(id: string, signal?: AbortSignal): Promise<MedicineDetail | null> {
  let record: Medicine;
  try {
    record = await apiFetch<Medicine>(`/medicines/search/?id=${encodeURIComponent(id)}`, { signal });
  } catch (error) {
    // A 404 here is the answer — no such medicine. Anything else is the
    // platform failing to answer, which must not be reported as "not found".
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }

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
    activeIngredient: record.ingredients || record.generic_name || "",
    form: record.form || "",
    route: record.route || undefined,
    manufacturer: record.manufacturer || undefined,
    country: record.country || undefined,
    agent: record.agent || undefined,
    registrationNumber: record.registration_number || undefined,
    atcCode: record.classification || undefined,
    packSize: packSizeLabel(record.presentation, record.form || ""),
    image: record.image,
    requiresPrescription: Boolean(record.requires_prescription),
    productType: classifyProductType(record.brand_name, record.generic_name || "", record.brand_generic),
    availability: "unavailable",
    fromPrice,
    isPriceRegulated: Boolean(record.is_price_regulated),
    sourcingCount: 0,
    // No stocking pharmacy means nothing to measure a distance to, which is a
    // different thing from a distance we failed to compute - both read as null here.
    nearestKm: null,
    nearestPharmacy: "",
    aliases: (record.aliases ?? []).map((entry) => entry.alias)
  };

  return { ...medicine, related: await relatedTo(medicine, signal) };
}

/**
 * Other MARKETED products whose full composition text (active ingredient(s) + strength,
 * as one string) matches this one exactly - resolved server-side via
 * `same_composition_as` (see `apps.inventory.services.availability`), which is also
 * where the MARKETED-only filter and the exact-string match live.
 *
 * This is a *candidate list*, built the way WHO/Lebanese-MoPH guidance says candidates
 * should be generated (same complete active-ingredient set + strength), not a claim of
 * equivalence: there is no MoPH substitution-list or bioequivalence data behind it, so
 * the page must present it as "same composition, not verified interchangeable" - see
 * `medicine.related` on `MedicineDetail` and the section that renders it.
 *
 * Matching on the full `ingredients` string (rather than `generic`/`generic_name`, which
 * is populated on well under 1% of the production catalogue) is also what makes this
 * section render at all in production. A combination product's `ingredients` string
 * encodes every active plus its strength, so this can't collapse "amoxicillin" and
 * "amoxicillin + clavulanate" into the same group the way matching on a single "main
 * ingredient" would.
 *
 * A failure here empties the section instead of failing the whole medicine page -
 * supporting information, not the answer to the page.
 */
async function relatedTo(medicine: MedicineSummary, signal?: AbortSignal): Promise<MedicineSummary[]> {
  if (!medicine.activeIngredient) return [];
  let pool: MedicineSummary[];
  try {
    const siblings = await apiFetch<PublicAvailability[]>(
      `/public/search/?same_composition_as=${encodeURIComponent(medicine.id)}`,
      { signal }
    );
    pool = groupByMedicine(siblings);
  } catch (error) {
    if (signal?.aborted) throw error;
    return [];
  }

  return pool
    .filter((entry) => entry.id !== medicine.id)
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
  if (sort === "nearest") {
    // Rows with no distance sink rather than sorting as "here", the same way unpriced rows
    // sink under "price". The shopper picked this sort because distance is what they care
    // about; a row we cannot place is the least useful answer, not the best one.
    sorted.sort((a, b) => (a.nearestKm ?? Infinity) - (b.nearestKm ?? Infinity));
  } else if (sort === "price") {
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
