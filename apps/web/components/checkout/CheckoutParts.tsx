"use client";

import { Icon } from "@/components/ui/Icon";
import { formatDate } from "@/lib/patient/format";
import type { Address, PaymentMethod, Prescription } from "@/lib/patient/types";
import type { FulfillmentLine } from "@/lib/patient/fulfillment";

/**
 * Checkout, in four small decisions.
 *
 * Each block below is one of them. They are numbered on screen so the page
 * reads as a short sequence rather than a wall of form, but they all stay
 * visible: a patient should be able to see the address and the prescription
 * cover at the moment they press the button that spends their money.
 */

export function CheckoutStep({
  index,
  title,
  action,
  children
}: {
  index: number;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="hc-step-block" aria-labelledby={`step-${index}`}>
      <header className="hc-step-head">
        <span className="hc-step-index hc-num" aria-hidden="true">
          {index}
        </span>
        <h2 className="hc-h3" id={`step-${index}`}>
          {title}
        </h2>
        {action ? <div className="hc-step-action">{action}</div> : null}
      </header>
      <div className="hc-step-body">{children}</div>
    </section>
  );
}

export function AddressSelector({
  addresses,
  selectedId,
  onSelect,
  onAdd
}: {
  addresses: Address[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAdd: () => void;
}) {
  if (addresses.length === 0) {
    return (
      <div className="hc-choice-empty">
        <p className="hc-body">No delivery address saved yet.</p>
        <button type="button" className="hc-btn hc-btn-secondary hc-btn-sm" onClick={onAdd}>
          <Icon name="plus" size={15} />
          Add address
        </button>
      </div>
    );
  }

  return (
    <>
      <ul className="hc-choices" role="radiogroup" aria-label="Delivery address">
        {addresses.map((address) => (
          <li key={address.id}>
            <label className={`hc-choice${address.id === selectedId ? " hc-choice-selected" : ""}`}>
              <input
                type="radio"
                name="delivery-address"
                checked={address.id === selectedId}
                onChange={() => onSelect(address.id)}
              />
              <span className="hc-choice-mark" aria-hidden="true" />
              <span className="hc-choice-body">
                <strong>{address.label}</strong>
                <span className="hc-small">
                  {address.line1}
                  {address.building ? `, ${address.building}` : ""}
                </span>
                <span className="hc-small">
                  {address.area}, {address.city}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      <button type="button" className="hc-linkbtn" onClick={onAdd}>
        Add another address
      </button>
    </>
  );
}

export type DeliveryChoice = { kind: "asap" } | { kind: "scheduled"; window: string };

/**
 * When it arrives.
 *
 * Three windows and a soonest option, not a calendar. Medication delivery is a
 * today decision; a month view would be a lot of chrome around three buttons.
 */
export function DeliveryWindowSelector({
  etaLabel,
  windows,
  value,
  onChange
}: {
  etaLabel: string;
  windows: string[];
  value: DeliveryChoice;
  onChange: (next: DeliveryChoice) => void;
}) {
  const scheduled = value.kind === "scheduled";

  return (
    <div className="hc-when">
      <ul className="hc-choices" role="radiogroup" aria-label="Delivery time">
        <li>
          <label className={`hc-choice${!scheduled ? " hc-choice-selected" : ""}`}>
            <input type="radio" name="delivery-when" checked={!scheduled} onChange={() => onChange({ kind: "asap" })} />
            <span className="hc-choice-mark" aria-hidden="true" />
            <span className="hc-choice-body">
              <strong>As soon as possible</strong>
              <span className="hc-small">Estimated {etaLabel} from when the pharmacies confirm.</span>
            </span>
          </label>
        </li>
        <li>
          <label className={`hc-choice${scheduled ? " hc-choice-selected" : ""}`}>
            <input
              type="radio"
              name="delivery-when"
              checked={scheduled}
              onChange={() => onChange({ kind: "scheduled", window: windows[0] })}
            />
            <span className="hc-choice-mark" aria-hidden="true" />
            <span className="hc-choice-body">
              <strong>Schedule delivery</strong>
              <span className="hc-small">Pick a window later today.</span>
            </span>
          </label>
        </li>
      </ul>

      {scheduled ? (
        <div className="hc-windows" role="radiogroup" aria-label="Delivery window">
          {windows.map((window) => (
            <label key={window} className={`hc-window${value.window === window ? " hc-window-selected" : ""}`}>
              <input
                type="radio"
                name="delivery-window"
                checked={value.window === window}
                onChange={() => onChange({ kind: "scheduled", window })}
              />
              {window}
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Prescription cover, restated at the point of commitment.
 *
 * The wording is careful on purpose: a prescription is verified, a medication
 * is never "approved". HealthConnect checks that a valid prescription covers
 * what is being dispensed. It does not make clinical decisions and should not
 * word itself as though it does.
 */
export function PrescriptionVerificationSummary({
  lines,
  prescriptions
}: {
  lines: FulfillmentLine[];
  prescriptions: Prescription[];
}) {
  return (
    <ul className="hc-verify">
      {lines.map((line) => {
        const prescription = prescriptions.find((entry) => entry.id === line.prescriptionId);

        // Three distinct states, and the middle one is the reason this is not a
        // boolean. A medicine that needs a prescription and has not been matched
        // to one must never be reported as needing none.
        if (line.requiresPrescription && prescription) {
          return (
            <li key={line.medicineId} className="hc-verify-row hc-verify-ok">
              <Icon name="checkCircle" size={17} />
              <span>
                <strong>{line.name}</strong>
                <span className="hc-small">
                  Prescription <span className="hc-num">{prescription.id}</span> verified, valid until{" "}
                  {formatDate(prescription.validUntil)}
                </span>
              </span>
            </li>
          );
        }

        if (line.requiresPrescription) {
          return (
            <li key={line.medicineId} className="hc-verify-row hc-verify-open">
              <Icon name="rx" size={17} />
              <span>
                <strong>{line.name}</strong>
                <span className="hc-small">
                  Prescription required, none selected. The pharmacy will ask for it before dispensing.
                </span>
              </span>
            </li>
          );
        }

        return (
          <li key={line.medicineId} className="hc-verify-row">
            <Icon name="check" size={17} />
            <span>
              <strong>{line.name}</strong>
              <span className="hc-small">No prescription required</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function PaymentSelector({
  methods,
  selectedId,
  onSelect
}: {
  methods: PaymentMethod[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="hc-choices" role="radiogroup" aria-label="Payment method">
      {methods.map((method) => (
        <li key={method.id}>
          <label className={`hc-choice${method.id === selectedId ? " hc-choice-selected" : ""}`}>
            <input
              type="radio"
              name="payment-method"
              checked={method.id === selectedId}
              onChange={() => onSelect(method.id)}
            />
            <span className="hc-choice-mark" aria-hidden="true" />
            <span className="hc-choice-icon" aria-hidden="true">
              <Icon name={method.kind === "card" ? "card" : "receipt"} size={17} />
            </span>
            <span className="hc-choice-body">
              <strong>{paymentLabel(method)}</strong>
              <span className="hc-small">
                {method.kind === "card" ? `Expires ${method.expiry}` : "Pay the driver when your order arrives"}
              </span>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

export function paymentLabel(method: PaymentMethod): string {
  return method.kind === "card" ? `${method.brand} ending ${method.last4}` : "Cash on delivery";
}
