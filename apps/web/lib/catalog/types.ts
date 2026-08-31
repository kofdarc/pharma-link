/** Patient-facing view of the catalogue. */

/**
 * What a patient is allowed to know about supply.
 *
 * Deliberately coarse: pharmacies never expose stock depth through the public
 * surface, so the UI has three words and no numbers. See `docs/ARCHITECTURE.md`
 * on the orderable ceiling.
 */
export type AvailabilityState = "available" | "limited" | "unavailable";

export type ProductType = "brand" | "generic";

export interface MedicineSummary {
  id: string;
  /** Brand or product name, e.g. "Augmentin". */
  brand: string;
  /** e.g. "1g". May be empty for products sold at a single strength. */
  strength: string;
  /** Listed active ingredient(s), e.g. "Amoxicillin / Clavulanic Acid". Sourced from
   *  `Medicine.generic_name` when present, otherwise derived from `activeIngredient`
   *  (rarely both are set - `generic_name` is populated on a small fraction of the
   *  MoPH-synced catalogue). */
  generic: string;
  /** Full composition string from the MoPH source, e.g. "Atorvastatin (calcium) - 10mg"
   *  or, for a combination product, each active and its strength. This is the reliable
   *  active-ingredient field - prefer it over `generic` for display and for any
   *  same-composition comparison. */
  activeIngredient: string;
  /** Dosage form, e.g. "Tablet", "Inhaler". */
  form: string;
  /** Route of administration, e.g. "Oral", "Intravenous". Distinct products sharing a
   *  route can still differ in release profile (immediate vs. modified-release, etc.),
   *  which isn't separately tracked - route is the closest available proxy. */
  route?: string;
  packSize?: string;
  manufacturer?: string;
  /** Country of origin/manufacture. */
  country?: string;
  /** Lebanese importer/distributor - distinct from `manufacturer`. */
  agent?: string;
  /** MoPH product registration number, when known. */
  registrationNumber?: string;
  /** ATC classification code (e.g. "C10AA05"). Discovery/validation metadata only -
   *  never treat two products as the same medicine, or as substitutable, merely because
   *  they share an ATC code: ATC can vary by route/strength/therapeutic use, and a
   *  shared code groups a pharmacological class, not a single interchangeable product. */
  atcCode?: string;
  image?: string | null;
  requiresPrescription: boolean;
  productType: ProductType;
  availability: AvailabilityState;
  /** Lowest price seen across connected pharmacies, or null when unpriced. */
  fromPrice: number | null;
  /**
   * MoPH-regulated medicines are sold at one fixed nationwide price - every
   * pharmacy charges the same, so `fromPrice` isn't a range and shouldn't be
   * labelled "from". Unset is treated as unregulated.
   */
  isPriceRegulated?: boolean;
  /**
   * NSSF (National Social Security Fund) reimbursement. `nssfCovered` is whether the
   * medicine is on an NSSF reimbursable list; the reference price and rate come from
   * that same list and are null when covered but not yet detailed, or when not covered.
   * Unrelated to MoPH import subsidy.
   */
  nssfCovered?: boolean;
  nssfReferencePrice?: number | null;
  nssfReimbursementRate?: number | null;
  /** How many connected pharmacies may be able to fulfil it. Never stock depth. */
  sourcingCount: number;
  /**
   * Road distance to the closest pharmacy listing it, in km, or null when the
   * shopper has shared no location. Null is meaningful and must stay
   * distinguishable from zero: "we don't know how far" is not "it's right here".
   */
  nearestKm: number | null;
  /** Which pharmacy that closest listing is at. Empty when distance is unknown. */
  nearestPharmacy: string;
  /** Extra terms search should match: brand aliases, common misspellings. */
  aliases: string[];
}

export interface MedicineDetail extends MedicineSummary {
  /**
   * Other MARKETED products whose full active-ingredient-and-strength composition text
   * matches this one exactly. This is a *candidate list*, not a clinical equivalence
   * claim: nothing here has been checked against the MoPH substitution list or any
   * bioequivalence evidence, so the UI must present it as "same composition, not
   * verified interchangeable" rather than "alternative" or "substitute". See the
   * disclaimer copy next to where this is rendered.
   */
  related: MedicineSummary[];
}

export type SortMode = "recommended" | "nearest" | "price" | "availability";

export interface SearchFilters {
  availability: "any" | "available";
  nssfCoverage: "any" | "covered";
  prescription: "any" | "required" | "none";
  productType: "any" | ProductType;
  form: string;
}

export const DEFAULT_FILTERS: SearchFilters = {
  availability: "any",
  nssfCoverage: "any",
  prescription: "any",
  productType: "any",
  form: "any"
};

export function countActiveFilters(filters: SearchFilters): number {
  return Object.entries(filters).filter(([, value]) => value !== "any").length;
}

export function medicineLabel(medicine: Pick<MedicineSummary, "brand" | "strength">): string {
  return [medicine.brand, medicine.strength].filter(Boolean).join(" ");
}
