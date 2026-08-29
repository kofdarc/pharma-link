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
  /** Listed active ingredient(s), e.g. "Amoxicillin / Clavulanic Acid". */
  generic: string;
  /** Dosage form, e.g. "Tablet", "Inhaler". */
  form: string;
  packSize?: string;
  manufacturer?: string;
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
  /** Other products listing the same active ingredient. */
  related: MedicineSummary[];
}

export type SortMode = "recommended" | "nearest" | "price" | "availability";

export interface SearchFilters {
  availability: "any" | "available";
  prescription: "any" | "required" | "none";
  productType: "any" | ProductType;
  form: string;
}

export const DEFAULT_FILTERS: SearchFilters = {
  availability: "any",
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
