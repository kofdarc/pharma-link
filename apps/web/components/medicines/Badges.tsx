import { Icon } from "@/components/ui/Icon";
import type { AvailabilityState } from "@/lib/catalog/types";

/**
 * Prescription status, stated calmly.
 *
 * It is a fact about how the medicine is dispensed, not a warning, so it gets
 * the brand tint rather than a danger colour.
 */
export function PrescriptionBadge({ required }: { required: boolean }) {
  return required ? (
    <span className="hc-chip hc-chip-rx">
      <Icon name="rx" size={13} />
      Prescription required
    </span>
  ) : (
    <span className="hc-chip hc-chip-otc">
      <Icon name="check" size={13} />
      No prescription needed
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
    <span className={`hc-chip ${className}`}>
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
