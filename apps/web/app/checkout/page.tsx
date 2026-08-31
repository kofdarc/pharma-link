"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { AddressFormDialog } from "@/components/account/AddressForm";
import {
  AddressSelector,
  CardFields,
  CheckoutStep,
  DeliveryWindowSelector,
  EMPTY_CARD,
  PaymentSelector,
  PrescriptionVerificationSummary,
  validateCard,
  type CardDraft,
  type CardErrors,
  type DeliveryChoice,
  type PaymentMethodId
} from "@/components/checkout/CheckoutParts";
import { Icon } from "@/components/ui/Icon";
import { apiFetch, ApiError } from "@/lib/api-client";
import { useBasket } from "@/lib/basket";
import { useCheckoutPlan } from "@/lib/patient/checkout";
import { useAccount, usePrescriptions } from "@/lib/patient/store";
import { toOrder } from "@/lib/patient/adapters";
import { formatMoney, plural } from "@/lib/patient/format";
import type { Order as ApiOrder } from "@/types/api";
import type { Order } from "@/lib/patient/types";

/** Windows offered for a scheduled delivery. Three, so the choice stays a choice. */
const WINDOWS = ["4:00 - 5:00 PM", "5:00 - 6:00 PM", "6:00 - 7:00 PM"];

type Phase = "editing" | "placing" | "placed" | "failed";

/**
 * Checkout.
 *
 * One page, four blocks, and an order summary that stays in view on desktop.
 * The fulfilment option was already chosen, so nothing here re-opens that
 * decision; what is left is where it goes, when, on what prescription, and how
 * it is paid for.
 */
export default function CheckoutPage() {
  const router = useRouter();
  const basket = useBasket();
  const { plan, ready: planReady, clearPlan } = useCheckoutPlan();
  const account = useAccount();
  const { prescriptions } = usePrescriptions();

  const [addressId, setAddressId] = useState<string | null>(null);
  // Payment method is a fixed local choice for now — nothing here is wired to a
  // real gateway, so there is no saved-method list to reconcile against.
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethodId>("cod");
  const [card, setCard] = useState<CardDraft>(EMPTY_CARD);
  const [cardErrors, setCardErrors] = useState<CardErrors>({});
  const [when, setWhen] = useState<DeliveryChoice>({ kind: "asap" });
  const [addressOpen, setAddressOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("editing");
  const [failure, setFailure] = useState("");
  const [placed, setPlaced] = useState<Order | null>(null);

  // Guards the button against a second press while the first is in flight and
  // against a double-submit from a fast double click.
  const submitting = useRef(false);
  // Stable for the life of this checkout, so a retry after a lost response
  // returns the order the first attempt created instead of placing a second.
  const idempotencyKey = useRef(`checkout-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`);

  useEffect(() => {
    if (!account.ready) return;
    setAddressId((current) => current ?? account.addresses.find((entry) => entry.isDefault)?.id ?? account.addresses[0]?.id ?? null);
  }, [account.ready, account.addresses]);

  const address = account.addresses.find((entry) => entry.id === addressId) ?? null;
  const loading = !planReady || !account.ready || !basket.ready;

  if (placed) return <OrderPlaced order={placed} />;

  if (loading) {
    return (
      <PatientShell>
        <div className="hc-wrap hc-page">
          <CardSkeletons count={3} lines={3} />
        </div>
      </PatientShell>
    );
  }

  // Landing here without a chosen plan means a reload or a bookmark, not a
  // wrong turn, so the page sends the patient back to the step that produces one.
  if (!plan) {
    return (
      <PatientShell>
        <div className="hc-wrap hc-page">
          <PageHead title="Checkout" back={{ href: "/cart", label: "Basket" }} />
          <EmptyPanel
            icon="info"
            title="Choose how your order is filled first"
            body="Delivery times and prices depend on which pharmacies supply your basket, so that comes before checkout."
          >
            <Link href="/cart/fulfillment" className="hc-btn hc-btn-primary">
              Find best fulfilment
            </Link>
          </EmptyPanel>
        </div>
      </PatientShell>
    );
  }

  const total = plan.total;
  const canPlace = Boolean(address) && phase !== "placing";

  async function place() {
    if (!plan || !address || submitting.current) return;

    // Card details are collected but not transmitted in this build; still, a
    // half-filled form should stop here rather than at a confusing server error.
    if (paymentMethod === "card") {
      const found = validateCard(card);
      setCardErrors(found);
      if (Object.keys(found).length > 0) return;
    }

    submitting.current = true;
    setPhase("placing");
    setFailure("");

    try {
      // The platform re-sources the basket at this point and reserves the
      // stock. The plan chosen a screen ago informed the price shown; it is not
      // an instruction, because supply moves and only what is actually
      // reservable can be sold.
      const record = await apiFetch<ApiOrder>("/shop/orders/", {
        method: "POST",
        // Guards against a double-submit surviving a retry or a lost response:
        // the same key returns the order the first request created.
        headers: { "Idempotency-Key": idempotencyKey.current },
        body: JSON.stringify({
          items: plan.lines.map((line) => ({ medicine: line.medicineId, quantity: line.quantity })),
          address: address.id,
          fulfillment_type: "DELIVERY",
          scheduled_for: when.kind === "scheduled" ? windowStart(when.window) : null,
          // Not wired to Whish yet — anything other than cash still runs through
          // the demonstration gateway.
          payment_method: paymentMethod === "cod" ? "COD" : "MOCK_GATEWAY",
          prescription_code: plan.lines.find((line) => line.prescriptionId)?.prescriptionId ?? ""
        })
      });

      basket.clear();
      clearPlan();
      setPlaced(toOrder(record));
    } catch (error) {
      // The API explains a refusal — an unverified email, a missing
      // prescription, stock that went while the patient was deciding — and
      // that reason is far more useful than "something went wrong".
      setFailure(error instanceof ApiError ? error.message : "");
      setPhase("failed");
    } finally {
      submitting.current = false;
    }
  }

  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        <PageHead title="Checkout" back={{ href: "/cart/fulfillment", label: "Fulfilment options" }} />

        <div className="hc-checkout">
          <div className="hc-checkout-main">
            <CheckoutStep index={1} title="Delivery">
              <AddressSelector
                addresses={account.addresses}
                selectedId={addressId}
                onSelect={setAddressId}
                onAdd={() => setAddressOpen(true)}
              />
              <hr className="hc-rule" />
              <DeliveryWindowSelector etaLabel={plan.etaLabel} windows={WINDOWS} value={when} onChange={setWhen} />
            </CheckoutStep>

            <CheckoutStep index={2} title="Prescriptions">
              <PrescriptionVerificationSummary lines={plan.lines} prescriptions={prescriptions} />
              <p className="hc-small">
                HealthConnect confirms that a valid prescription covers what is being dispensed. It does not review or
                change what your physician prescribed.
              </p>
            </CheckoutStep>

            <CheckoutStep index={3} title="Payment">
              <PaymentSelector selectedId={paymentMethod} onSelect={setPaymentMethod} />
              {paymentMethod === "card" ? (
                <CardFields
                  value={card}
                  onChange={(next) => {
                    setCard(next);
                    if (Object.keys(cardErrors).length > 0) setCardErrors({});
                  }}
                  errors={cardErrors}
                />
              ) : null}
            </CheckoutStep>

            <CheckoutStep index={4} title="Review">
              <ul className="hc-review-lines">
                {plan.lines.map((line) => (
                  <li key={line.medicineId}>
                    <span>
                      <strong>
                        {line.name}
                        {line.quantity > 1 ? <span className="hc-num"> x {line.quantity}</span> : null}
                      </strong>
                      <span className="hc-small">{line.pharmacy}</span>
                    </span>
                    <span className="hc-num">{formatMoney(line.unitPrice * line.quantity)}</span>
                  </li>
                ))}
              </ul>
            </CheckoutStep>
          </div>

          <aside className="hc-summary hc-summary-sticky" aria-labelledby="checkout-summary">
            <h2 className="hc-h3" id="checkout-summary">
              Order summary
            </h2>

            <dl className="hc-summary-rows">
              <div>
                <dt>Medications</dt>
                <dd className="hc-num">{formatMoney(plan.medicationTotal)}</dd>
              </div>
              <div>
                <dt>Delivery</dt>
                <dd className="hc-num">{formatMoney(plan.deliveryFee)}</dd>
              </div>
              <div>
                <dt>Arriving</dt>
                <dd>{when.kind === "asap" ? `Estimated ${plan.etaLabel}` : when.window}</dd>
              </div>
            </dl>

            <div className="hc-summary-total">
              <span>Total</span>
              <strong className="hc-num">{formatMoney(total)}</strong>
            </div>

            {plan.pharmacies.length > 1 ? (
              <p className="hc-small">Includes fulfilment from {plural(plan.pharmacies.length, "pharmacy", "pharmacies")}.</p>
            ) : null}

            <button
              type="button"
              className="hc-btn hc-btn-primary hc-btn-lg hc-btn-block"
              onClick={place}
              disabled={!canPlace}
              aria-busy={phase === "placing"}
            >
              {phase === "placing" ? (
                <>
                  <span className="hc-spinner" aria-hidden="true" />
                  Placing order
                </>
              ) : (
                <>Place order · {formatMoney(total)}</>
              )}
            </button>

            {!address ? (
              <p className="hc-inline-note hc-inline-note-warn">
                <Icon name="pin" size={16} />
                Choose a delivery address to continue.
              </p>
            ) : null}

            {phase === "failed" ? (
              <p className="hc-inline-note hc-inline-note-alert" role="alert">
                <Icon name="alert" size={16} />
                {failure || "We could not place your order. Please try again."} Nothing has been charged.
              </p>
            ) : null}
          </aside>
        </div>
      </div>

      <AddressFormDialog
        open={addressOpen}
        onClose={() => setAddressOpen(false)}
        onSave={(next) => {
          account.saveAddress(next);
          setAddressId(next.id);
        }}
        makeDefaultByDefault={account.addresses.length === 0}
      />
    </PatientShell>
  );
}

/**
 * The instant a chosen window opens, as the API wants it.
 *
 * WINDOWS above are written the way they are read aloud ("4:00 - 5:00 PM"), so
 * the start time is parsed back out of the label rather than kept alongside it.
 * The window's width is the order's `window_minutes`, which the API defaults.
 */
function windowStart(label: string): string {
  const match = /^(\d{1,2}):(\d{2})\s*-\s*\d{1,2}:\d{2}\s*(AM|PM)$/i.exec(label.trim());
  const when = new Date();
  if (match) {
    const [, rawHour, minutes, meridiem] = match;
    let hour = Number(rawHour) % 12;
    if (meridiem.toUpperCase() === "PM") hour += 12;
    when.setHours(hour, Number(minutes), 0, 0);
    // A window that has already passed today is meant for tomorrow.
    if (when.getTime() < Date.now()) when.setDate(when.getDate() + 1);
  }
  return when.toISOString();
}

/**
 * Confirmation.
 *
 * Calm on purpose. The patient has just bought medicine they need, so the
 * screen answers what happens next and gets out of the way; there is nothing to
 * celebrate here.
 */
function OrderPlaced({ order }: { order: Order }) {
  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        <div className="hc-confirm">
          <span className="hc-confirm-mark" aria-hidden="true">
            <Icon name="check" size={26} strokeWidth={2.2} />
          </span>
          <h1 className="hc-h2">Order confirmed</h1>
          <p className="hc-lead">Your pharmacies are preparing your medication.</p>

          <dl className="hc-kv hc-confirm-facts">
            <div>
              <dt>Order</dt>
              <dd className="hc-num">{order.id}</dd>
            </div>
            <div>
              <dt>{order.scheduled ? "Delivery window" : "Estimated delivery"}</dt>
              <dd>{order.arrivalWindow}</dd>
            </div>
            <div>
              <dt>Delivering to</dt>
              <dd>{order.address.label}</dd>
            </div>
          </dl>

          <div className="hc-actions hc-confirm-actions">
            <Link href={`/orders/${order.id}`} className="hc-btn hc-btn-primary hc-btn-lg">
              Track order
            </Link>
            <Link href="/home" className="hc-btn hc-btn-secondary hc-btn-lg">
              Back to home
            </Link>
          </div>
        </div>
      </div>
    </PatientShell>
  );
}
