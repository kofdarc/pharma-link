import Link from "next/link";
import { AvailabilityBadge, MetaChip, PrescriptionBadge } from "./Badges";
import { PackThumb } from "./PackThumb";
import type { MedicineSummary } from "@/lib/catalog/types";

export function formatPrice(value: number): string {
  return `$${value.toFixed(2)}`;
}

/**
 * How many connected pharmacies could supply it — never how much they hold.
 */
export function sourcingLine(medicine: MedicineSummary): string {
  if (medicine.availability === "unavailable") return "No connected pharmacy can supply this right now";
  if (medicine.sourcingCount <= 0) return "Availability confirmed when you order";
  if (medicine.sourcingCount === 1) return "1 connected pharmacy can supply this";
  return `${medicine.sourcingCount} connected pharmacies can supply this`;
}

export function MedicineResult({ medicine }: { medicine: MedicineSummary }) {
  return (
    <article className="hc-result">
      <PackThumb brand={medicine.brand} image={medicine.image} />

      <div className="hc-result-main">
        <h3 className="hc-result-title">
          <Link href={`/medications/${encodeURIComponent(medicine.id)}`}>
            {medicine.brand} {medicine.strength ? <span className="hc-result-strength">{medicine.strength}</span> : null}
          </Link>
        </h3>
        {medicine.generic ? <p className="hc-result-generic">{medicine.generic}</p> : null}
        <div className="hc-result-meta">
          <AvailabilityBadge state={medicine.availability} />
          <PrescriptionBadge required={medicine.requiresPrescription} />
          {medicine.form ? <MetaChip>{medicine.form}</MetaChip> : null}
          {medicine.packSize ? <MetaChip>{medicine.packSize}</MetaChip> : null}
        </div>
      </div>

      <div className="hc-result-side">
        <div>
          {medicine.fromPrice !== null ? (
            <p className="hc-price">
              <small>From</small>
              {formatPrice(medicine.fromPrice)}
            </p>
          ) : (
            <p className="hc-result-sourcing">Price shown when available</p>
          )}
          <p className="hc-result-sourcing">{sourcingLine(medicine)}</p>
        </div>
        <Link href={`/medications/${encodeURIComponent(medicine.id)}`} className="hc-btn hc-btn-secondary hc-btn-sm">
          View medication
        </Link>
      </div>
    </article>
  );
}
