"use client";

import { useState } from "react";
import Link from "next/link";
import { Dialog } from "@/components/patient/Dialog";
import { Icon, type IconName } from "@/components/ui/Icon";
import { formatDate, formatMoney, plural } from "@/lib/patient/format";
import { ORDER_STAGES, orderPharmacies, orderTotal, type Order, type OrderStage } from "@/lib/patient/types";

/**
 * Orders, built around one question: where is my medication.
 *
 * Status therefore outranks price everywhere in this section. On an active
 * order the stage and the arrival window are the largest things on the card;
 * the amount is a detail the patient already agreed to.
 */

const STAGE_COPY: Record<OrderStage, { label: string; chip: string; icon: IconName }> = {
  confirmed: { label: "Confirmed", chip: "hc-chip-rx", icon: "check" },
  preparing: { label: "Pharmacy preparing", chip: "hc-chip-rx", icon: "pharmacy" },
  collecting: { label: "Driver collecting", chip: "hc-chip-limited", icon: "box" },
  transit: { label: "Out for delivery", chip: "hc-chip-limited", icon: "truck" },
  delivered: { label: "Delivered", chip: "hc-chip-ok", icon: "checkCircle" }
};

export function OrderStatusChip({ stage }: { stage: OrderStage }) {
  const { label, chip, icon } = STAGE_COPY[stage];
  return (
    <span className={`hc-chip ${chip}`}>
      <Icon name={icon} size={13} strokeWidth={2.1} />
      {label}
    </span>
  );
}

/** The stage icon, tinted, for use beside a headline that already names it. */
export function OrderStatusMark({ stage }: { stage: OrderStage }) {
  const { chip, icon } = STAGE_COPY[stage];
  return (
    <span className={`hc-stagemark ${chip}`} aria-hidden="true">
      <Icon name={icon} size={15} strokeWidth={2.1} />
    </span>
  );
}

export function stageLabel(stage: OrderStage): string {
  return STAGE_COPY[stage].label;
}

export function OrderCard({ order }: { order: Order }) {
  const pharmacies = orderPharmacies(order);
  const medicationCount = order.lines.reduce((sum, line) => sum + line.quantity, 0);
  const delivered = order.stage === "delivered";

  return (
    <article className={`hc-card hc-ordercard${delivered ? "" : " hc-ordercard-active"}`}>
      {/* The stage is the headline, so it does not also need a chip repeating
          it beside itself. The tinted mark keeps icon, word and colour together
          without saying the same thing twice. */}
      <p className="hc-card-label hc-num">{order.id}</p>
      <h2 className="hc-h3 hc-ordercard-title">
        <OrderStatusMark stage={order.stage} />
        {stageLabel(order.stage)}
      </h2>

      <dl className="hc-kv">
        <div>
          <dt>Medications</dt>
          <dd>{plural(medicationCount, "item")}</dd>
        </div>
        {pharmacies.length > 1 ? (
          <div>
            <dt>Filled by</dt>
            <dd>{plural(pharmacies.length, "pharmacy", "pharmacies")}</dd>
          </div>
        ) : null}
        {delivered ? (
          <>
            <div>
              <dt>Delivered</dt>
              <dd>{formatDate(order.placedAt)}</dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd className="hc-num">{formatMoney(orderTotal(order))}</dd>
            </div>
          </>
        ) : (
          <div>
            <dt>{order.scheduled ? "Delivery window" : "Estimated arrival"}</dt>
            <dd>{order.arrivalWindow}</dd>
          </div>
        )}
      </dl>

      <div className="hc-rxcard-actions">
        <Link
          href={`/orders/${order.id}`}
          className={`hc-btn hc-btn-sm ${delivered ? "hc-btn-secondary" : "hc-btn-primary"}`}
        >
          {delivered ? "View order" : "Track order"}
        </Link>
        {delivered ? (
          /**
           * Reordering routes back through the basket rather than repeating the
           * order outright. Prescription cover has to be checked again, and the
           * previous order is not evidence that it still holds.
           */
          <Link href={`/orders/${order.id}?again=1`} className="hc-btn hc-btn-quiet hc-btn-sm">
            Order again
          </Link>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Delivery progress.
 *
 * Five stages, whatever the order's shape. When several pharmacies are
 * involved, their individual pickups collapse into one "collecting" step:
 * a patient tracking a delivery does not need a per-counter event log, and
 * showing one would make a coordinated order look like several.
 */
export function OrderStatusTimeline({ order }: { order: Order }) {
  const currentIndex = ORDER_STAGES.findIndex((entry) => entry.stage === order.stage);

  return (
    <ol className="hc-track hc-track-lg">
      {ORDER_STAGES.map((entry, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "todo";
        const at = order.reachedAt[entry.stage];
        return (
          <li key={entry.stage} data-state={state}>
            <span className="hc-track-mark">
              {state === "done" ? <Icon name="check" size={12} strokeWidth={2.6} /> : null}
              {state === "current" ? <span className="hc-track-dot" /> : null}
            </span>
            {entry.label}
            {at ? <span className="hc-track-time hc-num">{at}</span> : null}
            {state === "current" && !at ? <span className="hc-track-time">In progress</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * One rating for the delivery as a whole.
 *
 * Asking a patient to score the platform, two pharmacies and a driver
 * separately would make feedback a chore and produce worse data than one
 * honest answer.
 */
export function ReviewDialog({
  open,
  onClose,
  onSubmit,
  orderId
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (rating: number, comment: string) => void;
  orderId: string;
}) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="How was your order?"
      description={`Order ${orderId}`}
      size="sm"
      footer={
        <>
          <button type="button" className="hc-btn hc-btn-secondary" onClick={onClose}>
            Not now
          </button>
          <button
            type="button"
            className="hc-btn hc-btn-primary"
            disabled={rating === 0}
            onClick={() => {
              onSubmit(rating, comment.trim());
              onClose();
            }}
          >
            Send feedback
          </button>
        </>
      }
    >
      <div className="hc-rate" role="radiogroup" aria-label="Rating out of five">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={rating === value}
            aria-label={`${value} out of 5`}
            className={`hc-rate-star${value <= rating ? " hc-rate-on" : ""}`}
            onClick={() => setRating(value)}
          >
            <Icon name="star" size={26} strokeWidth={1.5} />
          </button>
        ))}
      </div>

      <div className="hc-field" style={{ marginTop: 18 }}>
        <label htmlFor="review-comment">
          Comment
          <span className="hc-field-hint"> (optional)</span>
        </label>
        <textarea
          id="review-comment"
          className="hc-input hc-textarea"
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          placeholder="Anything you would want us to know."
        />
      </div>
    </Dialog>
  );
}

export function ReceiptDialog({ open, onClose, order }: { open: boolean; onClose: () => void; order: Order }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Receipt"
      description={`Order ${order.id} · ${formatDate(order.placedAt)}`}
      footer={
        <button type="button" className="hc-btn hc-btn-secondary hc-btn-block" onClick={onClose}>
          Close
        </button>
      }
    >
      <ul className="hc-receipt">
        {order.lines.map((line) => (
          <li key={line.medicineId}>
            <span>
              {line.name}
              {line.quantity > 1 ? <span className="hc-num"> x {line.quantity}</span> : null}
            </span>
            <span className="hc-num">{formatMoney(line.unitPrice * line.quantity)}</span>
          </li>
        ))}
      </ul>

      <dl className="hc-summary-rows">
        <div>
          <dt>Medication subtotal</dt>
          <dd className="hc-num">{formatMoney(order.medicationTotal)}</dd>
        </div>
        <div>
          <dt>Delivery</dt>
          <dd className="hc-num">{formatMoney(order.deliveryFee)}</dd>
        </div>
        <div>
          <dt>Paid with</dt>
          <dd>{order.paymentLabel}</dd>
        </div>
      </dl>

      <div className="hc-summary-total">
        <span>Total</span>
        <strong className="hc-num">{formatMoney(orderTotal(order))}</strong>
      </div>
    </Dialog>
  );
}
