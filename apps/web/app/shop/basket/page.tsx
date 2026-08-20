"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useBasket } from "@/lib/basket";
import { useTranslations } from "@/lib/i18n/context";
import type { BasketQuote, DeliveryAddress, Order, Paginated, PaymentMethod, PaymentProvider } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function BasketPage() {
  const router = useRouter();
  const basket = useBasket();
  const t = useTranslations();
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
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<PaymentProvider>("COD");

  useEffect(() => {
    apiFetch<PaymentMethod[]>("/shop/payment-methods/")
      .then(setPaymentMethods)
      .catch((exception) => setError((exception as ApiError).message || t("shop.paymentMethodsError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    apiFetch<Paginated<DeliveryAddress> | DeliveryAddress[]>("/shop/addresses/")
      .then((payload) => {
        const list = asList(payload);
        setAddresses(list);
        const preferred = list.find((entry) => entry.is_default) || list[0];
        if (preferred) setAddressId(preferred.id);
      })
      .catch((exception) => setError((exception as ApiError).message || t("shop.addressesError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      setError((exception as ApiError).message || t("shop.quoteError"));
    } finally {
      setQuoting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basket.items, address]);

  useEffect(() => {
    void requestQuote();
  }, [requestQuote]);

  async function placeOrder() {
    setPlacing(true);
    setError("");
    try {
      // The displayed quote can go stale while the shopper fills out the delivery form -
      // price/stock may have moved. Re-quote right before committing so a mismatch is caught
      // here instead of surfacing as a confusing order-placement error.
      if (address) {
        const freshQuote = await apiFetch<BasketQuote>("/shop/quote/", {
          method: "POST",
          body: JSON.stringify({
            items: basket.items.map((item) => ({ medicine: item.medicine, quantity: item.quantity })),
            latitude: address.latitude,
            longitude: address.longitude
          })
        });
        if (quote && freshQuote.items_subtotal !== quote.items_subtotal) {
          setQuote(freshQuote);
          setError(t("shop.basketChangedError"));
          setPlacing(false);
          return;
        }
      }

      const order = await apiFetch<Order>("/shop/orders/", {
        method: "POST",
        body: JSON.stringify({
          items: basket.items.map((item) => ({ medicine: item.medicine, quantity: item.quantity })),
          address: addressId || null,
          fulfillment_type: fulfillmentType,
          scheduled_for: scheduleMode === "LATER" && scheduledFor ? new Date(scheduledFor).toISOString() : null,
          window_minutes: windowMinutes,
          notes,
          prescription_code: prescriptionCode.trim(),
          payment_method: paymentMethod
        })
      });

      let recurringFailed = false;
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
        }).catch(() => {
          recurringFailed = true;
        });
      }

      basket.clear();
      router.push(`/shop/orders?highlight=${order.reference}${recurringFailed ? "&recurringFailed=1" : ""}`);
    } catch (exception) {
      setError((exception as ApiError).message || t("shop.placeOrderError"));
    } finally {
      setPlacing(false);
    }
  }

  if (basket.items.length === 0) {
    return (
      <>
        <h1>{t("shop.yourBasket")}</h1>
        <EmptyState title={t("shop.basketEmpty")} detail={t("shop.basketEmptyHint")} />
        <Link className="button" href="/shop">
          {t("shop.findMedicine")}
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
          <h1>{t("shop.yourBasket")}</h1>
          <p className="muted">{t("shop.basketSubtitle")}</p>
        </div>
        <Link className="button button-secondary" href="/shop">
          {t("shop.keepShopping")}
        </Link>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <section className="panel">
        <h3>{t("shop.items")}</h3>
        <table className="table">
          <thead>
            <tr>
              <th>{t("shop.item")}</th>
              <th>{t("common.quantity")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {basket.items.map((item) => (
              <tr key={item.medicine}>
                <td>
                  {item.name}
                  {item.requires_prescription ? <span className="tag tag-rx">{t("shop.rxTag")}</span> : null}
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
                    {t("common.remove")}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h3>{t("shop.howSourced")}</h3>
        {quoting ? <div className="skeleton-card" /> : null}
        {!address ? (
          <Notice>
            <Link href="/shop/addresses">{t("shop.addAddress")}</Link> {t("shop.addAddressToFindPharmacies")}
          </Notice>
        ) : null}

        {quote ? (
          <>
            <p className="muted">
              {quote.pharmacy_count === 1 ? t("shop.onePharmacy") : t("shop.multiplePharmacies", { count: quote.pharmacy_count })}
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
                      {line.is_price_regulated ? <span className="tag tag-regulated">{t("shop.mophPrice")}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            {quote.allocations.length > 1 &&
            new Set(quote.allocations.map((allocation) => allocation.preparation_minutes)).size > 1 ? (
              <Notice>
                {t("shop.prepTimeNotice", {
                  details: quote.allocations.map((allocation) => `${allocation.pharmacy_name} ~${allocation.preparation_minutes} min`).join(", ")
                })}
              </Notice>
            ) : null}

            {quote.unfulfilled.length > 0 ? (
              <Notice tone="danger">
                {t("shop.unavailableNearby", {
                  details: quote.unfulfilled.map((row) => `${row.medicine_name} (${row.quantity_short} short)`).join(", ")
                })}
              </Notice>
            ) : null}

            <details className="explain">
              <summary>{t("shop.whyThesePharmacies")}</summary>
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
        <h3>{t("shop.delivery")}</h3>
        <div className="form-grid">
          <Field label={t("shop.howDeliver")}>
            <select value={fulfillmentType} onChange={(event) => setFulfillmentType(event.target.value as "DELIVERY" | "PICKUP")}>
              <option value="DELIVERY">{t("shop.deliverToMe")}</option>
              <option value="PICKUP">{t("shop.collectInStore")}</option>
            </select>
          </Field>
          <Field label={t("shop.address")}>
            <select value={addressId} onChange={(event) => setAddressId(event.target.value)}>
              <option value="">{t("shop.selectAddress")}</option>
              {addresses.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label} — {entry.area}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("shop.when")}>
            <select value={scheduleMode} onChange={(event) => setScheduleMode(event.target.value as "ASAP" | "LATER")}>
              <option value="ASAP">{t("shop.asap")}</option>
              <option value="LATER">{t("shop.later")}</option>
            </select>
          </Field>
          {scheduleMode === "LATER" ? (
            <>
              <Field label={t("shop.dateTime")}>
                <input type="datetime-local" value={scheduledFor} onChange={(event) => setScheduledFor(event.target.value)} />
              </Field>
              <Field label={t("shop.window")} hint={t("shop.windowHint")}>
                <select value={windowMinutes} onChange={(event) => setWindowMinutes(Number(event.target.value))}>
                  <option value={60}>{t("shop.window30")}</option>
                  <option value={120}>{t("shop.window60")}</option>
                  <option value={240}>{t("shop.window120")}</option>
                </select>
              </Field>
            </>
          ) : null}
          {needsPrescription ? (
            <Field label={t("shop.prescriptionCode")} hint={t("shop.prescriptionCodeHint")}>
              <input value={prescriptionCode} onChange={(event) => setPrescriptionCode(event.target.value.toUpperCase())} placeholder={t("shop.rxPlaceholder")} />
            </Field>
          ) : null}
          <Field label={t("shop.notes")}>
            <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={t("shop.notesPlaceholder")} />
          </Field>
          <Field label={t("shop.payWith")}>
            <select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as PaymentProvider)}>
              {(paymentMethods.length ? paymentMethods : [{ code: "COD", label: "Cash on delivery" }]).map((method) => (
                <option key={method.code} value={method.code}>
                  {method.label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <label className="field checkbox-field">
          <span>{t("shop.repeatOrder")}</span>
          <input type="checkbox" checked={makeRecurring} onChange={(event) => setMakeRecurring(event.target.checked)} />
          <small>{t("shop.repeatHint")}</small>
        </label>
        {makeRecurring ? (
          <Field label={t("shop.repeatEvery")}>
            <input type="number" min={1} max={180} value={intervalDays} onChange={(event) => setIntervalDays(Number(event.target.value) || 30)} />
          </Field>
        ) : null}
      </section>

      <section className="panel checkout-summary">
        <div>
          <span className="muted">{t("shop.checkoutItems")}</span>
          <strong>${quote?.items_subtotal ?? "0.00"}</strong>
        </div>
        <div>
          <span className="muted">{t("shop.checkoutDelivery")}</span>
          <strong>{fulfillmentType === "DELIVERY" ? "$3.00" : t("shop.checkoutFree")}</strong>
        </div>
        <div>
          <span className="muted">{t("shop.checkoutTotal")}</span>
          <strong className="price">${total.toFixed(2)}</strong>
        </div>
        <Button
          type="button"
          onClick={placeOrder}
          disabled={placing || !quote || quote.allocations.length === 0 || (fulfillmentType === "DELIVERY" && !addressId)}
        >
          {placing ? t("shop.placingOrder") : t("shop.placeOrder")}
        </Button>
      </section>

      <Notice>{t("shop.holdNotice")}</Notice>
    </>
  );
}
