"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { ORDER_STATUS_LABELS } from "@/lib/constants";
import { useTranslations } from "@/lib/i18n/context";
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

function paymentTone(status: string) {
  if (status === "PAID") return "success" as const;
  if (status === "FAILED") return "danger" as const;
  return "info" as const;
}

function OrdersView() {
  const params = useSearchParams();
  const t = useTranslations();
  const highlight = params.get("highlight");
  const recurringFailed = params.get("recurringFailed") === "1";
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reviewFor, setReviewFor] = useState<{ order: string; pharmacy: string; name: string } | null>(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  const load = useCallback(() => {
    apiFetch<Paginated<Order> | Order[]>("/shop/orders/")
      .then((payload) => setOrders(asList(payload)))
      .catch(() => setError(t("orders.loadError")))
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
      <h1>{t("orders.title")}</h1>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {highlight ? <Notice tone="success">{t("orders.placedNotice", { reference: highlight })}</Notice> : null}
      {recurringFailed ? (
        <Notice tone="danger">
          {t("orders.recurringFailedNotice")} <Link href="/shop/refills">{t("orders.refills")}</Link>.
        </Notice>
      ) : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && orders.length === 0 ? <EmptyState title={t("orders.noOrders")} /> : null}

      {orders.map((order) => {
        const cancellable = !["DELIVERED", "COLLECTED", "CANCELLED", "IN_TRANSIT"].includes(order.status);
        const reviewable = ["DELIVERED", "COLLECTED", "PARTIALLY_CANCELLED"].includes(order.status);
        return (
          <section className={`panel ${highlight === order.reference ? "panel-highlight" : ""}`} key={order.id}>
            <div className="section-header">
              <div>
                <h3>{order.reference}</h3>
                <p className="muted small">
                  {t("orders.placed", {
                    when: new Date(order.created_at).toLocaleString(),
                    type: order.fulfillment_type === "PICKUP" ? t("orders.storeCollection") : t("orders.delivery")
                  })}
                  {order.scheduled_for ? ` · ${t("orders.scheduledFor", { when: new Date(order.scheduled_for).toLocaleString() })}` : ""}
                  {order.source === "RECURRING" ? ` · ${t("orders.fromRepeatSchedule")}` : ""}
                </p>
              </div>
              <Badge tone={orderTone(order.status)}>{ORDER_STATUS_LABELS[order.status] || order.status}</Badge>
            </div>

            {order.fulfillments.length > 1 ? (
              <p className="muted small">{t("orders.sourcedFrom", { count: order.fulfillments.length })}</p>
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
                      {line.is_price_regulated ? <span className="tag tag-regulated">{t("orders.mophPrice")}</span> : null}
                    </li>
                  ))}
                </ul>
                {reviewable && fulfillment.status !== "REJECTED" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setReviewFor({ order: order.id, pharmacy: fulfillment.pharmacy, name: fulfillment.pharmacy_name })}
                  >
                    {t("orders.rate", { pharmacy: fulfillment.pharmacy_name })}
                  </Button>
                ) : null}
              </div>
            ))}

            <div className="checkout-summary">
              <div>
                <span className="muted">{t("orders.items")}</span>
                <strong>${order.items_subtotal}</strong>
              </div>
              <div>
                <span className="muted">{t("orders.delivery2")}</span>
                <strong>${order.delivery_fee}</strong>
              </div>
              <div>
                <span className="muted">{t("orders.total")}</span>
                <strong className="price">${order.total}</strong>
              </div>
              {order.payment ? (
                <div>
                  <span className="muted">{t("orders.payment")}</span>
                  <Badge tone={paymentTone(order.payment.status)}>{t(`orders.paymentStatus.${order.payment.status}`)}</Badge>
                </div>
              ) : null}
              {order.payment && order.payment.provider !== "COD" && order.payment.status === "FAILED" ? (
                <Button type="button" onClick={() => payNow(order)}>
                  {t("orders.retryPayment")}
                </Button>
              ) : null}
              {cancellable ? (
                <Button type="button" variant="danger" onClick={() => cancel(order)}>
                  {t("orders.cancelOrder")}
                </Button>
              ) : null}
            </div>
          </section>
        );
      })}

      {reviewFor ? (
        <section className="panel">
          <h3>{t("orders.rateTitle", { pharmacy: reviewFor.name })}</h3>
          <p className="muted small">{t("orders.rateHint")}</p>
          <div className="form-grid">
            <Field label={t("orders.rating")}>
              <select value={rating} onChange={(event) => setRating(Number(event.target.value))}>
                {[5, 4, 3, 2, 1].map((value) => (
                  <option key={value} value={value}>
                    {"★".repeat(value)} ({value})
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("orders.comment")}>
              <input value={comment} onChange={(event) => setComment(event.target.value)} />
            </Field>
          </div>
          <div className="actions">
            <Button type="button" onClick={submitReview}>
              {t("orders.submitRating")}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setReviewFor(null)}>
              {t("common.cancel")}
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
