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
 * All of it comes from `POST /shop/fulfillment-options/`, which plans the same
 * basket against live inventory several ways and returns only the ones that
 * actually exist. Nothing here invents a pharmacy, a price or an arrival time —
 * if the request fails the caller shows an error rather than a plan.
 */

import { apiFetch } from "@/lib/api-client";
import type { BasketItem } from "@/lib/basket";

export type PlanKind = "best" | "fastest" | "cheapest" | "single";

export interface FulfillmentLine {
  medicineId: string;
  name: string;
  generic: string;
  quantity: number;
  unitPrice: number;
  pharmacy: string;
  /**
   * Carried through from the basket rather than inferred from whether a
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

/** Where the basket is being delivered. Sourcing is distance-ranked, so this is required. */
export interface DeliveryPoint {
  latitude: number;
  longitude: number;
}

// --- API payloads ----------------------------------------------------------

interface ApiAllocationLine {
  medicine: string;
  medicine_name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  is_price_regulated: boolean;
}

interface ApiAllocation {
  pharmacy: string;
  pharmacy_name: string;
  pharmacy_area: string;
  distance_km: number;
  preparation_minutes: number;
  subtotal: string;
  lines: ApiAllocationLine[];
}

interface ApiUnfulfilled {
  medicine: string;
  medicine_name: string;
  quantity_short: number;
}

interface ApiOption {
  kind: PlanKind;
  label: string;
  tagline: string;
  allocations: ApiAllocation[];
  unfulfilled: ApiUnfulfilled[];
  items_subtotal: string;
  delivery_fee: string;
  total: string;
  eta_minutes_low: number | null;
  eta_minutes_high: number | null;
  explanation: string[];
}

function money(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * "45 - 60 min", or hours once the range gets long enough that minutes stop
 * being the unit anyone thinks in.
 */
function etaLabel(low: number | null, high: number | null): string {
  if (low === null || high === null) return "Estimated at checkout";
  if (high < 90) return `${low} - ${high} min`;
  const hours = (value: number) => (value / 60).toFixed(value % 60 === 0 ? 0 : 1);
  return `${hours(low)} - ${hours(high)} hours`;
}

function toPlan(option: ApiOption, items: BasketItem[]): FulfillmentPlan {
  const byMedicine = new Map(items.map((item) => [item.medicine, item]));

  const lines: FulfillmentLine[] = option.allocations.flatMap((allocation) =>
    allocation.lines.map((line) => {
      const item = byMedicine.get(line.medicine);
      return {
        medicineId: line.medicine,
        // The basket's own name is what the patient chose it by; the
        // catalogue's is the fallback for a line added elsewhere.
        name: item?.name ?? line.medicine_name,
        generic: item?.generic ?? "",
        quantity: line.quantity,
        unitPrice: money(line.unit_price),
        pharmacy: allocation.pharmacy_name,
        requiresPrescription: Boolean(item?.requires_prescription),
        prescriptionId: item?.prescription_id ?? null
      };
    })
  );

  return {
    kind: option.kind,
    label: option.label,
    tagline: option.tagline,
    etaLabel: etaLabel(option.eta_minutes_low, option.eta_minutes_high),
    lines,
    medicationTotal: money(option.items_subtotal),
    deliveryFee: money(option.delivery_fee),
    total: money(option.total),
    pharmacies: [...new Set(option.allocations.map((allocation) => allocation.pharmacy_name))]
  };
}

/**
 * Ask the platform how this basket could be delivered.
 *
 * Rejects when the request fails. An empty `plans` array is a different and
 * real answer: nothing connected can supply this basket right now.
 */
export async function buildFulfillment(
  items: BasketItem[],
  to: DeliveryPoint,
  signal?: AbortSignal
): Promise<FulfillmentResult> {
  if (items.length === 0) {
    return { plans: [], unavailable: [], availableCount: 0, totalCount: 0 };
  }

  const payload = await apiFetch<{ options: ApiOption[] }>("/shop/fulfillment-options/", {
    method: "POST",
    signal,
    body: JSON.stringify({
      items: items.map((item) => ({ medicine: item.medicine, quantity: item.quantity })),
      latitude: to.latitude,
      longitude: to.longitude
    })
  });

  const options = payload.options ?? [];
  const plans = options.map((option) => toPlan(option, items));

  // What no plan could source. Taken from the first option rather than
  // intersected across them: the options are alternative ways to fill the same
  // basket, and a medicine missing from the best plan is missing from stock.
  const shortfall = options[0]?.unfulfilled ?? [];
  const unavailable: UnavailableItem[] = shortfall.map((entry) => ({
    medicineId: entry.medicine,
    name: items.find((item) => item.medicine === entry.medicine)?.name || entry.medicine_name
  }));

  const sourcedIds = new Set(plans[0]?.lines.map((line) => line.medicineId) ?? []);
  return {
    plans,
    unavailable,
    availableCount: items.filter((item) => sourcedIds.has(item.medicine)).length,
    totalCount: items.length
  };
}

/** Group a plan's lines by the pharmacy supplying them, in reading order. */
export function byPharmacy(plan: FulfillmentPlan): { pharmacy: string; lines: FulfillmentLine[] }[] {
  return plan.pharmacies.map((pharmacy) => ({
    pharmacy,
    lines: plan.lines.filter((line) => line.pharmacy === pharmacy)
  }));
}
