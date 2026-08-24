"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { AddressFormDialog } from "@/components/account/AddressForm";
import {
  AddressSelector,
  CheckoutStep,
  DeliveryWindowSelector,
  PaymentSelector,
  PrescriptionVerificationSummary,
  paymentLabel,
  type DeliveryChoice
} from "@/components/checkout/CheckoutParts";
import { Icon } from "@/components/ui/Icon";
import { useCurrentUser } from "@/lib/auth";
import { useBasket } from "@/lib/basket";
import { useCheckoutPlan } from "@/lib/patient/checkout";
import { applyDispensing, useAccount, useOrders, usePrescriptions } from "@/lib/patient/store";
import { MOCK_PROFILE } from "@/lib/patient/mock-patient";
import { formatMoney, plural, todayIso } from "@/lib/patient/format";
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
  const { user } = useCurrentUser();
  const basket = useBasket();
  const { plan, ready: planReady, clearPlan } = useCheckoutPlan();
  const account = useAccount();
  const { prescriptions } = usePrescriptions();
  const { placeOrder } = useOrders();

  const [addressId, setAddressId] = useState<string | null>(null);
  const [paymentId, setPaymentId] = useState<string | null>(null);
  const [when, setWhen] = useState<DeliveryChoice>({ kind: "asap" });
  const [addressOpen, setAddressOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("editing");
  const [placed, setPlaced] = useState<Order | null>(null);

  // Guards the button against a second press while the first is in flight and
  // against a double-submit from a fast double click.
  const submitting = useRef(false);

  useEffect(() => {
    if (!account.ready) return;
    setAddressId((current) => current ?? account.addresses.find((entry) => entry.isDefault)?.id ?? account.addresses[0]?.id ?? null);
    setPaymentId((current) => current ?? account.payments.find((entry) => entry.isDefault)?.id ?? account.payments[0]?.id ?? null);
  }, [account.ready, account.addresses, account.payments]);

  const initials = initialsFor(user?.first_name ?? MOCK_PROFILE.firstName, user?.last_name);
  const address = account.addresses.find((entry) => entry.id === addressId) ?? null;
  const payment = account.payments.find((entry) => entry.id === paymentId) ?? null;
  const loading = !planReady || !account.ready || !basket.ready;

  if (placed) return <OrderPlaced order={placed} initials={initials} />;

  if (loading) {
    return (
      <PatientShell initials={initials}>
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
      <PatientShell initials={initials}>
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
  const canPlace = Boolean(address && payment) && phase !== "placing";

  async function place() {
    if (!plan || !address || !payment || submitting.current) return;
    submitting.current = true;
    setPhase("placing");

    try {
      // Stands in for POST /orders/. The delay is what makes the disabled and
      // loading states worth building rather than theoretical.
      await new Promise((resolve) => setTimeout(resolve, 1200));

      const reference = `HC-${Math.floor(24100 + Math.random() * 800)}`;
      const order: Order = {
        id: reference,
        placedAt: todayIso(),
        stage: "confirmed",
        arrivalWindow: when.kind === "asap" ? plan.etaLabel : when.window,
        scheduled: when.kind === "scheduled",
        deliveredAt: null,
        address,
        paymentLabel: paymentLabel(payment),
        medicationTotal: plan.medicationTotal,
        deliveryFee: plan.deliveryFee,
        reachedAt: { confirmed: nowLabel() },
        rating: null,
        reviewComment: "",
        lines: plan.lines.map((line) => ({
          medicineId: line.medicineId,
          name: line.name,
          generic: line.generic,
          quantity: line.quantity,
          unitPrice: line.unitPrice,
          pharmacy: line.pharmacy,
          prescriptionId: line.prescriptionId ?? null
        }))
      };

      placeOrder(order);
      applyDispensing(order.lines);
      basket.clear();
      clearPlan();
      setPlaced(order);
    } catch {
      setPhase("failed");
    } finally {
      submitting.current = false;
    }
  }

  return (
    <PatientShell initials={initials}>
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
              <PaymentSelector methods={account.payments} selectedId={paymentId} onSelect={setPaymentId} />
              <p className="hc-small">
                This is a demonstration build. No payment is taken and no card details are stored.
              </p>
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
                We could not place your order. Nothing has been charged. Please try again.
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

function nowLabel(): string {
  return new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/**
 * Confirmation.
 *
 * Calm on purpose. The patient has just bought medicine they need, so the
 * screen answers what happens next and gets out of the way; there is nothing to
 * celebrate here.
 */
function OrderPlaced({ order, initials }: { order: Order; initials: string }) {
  return (
    <PatientShell initials={initials}>
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
