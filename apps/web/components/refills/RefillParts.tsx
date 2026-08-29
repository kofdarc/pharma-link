"use client";

import { useState } from "react";
import { Dialog } from "@/components/patient/Dialog";
import { Icon } from "@/components/ui/Icon";
import { formatDate, daysUntil } from "@/lib/patient/format";
import type { Address, DeliveryPreference, Prescription, Refill } from "@/lib/patient/types";

/**
 * Recurring refills.
 *
 * The screen has one job and one risk. The job is to make a repeating delivery
 * feel controllable: what, how often, when next, and how to stop it. The risk is
 * implying that because a refill is scheduled, the patient is entitled to it.
 * They are not, a prescription can run out first, so every card checks its
 * prescription against its next delivery date and says so plainly.
 */

const INTERVALS = [14, 30, 60, 90];

const PREFERENCE_COPY: Record<DeliveryPreference, string> = {
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening"
};

export function refillWarning(refill: Refill, prescriptions: Prescription[]): string | null {
  if (!refill.prescriptionId || refill.status !== "active") return null;
  const prescription = prescriptions.find((entry) => entry.id === refill.prescriptionId);
  if (!prescription) return "The prescription this refill draws on is no longer on your account.";
  if (prescription.validUntil < refill.nextRefill) {
    return `Your current prescription expires on ${formatDate(prescription.validUntil)}, before this delivery. A new prescription may be needed.`;
  }
  return null;
}

export function RefillCard({
  refill,
  prescriptions,
  address,
  onManage,
  onRefillNow,
  onResume
}: {
  refill: Refill;
  prescriptions: Prescription[];
  address?: Address;
  onManage: () => void;
  onRefillNow: () => void;
  onResume: () => void;
}) {
  const paused = refill.status === "paused";
  const warning = refillWarning(refill, prescriptions);
  const countdown = daysUntil(refill.nextRefill);

  return (
    <article className={`hc-card hc-refillcard${paused ? " hc-refillcard-paused" : ""}`}>
      <div className="hc-card-head">
        <div>
          <h2 className="hc-h3 hc-refillcard-name">{refill.name}</h2>
          <p className="hc-small">{refill.generic}</p>
        </div>
        {paused ? (
          <span className="hc-chip hc-chip-off hc-status">
            <Icon name="pause" size={13} strokeWidth={2.1} />
            Paused
          </span>
        ) : (
          <span className="hc-chip hc-chip-ok hc-status">
            <Icon name="refresh" size={13} strokeWidth={2.1} />
            Active
          </span>
        )}
      </div>

      <dl className="hc-kv">
        <div>
          <dt>Every</dt>
          <dd>{refill.everyDays} days</dd>
        </div>
        <div>
          <dt>Next refill</dt>
          <dd>
            {paused ? "Paused" : formatDate(refill.nextRefill)}
            {!paused && countdown >= 0 ? (
              <span className="hc-small"> {countdown === 0 ? "today" : `in ${countdown} days`}</span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>Delivering to</dt>
          <dd>
            {address?.label ?? "No address"} · {PREFERENCE_COPY[refill.preference]}
          </dd>
        </div>
      </dl>

      {warning ? (
        <p className="hc-inline-note hc-inline-note-warn">
          <Icon name="alert" size={16} />
          {warning}
        </p>
      ) : null}

      {paused ? (
        <p className="hc-small">Paused refills are not delivered and nothing is charged until you resume.</p>
      ) : null}

      <div className="hc-rxcard-actions">
        {paused ? (
          <button type="button" className="hc-btn hc-btn-primary hc-btn-sm" onClick={onResume}>
            <Icon name="play" size={15} />
            Resume
          </button>
        ) : (
          <button type="button" className="hc-btn hc-btn-primary hc-btn-sm" onClick={onRefillNow}>
            Refill now
          </button>
        )}
        <button type="button" className="hc-btn hc-btn-secondary hc-btn-sm" onClick={onManage}>
          Manage
        </button>
      </div>
    </article>
  );
}

/**
 * Editing a schedule.
 *
 * Pause and cancel live in here rather than on the card, because a destructive
 * control next to "Refill now" is a mis-tap waiting to happen on a phone.
 */
export function RefillScheduleDialog({
  open,
  onClose,
  refill,
  addresses,
  onSave,
  onPause,
  onCancel
}: {
  open: boolean;
  onClose: () => void;
  refill: Refill;
  addresses: Address[];
  onSave: (patch: Partial<Refill>) => void;
  onPause: () => void;
  onCancel: () => void;
}) {
  const [everyDays, setEveryDays] = useState(refill.everyDays);
  const [nextRefill, setNextRefill] = useState(refill.nextRefill);
  const [preference, setPreference] = useState<DeliveryPreference>(refill.preference);
  const [addressId, setAddressId] = useState(refill.addressId);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Manage refill"
      description={refill.name}
      footer={
        <>
          <button type="button" className="hc-btn hc-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="hc-btn hc-btn-primary"
            onClick={() => {
              onSave({ everyDays, nextRefill, preference, addressId });
              onClose();
            }}
          >
            Save changes
          </button>
        </>
      }
    >
      <div className="hc-form">
        <fieldset className="hc-filter-group">
          <legend className="hc-label">Repeat every</legend>
          <div className="hc-pills">
            {INTERVALS.map((days) => (
              <label key={days} className={`hc-pill${everyDays === days ? " hc-pill-on" : ""}`}>
                <input type="radio" name="refill-interval" checked={everyDays === days} onChange={() => setEveryDays(days)} />
                {days} days
              </label>
            ))}
          </div>
        </fieldset>

        <div className="hc-field">
          <label htmlFor="refill-next">Next delivery</label>
          <input
            id="refill-next"
            type="date"
            className="hc-input"
            value={nextRefill}
            onChange={(event) => setNextRefill(event.target.value)}
          />
        </div>

        <fieldset className="hc-filter-group">
          <legend className="hc-label">Preferred time</legend>
          <div className="hc-pills">
            {(Object.keys(PREFERENCE_COPY) as DeliveryPreference[]).map((value) => (
              <label key={value} className={`hc-pill${preference === value ? " hc-pill-on" : ""}`}>
                <input
                  type="radio"
                  name="refill-preference"
                  checked={preference === value}
                  onChange={() => setPreference(value)}
                />
                {PREFERENCE_COPY[value]}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="hc-field">
          <label htmlFor="refill-address">Delivery address</label>
          <select
            id="refill-address"
            className="hc-input"
            value={addressId}
            onChange={(event) => setAddressId(event.target.value)}
          >
            {addresses.map((address) => (
              <option key={address.id} value={address.id}>
                {address.label} · {address.area}
              </option>
            ))}
          </select>
        </div>

        <hr className="hc-rule" />

        <div className="hc-refill-danger">
          {refill.status === "active" ? (
            <button
              type="button"
              className="hc-btn hc-btn-secondary hc-btn-sm"
              onClick={() => {
                onPause();
                onClose();
              }}
            >
              <Icon name="pause" size={15} />
              Pause this refill
            </button>
          ) : null}
          <button type="button" className="hc-linkbtn hc-linkbtn-danger" onClick={onCancel}>
            Cancel this refill
          </button>
        </div>
      </div>
    </Dialog>
  );
}
