"use client";

import Link from "next/link";
import { PatientShell, initialsFor } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { CartLine, CartSummary } from "@/components/cart/CartParts";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useCurrentUser } from "@/lib/auth";
import { useBasket } from "@/lib/basket";
import { usePrescriptions } from "@/lib/patient/store";
import { useAutoPrescriptionMatch } from "@/lib/patient/checkout";
import { MOCK_PROFILE } from "@/lib/patient/mock-patient";

/**
 * The basket.
 *
 * Closer to a pharmacy counter than a shopping cart: the primary action is not
 * "check out" but "find out how this can be filled", because until HealthConnect
 * has matched the basket to pharmacies there is no delivery time and no final
 * price to check out against.
 */
export default function CartPage() {
  const { user } = useCurrentUser();
  const basket = useBasket();
  const { prescriptions, ready: prescriptionsReady } = usePrescriptions();
  const { notify } = useToast();

  const { items, ready: basketReady, setPrescription } = basket;
  useAutoPrescriptionMatch(items, prescriptions, basketReady && prescriptionsReady, setPrescription);

  const initials = initialsFor(user?.first_name ?? MOCK_PROFILE.firstName, user?.last_name);
  const loading = !basket.ready || !prescriptionsReady;
  const uncovered = basket.items.filter((item) => item.requires_prescription && !item.prescription_id);

  return (
    <PatientShell initials={initials}>
      <div className="hc-wrap hc-page">
        <PageHead title="Your medications" lead="Review what you need before HealthConnect looks for a way to fill it." />

        {loading ? (
          <CardSkeletons count={2} lines={2} />
        ) : basket.items.length === 0 ? (
          <EmptyPanel
            icon="search"
            title="Your basket is empty"
            body="Search for a medication and HealthConnect will find which connected pharmacies can supply it."
          >
            <Link href="/search" className="hc-btn hc-btn-primary">
              <Icon name="search" size={17} />
              Search medications
            </Link>
            <Link href="/prescriptions" className="hc-btn hc-btn-secondary">
              Order from a prescription
            </Link>
          </EmptyPanel>
        ) : (
          <div className="hc-cart-layout">
            <div className="hc-cartlines">
              {basket.items.map((item) => (
                <CartLine
                  key={item.medicine}
                  item={item}
                  prescriptions={prescriptions}
                  onQuantity={(quantity) => basket.setQuantity(item.medicine, quantity)}
                  onRemove={() => {
                    basket.remove(item.medicine);
                    notify(`${item.name} removed from your basket`);
                  }}
                  onAttach={(prescriptionId) => {
                    basket.setPrescription(item.medicine, prescriptionId);
                    notify(prescriptionId ? `Prescription ${prescriptionId} selected` : "Prescription removed");
                  }}
                />
              ))}
            </div>

            <CartSummary items={basket.items}>
              <Link href="/cart/fulfillment" className="hc-btn hc-btn-primary hc-btn-lg hc-btn-block">
                Find best fulfilment
              </Link>

              {uncovered.length > 0 ? (
                <p className="hc-inline-note hc-inline-note-warn">
                  <Icon name="rx" size={16} />
                  {uncovered.length === 1 ? `${uncovered[0].name} needs` : `${uncovered.length} medications need`} a
                  prescription. You can continue, and the pharmacy will ask for it before dispensing.
                </p>
              ) : null}

              <Link href="/search" className="hc-textlink hc-summary-link">
                Add another medication
                <Icon name="arrowRight" size={16} />
              </Link>
            </CartSummary>
          </div>
        )}
      </div>
    </PatientShell>
  );
}
