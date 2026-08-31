"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef } from "react";
import { Icon } from "@/components/ui/Icon";
import { CardSkeletons } from "@/components/patient/Page";
import { useOrders } from "@/lib/patient/store";
import { formatDate, formatMoney } from "@/lib/patient/format";
import { orderPharmacies, orderTotal, type Order, type OrderPharmacy } from "@/lib/patient/types";

/**
 * The order receipt, as a document rather than a screen.
 *
 * `/orders/[id]` answers "where is my medication"; this answers "what did I pay
 * for, and who dispensed it". It opens on its own page with no app chrome and
 * downloads as a PDF document with the HealthConnect mark,
 * the order reference, each fulfilling pharmacy with how to reach it, the lines
 * that pharmacy supplied, and the totals the patient already agreed to.
 *
 * The PDF is rendered from the receipt itself so it preserves what is shown
 * without sending the patient through a browser print dialog.
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
  const receiptRef = useRef<HTMLElement>(null);
  // Fall back to the pharmacy names carried on the lines when the order predates
  // per-fulfillment detail, so an older order still produces a receipt.
  const pharmacies: OrderPharmacy[] =
    order.fulfilledBy.length > 0
      ? order.fulfilledBy
      : orderPharmacies(order).map((name) => ({ name, area: "", phone: "", subtotal: 0 }));
  const multiPharmacy = pharmacies.length > 1;
  const total = orderTotal(order);

  async function downloadReceipt() {
    if (!receiptRef.current) return;

    const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
      import("html2canvas"),
      import("jspdf"),
    ]);
    const canvas = await html2canvas(receiptRef.current, {
      backgroundColor: "#ffffff",
      scale: 2,
      useCORS: true,
    });
    const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    const imageWidth = pageWidth - margin * 2;
    const imageHeight = (canvas.height * imageWidth) / canvas.width;
    const printableHeight = pageHeight - margin * 2;
    const image = canvas.toDataURL("image/jpeg", 0.98);

    for (let offset = 0, page = 0; offset < imageHeight; offset += printableHeight, page += 1) {
      if (page > 0) pdf.addPage();
      pdf.addImage(image, "JPEG", margin, margin - offset, imageWidth, imageHeight);
    }

    pdf.save(`receipt-${safeFileName(order.id)}.pdf`);
  }

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
          onClick={downloadReceipt}
        >
          <Icon name="receipt" size={16} />
          Download receipt
        </button>
      </div>

      <article className="hc-rcpt-doc" ref={receiptRef}>
        <header className="hc-rcpt-head">
          {/* Plain <img> gives the PDF renderer the exact displayed asset. */}
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

function safeFileName(value: string) {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "-");
}
