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

/**
 * How far the nearest listing is, or "" when the shopper has shared no location.
 *
 * Returning an empty string rather than a placeholder is deliberate: a card that says
 * nothing about distance is honest, and one that says "distance unknown" is noise on every
 * row until someone shares a position.
 */
export function distanceLine(medicine: MedicineSummary): string {
  if (medicine.nearestKm === null) return "";
  const how = medicine.nearestKm < 1 ? "under 1 km" : `${medicine.nearestKm.toFixed(1)} km`;
  return medicine.nearestPharmacy ? `${how} away · ${medicine.nearestPharmacy}` : `${how} away`;
}

export function MedicineResult({ medicine }: { medicine: MedicineSummary }) {
  return (
    <article className="hc-result">
      <PackThumb brand={medicine.brand} image={medicine.image} size="result" />

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
              {!medicine.isPriceRegulated ? <small>From</small> : null}
              {formatPrice(medicine.fromPrice)}
            </p>
          ) : (
            <p className="hc-result-sourcing">Price shown when available</p>
          )}
          <p className="hc-result-sourcing">{sourcingLine(medicine)}</p>
          {distanceLine(medicine) ? <p className="hc-result-distance">{distanceLine(medicine)}</p> : null}
        </div>
        <Link href={`/medications/${encodeURIComponent(medicine.id)}`} className="hc-btn hc-btn-secondary hc-btn-sm">
          View medication
        </Link>
      </div>
    </article>
  );
}
