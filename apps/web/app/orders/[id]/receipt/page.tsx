"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { CardSkeletons } from "@/components/patient/Page";
import { useOrders } from "@/lib/patient/store";
import { formatDate, formatMoney } from "@/lib/patient/format";
import { orderPharmacies, orderTotal, type Order, type OrderPharmacy } from "@/lib/patient/types";

/**
 * The order receipt, as a document rather than a screen.
 *
 * `/orders/[id]` answers "where is my medication"; this answers "what did I pay
 * for, and who dispensed it". It opens on its own page with no app chrome so it
 * prints — or saves as a PDF — as a single clean page: the HealthConnect mark,
 * the order reference, each fulfilling pharmacy with how to reach it, the lines
 * that pharmacy supplied, and the totals the patient already agreed to.
 *
 * Print density lives entirely in `@media print` in `receipt.css`. An earlier
 * version measured the on-screen document from `beforeprint` and shrank it with
 * CSS `zoom` to force one page; that measurement never matched the print layout,
 * and Chrome rasterises a fractionally-zoomed element as a blank PDF page. A
 * long multi-pharmacy order now breaks across sheets at a row boundary instead.
 */

export default function OrderReceiptPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === "string" ? decodeURIComponent(params.id) : "";
  const { orders, ready } = useOrders();
  const order = orders.find((entry) => entry.id === id);

  if (!ready) {
    return (
      <div className="hc-rcpt">
        <CardSkeletons count={1} lines={8} />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="hc-rcpt-status">
        <h1 className="hc-h3">We could not load that receipt</h1>
        <p className="hc-body">
          The link may be out of date, or the order may belong to another account.
        </p>
        <Link href="/orders" className="hc-btn hc-btn-primary">
          Back to orders
        </Link>
      </div>
    );
  }

  return <Receipt order={order} />;
}

function Receipt({ order }: { order: Order }) {
  // Fall back to the pharmacy names carried on the lines when the order predates
  // per-fulfillment detail, so an older order still produces a receipt.
  const pharmacies: OrderPharmacy[] =
    order.fulfilledBy.length > 0
      ? order.fulfilledBy
      : orderPharmacies(order).map((name) => ({ name, area: "", phone: "", subtotal: 0 }));
  const multiPharmacy = pharmacies.length > 1;
  const total = orderTotal(order);

  return (
    <div className="hc-rcpt">
      <div className="hc-rcpt-bar hc-rcpt-noprint">
        <Link href={`/orders/${order.id}`} className="hc-textlink">
          <Icon name="arrowLeft" size={16} />
          Back to order
        </Link>
        <button
          type="button"
          className="hc-btn hc-btn-primary hc-btn-sm"
          onClick={() => window.print()}
        >
          <Icon name="receipt" size={16} />
          Save as PDF
        </button>
      </div>

      <article className="hc-rcpt-doc">
        <header className="hc-rcpt-head">
          {/* Plain <img>: this page is printed, and next/image's wrapper and
              lazy loading get in the way of a clean print snapshot. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-primary.webp" alt="HealthConnect" className="hc-rcpt-logo" />
          <div className="hc-rcpt-meta">
            <h1>Receipt</h1>
            <dl>
              <div>
                <dt>Receipt no.</dt>
                <dd>{order.id}</dd>
              </div>
              <div>
                <dt>Order placed</dt>
                <dd>{formatDate(order.placedAt)}</dd>
              </div>
              {order.deliveredAt ? (
                <div>
                  <dt>Delivered</dt>
                  <dd>
                    {formatDate(order.placedAt)} · {order.deliveredAt}
                  </dd>
                </div>
              ) : null}
            </dl>
          </div>
        </header>

        <section className="hc-rcpt-parties">
          <div>
            <h2>Billed to</h2>
            <p>{order.contactName || "HealthConnect account holder"}</p>
            {order.contactPhone ? <p>{order.contactPhone}</p> : null}
          </div>
          <div>
            <h2>Delivered to</h2>
            <p>
              {order.address.line1}
              {order.address.building ? `, ${order.address.building}` : ""}
            </p>
            <p>
              {order.address.area}
              {order.address.city ? `, ${order.address.city}` : ""}
            </p>
          </div>
          <div>
            <h2>{multiPharmacy ? "Fulfilling pharmacies" : "Fulfilled by"}</h2>
            {pharmacies.map((pharmacy) => (
              <div className="hc-rcpt-pharm" key={pharmacy.name}>
                <p className="hc-rcpt-pharm-name">{pharmacy.name}</p>
                {pharmacy.area ? <p>{pharmacy.area}</p> : null}
                {pharmacy.phone ? <p>{pharmacy.phone}</p> : null}
              </div>
            ))}
          </div>
        </section>

        {pharmacies.map((pharmacy) => {
          const lines = multiPharmacy
            ? order.lines.filter((line) => line.pharmacy === pharmacy.name)
            : order.lines;
          if (lines.length === 0) return null;
          return (
            <section className="hc-rcpt-lines" key={pharmacy.name}>
              {multiPharmacy ? <h3>{pharmacy.name}</h3> : null}
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Qty</th>
                    <th>Unit price</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.medicineId}>
                      <td>
                        <span className="hc-rcpt-item">{line.name}</span>
                        {line.generic ? <span className="hc-rcpt-sub">{line.generic}</span> : null}
                        {line.prescriptionId ? (
                          <span className="hc-rcpt-sub">On prescription {line.prescriptionId}</span>
                        ) : null}
                      </td>
                      <td>{line.quantity}</td>
                      <td>{formatMoney(line.unitPrice)}</td>
                      <td>{formatMoney(line.unitPrice * line.quantity)}</td>
                    </tr>
                  ))}
                </tbody>
                {multiPharmacy && pharmacy.subtotal > 0 ? (
                  <tfoot>
                    <tr>
                      <td colSpan={3}>{pharmacy.name} subtotal</td>
                      <td>{formatMoney(pharmacy.subtotal)}</td>
                    </tr>
                  </tfoot>
                ) : null}
              </table>
            </section>
          );
        })}

        <div className="hc-rcpt-totals">
          <div>
            <span>Medication subtotal</span>
            <span>{formatMoney(order.medicationTotal)}</span>
          </div>
          <div>
            <span>Delivery</span>
            <span>{formatMoney(order.deliveryFee)}</span>
          </div>
          <div className="hc-rcpt-grand">
            <span>Total</span>
            <span>{formatMoney(total)}</span>
          </div>
        </div>

        <section className="hc-rcpt-payment">
          <h2>Payment</h2>
          <p>
            {order.paymentLabel}
            {order.paidAt ? ` · paid ${formatDate(order.paidAt)}` : ""}
          </p>
        </section>

        <footer className="hc-rcpt-foot">
          <p>HealthConnect · Questions about this receipt? support@healthconnect.dev</p>
          <p>
            © {new Date().getFullYear()} HealthConnect. HealthConnect does not provide medical
            advice.
          </p>
        </footer>
      </article>
    </div>
  );
}
