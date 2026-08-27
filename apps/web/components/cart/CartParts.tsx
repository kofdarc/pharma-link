"use client";

import { useState } from "react";
import { Dialog } from "@/components/patient/Dialog";
import { Icon } from "@/components/ui/Icon";
import { PackThumb } from "@/components/medicines/PackThumb";
import type { BasketItem } from "@/lib/basket";
import { formatDate, formatMoney, plural } from "@/lib/patient/format";
import { prescriptionsCovering, remainingFor } from "@/lib/patient/checkout";
import type { Prescription } from "@/lib/patient/types";

const MAX_QUANTITY = 10;

/**
 * One medication in the basket.
 *
 * Structured as a medication rather than a product: the generic name and form
 * sit directly under the brand, and prescription cover gets its own block below
 * the line instead of being reduced to a badge. A patient scanning this needs to
 * know what is missing before they know what it costs, so cover comes before
 * price in the reading order on narrow screens.
 */
export function CartLine({
  item,
  prescriptions,
  onQuantity,
  onRemove,
  onAttach
}: {
  item: BasketItem;
  prescriptions: Prescription[];
  onQuantity: (quantity: number) => void;
  onRemove: () => void;
  onAttach: (prescriptionId: string | null) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  // Everything shown here comes off the basket line itself, captured when the
  // medicine was added. The cart does not re-query the catalogue: a line the
  // patient put there must keep rendering even when the API is unreachable.
  const price = item.unit_price ?? null;
  const matches = prescriptionsCovering(prescriptions, item.medicine);
  const attached = prescriptions.find((entry) => entry.id === item.prescription_id) ?? null;

  return (
    <article className="hc-cartline">
      <PackThumb brand={item.name} />

      <div className="hc-cartline-main">
        <h3 className="hc-cartline-name">{item.name}</h3>
        {item.generic ? <p className="hc-small">{item.generic}</p> : null}

        {item.requires_prescription ? (
          <div className={`hc-cover${attached ? " hc-cover-met" : ""}`}>
            <p className="hc-cover-head">
              <Icon name="rx" size={15} />
              Prescription required
            </p>
            {attached ? (
              <p className="hc-cover-body">
                <Icon name="check" size={14} strokeWidth={2.4} />
                <span>
                  Using <strong className="hc-num">{attached.id}</strong>, valid until {formatDate(attached.validUntil)}
                </span>
                <button type="button" className="hc-linkbtn" onClick={() => setPickerOpen(true)}>
                  Change
                </button>
              </p>
            ) : matches.length > 0 ? (
              <p className="hc-cover-body">
                <span>{plural(matches.length, "active prescription")} on your account covers this.</span>
                <button type="button" className="hc-linkbtn" onClick={() => setPickerOpen(true)}>
                  Select prescription
                </button>
              </p>
            ) : (
              <p className="hc-cover-body">
                No prescription on your account covers this yet. You can still continue, and the pharmacy will ask for a
                prescription before dispensing.
              </p>
            )}
          </div>
        ) : null}
      </div>

      <div className="hc-cartline-side">
        <p className="hc-cartline-price hc-num">
          {price !== null ? formatMoney(price * item.quantity) : "Priced when matched"}
        </p>
        {price !== null && item.quantity > 1 ? (
          <p className="hc-small hc-num">{formatMoney(price)} each</p>
        ) : null}

        <div className="hc-stepper" role="group" aria-label={`Quantity of ${item.name}`}>
          <button
            type="button"
            onClick={() => onQuantity(item.quantity - 1)}
            disabled={item.quantity <= 1}
            aria-label="Decrease quantity"
          >
            <Icon name="minus" size={16} />
          </button>
          <output aria-live="polite">{item.quantity}</output>
          <button
            type="button"
            onClick={() => onQuantity(item.quantity + 1)}
            disabled={item.quantity >= MAX_QUANTITY}
            aria-label="Increase quantity"
          >
            <Icon name="plus" size={16} />
          </button>
        </div>

        <button type="button" className="hc-linkbtn hc-linkbtn-quiet" onClick={onRemove}>
          Remove
        </button>
      </div>

      <PrescriptionPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        medicineName={item.name}
        medicineId={item.medicine}
        options={matches}
        selectedId={item.prescription_id ?? null}
        onSelect={(prescriptionId) => {
          onAttach(prescriptionId);
          setPickerOpen(false);
        }}
      />
    </article>
  );
}

/**
 * Choosing which prescription a line is dispensed against.
 *
 * Only prescriptions that actually cover the medicine and still have quantity
 * left are offered. There is no free-text field for a prescription number: if
 * the patient holds one, the account already knows it, and asking them to copy a
 * reference across screens invites typos on the one field that must be right.
 */
function PrescriptionPicker({
  open,
  onClose,
  medicineId,
  medicineName,
  options,
  selectedId,
  onSelect
}: {
  open: boolean;
  onClose: () => void;
  medicineId: string;
  medicineName: string;
  options: Prescription[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} title="Select prescription" description={medicineName} size="sm">
      {options.length === 0 ? (
        <p className="hc-body">No prescription on your account currently covers this medication.</p>
      ) : (
        <ul className="hc-picker">
          {options.map((prescription) => {
            const left = remainingFor(prescription, medicineId);
            const selected = prescription.id === selectedId;
            return (
              <li key={prescription.id}>
                <button
                  type="button"
                  className="hc-picker-option"
                  aria-pressed={selected}
                  onClick={() => onSelect(selected ? null : prescription.id)}
                >
                  <span className="hc-picker-body">
                    <strong className="hc-num">{prescription.id}</strong>
                    <span className="hc-small">
                      {prescription.prescriber.name} · valid until {formatDate(prescription.validUntil)}
                    </span>
                    <span className="hc-small">{left} remaining on this prescription</span>
                  </span>
                  {selected ? <Icon name="checkCircle" size={19} /> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Dialog>
  );
}

/**
 * Basket totals.
 *
 * Everything is called an estimate and the delivery row stays unpriced, because
 * no pharmacy has been matched yet. Naming a firm total here and revising it one
 * screen later would be the wrong kind of confidence.
 */
export function CartSummary({
  items,
  children
}: {
  items: BasketItem[];
  children?: React.ReactNode;
}) {
  // Distinct medications, not packs. "4 medications" for three medicines, one
  // of which is doubled, is a different and wrong fact.
  const count = items.length;
  const priced = items.filter((item) => (item.unit_price ?? null) !== null);
  const subtotal = priced.reduce((sum, item) => sum + (item.unit_price ?? 0) * item.quantity, 0);
  const someUnpriced = priced.length < items.length;

  return (
    <aside className="hc-summary" aria-labelledby="cart-summary">
      <h2 className="hc-h3" id="cart-summary">
        Summary
      </h2>

      <dl className="hc-summary-rows">
        <div>
          <dt>{plural(count, "medication")}</dt>
          <dd className="hc-num">{formatMoney(subtotal)}</dd>
        </div>
        <div>
          <dt>Delivery</dt>
          <dd className="hc-summary-pending">Calculated next</dd>
        </div>
      </dl>

      <div className="hc-summary-total">
        <span>Estimated total</span>
        <strong className="hc-num">
          {formatMoney(subtotal)}
          {someUnpriced ? "+" : ""}
        </strong>
      </div>

      <p className="hc-small">
        Prices are the lowest currently listed by connected pharmacies. The amount is confirmed once HealthConnect
        matches your basket to pharmacies that can supply it.
      </p>

      {children}
    </aside>
  );
}
