/**
 * The patient's own records, as the patient is allowed to see them.
 *
 * Deliberately narrower than the operational models in `types/api.ts`. Nothing
 * here carries stock depth, sourcing scores, pharmacy connector state or
 * dispensing ledgers: those are the platform's problem, not the patient's. What
 * is left is the handful of facts a person needs to answer "what can I get,
 * where is it, and when does it arrive".
 */

// --- prescriptions ---------------------------------------------------------

/**
 * Patient-facing prescription state.
 *
 * `partial` is the one that carries real meaning: a prescription can be drawn
 * down over several visits, and the remainder stays claimable until it expires.
 */
export type PrescriptionStatus = "active" | "partial" | "completed" | "expired";

export interface PrescriptionItem {
  /** Catalogue id, so a prescribed medicine can be ordered without retyping it. */
  medicineId: string;
  name: string;
  generic: string;
  /** Quantity the physician authorised, in `unit`. */
  prescribed: number;
  /** Quantity already collected against it. */
  dispensed: number;
  unit: string;
  dosage: string;
}

export interface Prescription {
  /** Also the route segment: `/prescriptions/HC-RX-38292`. */
  id: string;
  status: PrescriptionStatus;
  prescriber: { name: string; specialty: string };
  /** ISO date. Formatted for display at the edge, never stored formatted. */
  issuedOn: string;
  validUntil: string;
  items: PrescriptionItem[];
  /**
   * Shown only behind an explicit action, never in a list or a preview.
   * See `PrescriptionAccessDialog`.
   */
  accessPin: string;
}

export function remaining(item: PrescriptionItem): number {
  return Math.max(0, item.prescribed - item.dispensed);
}

export function prescriptionRemaining(prescription: Prescription): number {
  return prescription.items.reduce((sum, item) => sum + remaining(item), 0);
}

/** Whether anything on this prescription can still be ordered. */
export function isClaimable(prescription: Prescription): boolean {
  return (
    (prescription.status === "active" || prescription.status === "partial") &&
    prescriptionRemaining(prescription) > 0
  );
}

// --- addresses & payment ---------------------------------------------------

export interface Address {
  id: string;
  label: string;
  line1: string;
  building?: string;
  area: string;
  city: string;
  notes?: string;
  isDefault: boolean;
}

export interface PaymentMethod {
  id: string;
  kind: "card" | "cash";
  /** Card only. Never a full number: the mock stores four digits and nothing else. */
  brand?: string;
  last4?: string;
  expiry?: string;
  isDefault: boolean;
}

// --- orders ----------------------------------------------------------------

export type OrderStage = "confirmed" | "preparing" | "collecting" | "transit" | "delivered";

export const ORDER_STAGES: { stage: OrderStage; label: string }[] = [
  { stage: "confirmed", label: "Order confirmed" },
  { stage: "preparing", label: "Pharmacy preparing" },
  { stage: "collecting", label: "Driver collecting" },
  { stage: "transit", label: "Out for delivery" },
  { stage: "delivered", label: "Delivered" }
];

export interface OrderLine {
  medicineId: string;
  name: string;
  generic: string;
  quantity: number;
  unitPrice: number;
  /** Which connected pharmacy supplied this line. Supporting detail only. */
  pharmacy: string;
  prescriptionId?: string | null;
}

export interface Order {
  id: string;
  placedAt: string;
  stage: OrderStage;
  /** e.g. "4:30 - 5:00 PM". Always presented as an estimate. */
  arrivalWindow: string;
  scheduled: boolean;
  deliveredAt: string | null;
  lines: OrderLine[];
  address: Address;
  paymentLabel: string;
  medicationTotal: number;
  deliveryFee: number;
  /** Timestamps for the stages that have actually happened. */
  reachedAt: Partial<Record<OrderStage, string>>;
  rating: number | null;
  reviewComment: string;
}

export function orderTotal(order: Order): number {
  return order.medicationTotal + order.deliveryFee;
}

export function orderPharmacies(order: Order): string[] {
  return [...new Set(order.lines.map((line) => line.pharmacy))];
}

export function isOrderActive(order: Order): boolean {
  return order.stage !== "delivered";
}

// --- refills ---------------------------------------------------------------

export type RefillStatus = "active" | "paused" | "cancelled";

export type DeliveryPreference = "morning" | "afternoon" | "evening";

export interface Refill {
  id: string;
  medicineId: string;
  name: string;
  generic: string;
  everyDays: number;
  /** ISO date of the next scheduled delivery. */
  nextRefill: string;
  status: RefillStatus;
  preference: DeliveryPreference;
  addressId: string;
  /** The prescription this refill draws on, when the medicine needs one. */
  prescriptionId: string | null;
}

// --- account ---------------------------------------------------------------

export interface PatientProfile {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
}

export interface NotificationPreferences {
  orderUpdates: boolean;
  deliveryUpdates: boolean;
  prescriptionReminders: boolean;
  refillReminders: boolean;
  productNews: boolean;
}
