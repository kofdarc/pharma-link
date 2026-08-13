"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useBasket } from "@/lib/basket";
import type { BasketQuote, DeliveryAddress, Order, Paginated } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function BasketPage() {
  const router = useRouter();
  const basket = useBasket();
  const [addresses, setAddresses] = useState<DeliveryAddress[]>([]);
  const [addressId, setAddressId] = useState("");
  const [quote, setQuote] = useState<BasketQuote | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState("");

  const [fulfillmentType, setFulfillmentType] = useState<"DELIVERY" | "PICKUP">("DELIVERY");
  const [scheduleMode, setScheduleMode] = useState<"ASAP" | "LATER">("ASAP");
  const [scheduledFor, setScheduledFor] = useState("");
  const [windowMinutes, setWindowMinutes] = useState(120);
  const [prescriptionCode, setPrescriptionCode] = useState("");
  const [notes, setNotes] = useState("");
  const [makeRecurring, setMakeRecurring] = useState(false);
  const [intervalDays, setIntervalDays] = useState(30);

  useEffect(() => {
    apiFetch<Paginated<DeliveryAddress> | DeliveryAddress[]>("/shop/addresses/")
      .then((payload) => {
        const list = asList(payload);
        setAddresses(list);
        const preferred = list.find((entry) => entry.is_default) || list[0];
        if (preferred) setAddressId(preferred.id);
      })
      .catch(() => setAddresses([]));
  }, []);

  const address = addresses.find((entry) => entry.id === addressId);

  const requestQuote = useCallback(async () => {
    if (basket.items.length === 0 || !address) {
      setQuote(null);
      return;
    }
    setQuoting(true);
    setError("");
    try {
      setQuote(
        await apiFetch<BasketQuote>("/shop/quote/", {
          method: "POST",
          body: JSON.stringify({
            items: basket.items.map((item) => ({ medicine: item.medicine, quantity: item.quantity })),
            latitude: address.latitude,
            longitude: address.longitude
          })
        })
      );
    } catch (exception) {
      setError((exception as ApiError).message || "Could not price this basket.");
    } finally {
      setQuoting(false);
    }
  }, [basket.items, address]);

  useEffect(() => {
    void requestQuote();
  }, [requestQuote]);

  async function placeOrder() {
    setPlacing(true);
    setError("");
    try {
      const order = await apiFetch<Order>("/shop/orders/", {
        method: "POST",
        body: JSON.stringify({
          items: basket.items.map((item) => ({ medicine: item.medicine, quantity: item.quantity })),
          address: addressId || null,
          fulfillment_type: fulfillmentType,
          scheduled_for: scheduleMode === "LATER" && scheduledFor ? new Date(scheduledFor).toISOString() : null,
          window_minutes: windowMinutes,
          notes,
          prescription_code: prescriptionCode.trim()
        })
      });

      if (makeRecurring && addressId) {
        await apiFetch("/shop/recurring-orders/", {
          method: "POST",
          body: JSON.stringify({
            label: "Repeat refill",
            address: addressId,
            items: basket.items.map((item) => ({ medicine: item.medicine, quantity: item.quantity })),
            interval_days: intervalDays,
            next_run_at: new Date(Date.now() + intervalDays * 86400000).toISOString()
          })
        }).catch(() => undefined);
      }

      basket.clear();
      router.push(`/shop/orders?highlight=${order.reference}`);
    } catch (exception) {
      setError((exception as ApiError).message || "Could not place the order.");
    } finally {
      setPlacing(false);
    }
  }

  if (basket.items.length === 0) {
    return (
      <>
        <h1>Your basket</h1>
        <EmptyState title="Your basket is empty." detail="Search for a medicine to get started." />
        <Link className="button" href="/shop">
          Find a medicine
        </Link>
      </>
    );
  }

  const needsPrescription = basket.items.some((item) => item.requires_prescription);
  const total = quote ? Number(quote.items_subtotal) + (fulfillmentType === "DELIVERY" ? 3 : 0) : 0;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Your basket</h1>
          <p className="muted">We work out which pharmacies can fill this, using as few as possible.</p>
        </div>
        <Link className="button button-secondary" href="/shop">
          Keep shopping
        </Link>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <section className="panel">
        <h3>Items</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Quantity</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {basket.items.map((item) => (
              <tr key={item.medicine}>
                <td>
                  {item.name}
                  {item.requires_prescription ? <span className="tag tag-rx">Rx</span> : null}
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={item.quantity}
                    className="qty-input"
                    onChange={(event) => basket.setQuantity(item.medicine, Number(event.target.value) || 1)}
                  />
                </td>
                <td>
                  <Button type="button" variant="secondary" onClick={() => basket.remove(item.medicine)}>
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h3>How this will be sourced</h3>
        {quoting ? <div className="skeleton-card" /> : null}
        {!address ? (
          <Notice>
            <Link href="/shop/addresses">Add a delivery address</Link> so we can find the closest pharmacies.
          </Notice>
        ) : null}

        {quote ? (
          <>
            <p className="muted">
              {quote.pharmacy_count === 1
                ? "One pharmacy covers everything — a single pickup, so the fastest possible delivery."
                : `${quote.pharmacy_count} pharmacies are needed. Your items are collected on one route, not one trip each.`}
            </p>

            {quote.allocations.map((allocation) => (
              <div key={allocation.pharmacy} className="allocation-card">
                <div className="section-header">
                  <div>
                    <strong>{allocation.pharmacy_name}</strong>
                    <p className="muted small">
                      {allocation.pharmacy_area} · {allocation.distance_km} km · ★ {allocation.rating} ·{" "}
                      {allocation.fulfillment_success_rate}% fulfilled · ready in ~{allocation.preparation_minutes} min
                    </p>
                  </div>
                  <strong>${allocation.subtotal}</strong>
                </div>
                <ul className="clean-list">
                  {allocation.lines.map((line) => (
                    <li key={line.medicine}>
                      {line.quantity} × {line.medicine_name} — ${line.line_total}
                      {line.is_price_regulated ? <span className="tag tag-regulated">MoPH price</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            {quote.unfulfilled.length > 0 ? (
              <Notice tone="danger">
                Not available nearby right now:{" "}
                {quote.unfulfilled.map((row) => `${row.medicine_name} (${row.quantity_short} short)`).join(", ")}. These
                will not be ordered, and we have flagged the demand to pharmacies in your area.
              </Notice>
            ) : null}

            <details className="explain">
              <summary>Why these pharmacies?</summary>
              <ul className="clean-list">
                {quote.explanation.map((line, index) => (
                  <li key={index} className="muted small">
                    {line}
                  </li>
                ))}
              </ul>
            </details>
          </>
        ) : null}
      </section>

      <section className="panel">
        <h3>Delivery</h3>
        <div className="form-grid">
          <Field label="How would you like it?">
            <select value={fulfillmentType} onChange={(event) => setFulfillmentType(event.target.value as "DELIVERY" | "PICKUP")}>
              <option value="DELIVERY">Deliver to me</option>
              <option value="PICKUP">I will collect in store</option>
            </select>
          </Field>
          <Field label="Address">
            <select value={addressId} onChange={(event) => setAddressId(event.target.value)}>
              <option value="">Select an address</option>
              {addresses.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label} — {entry.area}
                </option>
              ))}
            </select>
          </Field>
          <Field label="When?">
            <select value={scheduleMode} onChange={(event) => setScheduleMode(event.target.value as "ASAP" | "LATER")}>
              <option value="ASAP">As soon as possible</option>
              <option value="LATER">Schedule for later</option>
            </select>
          </Field>
          {scheduleMode === "LATER" ? (
            <>
              <Field label="Date and time">
                <input type="datetime-local" value={scheduledFor} onChange={(event) => setScheduledFor(event.target.value)} />
              </Field>
              <Field label="Acceptable window" hint="A wider window lets us batch your delivery efficiently.">
                <select value={windowMinutes} onChange={(event) => setWindowMinutes(Number(event.target.value))}>
                  <option value={60}>± 30 minutes</option>
                  <option value={120}>± 1 hour</option>
                  <option value={240}>± 2 hours</option>
                </select>
              </Field>
            </>
          ) : null}
          {needsPrescription ? (
            <Field label="Prescription code" hint="From the QR code your doctor emailed you.">
              <input value={prescriptionCode} onChange={(event) => setPrescriptionCode(event.target.value.toUpperCase())} placeholder="RX-XXXX-XXXX" />
            </Field>
          ) : null}
          <Field label="Notes for the driver">
            <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Building, floor, landmark..." />
          </Field>
        </div>

        <label className="field checkbox-field">
          <span>Repeat this order automatically</span>
          <input type="checkbox" checked={makeRecurring} onChange={(event) => setMakeRecurring(event.target.checked)} />
          <small>For chronic medication. We re-source it each cycle, so a closed pharmacy never blocks a refill.</small>
        </label>
        {makeRecurring ? (
          <Field label="Repeat every (days)">
            <input type="number" min={1} max={180} value={intervalDays} onChange={(event) => setIntervalDays(Number(event.target.value) || 30)} />
          </Field>
        ) : null}
      </section>

      <section className="panel checkout-summary">
        <div>
          <span className="muted">Items</span>
          <strong>${quote?.items_subtotal ?? "0.00"}</strong>
        </div>
        <div>
          <span className="muted">Delivery</span>
          <strong>{fulfillmentType === "DELIVERY" ? "$3.00" : "Free"}</strong>
        </div>
        <div>
          <span className="muted">Total</span>
          <strong className="price">${total.toFixed(2)}</strong>
        </div>
        <Button
          type="button"
          onClick={placeOrder}
          disabled={placing || !quote || quote.allocations.length === 0 || (fulfillmentType === "DELIVERY" && !addressId)}
        >
          {placing ? "Placing order..." : "Place order"}
        </Button>
      </section>

      <Notice>
        Placing the order holds the stock at each pharmacy so it cannot be sold from under you. Nothing leaves the
        shelf until a pharmacist hands it to your driver.
      </Notice>
    </>
  );
}
