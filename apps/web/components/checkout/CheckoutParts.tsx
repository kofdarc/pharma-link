"use client";

import { useId } from "react";
import { Icon } from "@/components/ui/Icon";
import { formatDate } from "@/lib/patient/format";
import type { Address, Prescription } from "@/lib/patient/types";
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

export type PaymentMethodId = "cod" | "card" | "whish";

/**
 * The payment methods HealthConnect offers, in the order they are shown.
 *
 * Fixed for now: nothing here is wired to a real gateway. Selecting Whish only
 * records the choice; the order still goes through the demonstration flow.
 */
export const PAYMENT_METHODS: {
  id: PaymentMethodId;
  label: string;
  hint: string;
  icon: React.ReactNode;
}[] = [
  {
    id: "cod",
    label: "Cash on delivery",
    hint: "Pay the driver when your order arrives",
    icon: (
      <span className="hc-choice-icon" aria-hidden="true">
        <Icon name="receipt" size={17} />
      </span>
    )
  },
  {
    id: "card",
    label: "Credit card",
    hint: "Visa, Mastercard, or Amex",
    icon: (
      <span className="hc-choice-icon" aria-hidden="true">
        <Icon name="card" size={17} />
      </span>
    )
  },
  {
    id: "whish",
    label: "Whish",
    hint: "Pay from your Whish wallet",
    icon: (
      <span className="hc-choice-icon hc-choice-icon-bare" aria-hidden="true">
        <WhishLogo size={34} />
      </span>
    )
  }
];

export function PaymentSelector({
  selectedId,
  onSelect
}: {
  selectedId: PaymentMethodId;
  onSelect: (id: PaymentMethodId) => void;
}) {
  return (
    <ul className="hc-choices" role="radiogroup" aria-label="Payment method">
      {PAYMENT_METHODS.map((method) => (
        <li key={method.id}>
          <label className={`hc-choice${method.id === selectedId ? " hc-choice-selected" : ""}`}>
            <input
              type="radio"
              name="payment-method"
              checked={method.id === selectedId}
              onChange={() => onSelect(method.id)}
            />
            <span className="hc-choice-mark" aria-hidden="true" />
            {method.icon}
            <span className="hc-choice-body">
              <strong>{method.label}</strong>
              <span className="hc-small">{method.hint}</span>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

/** Whish Money mark — a red "w" with the trailing speed lines from the brand logo. */
function WhishLogo({ size = 34 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={(size * 32) / 46}
      viewBox="0 0 46 32"
      role="img"
      aria-label="Whish"
      fill="none"
    >
      <path d="M5 10 19 8.4 19 11.6Z" fill="#E5384E" />
      <path d="M2 16 22 14 22 18Z" fill="#E5384E" />
      <path d="M6 22 18 20.6 18 23.4Z" fill="#E5384E" />
      <path
        d="M21 6 26 26 31 13 36 26 41 6"
        stroke="#E5384E"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// --- card details --------------------------------------------------------------

export type CardDraft = { number: string; name: string; expiry: string; cvc: string };

export const EMPTY_CARD: CardDraft = { number: "", name: "", expiry: "", cvc: "" };

/** Digits only, grouped in fours, capped at the 19 a card number can hold. */
export function formatCardNumber(raw: string): string {
  return raw
    .replace(/\D/g, "")
    .slice(0, 19)
    .replace(/(.{4})/g, "$1 ")
    .trim();
}

/** Digits only, shown as `MM / YY` once a month has been typed. */
export function formatExpiry(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)} / ${digits.slice(2)}`;
}

export type CardErrors = Partial<Record<keyof CardDraft, string>>;

/**
 * The usual four fields, and nothing a real processor's hosted form would not
 * also ask for. Validation is shape-only: enough to catch a fat-fingered entry,
 * not a substitute for the gateway that will eventually check the card.
 */
export function validateCard(card: CardDraft): CardErrors {
  const errors: CardErrors = {};
  const digits = card.number.replace(/\D/g, "");
  if (digits.length < 13 || digits.length > 19) errors.number = "Enter a valid card number.";
  if (!card.name.trim()) errors.name = "Enter the name on the card.";

  const expiry = /^(\d{2})\s*\/\s*(\d{2})$/.exec(card.expiry.trim());
  const month = expiry ? Number(expiry[1]) : 0;
  if (!expiry || month < 1 || month > 12) {
    errors.expiry = "Use MM / YY.";
  } else {
    const due = new Date(2000 + Number(expiry[2]), month, 0, 23, 59, 59);
    if (due.getTime() < Date.now()) errors.expiry = "This card has expired.";
  }

  if (!/^\d{3,4}$/.test(card.cvc)) errors.cvc = "3 or 4 digits.";
  return errors;
}

function CardField({
  label,
  error,
  children
}: {
  label: string;
  error?: string;
  children: (props: { id: string; "aria-invalid"?: true; "aria-describedby"?: string }) => React.ReactNode;
}) {
  const id = useId();
  return (
    <div className="hc-field">
      <label htmlFor={id}>{label}</label>
      {children(
        error
          ? { id, "aria-invalid": true, "aria-describedby": `${id}-error` }
          : { id }
      )}
      {error ? (
        <p className="hc-field-error" id={`${id}-error`}>
          <Icon name="alert" size={14} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function CardFields({
  value,
  onChange,
  errors
}: {
  value: CardDraft;
  onChange: (next: CardDraft) => void;
  errors?: CardErrors;
}) {
  const set = (key: keyof CardDraft, next: string) => onChange({ ...value, [key]: next });

  return (
    <div className="hc-form hc-card-fields">
      <CardField label="Card number" error={errors?.number}>
        {(props) => (
          <input
            {...props}
            className="hc-input"
            inputMode="numeric"
            autoComplete="cc-number"
            placeholder="1234 1234 1234 1234"
            value={value.number}
            onChange={(event) => set("number", formatCardNumber(event.target.value))}
          />
        )}
      </CardField>

      <CardField label="Name on card" error={errors?.name}>
        {(props) => (
          <input
            {...props}
            className="hc-input"
            autoComplete="cc-name"
            placeholder="As printed on the card"
            value={value.name}
            onChange={(event) => set("name", event.target.value)}
          />
        )}
      </CardField>

      <div className="hc-form-row">
        <CardField label="Expiry" error={errors?.expiry}>
          {(props) => (
            <input
              {...props}
              className="hc-input"
              inputMode="numeric"
              autoComplete="cc-exp"
              placeholder="MM / YY"
              value={value.expiry}
              onChange={(event) => set("expiry", formatExpiry(event.target.value))}
            />
          )}
        </CardField>

        <CardField label="Security code" error={errors?.cvc}>
          {(props) => (
            <input
              {...props}
              className="hc-input"
              inputMode="numeric"
              autoComplete="cc-csc"
              placeholder="CVC"
              value={value.cvc}
              onChange={(event) => set("cvc", event.target.value.replace(/\D/g, "").slice(0, 4))}
            />
          )}
        </CardField>
      </div>
    </div>
  );
}
