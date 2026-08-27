/**
 * Turning the platform's records into the patient's.
 *
 * The API models the operation: orders split into per-pharmacy fulfillments,
 * prescriptions with a dispensing ledger, refills as recurring order schedules.
 * `lib/patient/types.ts` models what a person needs to read. This file is the
 * seam between them, and it is the only place that knows both shapes.
 *
 * Everything here is a projection of data the server sent. Nothing is invented:
 * where the platform has no answer yet (an arrival window before dispatch has
 * assigned a driver, say) the patient-facing field says so rather than guessing.
 */

import type {
  DeliveryAddress as ApiAddress,
  Order as ApiOrder,
  OrderFulfillment as ApiFulfillment,
  OrderStatus,
  Payment,
  Prescription as ApiPrescription,
  RecurringOrder as ApiRecurringOrder,
  User
} from "@/types/api";
import type {
  Address,
  DeliveryPreference,
  NotificationPreferences,
  Order,
  OrderLine,
  OrderStage,
  PatientProfile,
  PaymentMethod,
  Prescription,
  PrescriptionItem,
  PrescriptionStatus,
  Refill
} from "./types";

// --- addresses -------------------------------------------------------------

export function toAddress(record: ApiAddress): Address {
  return {
    id: record.id,
    label: record.label,
    line1: record.address,
    building: record.building_notes ?? "",
    area: record.area,
    city: record.city,
    notes: "",
    isDefault: record.is_default,
    latitude: Number(record.latitude),
    longitude: Number(record.longitude)
  };
}

/**
 * The API requires a contact name and phone on every address; the patient form
 * asks for neither, because the account already knows who this is. They are
 * filled from the signed-in profile at write time rather than asked for twice.
 */
export function fromAddress(address: Address, profile: PatientProfile): Partial<ApiAddress> {
  return {
    label: address.label,
    contact_name: [profile.firstName, profile.lastName].filter(Boolean).join(" ") || address.label,
    phone: profile.phone,
    address: address.line1,
    area: address.area,
    city: address.city,
    building_notes: address.building ?? "",
    is_default: address.isDefault
  };
}

// --- profile & preferences -------------------------------------------------

export function toProfile(user: User): PatientProfile {
  return {
    firstName: user.first_name ?? "",
    lastName: user.last_name ?? "",
    email: user.email ?? "",
    phone: user.phone ?? ""
  };
}

export interface ApiNotificationPreferences {
  order_updates: boolean;
  delivery_updates: boolean;
  prescription_reminders: boolean;
  refill_reminders: boolean;
  product_news: boolean;
}

export function toNotifications(record: ApiNotificationPreferences): NotificationPreferences {
  return {
    orderUpdates: record.order_updates,
    deliveryUpdates: record.delivery_updates,
    prescriptionReminders: record.prescription_reminders,
    refillReminders: record.refill_reminders,
    productNews: record.product_news
  };
}

export function fromNotifications(preferences: NotificationPreferences): ApiNotificationPreferences {
  return {
    order_updates: preferences.orderUpdates,
    delivery_updates: preferences.deliveryUpdates,
    prescription_reminders: preferences.prescriptionReminders,
    refill_reminders: preferences.refillReminders,
    product_news: preferences.productNews
  };
}

// --- payment methods -------------------------------------------------------

export interface ApiSavedPaymentMethod {
  id: string;
  kind: "CARD" | "CASH";
  brand: string;
  last4: string;
  expiry: string;
  is_default: boolean;
  label: string;
}

export function toPaymentMethod(record: ApiSavedPaymentMethod): PaymentMethod {
  return {
    id: record.id,
    kind: record.kind === "CARD" ? "card" : "cash",
    brand: record.brand || undefined,
    last4: record.last4 || undefined,
    expiry: record.expiry || undefined,
    isDefault: record.is_default
  };
}

export function fromPaymentMethod(method: Omit<PaymentMethod, "id">): Partial<ApiSavedPaymentMethod> {
  return {
    kind: method.kind === "card" ? "CARD" : "CASH",
    brand: method.brand ?? "",
    last4: method.last4 ?? "",
    expiry: method.expiry ?? "",
    is_default: method.isDefault
  };
}

// --- prescriptions ---------------------------------------------------------

/**
 * The platform tracks five prescription states; the patient screens read four.
 *
 * CANCELLED collapses into `expired` because both mean the same thing to the
 * person holding it: nothing more can be claimed against this. The distinction
 * matters to the doctor who withdrew it, and is shown on their side.
 */
function toPrescriptionStatus(prescription: ApiPrescription): PrescriptionStatus {
  switch (prescription.status) {
    case "PARTIALLY_DISPENSED":
      return "partial";
    case "FULLY_DISPENSED":
      return "completed";
    case "EXPIRED":
    case "CANCELLED":
      return "expired";
    default:
      return prescription.is_expired ? "expired" : "active";
  }
}

export function toPrescription(record: ApiPrescription): Prescription {
  const items: PrescriptionItem[] = record.items.map((item) => ({
    // A doctor may prescribe by name without picking a catalogue entry, and
    // such a line cannot be added to a basket. The empty id is what the UI
    // checks to know that.
    medicineId: item.medicine ?? "",
    name: item.medicine_detail?.display_name || item.medicine_text,
    generic: item.medicine_detail?.generic_name ?? "",
    prescribed: item.quantity_prescribed,
    dispensed: item.quantity_dispensed,
    unit: item.unit,
    dosage: item.dosage_instructions
  }));

  return {
    // The human-readable code, not the uuid: it is what the patient reads out
    // at a counter and what the routes are keyed on.
    id: record.code,
    status: toPrescriptionStatus(record),
    prescriber: { name: record.doctor_name, specialty: "" },
    issuedOn: isoDate(record.issued_at),
    validUntil: isoDate(record.valid_until),
    items,
    // Issued once, to the doctor, at creation time. It is never re-served, so
    // the patient sees it only if they saved it.
    accessPin: record.one_time_secrets?.pin ?? ""
  };
}

// --- orders ----------------------------------------------------------------

/**
 * Where the order has reached, as one line on a five-step track.
 *
 * The order is split across pharmacies that move at their own pace, so the
 * stage shown is the SLOWEST slice: an order is not "out for delivery" while
 * one pharmacy is still packing. Order status wins once dispatch owns the
 * order, because at that point the pharmacies are done.
 */
export function toStage(order: ApiOrder): OrderStage {
  const byOrderStatus: Partial<Record<OrderStatus, OrderStage>> = {
    IN_TRANSIT: "transit",
    DELIVERED: "delivered",
    COLLECTED: "delivered",
    ASSIGNED: "collecting"
  };
  const fromStatus = byOrderStatus[order.status];
  if (fromStatus) return fromStatus;

  const active = order.fulfillments.filter((entry) => entry.status !== "REJECTED" && entry.status !== "CANCELLED");
  if (active.length === 0) return "confirmed";
  if (active.every((entry) => entry.completed_at)) return "delivered";
  if (active.every((entry) => entry.picked_up_at)) return "transit";
  if (active.every((entry) => entry.ready_at)) return "collecting";
  if (active.some((entry) => entry.accepted_at)) return "preparing";
  return "confirmed";
}

function reachedAt(order: ApiOrder): Partial<Record<OrderStage, string>> {
  const active = order.fulfillments.filter((entry) => entry.status !== "REJECTED" && entry.status !== "CANCELLED");
  const latest = (pick: (entry: ApiFulfillment) => string | null | undefined) => {
    const stamps = active.map(pick).filter((value): value is string => Boolean(value));
    // The whole order reached a step when its LAST pharmacy did.
    return stamps.length === active.length && stamps.length > 0 ? stamps.sort().at(-1) : undefined;
  };

  const reached: Partial<Record<OrderStage, string>> = { confirmed: timeLabel(order.created_at) };
  const preparing = latest((entry) => entry.accepted_at);
  const collecting = latest((entry) => entry.ready_at);
  const transit = latest((entry) => entry.picked_up_at);
  const delivered = latest((entry) => entry.completed_at);
  if (preparing) reached.preparing = timeLabel(preparing);
  if (collecting) reached.collecting = timeLabel(collecting);
  if (transit) reached.transit = timeLabel(transit);
  if (delivered) reached.delivered = timeLabel(delivered);
  return reached;
}

const PAYMENT_LABELS: Record<Payment["provider"], string> = {
  COD: "Cash on delivery",
  MOCK_GATEWAY: "Card"
};

export function toOrder(record: ApiOrder): Order {
  const lines: OrderLine[] = record.fulfillments
    .filter((entry) => entry.status !== "REJECTED" && entry.status !== "CANCELLED")
    .flatMap((fulfillment) =>
      fulfillment.lines.map((line) => ({
        medicineId: line.medicine,
        name: line.medicine_detail?.display_name ?? "",
        generic: line.medicine_detail?.generic_name ?? "",
        quantity: line.quantity,
        unitPrice: Number(line.unit_price),
        pharmacy: fulfillment.pharmacy_name,
        requiresPrescription: Boolean(line.medicine_detail?.requires_prescription),
        // An order carries at most one prescription, applied to whichever of
        // its lines needed cover.
        prescriptionId: line.medicine_detail?.requires_prescription ? record.prescription ?? null : null
      }))
    );

  const stage = toStage(record);
  return {
    id: record.reference,
    placedAt: isoDate(record.created_at),
    stage,
    arrivalWindow: arrivalWindow(record),
    scheduled: Boolean(record.scheduled_for),
    deliveredAt: stage === "delivered" ? reachedAt(record).delivered ?? null : null,
    lines,
    // The order carries its own copy of where it was sent, taken at the time.
    // Reading the live address book instead would rewrite delivery history
    // whenever the patient edits an address.
    address: {
      id: record.id,
      label: record.area || record.city || "Delivery address",
      line1: record.address,
      building: "",
      area: record.area,
      city: record.city,
      notes: record.delivery_notes ?? "",
      isDefault: false
    },
    paymentLabel: record.payment ? PAYMENT_LABELS[record.payment.provider] : "Not recorded",
    medicationTotal: Number(record.items_subtotal),
    deliveryFee: Number(record.delivery_fee),
    reachedAt: reachedAt(record),
    rating: record.review?.rating ?? null,
    reviewComment: record.review?.comment ?? ""
  };
}

/**
 * When it should arrive.
 *
 * A scheduled order has a window the platform committed to, so that is stated.
 * An as-soon-as-possible order has none until dispatch plans a route, and
 * saying "45 minutes" before a driver exists would be a number with nothing
 * behind it.
 */
function arrivalWindow(record: ApiOrder): string {
  if (record.window_start && record.window_end) {
    return `${timeLabel(record.window_start)} - ${timeLabel(record.window_end)}`;
  }
  if (record.scheduled_for) return timeLabel(record.scheduled_for);
  return "As soon as it is ready";
}

// --- refills ---------------------------------------------------------------

/**
 * A refill is a recurring order with one medicine on it.
 *
 * A schedule carrying several medicines is shown as one refill per medicine,
 * because that is how a person thinks about "my Lipitor refill" - but they all
 * belong to one schedule, so pausing one pauses them all. The id keeps both
 * halves so the row stays distinct on screen while every write still addresses
 * the schedule; use `scheduleId` to get back to it.
 */
export function toRefills(record: ApiRecurringOrder): Refill[] {
  return (record.item_details ?? []).map((item) => ({
    id: `${record.id}::${item.medicine}`,
    medicineId: item.medicine,
    name: item.name,
    generic: item.generic_name,
    everyDays: record.interval_days,
    nextRefill: isoDate(record.next_run_at),
    status: record.is_active ? "active" : "paused",
    preference: toPreference(record.preferred_hour),
    addressId: record.address,
    prescriptionId: record.prescription_code_value || null
  }));
}

/** The recurring order a refill row belongs to. See `toRefills` for the pairing. */
export function scheduleId(refillId: string): string {
  return refillId.split("::")[0];
}

export function toPreference(hour: number): DeliveryPreference {
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}

/** Middle of the chosen part of the day, so a preference maps to a real hour. */
export function fromPreference(preference: DeliveryPreference): number {
  return { morning: 10, afternoon: 15, evening: 19 }[preference];
}

// --- shared ----------------------------------------------------------------

function isoDate(value: string): string {
  return value.slice(0, 10);
}

function timeLabel(value: string): string {
  return new Date(value).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
