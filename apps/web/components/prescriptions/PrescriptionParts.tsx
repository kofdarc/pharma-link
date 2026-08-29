"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";
import { formatDate, plural } from "@/lib/patient/format";
import { isClaimable, remaining, type Prescription, type PrescriptionItem, type PrescriptionStatus } from "@/lib/patient/types";

/**
 * The prescription wallet, in parts.
 *
 * The guiding idea for this whole section: a prescription is a document the
 * patient owns, not a record the system keeps about them. So the card leads
 * with the person who wrote it and the dates it covers, and the numbers that
 * matter operationally (what is left to collect) are stated in plain counts
 * rather than as a dispensing ledger.
 */

const STATUS: Record<PrescriptionStatus, { label: string; chip: string; icon: IconName }> = {
  active: { label: "Active", chip: "hc-chip-ok", icon: "check" },
  partial: { label: "Partly collected", chip: "hc-chip-limited", icon: "pill" },
  completed: { label: "Fully collected", chip: "hc-chip-off", icon: "check" },
  expired: { label: "Expired", chip: "hc-chip-off", icon: "clock" }
};

/** Icon plus word plus colour. Never colour on its own. */
export function PrescriptionStatusChip({ status }: { status: PrescriptionStatus }) {
  const { label, chip, icon } = STATUS[status];
  return (
    <span className={`hc-chip hc-status ${chip}`}>
      <Icon name={icon} size={13} strokeWidth={2.1} />
      {label}
    </span>
  );
}

export function PrescriptionCard({ prescription }: { prescription: Prescription }) {
  const claimable = isClaimable(prescription);

  return (
    <article className="hc-card hc-rxcard">
      <div className="hc-card-head">
        <div>
          <p className="hc-card-label">{prescription.id}</p>
          <h2 className="hc-h3 hc-rxcard-name">{prescription.prescriber.name}</h2>
          <p className="hc-small">{prescription.prescriber.specialty}</p>
        </div>
        <PrescriptionStatusChip status={prescription.status} />
      </div>

      <dl className="hc-kv">
        <div>
          <dt>Issued</dt>
          <dd>{formatDate(prescription.issuedOn)}</dd>
        </div>
        <div>
          <dt>Valid until</dt>
          <dd>{formatDate(prescription.validUntil)}</dd>
        </div>
        <div>
          <dt>Medications</dt>
          <dd>{plural(prescription.items.length, "medication")}</dd>
        </div>
      </dl>

      <div className="hc-rxcard-actions">
        <Link href={`/prescriptions/${prescription.id}`} className="hc-btn hc-btn-secondary hc-btn-sm">
          View prescription
        </Link>
        {claimable ? (
          <Link href={`/prescriptions/${prescription.id}?order=1`} className="hc-btn hc-btn-primary hc-btn-sm">
            Order medications
          </Link>
        ) : null}
      </div>
    </article>
  );
}

/**
 * One prescribed medicine, with what is left on it.
 *
 * Prescribed / collected / remaining are shown as three plain figures because
 * the difference between them is the thing a patient actually needs: a
 * prescription can be drawn down over several orders, and the balance stays
 * theirs until it expires.
 */
export function PrescriptionMedicationRow({
  item,
  claimable
}: {
  item: PrescriptionItem;
  claimable: boolean;
}) {
  const left = remaining(item);
  const collected = item.dispensed;
  const progress = item.prescribed > 0 ? collected / item.prescribed : 0;

  return (
    <li className="hc-rxmed">
      <div className="hc-rxmed-top">
        <div>
          <p className="hc-rxmed-name">{item.name}</p>
          <p className="hc-small">{item.generic}</p>
        </div>
        {left > 0 && claimable ? (
          <span className="hc-chip hc-chip-outline hc-num">
            {left} {item.unit} left
          </span>
        ) : null}
      </div>

      <p className="hc-rxmed-dosage">
        <Icon name="info" size={14} />
        {item.dosage}
      </p>

      <dl className="hc-rxmed-figures">
        <div>
          <dt>Prescribed</dt>
          <dd className="hc-num">
            {item.prescribed} {item.unit}
          </dd>
        </div>
        <div>
          <dt>Collected</dt>
          <dd className="hc-num">
            {collected} {item.unit}
          </dd>
        </div>
        <div>
          <dt>Remaining</dt>
          <dd className="hc-num">
            {left} {item.unit}
          </dd>
        </div>
      </dl>

      {collected > 0 ? (
        <div className="hc-rxmed-progress">
          <span
            className="hc-rxmed-progress-fill"
            style={{ inlineSize: `${Math.round(progress * 100)}%` }}
            aria-hidden="true"
          />
          <p className="hc-small">
            {left > 0
              ? `${collected} of ${item.prescribed} collected. ${left} ${item.unit} remain available on this prescription.`
              : `All ${item.prescribed} ${item.unit} have been collected.`}
          </p>
        </div>
      ) : null}
    </li>
  );
}
