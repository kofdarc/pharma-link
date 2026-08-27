import type { Prescription } from "@/types/api";

export interface Patient {
  key: string;
  name: string;
  email: string;
  phone: string;
  fax: string;
  prescriptions: Prescription[];
}

/** Prescriptions carry patient details inline (there's no separate patient record), so a
 * doctor's patient list is derived by grouping their own prescriptions by name + email. */
export function groupPatients(prescriptions: Prescription[]): Patient[] {
  const groups = new Map<string, Patient>();
  for (const prescription of prescriptions) {
    const key = `${prescription.patient_name.trim().toLowerCase()}|${(prescription.patient_email || "").trim().toLowerCase()}`;
    const existing = groups.get(key);
    if (existing) {
      existing.prescriptions.push(prescription);
      if (!existing.phone && prescription.patient_phone) existing.phone = prescription.patient_phone;
      if (!existing.fax && prescription.patient_fax) existing.fax = prescription.patient_fax;
    } else {
      groups.set(key, {
        key,
        name: prescription.patient_name,
        email: prescription.patient_email || "",
        phone: prescription.patient_phone || "",
        fax: prescription.patient_fax || "",
        prescriptions: [prescription]
      });
    }
  }
  return Array.from(groups.values())
    .map((patient) => ({
      ...patient,
      prescriptions: [...patient.prescriptions].sort(
        (a, b) => new Date(b.issued_at).getTime() - new Date(a.issued_at).getTime()
      )
    }))
    .sort((a, b) => new Date(b.prescriptions[0].issued_at).getTime() - new Date(a.prescriptions[0].issued_at).getTime());
}
