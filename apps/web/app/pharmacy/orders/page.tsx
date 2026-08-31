"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { OrderFulfillment, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { ChatPanel } from "@/components/messaging/ChatPanel";

function tone(status: string) {
  if (status === "DELIVERED" || status === "COLLECTED" || status === "PICKED_UP") return "success" as const;
  if (status === "REJECTED" || status === "CANCELLED") return "danger" as const;
  if (status === "READY" || status === "ACCEPTED") return "warning" as const;
  return "info" as const;
}

export default function PharmacyOrdersPage() {
  const t = useTranslations();
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
      .catch(() => setError(t("pharmacyOrders.loadError")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openOnly]);

  useEffect(load, [load]);

  async function act(id: string, verb: string, body?: object, successMessage?: string) {
    setBusy(id + verb);
    setError("");
    setMessage("");
    try {
      await apiFetch(`/pharmacy/orders/${id}/${verb}/`, { method: "POST", body: JSON.stringify(body ?? {}) });
      setMessage(successMessage || t("pharmacyOrders.done"));
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyOrders.actionFailed"));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyOrders.title")}</h1>
          <p className="muted">{t("pharmacyOrders.subtitle")}</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => setOpenOnly((current) => !current)}>
          {openOnly ? t("pharmacyOrders.showAll") : t("pharmacyOrders.showOpenOnly")}
        </Button>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && orders.length === 0 ? (
        <EmptyState title={openOnly ? t("pharmacyOrders.noOpenOrders") : t("pharmacyOrders.noOrdersYet")} />
      ) : null}

      {orders.map((order) => (
        <section className="panel" key={order.id}>
          <div className="section-header">
            <div>
              <h3>
                {order.order_reference} · {order.contact_name}
              </h3>
              <p className="muted small">
                {order.order_area} · {order.fulfillment_type === "PICKUP" ? t("pharmacyOrders.customerCollects") : t("pharmacyOrders.delivery")}
                {order.scheduled_for
                  ? t("pharmacyOrders.scheduledFor", { when: new Date(order.scheduled_for).toLocaleString() })
                  : t("pharmacyOrders.asSoonAsPossible")}
                {order.is_shared_order ? t("pharmacyOrders.sharedOrderNote") : ""}
              </p>
            </div>
            <Badge status tone={tone(order.status)}>{order.status.replace(/_/g, " ")}</Badge>
          </div>

          {order.is_shared_order ? <Notice>{t("pharmacyOrders.sharedOrderNotice")}</Notice> : null}

          <table className="table">
            <thead>
              <tr>
                <th>{t("pharmacyOrders.item")}</th>
                <th>{t("pharmacyOrders.quantity")}</th>
                <th>{t("pharmacyOrders.unitPrice")}</th>
                <th>{t("pharmacyOrders.lineTotal")}</th>
              </tr>
            </thead>
            <tbody>
              {order.lines.map((line) => (
                <tr key={line.id}>
                  <td>{line.medicine_detail?.display_name || line.medicine}</td>
                  <td>{line.quantity}</td>
                  <td>${line.unit_price}</td>
                  <td>${line.line_total}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="checkout-summary">
            <div>
              <span className="muted">{t("pharmacyOrders.yourSubtotal")}</span>
              <strong className="price">${order.subtotal}</strong>
            </div>
            {order.status === "ACCEPTED" || order.status === "READY" ? (
              <div>
                <span className="muted">{t("pharmacyOrders.handoverCode")}</span>
                <strong className="big-code">{order.handover_code}</strong>
              </div>
            ) : null}
          </div>

          <div className="actions">
            {order.status === "PENDING" ? (
              <>
                <Button
                  type="button"
                  onClick={() => act(order.id, "accept", {}, t("pharmacyOrders.acceptedMessage"))}
                  disabled={busy === order.id + "accept"}
                >
                  {t("pharmacyOrders.accept")}
                </Button>
                <Button
                  type="button"
                  variant="danger"
                  onClick={() => {
                    const reason = window.prompt(t("pharmacyOrders.rejectPrompt")) || "";
                    if (reason) act(order.id, "reject", { reason }, t("pharmacyOrders.rejectedMessage"));
                  }}
                >
                  {t("pharmacyOrders.reject")}
                </Button>
              </>
            ) : null}

            {order.status === "ACCEPTED" ? (
              <Button type="button" onClick={() => act(order.id, "ready", {}, t("pharmacyOrders.readyMessage"))} disabled={busy === order.id + "ready"}>
                {t("pharmacyOrders.markReady")}
              </Button>
            ) : null}

            {(order.status === "ACCEPTED" || order.status === "READY") && order.fulfillment_type === "PICKUP" ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() =>
                  act(order.id, "handover", { handover_code: order.handover_code, collected_in_store: true }, t("pharmacyOrders.collectedMessage"))
                }
              >
                {t("pharmacyOrders.customerCollectedIt")}
              </Button>
            ) : null}
          </div>

          {order.rejection_reason ? (
            <Notice tone="danger">{t("pharmacyOrders.rejectedLabel", { reason: order.rejection_reason })}</Notice>
          ) : null}

          <ChatPanel basePath="/pharmacy/order-fulfillments" orderFulfillmentId={order.id} />
        </section>
      ))}
    </>
  );
}
