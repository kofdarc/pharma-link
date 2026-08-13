"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { ORDER_STATUS_LABELS } from "@/lib/constants";
import type { Order, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

function orderTone(status: string) {
  if (status === "DELIVERED" || status === "COLLECTED") return "success" as const;
  if (status === "CANCELLED") return "danger" as const;
  if (status === "IN_TRANSIT" || status === "READY" || status === "ASSIGNED") return "warning" as const;
  return "info" as const;
}

const PAYMENT_STATUS_LABELS: Record<string, string> = {
  PENDING: "Cash on delivery",
  PAID: "Paid",
  FAILED: "Payment failed",
  REFUNDED: "Refunded"
};

function paymentTone(status: string) {
  if (status === "PAID") return "success" as const;
  if (status === "FAILED") return "danger" as const;
  return "info" as const;
}

function OrdersView() {
  const params = useSearchParams();
  const highlight = params.get("highlight");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reviewFor, setReviewFor] = useState<{ order: string; pharmacy: string; name: string } | null>(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  const load = useCallback(() => {
    apiFetch<Paginated<Order> | Order[]>("/shop/orders/")
      .then((payload) => setOrders(asList(payload)))
      .catch(() => setError("Could not load your orders."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  async function payNow(order: Order) {
    try {
      await apiFetch(`/shop/orders/${order.id}/pay/`, { method: "POST" });
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  async function cancel(order: Order) {
    try {
      await apiFetch(`/shop/orders/${order.id}/cancel/`, { method: "POST", body: JSON.stringify({ reason: "Cancelled by customer" }) });
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  async function submitReview() {
    if (!reviewFor) return;
    try {
      await apiFetch(`/shop/orders/${reviewFor.order}/review/`, {
        method: "POST",
        body: JSON.stringify({ pharmacy: reviewFor.pharmacy, rating, comment })
      });
      setReviewFor(null);
      setComment("");
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  return (
    <>
      <h1>My orders</h1>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {highlight ? <Notice tone="success">Order {highlight} placed. The pharmacies have been notified.</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && orders.length === 0 ? <EmptyState title="No orders yet." /> : null}

      {orders.map((order) => {
        const cancellable = !["DELIVERED", "COLLECTED", "CANCELLED", "IN_TRANSIT"].includes(order.status);
        const reviewable = ["DELIVERED", "COLLECTED", "PARTIALLY_CANCELLED"].includes(order.status);
        return (
          <section className={`panel ${highlight === order.reference ? "panel-highlight" : ""}`} key={order.id}>
            <div className="section-header">
              <div>
                <h3>{order.reference}</h3>
                <p className="muted small">
                  Placed {new Date(order.created_at).toLocaleString()} ·{" "}
                  {order.fulfillment_type === "PICKUP" ? "Store collection" : "Delivery"}
                  {order.scheduled_for ? ` · scheduled for ${new Date(order.scheduled_for).toLocaleString()}` : ""}
                  {order.source === "RECURRING" ? " · from a repeat schedule" : ""}
                </p>
              </div>
              <Badge tone={orderTone(order.status)}>{ORDER_STATUS_LABELS[order.status] || order.status}</Badge>
            </div>

            {order.fulfillments.length > 1 ? (
              <p className="muted small">
                Sourced from {order.fulfillments.length} pharmacies and delivered together in one trip.
              </p>
            ) : null}

            {order.fulfillments.map((fulfillment) => (
              <div key={fulfillment.id} className="allocation-card">
                <div className="section-header">
                  <div>
                    <strong>{fulfillment.pharmacy_name}</strong>
                    <p className="muted small">
                      {fulfillment.pharmacy_area} · {fulfillment.status.replace(/_/g, " ").toLowerCase()}
                      {fulfillment.rejection_reason ? ` — ${fulfillment.rejection_reason}` : ""}
                    </p>
                  </div>
                  <strong>${fulfillment.subtotal}</strong>
                </div>
                <ul className="clean-list">
                  {fulfillment.lines.map((line) => (
                    <li key={line.id}>
                      {line.quantity} × {line.medicine_detail?.display_name || line.medicine} — ${line.line_total}
                      {line.is_price_regulated ? <span className="tag tag-regulated">MoPH price</span> : null}
                    </li>
                  ))}
                </ul>
                {reviewable && fulfillment.status !== "REJECTED" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setReviewFor({ order: order.id, pharmacy: fulfillment.pharmacy, name: fulfillment.pharmacy_name })}
                  >
                    Rate {fulfillment.pharmacy_name}
                  </Button>
                ) : null}
              </div>
            ))}

            <div className="checkout-summary">
              <div>
                <span className="muted">Items</span>
                <strong>${order.items_subtotal}</strong>
              </div>
              <div>
                <span className="muted">Delivery</span>
                <strong>${order.delivery_fee}</strong>
              </div>
              <div>
                <span className="muted">Total</span>
                <strong className="price">${order.total}</strong>
              </div>
              {order.payment ? (
                <div>
                  <span className="muted">Payment</span>
                  <Badge tone={paymentTone(order.payment.status)}>
                    {PAYMENT_STATUS_LABELS[order.payment.status] || order.payment.status}
                  </Badge>
                </div>
              ) : null}
              {order.payment && order.payment.provider !== "COD" && order.payment.status === "FAILED" ? (
                <Button type="button" onClick={() => payNow(order)}>
                  Retry payment
                </Button>
              ) : null}
              {cancellable ? (
                <Button type="button" variant="danger" onClick={() => cancel(order)}>
                  Cancel order
                </Button>
              ) : null}
            </div>
          </section>
        );
      })}

      {reviewFor ? (
        <section className="panel">
          <h3>Rate {reviewFor.name}</h3>
          <p className="muted small">Your rating feeds directly into how we rank pharmacies for other shoppers.</p>
          <div className="form-grid">
            <Field label="Rating">
              <select value={rating} onChange={(event) => setRating(Number(event.target.value))}>
                {[5, 4, 3, 2, 1].map((value) => (
                  <option key={value} value={value}>
                    {"★".repeat(value)} ({value})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Comment (optional)">
              <input value={comment} onChange={(event) => setComment(event.target.value)} />
            </Field>
          </div>
          <div className="actions">
            <Button type="button" onClick={submitReview}>
              Submit rating
            </Button>
            <Button type="button" variant="secondary" onClick={() => setReviewFor(null)}>
              Cancel
            </Button>
          </div>
        </section>
      ) : null}
    </>
  );
}

export default function ShopOrdersPage() {
  return (
    <Suspense fallback={<div className="skeleton-card" />}>
      <OrdersView />
    </Suspense>
  );
}
