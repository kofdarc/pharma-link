"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";
import type { Address, PaymentMethod } from "@/lib/patient/types";

/**
 * Settings, as a list rather than a wall of cards.
 *
 * Every account screen in every app is the same shape, and patients already
 * know it: grouped rows, a label, a value, a chevron. Wrapping each row in its
 * own elevated card would make a familiar surface feel unfamiliar for no gain.
 */

export function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="hc-settings-group" aria-label={title}>
      <h2 className="hc-section-label">{title}</h2>
      <ul className="hc-settings-list">{children}</ul>
    </section>
  );
}

export function SettingsRow({
  href,
  icon,
  label,
  value,
  onClick,
  tone = "default"
}: {
  href?: string;
  icon: IconName;
  label: string;
  value?: string;
  onClick?: () => void;
  tone?: "default" | "danger";
}) {
  const inner = (
    <>
      <span className="hc-settings-icon" aria-hidden="true">
        <Icon name={icon} size={17} />
      </span>
      <span className="hc-settings-label">{label}</span>
      {value ? <span className="hc-settings-value">{value}</span> : null}
      {href ? <Icon name="chevronRight" size={16} className="hc-settings-chevron" /> : null}
    </>
  );

  return (
    <li className={tone === "danger" ? "hc-settings-danger" : undefined}>
      {href ? (
        <Link href={href} className="hc-settings-row">
          {inner}
        </Link>
      ) : (
        <button type="button" className="hc-settings-row" onClick={onClick}>
          {inner}
        </button>
      )}
    </li>
  );
}

export function AddressCard({
  address,
  onEdit,
  onDelete,
  onSetDefault
}: {
  address: Address;
  onEdit: () => void;
  onDelete: () => void;
  onSetDefault: () => void;
}) {
  return (
    <article className="hc-card hc-addresscard">
      <div className="hc-card-head">
        <div>
          <h3 className="hc-h3">{address.label}</h3>
          <p className="hc-small">
            {address.line1}
            {address.building ? `, ${address.building}` : ""}
          </p>
          <p className="hc-small">
            {address.area}, {address.city}
          </p>
          {address.notes ? <p className="hc-small hc-addresscard-note">{address.notes}</p> : null}
        </div>
        {address.isDefault ? (
          <span className="hc-chip hc-chip-ok">
            <Icon name="check" size={13} strokeWidth={2.1} />
            Default
          </span>
        ) : null}
      </div>

      <div className="hc-rxcard-actions">
        <button type="button" className="hc-btn hc-btn-secondary hc-btn-sm" onClick={onEdit}>
          <Icon name="pencil" size={15} />
          Edit
        </button>
        {!address.isDefault ? (
          <button type="button" className="hc-btn hc-btn-quiet hc-btn-sm" onClick={onSetDefault}>
            Set as default
          </button>
        ) : null}
        <button type="button" className="hc-linkbtn hc-linkbtn-danger hc-addresscard-delete" onClick={onDelete}>
          Delete
        </button>
      </div>
    </article>
  );
}

/**
 * A saved payment method.
 *
 * Four digits and an expiry, which is all the UI ever needs and all the demo
 * ever holds. There is no card number anywhere in this codebase.
 */
export function PaymentMethodCard({
  method,
  onSetDefault,
  onRemove
}: {
  method: PaymentMethod;
  onSetDefault: () => void;
  onRemove: () => void;
}) {
  return (
    <article className="hc-card hc-paycard">
      <span className="hc-paycard-icon" aria-hidden="true">
        <Icon name={method.kind === "card" ? "card" : "receipt"} size={19} />
      </span>

      <div className="hc-paycard-body">
        <h3 className="hc-h3">{method.kind === "card" ? method.brand : "Cash on delivery"}</h3>
        {method.kind === "card" ? (
          <>
            <p className="hc-small hc-num">Ending {method.last4}</p>
            <p className="hc-small">Expires {method.expiry}</p>
          </>
        ) : (
          <p className="hc-small">Pay the driver when your order arrives.</p>
        )}
      </div>

      <div className="hc-paycard-side">
        {method.isDefault ? (
          <span className="hc-chip hc-chip-ok">
            <Icon name="check" size={13} strokeWidth={2.1} />
            Default
          </span>
        ) : (
          <button type="button" className="hc-btn hc-btn-quiet hc-btn-sm" onClick={onSetDefault}>
            Set as default
          </button>
        )}
        {method.kind === "card" ? (
          <button type="button" className="hc-linkbtn hc-linkbtn-danger" onClick={onRemove}>
            Remove
          </button>
        ) : null}
      </div>
    </article>
  );
}
