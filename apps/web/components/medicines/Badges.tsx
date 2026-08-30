import { Icon } from "@/components/ui/Icon";
import type { AvailabilityState } from "@/lib/catalog/types";

/**
 * Prescription status, stated calmly.
 *
 * It is a fact about how the medicine is dispensed, not a warning, so it reads
 * as supporting metadata rather than a coloured status badge.
 */
export function PrescriptionBadge({ required }: { required: boolean }) {
  return (
    <span className={`hc-prescription-status ${required ? "is-required" : "is-not-required"}`}>
      <Icon name={required ? "rx" : "check"} size={13} />
      {required ? "Prescription required" : "Prescription not required"}
    </span>
  );
}

const AVAILABILITY_COPY: Record<AvailabilityState, { label: string; className: string }> = {
  available: { label: "Available", className: "hc-chip-ok" },
  limited: { label: "Limited availability", className: "hc-chip-limited" },
  unavailable: { label: "Currently unavailable", className: "hc-chip-off" }
};

/**
 * Supply, in words only. Pharmacies never expose stock depth publicly, so there
 * is no number to show here, and the label carries the meaning without relying
 * on the colour.
 */
export function AvailabilityBadge({ state }: { state: AvailabilityState }) {
  const { label, className } = AVAILABILITY_COPY[state];
  return (
    <span className={`hc-chip hc-status ${className}`}>
      <span className="hc-dot" />
      {label}
    </span>
  );
}

export function availabilityLabel(state: AvailabilityState): string {
  return AVAILABILITY_COPY[state].label;
}

export function MetaChip({ children }: { children: React.ReactNode }) {
  return <span className="hc-chip hc-chip-outline">{children}</span>;
}

/**
 * Whether the National Social Security Fund reimburses this medicine.
 *
 * Only rendered when it is covered - an absent badge is not a claim that the NSSF
 * refuses it, only that the platform has no coverage record. When the reimbursement
 * rate is known it is shown inline ("NSSF 80%"), since that is the number a patient
 * actually acts on.
 */
export function NssfBadge({ covered, rate }: { covered?: boolean; rate?: number | null }) {
  if (!covered) return null;
  return (
    <span className="hc-chip hc-status hc-chip-nssf">
      <Icon name="shield" size={13} />
      {typeof rate === "number" ? `NSSF ${rate % 1 === 0 ? rate : rate.toFixed(2)}%` : "NSSF covered"}
    </span>
  );
}
