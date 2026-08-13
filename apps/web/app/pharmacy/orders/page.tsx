"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { OrderFulfillment, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

function tone(status: string) {
  if (status === "DELIVERED" || status === "COLLECTED" || status === "PICKED_UP") return "success" as const;
  if (status === "REJECTED" || status === "CANCELLED") return "danger" as const;
  if (status === "READY" || status === "ACCEPTED") return "warning" as const;
  return "info" as const;
}

export default function PharmacyOrdersPage() {
  const [orders, setOrders] = useState<OrderFulfillment[]>([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<Paginated<OrderFulfillment> | OrderFulfillment[]>(`/pharmacy/orders/${openOnly ? "?open=true" : ""}`)
      .then((payload) => setOrders(asList(payload)))
      .catch(() => setError("Could not load online orders."))
      .finally(() => setLoading(false));
  }, [openOnly]);

  useEffect(load, [load]);

  async function act(id: string, verb: string, body?: object, successMessage?: string) {
    setBusy(id + verb);
    setError("");
    setMessage("");
    try {
      await apiFetch(`/pharmacy/orders/${id}/${verb}/`, { method: "POST", body: JSON.stringify(body ?? {}) });
      setMessage(successMessage || "Done.");
      load();
    } catch (exception) {
      setError((exception as ApiError).message || "That action failed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Online orders</h1>
          <p className="muted">
            Stock is already held for each accepted order, so nothing here can be sold twice. It only leaves your
            shelf when you hand it over and an invoice is written.
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => setOpenOnly((current) => !current)}>
          {openOnly ? "Show all" : "Show open only"}
        </Button>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && orders.length === 0 ? <EmptyState title={openOnly ? "No open online orders." : "No online orders yet."} /> : null}

      {orders.map((order) => (
        <section className="panel" key={order.id}>
          <div className="section-header">
            <div>
              <h3>
                {order.order_reference} · {order.contact_name}
              </h3>
              <p className="muted small">
                {order.order_area} · {order.fulfillment_type === "PICKUP" ? "customer collects" : "delivery"}
                {order.scheduled_for ? ` · scheduled ${new Date(order.scheduled_for).toLocaleString()}` : " · as soon as possible"}
                {order.is_shared_order ? " · part of a multi-pharmacy order" : ""}
              </p>
            </div>
            <Badge tone={tone(order.status)}>{order.status.replace(/_/g, " ")}</Badge>
          </div>

          {order.is_shared_order ? (
            <Notice>
              This customer is also buying from another pharmacy. A single driver collects both parts, so prepare
              only your items below.
            </Notice>
          ) : null}

          <table className="table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>Line total</th>
              </tr>
            </thead>
            <tbody>
              {order.lines.map((line) => (
                <tr key={line.id}>
                  <td>
                    {line.medicine_detail?.display_name || line.medicine}
                    {line.is_price_regulated ? <span className="tag tag-regulated">MoPH price</span> : null}
                  </td>
                  <td>{line.quantity}</td>
                  <td>${line.unit_price}</td>
                  <td>${line.line_total}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="checkout-summary">
            <div>
              <span className="muted">Your subtotal</span>
              <strong className="price">${order.subtotal}</strong>
            </div>
            {order.status === "ACCEPTED" || order.status === "READY" ? (
              <div>
                <span className="muted">Handover code for the driver</span>
                <strong className="big-code">{order.handover_code}</strong>
              </div>
            ) : null}
          </div>

          <div className="actions">
            {order.status === "PENDING" ? (
              <>
                <Button type="button" onClick={() => act(order.id, "accept", {}, "Order accepted.")} disabled={busy === order.id + "accept"}>
                  Accept
                </Button>
                <Button
                  type="button"
                  variant="danger"
                  onClick={() => {
                    const reason = window.prompt("Why are you rejecting this order?") || "";
                    if (reason) act(order.id, "reject", { reason }, "Order rejected and stock released.");
                  }}
                >
                  Reject
                </Button>
              </>
            ) : null}

            {order.status === "ACCEPTED" ? (
              <Button type="button" onClick={() => act(order.id, "ready", {}, "Marked ready for pickup.")} disabled={busy === order.id + "ready"}>
                Mark ready
              </Button>
            ) : null}

            {(order.status === "ACCEPTED" || order.status === "READY") && order.fulfillment_type === "PICKUP" ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => act(order.id, "handover", { handover_code: order.handover_code, collected_in_store: true }, "Collected in store and invoiced.")}
              >
                Customer collected it
              </Button>
            ) : null}
          </div>

          {order.rejection_reason ? <Notice tone="danger">Rejected: {order.rejection_reason}</Notice> : null}
        </section>
      ))}
    </>
  );
}
