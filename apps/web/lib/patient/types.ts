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

/**
 * A photo or scan of a paper prescription the patient uploaded themselves.
 *
 * Separate from `Prescription`: it is not a digital record a doctor issued, it
 * is an image a pharmacy has to look at and verify before anything can be
 * dispensed against it. Until then it sits in `pending` review.
 */
export type PrescriptionUploadStatus = "pending" | "accepted" | "rejected";

export interface OcrMedication {
  name: string;
  strength: string;
  quantity: number | null;
  directions: string;
  duration: string;
  refills: number | null;
  /** The catalog Medicine this row was reconciled to server-side ("" if unmatched),
   * its display name, and the 0-1 match score. */
  medicineId: string;
  catalogName: string;
  matchConfidence: number | null;
}

/** What OCR read off the uploaded scan. The patient sees this read-only and can
 * flag it; a pharmacist corrects it on review. */
export interface OcrFields {
  patientName: string;
  patientPhone: string;
  doctorName: string;
  prescriptionDate: string;
  medications: OcrMedication[];
  notes: string;
}

export interface PrescriptionUpload {
  id: string;
  status: PrescriptionUploadStatus;
  /** What OCR read as the prescriber, mirrored onto the record. */
  doctorName: string;
  uploadedOn: string;
  fileName: string;
  /** Set by the pharmacy when they turn it down. */
  rejectionReason: string;
  /** Non-blocking advice from the legibility check, e.g. "a little soft". */
  qualityWarnings: string[];
  /** API path to fetch the file itself, token-authenticated. */
  filePath: string;
  /** The structured OCR read, or null if extraction was off or produced nothing. */
  ocrFields: OcrFields | null;
  /** A read exists but is too weak to trust: the UI withholds the parsed medication list
   * and shows a "a pharmacist will check your photo" notice instead. */
  ocrLowConfidence: boolean;
  /** The patient flagged the OCR read as wrong. */
  ocrReviewRequested: boolean;
  ocrReviewNote: string;
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
  /**
   * Where this is, for ranking pharmacies by distance. Resolved from the area
   * by the API rather than asked for - nobody types their own latitude - so it
   * is absent on an address the patient has only just filled in locally.
   */
  latitude?: number;
  longitude?: number;
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
  /**
   * Carried on the line so "order again" can rebuild the basket without a
   * second catalogue lookup. Cover is re-checked against what is valid today,
   * so this says the medicine needs a prescription, not that one is held.
   */
  requiresPrescription: boolean;
  prescriptionId?: string | null;
}

/**
 * One connected pharmacy's part in an order, with its own totals.
 *
 * The order screen only needs the names (see `orderPharmacies`), but the
 * receipt is a document: it names each pharmacy that dispensed, where it is and
 * how to reach it, and what its own lines came to.
 */
export interface OrderPharmacy {
  name: string;
  area: string;
  phone: string;
  /** What this pharmacy's lines came to, before the delivery fee. */
  subtotal: number;
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
  /** Who the order was placed for, carried on the order at the time. */
  contactName: string;
  contactPhone: string;
  paymentLabel: string;
  /** ISO date the payment cleared, when it has. Null for cash on delivery. */
  paidAt: string | null;
  /** The connected pharmacies that filled this order. */
  fulfilledBy: OrderPharmacy[];
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
