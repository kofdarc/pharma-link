/**
 * Working out how a basket can actually be filled.
 *
 * The real thing is a sourcing problem: live stock per pharmacy, expiry
 * ordering, reservation windows, distance and driver routing. None of that is
 * the patient's concern, and none of it is exposed here. What this module
 * produces is the only part that belongs on screen: a short list of whole
 * baskets the platform believes it can deliver, each with a price, an estimate
 * and which pharmacy supplies what.
 *
 * Until the sourcing endpoint exists, the options are derived from the
 * catalogue the patient already saw, so the numbers on this screen and the
 * numbers on the medication page agree.
 */

import { MOCK_CATALOG } from "@/lib/catalog/mock-catalog";
import type { MedicineSummary } from "@/lib/catalog/types";
import type { BasketItem } from "@/lib/basket";

/** The connected pharmacies used across the demo. Fictional. */
const PHARMACIES = ["Cedar Care Pharmacy", "Verdun Health Pharmacy", "Achrafieh Pharmacy", "Mar Elias Pharmacy"];

export type PlanKind = "best" | "fastest" | "cheapest" | "single";

export interface FulfillmentLine {
  medicineId: string;
  name: string;
  generic: string;
  quantity: number;
  unitPrice: number;
  pharmacy: string;
  /**
   * Carried through from the catalogue rather than inferred from whether a
   * prescription happens to be attached. Checkout has to be able to say "this
   * needs a prescription and does not have one yet", which is not the same
   * statement as "this needs no prescription".
   */
  requiresPrescription: boolean;
  prescriptionId?: string | null;
}

export interface FulfillmentPlan {
  kind: PlanKind;
  label: string;
  /** One short line explaining what this option optimises for. */
  tagline: string;
  etaLabel: string;
  lines: FulfillmentLine[];
  medicationTotal: number;
  deliveryFee: number;
  total: number;
  pharmacies: string[];
}

export interface UnavailableItem {
  medicineId: string;
  name: string;
}

export interface FulfillmentResult {
  plans: FulfillmentPlan[];
  unavailable: UnavailableItem[];
  /** How many basket lines the platform believes it can supply. */
  availableCount: number;
  totalCount: number;
}

/** Stable per-medicine number, so the same basket always splits the same way. */
function hash(value: string): number {
  let total = 0;
  for (let index = 0; index < value.length; index += 1) total = (total * 31 + value.charCodeAt(index)) >>> 0;
  return total;
}

function catalogEntry(id: string): MedicineSummary | undefined {
  return MOCK_CATALOG.find((entry) => entry.id === id);
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

interface PlanShape {
  kind: PlanKind;
  label: string;
  tagline: string;
  etaLabel: string;
  priceFactor: number;
  deliveryFee: number;
  pharmacyCount: number;
}

const SHAPES: PlanShape[] = [
  {
    kind: "best",
    label: "Best overall",
    tagline: "The quickest way to get everything, at close to the lowest price.",
    etaLabel: "45 - 60 min",
    priceFactor: 1,
    deliveryFee: 3,
    pharmacyCount: 2
  },
  {
    kind: "fastest",
    label: "Fastest",
    tagline: "Pharmacies that can start preparing straight away.",
    etaLabel: "35 - 45 min",
    priceFactor: 1.08,
    deliveryFee: 4.5,
    pharmacyCount: 2
  },
  {
    kind: "cheapest",
    label: "Lowest cost",
    tagline: "The lowest listed prices, with a longer wait.",
    etaLabel: "60 - 75 min",
    priceFactor: 0.96,
    deliveryFee: 2.5,
    pharmacyCount: 2
  },
  {
    kind: "single",
    label: "One pharmacy",
    tagline: "Everything from a single pharmacy, if you would rather keep it together.",
    etaLabel: "70 - 90 min",
    priceFactor: 1.05,
    deliveryFee: 3.5,
    pharmacyCount: 1
  }
];

/**
 * Spread the basket over `count` pharmacies.
 *
 * Contiguous rather than round-robin: a patient reading the breakdown should
 * see a couple of short lists, not every item at a different counter.
 */
function allocate(items: BasketItem[], count: number, offset: number): string[] {
  const pool = PHARMACIES.slice(offset, offset + count);
  const perPharmacy = Math.ceil(items.length / pool.length);
  return items.map((_, index) => pool[Math.min(pool.length - 1, Math.floor(index / perPharmacy))]);
}

export function buildFulfillment(items: BasketItem[]): FulfillmentResult {
  const entries = items.map((item) => ({ item, medicine: catalogEntry(item.medicine) }));

  const unavailable = entries
    .filter(({ medicine }) => medicine?.availability === "unavailable")
    .map(({ item }) => ({ medicineId: item.medicine, name: item.name }));

  const fulfillable = entries.filter(({ medicine }) => medicine?.availability !== "unavailable");

  if (fulfillable.length === 0) {
    return { plans: [], unavailable, availableCount: 0, totalCount: items.length };
  }

  // A single pharmacy can only be offered when nothing in the basket is in
  // short supply. Promising it otherwise would be inventing a capability.
  const everythingWidelyStocked = fulfillable.every(({ medicine }) => medicine?.availability === "available");

  const basketItems = fulfillable.map(({ item }) => item);
  const seedOffset = hash(basketItems.map((item) => item.medicine).join("|")) % 2;

  const plans = SHAPES.filter((shape) => {
    if (shape.kind === "single") return everythingWidelyStocked && basketItems.length > 1;
    // With one line there is nothing to split, so the multi-pharmacy variants
    // would be four identical cards with different prices.
    if (basketItems.length === 1) return shape.kind === "best" || shape.kind === "cheapest";
    return true;
  }).map((shape) => {
    const pharmacyCount = Math.min(shape.pharmacyCount, basketItems.length);
    const assigned = allocate(basketItems, pharmacyCount, shape.kind === "cheapest" ? seedOffset + 1 : seedOffset);

    const lines: FulfillmentLine[] = fulfillable.map(({ item, medicine }, index) => ({
      medicineId: item.medicine,
      name: item.name,
      generic: item.generic ?? medicine?.generic ?? "",
      quantity: item.quantity,
      unitPrice: round((item.unit_price ?? medicine?.fromPrice ?? 0) * shape.priceFactor),
      pharmacy: assigned[index],
      requiresPrescription: Boolean(item.requires_prescription ?? medicine?.requiresPrescription),
      prescriptionId: item.prescription_id ?? null
    }));

    const medicationTotal = round(lines.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0));
    return {
      kind: shape.kind,
      label: shape.label,
      tagline: shape.tagline,
      etaLabel: shape.etaLabel,
      lines,
      medicationTotal,
      deliveryFee: shape.deliveryFee,
      total: round(medicationTotal + shape.deliveryFee),
      pharmacies: [...new Set(lines.map((line) => line.pharmacy))]
    };
  });

  return { plans, unavailable, availableCount: fulfillable.length, totalCount: items.length };
}

/** Group a plan's lines by the pharmacy supplying them, in reading order. */
export function byPharmacy(plan: FulfillmentPlan): { pharmacy: string; lines: FulfillmentLine[] }[] {
  return plan.pharmacies.map((pharmacy) => ({
    pharmacy,
    lines: plan.lines.filter((line) => line.pharmacy === pharmacy)
  }));
}
