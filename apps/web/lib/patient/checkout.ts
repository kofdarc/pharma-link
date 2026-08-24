"use client";

import { useCallback, useEffect, useState } from "react";
import type { FulfillmentPlan } from "./fulfillment";
import { isClaimable, remaining, type Prescription } from "./types";

/**
 * The fulfilment option carried from `/cart/fulfillment` into `/checkout`.
 *
 * Session-scoped on purpose. A chosen plan is a quote against supply that moves
 * during the day; it should not survive a closed tab and reappear tomorrow as
 * though the price and the estimate still held.
 */

const DRAFT_KEY = "healthconnect_checkout_plan";
const CHANGED_EVENT = "healthconnect:checkout-changed";

function read(): FulfillmentPlan | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as FulfillmentPlan) : null;
  } catch {
    return null;
  }
}

export function useCheckoutPlan() {
  const [plan, setPlan] = useState<FulfillmentPlan | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPlan(read());
    setReady(true);
    const sync = () => setPlan(read());
    window.addEventListener(CHANGED_EVENT, sync);
    return () => window.removeEventListener(CHANGED_EVENT, sync);
  }, []);

  const choose = useCallback((next: FulfillmentPlan) => {
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event(CHANGED_EVENT));
  }, []);

  const clearPlan = useCallback(() => {
    window.sessionStorage.removeItem(DRAFT_KEY);
    window.dispatchEvent(new Event(CHANGED_EVENT));
  }, []);

  return { plan, ready, choose, clearPlan };
}

// --- prescription matching -------------------------------------------------

/**
 * Attach the obvious prescription to any basket line that needs one.
 *
 * Runs on every screen that reads the basket, not only on the cart page: a
 * patient can arrive at fulfilment or checkout by a link or a reload, and a
 * line whose cover was never resolved would be presented as though it needed
 * none. Lines with more than one candidate are left alone, because choosing
 * between two valid prescriptions is a real decision and belongs to the patient.
 */
export function useAutoPrescriptionMatch(
  items: { medicine: string; requires_prescription?: boolean; prescription_id?: string | null }[],
  prescriptions: Prescription[],
  ready: boolean,
  setPrescription: (medicine: string, prescriptionId: string | null) => void
) {
  useEffect(() => {
    if (!ready) return;
    for (const item of items) {
      if (!item.requires_prescription || item.prescription_id) continue;
      const matches = prescriptionsCovering(prescriptions, item.medicine);
      if (matches.length === 1) setPrescription(item.medicine, matches[0].id);
    }
    // `items` only changes when the stored basket does, so this settles after
    // one write rather than re-running itself.
  }, [items, prescriptions, ready, setPrescription]);
}

/**
 * Prescriptions the patient already holds that still cover this medicine.
 *
 * The patient should never have to copy a prescription number across screens:
 * if they have one, the account finds it. Expired, fully dispensed and unrelated
 * prescriptions are excluded rather than shown greyed out, because offering a
 * prescription that cannot be used is worse than offering none.
 */
export function prescriptionsCovering(prescriptions: Prescription[], medicineId: string): Prescription[] {
  return prescriptions.filter(
    (prescription) =>
      isClaimable(prescription) &&
      prescription.items.some((item) => item.medicineId === medicineId && remaining(item) > 0)
  );
}

/** How much of `medicineId` is still claimable on this prescription. */
export function remainingFor(prescription: Prescription, medicineId: string): number {
  const item = prescription.items.find((entry) => entry.medicineId === medicineId);
  return item ? remaining(item) : 0;
}
