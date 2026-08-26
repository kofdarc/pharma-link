"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  Address,
  NotificationPreferences,
  Order,
  PatientProfile,
  PaymentMethod,
  Prescription,
  Refill,
  RefillStatus
} from "./types";
import { addDays, todayIso } from "./format";

/**
 * The patient's records for the demo build.
 *
 * Same shape and same reasoning as `lib/basket.ts`: one localStorage key, a
 * custom event so components in the same tab stay in sync, and no provider to
 * thread through the tree. There is no patient-facing API for prescriptions,
 * orders, refills or account settings yet, so this is the seam. When those
 * endpoints land, each `use*` hook below becomes a fetch; nothing outside this
 * file has to change.
 *
 * A new patient starts empty. This used to seed itself from
 * `mock-patient.ts` so the demo had something to show, but that meant every
 * visitor - signed in or not - was shown one fictional patient's records as if
 * they were their own. The fixtures are still there for tests and design work;
 * nothing in the running app reads them.
 *
 * Kept deliberately small. A demo does not need a state library, and adding one
 * would make this slice the odd one out in a repo that has none.
 */

// Bumped from _v1 when the seed data was removed: browsers that visited the
// demo build hold a blob full of the old fictional patient's records, and a
// signed-in user must not inherit them.
export const PATIENT_STORAGE_KEY = "healthconnect_patient_v2";
const CHANGED_EVENT = "healthconnect:patient-changed";

export interface PatientState {
  profile: PatientProfile;
  addresses: Address[];
  payments: PaymentMethod[];
  notifications: NotificationPreferences;
  prescriptions: Prescription[];
  orders: Order[];
  refills: Refill[];
}

/** What a patient with no records yet has. Preferences still need a default. */
const DEFAULT_NOTIFICATIONS: NotificationPreferences = {
  orderUpdates: true,
  deliveryUpdates: true,
  prescriptionReminders: true,
  refillReminders: true,
  productNews: false
};

function seed(): PatientState {
  return {
    profile: { firstName: "", lastName: "", email: "", phone: "" },
    addresses: [],
    payments: [],
    notifications: { ...DEFAULT_NOTIFICATIONS },
    prescriptions: [],
    orders: [],
    refills: []
  };
}

/** Drop everything this device holds for the patient. Used when signing out. */
export function clearPatientState() {
  window.localStorage.removeItem(PATIENT_STORAGE_KEY);
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

function read(): PatientState {
  if (typeof window === "undefined") return seed();
  try {
    const raw = window.localStorage.getItem(PATIENT_STORAGE_KEY);
    if (!raw) return seed();
    // Shallow-merged over the seed so a stored blob written by an older build
    // still renders: missing collections fall back rather than crashing a page.
    return { ...seed(), ...(JSON.parse(raw) as Partial<PatientState>) };
  } catch {
    return seed();
  }
}

function write(state: PatientState) {
  window.localStorage.setItem(PATIENT_STORAGE_KEY, JSON.stringify(state));
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

function mutate(change: (state: PatientState) => PatientState) {
  write(change(read()));
}

/**
 * Subscribe to the stored records.
 *
 * `ready` is false until the first client read, because the server renders the
 * seed and the browser may hold something newer. Pages use it to show their
 * skeleton rather than flashing seed data and then replacing it.
 */
export function usePatientState() {
  const [state, setState] = useState<PatientState>(seed);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setState(read());
    sync();
    setReady(true);
    window.addEventListener(CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return { state, ready };
}

// --- prescriptions ---------------------------------------------------------

export function usePrescriptions() {
  const { state, ready } = usePatientState();
  return { prescriptions: state.prescriptions, ready };
}

// --- orders ----------------------------------------------------------------

export function useOrders() {
  const { state, ready } = usePatientState();

  const placeOrder = useCallback((order: Order) => {
    mutate((current) => ({ ...current, orders: [order, ...current.orders] }));
  }, []);

  const reviewOrder = useCallback((id: string, rating: number, comment: string) => {
    mutate((current) => ({
      ...current,
      orders: current.orders.map((order) => (order.id === id ? { ...order, rating, reviewComment: comment } : order))
    }));
  }, []);

  return { orders: state.orders, ready, placeOrder, reviewOrder };
}

/**
 * Draw down the prescribed quantities an order consumed, and move a
 * prescription to `partial` or `completed` accordingly.
 *
 * The real ledger lives server-side; this keeps the demo self-consistent, so a
 * prescription ordered on one screen reads as partly dispensed on the next.
 */
export function applyDispensing(lines: { medicineId: string; quantity: number; prescriptionId?: string | null }[]) {
  mutate((current) => ({
    ...current,
    prescriptions: current.prescriptions.map((prescription) => {
      const relevant = lines.filter((line) => line.prescriptionId === prescription.id);
      if (relevant.length === 0) return prescription;

      const items = prescription.items.map((item) => {
        const line = relevant.find((entry) => entry.medicineId === item.medicineId);
        if (!line) return item;
        return { ...item, dispensed: Math.min(item.prescribed, item.dispensed + line.quantity) };
      });

      const anyRemaining = items.some((item) => item.dispensed < item.prescribed);
      const anyDispensed = items.some((item) => item.dispensed > 0);
      const status = !anyRemaining ? "completed" : anyDispensed ? "partial" : prescription.status;
      return { ...prescription, items, status };
    })
  }));
}

// --- refills ---------------------------------------------------------------

export function useRefills() {
  const { state, ready } = usePatientState();

  const setStatus = useCallback((id: string, status: RefillStatus) => {
    mutate((current) => ({
      ...current,
      refills:
        status === "cancelled"
          ? current.refills.filter((refill) => refill.id !== id)
          : current.refills.map((refill) => (refill.id === id ? { ...refill, status } : refill))
    }));
  }, []);

  const updateRefill = useCallback((id: string, patch: Partial<Refill>) => {
    mutate((current) => ({
      ...current,
      refills: current.refills.map((refill) => (refill.id === id ? { ...refill, ...patch } : refill))
    }));
  }, []);

  /** Bring the next delivery forward to today plus the usual gap. */
  const refillNow = useCallback((id: string) => {
    mutate((current) => ({
      ...current,
      refills: current.refills.map((refill) =>
        refill.id === id ? { ...refill, nextRefill: addDays(todayIso(), refill.everyDays) } : refill
      )
    }));
  }, []);

  return { refills: state.refills, ready, setStatus, updateRefill, refillNow };
}

// --- account ---------------------------------------------------------------

export function useAccount() {
  const { state, ready } = usePatientState();

  const saveProfile = useCallback((profile: PatientProfile) => {
    mutate((current) => ({ ...current, profile }));
  }, []);

  const saveAddress = useCallback((address: Address) => {
    mutate((current) => {
      const exists = current.addresses.some((entry) => entry.id === address.id);
      const addresses = exists
        ? current.addresses.map((entry) => (entry.id === address.id ? address : entry))
        : [...current.addresses, address];
      // One default at a time, whichever way the edit came in.
      return {
        ...current,
        addresses: address.isDefault
          ? addresses.map((entry) => ({ ...entry, isDefault: entry.id === address.id }))
          : addresses
      };
    });
  }, []);

  const removeAddress = useCallback((id: string) => {
    mutate((current) => {
      const addresses = current.addresses.filter((entry) => entry.id !== id);
      // Never leave the account without a default to deliver to.
      if (addresses.length > 0 && !addresses.some((entry) => entry.isDefault)) addresses[0].isDefault = true;
      return { ...current, addresses };
    });
  }, []);

  const setDefaultAddress = useCallback((id: string) => {
    mutate((current) => ({
      ...current,
      addresses: current.addresses.map((entry) => ({ ...entry, isDefault: entry.id === id }))
    }));
  }, []);

  const setDefaultPayment = useCallback((id: string) => {
    mutate((current) => ({
      ...current,
      payments: current.payments.map((entry) => ({ ...entry, isDefault: entry.id === id }))
    }));
  }, []);

  const removePayment = useCallback((id: string) => {
    mutate((current) => {
      const payments = current.payments.filter((entry) => entry.id !== id);
      if (payments.length > 0 && !payments.some((entry) => entry.isDefault)) payments[0].isDefault = true;
      return { ...current, payments };
    });
  }, []);

  const addPayment = useCallback((payment: PaymentMethod) => {
    mutate((current) => ({ ...current, payments: [...current.payments, payment] }));
  }, []);

  const setNotifications = useCallback((notifications: NotificationPreferences) => {
    mutate((current) => ({ ...current, notifications }));
  }, []);

  return {
    ready,
    profile: state.profile,
    addresses: state.addresses,
    payments: state.payments,
    notifications: state.notifications,
    saveProfile,
    saveAddress,
    removeAddress,
    setDefaultAddress,
    setDefaultPayment,
    removePayment,
    addPayment,
    setNotifications
  };
}

/**
 * The stored profile, with anything the signed-in account actually knows laid
 * over it.
 *
 * Name and email are real: they come from `/auth/me/`. Phone has no field on
 * the account yet, so it stays local. Without this merge the account hub would
 * greet the signed-in user by name while the profile screen underneath it
 * showed the seed data, which is the kind of split a demo gets away with and a
 * real build does not.
 */
export function profileFor(
  profile: PatientProfile,
  user?: { first_name?: string | null; last_name?: string | null; email?: string | null } | null
): PatientProfile {
  if (!user) return profile;
  return {
    firstName: user.first_name || profile.firstName,
    lastName: user.last_name || profile.lastName,
    email: user.email || profile.email,
    phone: profile.phone
  };
}

/** Which refills would be disrupted if this address went away. */
export function refillsUsingAddress(refills: Refill[], addressId: string): Refill[] {
  return refills.filter((refill) => refill.addressId === addressId && refill.status !== "cancelled");
}
