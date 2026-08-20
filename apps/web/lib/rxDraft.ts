import type { Prescription } from "@/types/api";

const STORAGE_KEY = "pharmalink_rx_draft";

export interface RxDraftItem {
  medicine: string;
  medicine_text: string;
  quantity_prescribed: number;
  unit: string;
  dosage_instructions: string;
  allow_generic_substitution: boolean;
}

export interface RxDraft {
  patient_name: string;
  patient_email: string;
  patient_phone: string;
  items: RxDraftItem[];
}

export function draftFromPrescription(prescription: Prescription): RxDraft {
  return {
    patient_name: prescription.patient_name,
    patient_email: prescription.patient_email || "",
    patient_phone: prescription.patient_phone || "",
    items: prescription.items.map((item) => ({
      medicine: item.medicine || "",
      medicine_text: item.medicine_text,
      quantity_prescribed: item.quantity_prescribed,
      unit: item.unit,
      dosage_instructions: item.dosage_instructions,
      allow_generic_substitution: item.allow_generic_substitution
    }))
  };
}

/** Handed off through sessionStorage (not a query string - a prescription's items don't
 * fit cleanly in a URL) from wherever "Prescribe again" is offered to the write-prescription
 * page, which reads it once on mount via takeDraft(). */
export function saveDraft(draft: RxDraft) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
}

/** Reads and clears the pending draft, if any, so a later visit to the write-prescription
 * page (e.g. via the nav link) starts blank instead of replaying a stale prefill. */
export function takeDraft(): RxDraft | null {
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  window.sessionStorage.removeItem(STORAGE_KEY);
  try {
    return JSON.parse(raw) as RxDraft;
  } catch {
    return null;
  }
}
