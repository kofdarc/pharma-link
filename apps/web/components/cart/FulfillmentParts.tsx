"use client";

import { useId, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { formatMoney, plural } from "@/lib/patient/format";
import { byPharmacy, type FulfillmentPlan } from "@/lib/patient/fulfillment";

/**
 * One way the basket could be filled.
 *
 * The card leads with the outcome (how long, how much) and keeps the pharmacy
 * split folded away underneath. That order is the whole point of this screen:
 * the patient is choosing a delivery, not shopping between pharmacies, and a
 * layout that opens with two pharmacy profiles turns a solved problem back into
 * the patient's problem.
 */
export function FulfillmentOption({
  plan,
  recommended,
  selected,
  onSelect,
  name
}: {
  plan: FulfillmentPlan;
  recommended: boolean;
  selected: boolean;
  onSelect: () => void;
  name: string;
}) {
  const [openBreakdown, setOpenBreakdown] = useState(false);
  const id = useId();

  return (
    <div className={`hc-plan${selected ? " hc-plan-selected" : ""}`}>
      <label className="hc-plan-choice" htmlFor={id}>
        <input
          id={id}
          type="radio"
          name={name}
          checked={selected}
          onChange={onSelect}
          className="hc-plan-radio"
        />
        <span className="hc-plan-mark" aria-hidden="true" />

        <span className="hc-plan-body">
          <span className="hc-plan-top">
            <span className="hc-plan-title">
              {recommended ? <span className="hc-chip hc-chip-rx hc-plan-flag">Recommended</span> : null}
              <strong>{plan.label}</strong>
            </span>
            <span className="hc-plan-total hc-num">{formatMoney(plan.total)}</span>
          </span>

          <span className="hc-plan-tagline">{plan.tagline}</span>

          <span className="hc-plan-facts">
            <span>
              <Icon name="clock" size={15} />
              {plan.etaLabel}
            </span>
            <span>
              <Icon name="pharmacy" size={15} />
              {plural(plan.pharmacies.length, "pharmacy", "pharmacies")}
            </span>
            <span>
              <Icon name="truck" size={15} />
              One delivery
            </span>
          </span>
        </span>
      </label>

      <dl className="hc-plan-costs">
        <div>
          <dt>Medications</dt>
          <dd className="hc-num">{formatMoney(plan.medicationTotal)}</dd>
        </div>
        <div>
          <dt>Delivery</dt>
          <dd className="hc-num">{formatMoney(plan.deliveryFee)}</dd>
        </div>
      </dl>

      <div className="hc-plan-breakdown">
        <button
          type="button"
          className="hc-disclosure"
          aria-expanded={openBreakdown}
          onClick={() => setOpenBreakdown((value) => !value)}
        >
          <Icon name="chevronDown" size={15} className={openBreakdown ? "hc-disclosure-open" : undefined} />
          Which pharmacy supplies what
        </button>

        {openBreakdown ? <FulfillmentBreakdown plan={plan} /> : null}
      </div>
    </div>
  );
}

/** Supporting detail, in the smallest form that still answers the question. */
export function FulfillmentBreakdown({ plan }: { plan: FulfillmentPlan }) {
  return (
    <div className="hc-split">
      {byPharmacy(plan).map((group) => (
        <div className="hc-split-group" key={group.pharmacy}>
          <p className="hc-split-name">{group.pharmacy}</p>
          <ul>
            {group.lines.map((line) => (
              <li key={line.medicineId}>
                <Icon name="pill" size={14} />
                {line.name}
                {line.quantity > 1 ? <span className="hc-num"> x {line.quantity}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/**
 * The question this screen creates: why is more than one pharmacy involved?
 *
 * Answered in two sentences, closed by default. Explaining sourcing at length
 * would make a solved problem look like a complication.
 */
export function WhyMultiplePharmacies() {
  const [open, setOpen] = useState(false);
  return (
    <div className="hc-why">
      <button type="button" className="hc-disclosure" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <Icon name="help" size={16} className={open ? "hc-disclosure-open" : undefined} />
        Why more than one pharmacy?
      </button>
      {open ? (
        <p className="hc-body hc-why-body">
          One pharmacy will not always have every item in your basket at the same time. HealthConnect can combine several
          into a single order, so the pickups are coordinated for you and everything arrives together.
        </p>
      ) : null}
    </div>
  );
}
