"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import type {
  DeliveryAddress as ApiAddress,
  Order as ApiOrder,
  Prescription as ApiPrescription,
  PrescriptionUpload as ApiPrescriptionUpload,
  RecurringOrder as ApiRecurringOrder,
  User
} from "@/types/api";
import {
  fromAddress,
  fromNotifications,
  fromPaymentMethod,
  fromPreference,
  scheduleId,
  toAddress,
  toNotifications,
  toOrder,
  toPaymentMethod,
  toPrescription,
  toPrescriptionUpload,
  toProfile,
  toRefills,
  type ApiNotificationPreferences,
  type ApiSavedPaymentMethod
} from "./adapters";
import type {
  Address,
  NotificationPreferences,
  Order,
  PatientProfile,
  PaymentMethod,
  Prescription,
  PrescriptionUpload,
  Refill,
  RefillStatus
} from "./types";
import { addDays, todayIso } from "./format";

/**
 * The patient's records, read from the API.
 *
 * These used to live in localStorage, which meant a patient's prescriptions,
 * orders and refills existed only in the browser that created them: invisible
 * on a second device, gone with the cache, and unrelated to what the pharmacy
 * or the platform believed. The database is now the only source of truth, and
 * every hook below is a request against it.
 *
 * Shapes are translated in `adapters.ts` so `types.ts` — and therefore every
 * page — stays a description of what a patient reads rather than of how the
 * platform stores it.
 *
 * Each hook fetches independently and exposes a `refresh`. There is no cache
 * layer and no state library: the patient area is a handful of screens, and a
 * store would be the odd one out in a repo that has none. A mutation refetches
 * the collection it touched rather than reconciling it locally, so what is on
 * screen is always something the server actually said.
 */

const CHANGED_EVENT = "healthconnect:patient-changed";

/** Tell every mounted hook to re-read. Used after a write, and on sign-out. */
function announce() {
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

/**
 * Drop what this device is showing. Used when signing out.
 *
 * There is nothing stored to clear any more — the records live on the server —
 * so this only asks the mounted hooks to re-read, which they will now do
 * without a token and get nothing back.
 */
export function clearPatientState() {
  announce();
}

/**
 * One collection, fetched and kept in step.
 *
 * `ready` is false until the first response, so pages show a skeleton instead
 * of rendering an empty list and correcting it a moment later — the difference
 * between "you have no orders" and "we haven't asked yet".
 */
function useCollection<T>(load: (signal: AbortSignal) => Promise<T>, empty: T) {
  const [data, setData] = useState<T>(empty);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const run = () => {
      load(controller.signal)
        .then((result) => {
          if (cancelled) return;
          setData(result);
          setFailed(false);
        })
        .catch(() => {
          if (cancelled || controller.signal.aborted) return;
          // A signed-out visitor legitimately has no records; the pages read
          // that as an empty account rather than an error.
          setData(empty);
          setFailed(true);
        })
        .finally(() => {
          if (!cancelled) setReady(true);
        });
    };

    run();
    const sync = () => run();
    window.addEventListener(CHANGED_EVENT, sync);
    return () => {
      cancelled = true;
      controller.abort();
      window.removeEventListener(CHANGED_EVENT, sync);
    };
    // `load` is recreated each render by callers; `attempt` is the retry handle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const refresh = useCallback(() => setAttempt((value) => value + 1), []);
  return { data, ready, failed, refresh };
}

function list<T>(payload: T[] | { results: T[] } | null | undefined): T[] {
  if (!payload) return [];
  return Array.isArray(payload) ? payload : payload.results ?? [];
}

// --- prescriptions ---------------------------------------------------------

export function usePrescriptions() {
  const { data, ready, failed, refresh } = useCollection<Prescription[]>(
    async (signal) => list(await apiFetch<ApiPrescription[]>("/shop/prescriptions/mine/", { signal })).map(toPrescription),
    []
  );
  return { prescriptions: data, ready, failed, refresh };
}

/**
 * Paper prescriptions the patient photographed and uploaded, each waiting on a
 * pharmacy to verify it. Distinct from `usePrescriptions`, which is the digital
 * records a doctor issued.
 */
export function usePrescriptionUploads() {
  const { data, ready, failed, refresh } = useCollection<PrescriptionUpload[]>(
    async (signal) =>
      list(await apiFetch<ApiPrescriptionUpload[]>("/shop/prescription-uploads/", { signal })).map(toPrescriptionUpload),
    []
  );

  const remove = useCallback(async (id: string) => {
    await apiFetch(`/shop/prescription-uploads/${id}/`, { method: "DELETE" });
    announce();
  }, []);

  const flag = useCallback(async (id: string, note: string) => {
    await apiFetch(`/shop/prescription-uploads/${id}/flag/`, { method: "POST", body: JSON.stringify({ note }) });
    announce();
  }, []);

  return { uploads: data, ready, failed, refresh, remove, flag };
}

// --- orders ----------------------------------------------------------------

export function useOrders() {
  const { data, ready, failed, refresh } = useCollection<Order[]>(
    async (signal) => list(await apiFetch<ApiOrder[]>("/shop/orders/", { signal })).map(toOrder),
    []
  );

  const reviewOrder = useCallback(
    async (id: string, rating: number, comment: string) => {
      // Routes carry the human-readable reference; the API is keyed on the uuid.
      const record = list(await apiFetch<ApiOrder[]>("/shop/orders/")).find((entry) => entry.reference === id);
      if (!record) return;
      // A review is of a pharmacy, on an order. With a split order the patient
      // rated the delivery as a whole, so it attaches to the pharmacy that
      // supplied most of it.
      const largest = [...record.fulfillments].sort((a, b) => Number(b.subtotal) - Number(a.subtotal))[0];
      if (!largest) return;
      await apiFetch(`/shop/orders/${record.id}/review/`, {
        method: "POST",
        body: JSON.stringify({ pharmacy: largest.pharmacy, rating, comment })
      });
      announce();
    },
    []
  );

  return { orders: data, ready, failed, refresh, reviewOrder };
}

// --- refills ---------------------------------------------------------------

export function useRefills() {
  const { data, ready, failed, refresh } = useCollection<Refill[]>(
    async (signal) => list(await apiFetch<ApiRecurringOrder[]>("/shop/recurring-orders/", { signal })).flatMap(toRefills),
    []
  );

  // Every write addresses the recurring order, not the row: a refill row is one
  // medicine on a schedule, and the schedule is what the API stores.
  const patch = useCallback(async (id: string, body: Record<string, unknown>) => {
    await apiFetch(`/shop/recurring-orders/${scheduleId(id)}/`, { method: "PATCH", body: JSON.stringify(body) });
    announce();
  }, []);

  const setStatus = useCallback(
    async (id: string, status: RefillStatus) => {
      if (status === "cancelled") {
        // Cancelling ends the schedule rather than parking it. Pausing is the
        // reversible option and has its own control.
        await apiFetch(`/shop/recurring-orders/${scheduleId(id)}/`, { method: "DELETE" });
        announce();
        return;
      }
      await patch(id, { is_active: status === "active" });
    },
    [patch]
  );

  const updateRefill = useCallback(
    async (id: string, changes: Partial<Refill>) => {
      const body: Record<string, unknown> = {};
      if (changes.everyDays !== undefined) body.interval_days = changes.everyDays;
      if (changes.preference !== undefined) body.preferred_hour = fromPreference(changes.preference);
      if (changes.addressId !== undefined) body.address = changes.addressId;
      if (changes.nextRefill !== undefined) body.next_run_at = changes.nextRefill;
      if (Object.keys(body).length > 0) await patch(id, body);
    },
    [patch]
  );

  /** Bring the next delivery forward to today plus the usual gap. */
  const refillNow = useCallback(
    async (id: string) => {
      const refill = data.find((entry) => entry.id === id);
      if (!refill) return;
      await patch(id, { next_run_at: addDays(todayIso(), refill.everyDays) });
    },
    [data, patch]
  );

  return { refills: data, ready, failed, refresh, setStatus, updateRefill, refillNow };
}

// --- account ---------------------------------------------------------------

interface AccountData {
  profile: PatientProfile;
  addresses: Address[];
  payments: PaymentMethod[];
  notifications: NotificationPreferences;
}

const EMPTY_ACCOUNT: AccountData = {
  profile: { firstName: "", lastName: "", email: "", phone: "" },
  addresses: [],
  payments: [],
  notifications: {
    orderUpdates: true,
    deliveryUpdates: true,
    prescriptionReminders: true,
    refillReminders: true,
    productNews: false
  }
};

export function useAccount() {
  const { data, ready, failed, refresh } = useCollection<AccountData>(async (signal) => {
    const [user, addresses, payments, notifications] = await Promise.all([
      apiFetch<User>("/auth/me/", { signal }),
      apiFetch<ApiAddress[]>("/shop/addresses/", { signal }),
      apiFetch<ApiSavedPaymentMethod[]>("/shop/saved-payment-methods/", { signal }),
      apiFetch<ApiNotificationPreferences>("/auth/notification-preferences/", { signal })
    ]);
    return {
      profile: toProfile(user),
      addresses: list(addresses).map(toAddress),
      payments: list(payments).map(toPaymentMethod),
      notifications: toNotifications(notifications)
    };
  }, EMPTY_ACCOUNT);

  const saveProfile = useCallback(async (profile: PatientProfile) => {
    // Email is the sign-in identity and is not editable here; see the API's
    // OwnProfileSerializer for the rest of that boundary.
    await apiFetch("/auth/me/", {
      method: "PATCH",
      body: JSON.stringify({ first_name: profile.firstName, last_name: profile.lastName, phone: profile.phone })
    });
    announce();
  }, []);

  const saveAddress = useCallback(
    async (address: Address) => {
      const body = fromAddress(address, data.profile);
      const known = data.addresses.some((entry) => entry.id === address.id);
      await apiFetch(known ? `/shop/addresses/${address.id}/` : "/shop/addresses/", {
        method: known ? "PUT" : "POST",
        body: JSON.stringify(body)
      });
      announce();
    },
    [data.addresses, data.profile]
  );

  const removeAddress = useCallback(async (id: string) => {
    await apiFetch(`/shop/addresses/${id}/`, { method: "DELETE" });
    announce();
  }, []);

  const setDefaultAddress = useCallback(async (id: string) => {
    await apiFetch(`/shop/addresses/${id}/`, { method: "PATCH", body: JSON.stringify({ is_default: true }) });
    announce();
  }, []);

  const addPayment = useCallback(async (payment: Omit<PaymentMethod, "id"> & { id?: string }) => {
    await apiFetch("/shop/saved-payment-methods/", { method: "POST", body: JSON.stringify(fromPaymentMethod(payment)) });
    announce();
  }, []);

  const setDefaultPayment = useCallback(async (id: string) => {
    await apiFetch(`/shop/saved-payment-methods/${id}/`, { method: "PATCH", body: JSON.stringify({ is_default: true }) });
    announce();
  }, []);

  const removePayment = useCallback(async (id: string) => {
    await apiFetch(`/shop/saved-payment-methods/${id}/`, { method: "DELETE" });
    announce();
  }, []);

  const setNotifications = useCallback(async (notifications: NotificationPreferences) => {
    await apiFetch("/auth/notification-preferences/", {
      method: "PATCH",
      body: JSON.stringify(fromNotifications(notifications))
    });
    announce();
  }, []);

  return {
    ready,
    failed,
    refresh,
    profile: data.profile,
    addresses: data.addresses,
    payments: data.payments,
    notifications: data.notifications,
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

// --- combined --------------------------------------------------------------

/**
 * Everything at once, for the home screen.
 *
 * A convenience over the hooks above rather than a store: it is only worth
 * having where one screen genuinely needs all of it, which is the hub and
 * nowhere else.
 */
export function usePatientState() {
  const { prescriptions, ready: prescriptionsReady } = usePrescriptions();
  const { orders, ready: ordersReady } = useOrders();
  const { refills, ready: refillsReady } = useRefills();
  const account = useAccount();

  return {
    state: {
      profile: account.profile,
      addresses: account.addresses,
      payments: account.payments,
      notifications: account.notifications,
      prescriptions,
      orders,
      refills
    },
    ready: prescriptionsReady && ordersReady && refillsReady && account.ready
  };
}

/**
 * The stored profile, with anything the signed-in account knows laid over it.
 *
 * Retained now that the profile itself comes from `/auth/me/`, because the
 * pages call it with the `useUser` record they already hold and it keeps them
 * from having to know which of the two is fresher.
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
