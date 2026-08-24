"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { OrderStatusChip, OrderStatusTimeline, ReceiptDialog, ReviewDialog, stageLabel } from "@/components/orders/OrderParts";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useCurrentUser } from "@/lib/auth";
import { useBasket } from "@/lib/basket";
import { useOrders } from "@/lib/patient/store";
import { MOCK_PROFILE } from "@/lib/patient/mock-patient";
import { formatDate, formatMoney, plural } from "@/lib/patient/format";
import { orderPharmacies, orderTotal, type Order } from "@/lib/patient/types";
import { MOCK_CATALOG } from "@/lib/catalog/mock-catalog";

/**
 * A single order.
 *
 * Structured to answer "where is my medication" in the first screenful:
 * the stage, the window, and the timeline. Everything else, what is in it,
 * which pharmacies filled it, what it cost, is supporting material and sits
 * below or to the side.
 */
function OrderDetailScreen() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === "string" ? decodeURIComponent(params.id) : "";
  const router = useRouter();
  const search = useSearchParams();
  const { user } = useCurrentUser();
  const { orders, ready, reviewOrder } = useOrders();
  const basket = useBasket();
  const { notify } = useToast();

  const [reviewOpen, setReviewOpen] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);

  const order = orders.find((entry) => entry.id === id);
  const initials = initialsFor(user?.first_name ?? MOCK_PROFILE.firstName, user?.last_name);

  /**
   * "Order again" refills the basket and sends the patient through the normal
   * flow. Prescription cover is intentionally not carried over: the cart
   * rematches against what is valid today, because a prescription that covered
   * an order in June may not cover one now.
   */
  useEffect(() => {
    if (!ready || !order || search.get("again") !== "1") return;
    for (const line of order.lines) {
      const listing = MOCK_CATALOG.find((entry) => entry.id === line.medicineId);
      basket.add({
        medicine: line.medicineId,
        name: line.name,
        generic: line.generic,
        quantity: line.quantity,
        requires_prescription: Boolean(listing?.requiresPrescription),
        unit_price: listing?.fromPrice ?? null,
        prescription_id: null
      });
    }
    notify("Added to your basket for a new order");
    router.replace("/cart");
    // Runs once for a given order when the flag is present.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, order?.id, search]);

  if (!ready) {
    return (
      <PatientShell initials={initials}>
        <div className="hc-wrap hc-page">
          <CardSkeletons count={2} lines={5} />
        </div>
      </PatientShell>
    );
  }

  if (!order) {
    return (
      <PatientShell initials={initials}>
        <div className="hc-wrap hc-page">
          <PageHead title="Order" back={{ href: "/orders", label: "Orders" }} />
          <EmptyPanel
            icon="search"
            title="We could not load that order"
            body="The link may be out of date, or the order may belong to another account."
          >
            <Link href="/orders" className="hc-btn hc-btn-primary">
              Back to orders
            </Link>
          </EmptyPanel>
        </div>
      </PatientShell>
    );
  }

  const delivered = order.stage === "delivered";
  const pharmacies = orderPharmacies(order);

  return (
    <PatientShell initials={initials}>
      <div className="hc-wrap hc-page">
        <PageHead title={`Order ${order.id}`} back={{ href: "/orders", label: "Orders" }} />

        <div className="hc-order">
          <div className="hc-order-main">
            <section className="hc-card hc-order-status">
              <div className="hc-card-head">
                <div>
                  <h2 className="hc-order-stage">{delivered ? "Delivered" : stageLabel(order.stage)}</h2>
                  <p className="hc-order-when">
                    {delivered
                      ? `${formatDate(order.placedAt)} · ${order.deliveredAt}`
                      : `${order.scheduled ? "Delivery window" : "Estimated arrival"} ${order.arrivalWindow}`}
                  </p>
                </div>
                <OrderStatusChip stage={order.stage} />
              </div>

              <OrderStatusTimeline order={order} />

              {!delivered ? (
                <p className="hc-inline-note">
                  <Icon name="info" size={16} />
                  Times are estimates and update as your pharmacies and driver make progress. Live driver location is not
                  available in this build.
                </p>
              ) : null}
            </section>

            {delivered ? (
              <section className="hc-card">
                <p className="hc-card-label">Your experience</p>
                {order.rating ? (
                  <div className="hc-rated">
                    <span className="hc-rated-stars" aria-label={`Rated ${order.rating} out of 5`}>
                      {[1, 2, 3, 4, 5].map((value) => (
                        <Icon
                          key={value}
                          name="star"
                          size={17}
                          className={value <= (order.rating ?? 0) ? "hc-rated-on" : undefined}
                        />
                      ))}
                    </span>
                    {order.reviewComment ? <p className="hc-body">{order.reviewComment}</p> : null}
                    <p className="hc-small">Thank you. Your feedback goes to the HealthConnect delivery team.</p>
                  </div>
                ) : (
                  <>
                    <p className="hc-body" style={{ marginTop: 8 }}>
                      One rating covers the whole delivery. It takes a moment and helps us fix what went wrong.
                    </p>
                    <button
                      type="button"
                      className="hc-btn hc-btn-secondary"
                      style={{ marginTop: 14 }}
                      onClick={() => setReviewOpen(true)}
                    >
                      <Icon name="star" size={16} />
                      Rate your experience
                    </button>
                  </>
                )}
              </section>
            ) : null}

            <section className="hc-card">
              <p className="hc-card-label">Medications</p>
              <ul className="hc-order-lines">
                {order.lines.map((line) => (
                  <li key={line.medicineId}>
                    <span className="hc-order-line-main">
                      <strong>
                        {line.name}
                        {line.quantity > 1 ? <span className="hc-num"> x {line.quantity}</span> : null}
                      </strong>
                      <span className="hc-small">{line.generic}</span>
                      {line.prescriptionId ? (
                        <span className="hc-small hc-num">On prescription {line.prescriptionId}</span>
                      ) : null}
                    </span>
                    <span className="hc-num">{formatMoney(line.unitPrice * line.quantity)}</span>
                  </li>
                ))}
              </ul>

              {pharmacies.length > 1 ? (
                <details className="hc-details">
                  <summary>Which pharmacy supplied what</summary>
                  <div className="hc-split">
                    {pharmacies.map((pharmacy) => (
                      <div className="hc-split-group" key={pharmacy}>
                        <p className="hc-split-name">{pharmacy}</p>
                        <ul>
                          {order.lines
                            .filter((line) => line.pharmacy === pharmacy)
                            .map((line) => (
                              <li key={line.medicineId}>
                                <Icon name="pill" size={14} />
                                {line.name}
                              </li>
                            ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </details>
              ) : (
                <p className="hc-small">Filled by {pharmacies[0]}.</p>
              )}
            </section>
          </div>

          <aside className="hc-order-side">
            <section className="hc-card">
              <p className="hc-card-label">Delivery</p>
              <address className="hc-order-address">
                <strong>{order.address.label}</strong>
                <span>
                  {order.address.line1}
                  {order.address.building ? `, ${order.address.building}` : ""}
                </span>
                <span>
                  {order.address.area}, {order.address.city}
                </span>
              </address>
              <dl className="hc-summary-rows">
                <div>
                  <dt>{order.scheduled ? "Window" : "Estimated"}</dt>
                  <dd>{order.arrivalWindow}</dd>
                </div>
                <div>
                  <dt>Order placed</dt>
                  <dd>{formatDate(order.placedAt)}</dd>
                </div>
              </dl>
            </section>

            <section className="hc-card">
              <p className="hc-card-label">Payment</p>
              <dl className="hc-summary-rows">
                <div>
                  <dt>Medications</dt>
                  <dd className="hc-num">{formatMoney(order.medicationTotal)}</dd>
                </div>
                <div>
                  <dt>Delivery</dt>
                  <dd className="hc-num">{formatMoney(order.deliveryFee)}</dd>
                </div>
              </dl>
              <div className="hc-summary-total">
                <span>Total</span>
                <strong className="hc-num">{formatMoney(orderTotal(order))}</strong>
              </div>
              <p className="hc-small">{order.paymentLabel}</p>
              {pharmacies.length > 1 ? (
                <p className="hc-small">Includes fulfilment from {plural(pharmacies.length, "pharmacy", "pharmacies")}.</p>
              ) : null}
              <button type="button" className="hc-btn hc-btn-secondary hc-btn-block" onClick={() => setReceiptOpen(true)}>
                <Icon name="receipt" size={16} />
                View receipt
              </button>
            </section>

            <section className="hc-card hc-card-quiet">
              <p className="hc-card-label">Need help</p>
              <p className="hc-body" style={{ marginTop: 8 }}>
                If something is wrong with this order, HealthConnect support can reach the pharmacies and the driver on
                your behalf.
              </p>
              <Link href="/account" className="hc-textlink" style={{ marginTop: 12 }}>
                Contact support
                <Icon name="arrowRight" size={16} />
              </Link>
            </section>
          </aside>
        </div>
      </div>

      <ReviewDialog
        open={reviewOpen}
        onClose={() => setReviewOpen(false)}
        orderId={order.id}
        onSubmit={(rating, comment) => {
          reviewOrder(order.id, rating, comment);
          notify("Thank you for the feedback");
        }}
      />
      <ReceiptDialog open={receiptOpen} onClose={() => setReceiptOpen(false)} order={order as Order} />
    </PatientShell>
  );
}

/** See the note on `/prescriptions/[id]`: `useSearchParams` needs a boundary. */
export default function OrderDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="hc hc-app">
          <div className="hc-wrap hc-page">
            <CardSkeletons count={2} lines={5} />
          </div>
        </div>
      }
    >
      <OrderDetailScreen />
    </Suspense>
  );
}
