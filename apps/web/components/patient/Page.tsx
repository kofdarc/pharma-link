"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";

/**
 * The furniture every signed-in page shares: a title block, a filter bar, and
 * the loading and failure shapes that go with them.
 *
 * These exist so the eight new sections open the same way. A patient moving
 * from Prescriptions to Orders to Refills should feel the page change, not the
 * product.
 */

export function PageHead({
  title,
  lead,
  back,
  actions
}: {
  /** Omitted when the page already opens with its own headline. */
  title?: string;
  lead?: string;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
}) {
  return (
    <header className="hc-pagehead">
      {back ? (
        <Link href={back.href} className="hc-backlink">
          <Icon name="arrowLeft" size={15} />
          {back.label}
        </Link>
      ) : null}
      {title || actions ? (
        <div className="hc-pagehead-row">
          <div>
            {title ? <h1 className="hc-pagetitle">{title}</h1> : null}
            {lead ? <p className="hc-body hc-pagelead">{lead}</p> : null}
          </div>
          {actions ? <div className="hc-actions">{actions}</div> : null}
        </div>
      ) : null}
    </header>
  );
}

/**
 * Segmented filter, as a real tablist.
 *
 * Arrow keys move between tabs and only the selected one is in the tab order,
 * which is what a screen reader and a keyboard user expect from something that
 * looks like this.
 */
export function Segmented<T extends string>({
  label,
  value,
  onChange,
  options
}: {
  label: string;
  value: T;
  onChange: (next: T) => void;
  options: { value: T; label: string; count?: number }[];
}) {
  function onKeyDown(event: React.KeyboardEvent) {
    const index = options.findIndex((option) => option.value === value);
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const step = event.key === "ArrowRight" ? 1 : -1;
      onChange(options[(index + step + options.length) % options.length].value);
    }
  }

  return (
    <div className="hc-segmented" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className="hc-segment"
            onClick={() => onChange(option.value)}
          >
            {option.label}
            {typeof option.count === "number" ? <span className="hc-segment-count">{option.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/** Rows of card-shaped placeholders that match what is about to load. */
export function CardSkeletons({ count = 3, lines = 3 }: { count?: number; lines?: number }) {
  return (
    <div className="hc-stack" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div className="hc-card" key={index}>
          <div style={{ display: "grid", gap: 12 }}>
            <span className="hc-skel" style={{ width: `${38 + ((index * 11) % 20)}%`, height: 17 }} />
            <span className="hc-skel" style={{ width: "28%", height: 12 }} />
            <span className="hc-skel" style={{ height: 1, marginBlock: 4 }} />
            {Array.from({ length: lines }, (_, row) => (
              <span className="hc-skel" style={{ width: `${52 + ((row * 17) % 30)}%`, height: 12 }} key={row} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Failure, said in words a patient can act on.
 *
 * The underlying status code belongs in logs. What belongs here is what did not
 * load and what to press.
 */
export function LoadError({
  title,
  body,
  onRetry
}: {
  title: string;
  body?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="hc-state" role="alert">
      <span className="hc-state-icon hc-state-icon-alert">
        <Icon name="alert" size={22} />
      </span>
      <h2 className="hc-h3">{title}</h2>
      <p className="hc-body">{body ?? "The connection may have dropped. Nothing has changed on your account."}</p>
      {onRetry ? (
        <div className="hc-actions">
          <button type="button" className="hc-btn hc-btn-secondary" onClick={onRetry}>
            <Icon name="refresh" size={16} />
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyPanel({
  icon,
  title,
  body,
  children
}: {
  icon: IconName;
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="hc-state">
      <span className="hc-state-icon">
        <Icon name={icon} size={22} />
      </span>
      <h2 className="hc-h3">{title}</h2>
      <p className="hc-body">{body}</p>
      {children ? <div className="hc-actions">{children}</div> : null}
    </div>
  );
}

/** A labelled on/off preference. Used across notifications and refill settings. */
export function Toggle({
  id,
  label,
  hint,
  checked,
  onChange
}: {
  id: string;
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="hc-toggle-row">
      <label htmlFor={id}>
        <span className="hc-toggle-label">{label}</span>
        {hint ? <span className="hc-toggle-hint">{hint}</span> : null}
      </label>
      <input
        id={id}
        type="checkbox"
        role="switch"
        className="hc-switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
    </div>
  );
}
