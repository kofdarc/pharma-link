"use client";

import { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { Icon } from "@/components/ui/Icon";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The one dialog for the patient area.
 *
 * A centred panel on desktop and a bottom sheet under 640px, because the same
 * content (prescription access, an address form, a review) wants thumb reach on
 * a phone and a calm centred card on a laptop. One component rather than two so
 * the focus handling only has to be right once.
 *
 * Focus is trapped while it is open, Escape closes, the trigger gets focus back
 * on close, and the page behind cannot scroll.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md"
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  const panel = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  const close = useCallback(() => onClose(), [onClose]);

  useEffect(() => {
    if (!open) return;

    restoreTo.current = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    // Focus the panel itself rather than the first control: a dialog that opens
    // with the destructive button already focused is an accident waiting.
    panel.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        close();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;

      const targets = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (node) => node.offsetParent !== null
      );
      if (targets.length === 0) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && (active === first || active === panel.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = overflow;
      restoreTo.current?.focus();
    };
  }, [open, close]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="hc-modal">
      <button type="button" className="hc-sheet-backdrop" aria-label="Close" onClick={close} tabIndex={-1} />
      <div
        ref={panel}
        className={`hc-modal-panel hc-modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <span className="hc-sheet-grip" aria-hidden="true" />
        <div className="hc-modal-head">
          <div>
            <h2 className="hc-h3" id={titleId}>
              {title}
            </h2>
            {description ? (
              <p className="hc-small" id={descriptionId} style={{ marginTop: 5 }}>
                {description}
              </p>
            ) : null}
          </div>
          <button type="button" className="hc-icon-btn" onClick={close} aria-label="Close">
            <Icon name="close" size={17} />
          </button>
        </div>

        <div className="hc-modal-body">{children}</div>

        {footer ? <div className="hc-modal-foot">{footer}</div> : null}
      </div>
    </div>,
    document.body
  );
}

/**
 * Confirmation for anything that cannot be undone with one click.
 *
 * `consequence` is where the screen explains what breaks, not just what
 * disappears: deleting an address that a refill delivers to is a different
 * decision from deleting a spare one.
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  body,
  consequence,
  confirmLabel,
  tone = "default"
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  body: string;
  consequence?: string;
  confirmLabel: string;
  tone?: "default" | "danger";
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <button type="button" className="hc-btn hc-btn-secondary" onClick={onClose}>
            Keep it
          </button>
          <button
            type="button"
            className={`hc-btn ${tone === "danger" ? "hc-btn-danger" : "hc-btn-primary"}`}
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="hc-body">{body}</p>
      {consequence ? (
        <p className="hc-inline-note hc-inline-note-warn" style={{ marginTop: 14 }}>
          <Icon name="alert" size={16} />
          {consequence}
        </p>
      ) : null}
    </Dialog>
  );
}
