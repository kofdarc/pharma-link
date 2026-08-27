"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, LoadError, PageHead } from "@/components/patient/Page";
import { FulfillmentOption, WhyMultiplePharmacies } from "@/components/cart/FulfillmentParts";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useBasket } from "@/lib/basket";
import { useAutoPrescriptionMatch, useCheckoutPlan } from "@/lib/patient/checkout";
import { buildFulfillment, type FulfillmentPlan, type FulfillmentResult } from "@/lib/patient/fulfillment";
import { formatMoney, plural } from "@/lib/patient/format";
import { useAccount, usePrescriptions } from "@/lib/patient/store";

/**
 * How the basket can actually be filled.
 *
 * The screen the rest of the product exists to make possible. The patient asked
 * for medicines; HealthConnect answers with whole deliveries, already worked
 * out, and only mentions pharmacies where the patient benefits from knowing.
 * Nothing about sourcing, reservations or routing appears anywhere on it.
 */
export default function FulfillmentPage() {
  const router = useRouter();
  const basket = useBasket();
  const { choose } = useCheckoutPlan();
  const { prescriptions, ready: prescriptionsReady } = usePrescriptions();
  const account = useAccount();
  const { notify } = useToast();

  const [searching, setSearching] = useState(true);
  const [result, setResult] = useState<FulfillmentResult | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const items = basket.items;
  const basketReady = basket.ready;

  // Sourcing ranks pharmacies by how far they are from the door, so there is
  // nothing to plan against until the patient has an address on file.
  const deliverTo = account.addresses.find((entry) => entry.isDefault) ?? account.addresses[0] ?? null;
  const hasCoordinates = deliverTo?.latitude !== undefined && deliverTo?.longitude !== undefined;

  // Resolve prescription cover before the plans are built, so a plan carries
  // the same cover the checkout will later state.
  useAutoPrescriptionMatch(items, prescriptions, basketReady && prescriptionsReady, basket.setPrescription);

  useEffect(() => {
    if (!basketReady || !account.ready) return;
    if (!deliverTo || !hasCoordinates) {
      setSearching(false);
      return;
    }

    const controller = new AbortController();
    setSearching(true);
    setFailed(false);

    buildFulfillment(items, { latitude: deliverTo.latitude!, longitude: deliverTo.longitude! }, controller.signal)
      .then(setResult)
      .catch(() => {
        if (controller.signal.aborted) return;
        setFailed(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setSearching(false);
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basketReady, account.ready, deliverTo?.id, items, attempt]);

  useEffect(() => {
    if (!searching && result && result.plans.length > 0 && !selected) setSelected(result.plans[0].kind);
  }, [searching, result, selected]);

  const plan = result?.plans.find((entry) => entry.kind === selected) ?? null;
  const everythingAvailable = (result?.unavailable.length ?? 0) === 0;

  function continueToCheckout(chosen: FulfillmentPlan) {
    choose(chosen);
    router.push("/checkout");
  }

  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        {/* No page title: the hero below is this page's headline, and two
            stacked display headings would be one too many. */}
        <PageHead back={{ href: "/cart", label: "Basket" }} />

        {!basket.ready || !account.ready || searching ? (
          <SearchingState count={basket.items.length} />
        ) : basket.items.length > 0 && !deliverTo ? (
          <EmptyPanel
            icon="pin"
            title="Where should this go?"
            body="HealthConnect matches your basket to the pharmacies nearest you, so it needs a delivery address before it can work out how the order is filled."
          >
            <Link href="/account/addresses" className="hc-btn hc-btn-primary">
              Add a delivery address
            </Link>
            <Link href="/cart" className="hc-btn hc-btn-secondary">
              Back to basket
            </Link>
          </EmptyPanel>
        ) : failed ? (
          <LoadError
            title="We could not check availability just now"
            body="Your basket has not changed. This is usually a connection problem rather than a supply problem."
            onRetry={() => setAttempt((value) => value + 1)}
          />
        ) : basket.items.length === 0 ? (
          <EmptyPanel
            icon="search"
            title="There is nothing to fill yet"
            body="Add a medication to your basket and HealthConnect will work out where it can come from."
          >
            <Link href="/search" className="hc-btn hc-btn-primary">
              Search medications
            </Link>
          </EmptyPanel>
        ) : !result || result.plans.length === 0 ? (
          <EmptyPanel
            icon="info"
            title="No connected pharmacy can supply this basket right now"
            body="Supply changes through the day. You can check back later, or look for another strength or brand of the same medication."
          >
            <Link href="/cart" className="hc-btn hc-btn-secondary">
              Back to basket
            </Link>
            <Link href="/search" className="hc-btn hc-btn-primary">
              Search medications
            </Link>
          </EmptyPanel>
        ) : (
          <>
            <section className="hc-fulfil-hero">
              <h1 className="hc-h2">
                {everythingAvailable ? "We found a way to fill your order." : "We found most of your order."}
              </h1>
              <p className="hc-lead">
                {everythingAvailable
                  ? "HealthConnect coordinates the pharmacy pickups so everything reaches you in one delivery."
                  : "Some of your basket is not available from any connected pharmacy at the moment. You can continue with the rest."}
              </p>
              <ul className="hc-fulfil-facts">
                <li>
                  <Icon name="checkCircle" size={17} />
                  {result.availableCount} of {plural(result.totalCount, "medication")} available
                </li>
                <li>
                  <Icon name="pharmacy" size={17} />
                  {plan ? plural(plan.pharmacies.length, "pharmacy", "pharmacies") : "Pharmacies matched"}
                </li>
                <li>
                  <Icon name="truck" size={17} />
                  One coordinated delivery
                </li>
              </ul>
            </section>

            {result.unavailable.length > 0 ? <UnavailableNotice items={result.unavailable} /> : null}

            <div className="hc-fulfil-layout">
              <div>
                <fieldset className="hc-plans">
                  <legend className="hc-sr">Choose how your order is filled</legend>
                  {result.plans.map((entry, index) => (
                    <FulfillmentOption
                      key={entry.kind}
                      name="fulfilment"
                      plan={entry}
                      recommended={index === 0}
                      selected={entry.kind === selected}
                      onSelect={() => setSelected(entry.kind)}
                    />
                  ))}
                </fieldset>

                <WhyMultiplePharmacies />
              </div>

              <aside className="hc-summary hc-summary-sticky" aria-labelledby="fulfil-summary">
                <h2 className="hc-h3" id="fulfil-summary">
                  {plan ? plan.label : "Your delivery"}
                </h2>

                {plan ? (
                  <>
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
                        <dt>Estimated arrival</dt>
                        <dd>{plan.etaLabel}</dd>
                      </div>
                    </dl>

                    <div className="hc-summary-total">
                      <span>Estimated total</span>
                      <strong className="hc-num">{formatMoney(plan.total)}</strong>
                    </div>

                    <button
                      type="button"
                      className="hc-btn hc-btn-primary hc-btn-lg hc-btn-block"
                      onClick={() => {
                        continueToCheckout(plan);
                        notify(`${plan.label} selected`);
                      }}
                    >
                      Choose this option
                    </button>

                    <p className="hc-small">
                      Delivery times are estimates. Nothing is charged until you place the order on the next screen.
                    </p>
                  </>
                ) : null}
              </aside>
            </div>
          </>
        )}
      </div>
    </PatientShell>
  );
}

function SearchingState({ count }: { count: number }) {
  return (
    <div className="hc-page-body">
      <p className="hc-searching" role="status">
        <Icon name="network" size={17} />
        Checking {count > 0 ? plural(count, "medication") : "your basket"} against connected pharmacies
      </p>
      <CardSkeletons count={3} lines={2} />
    </div>
  );
}

/**
 * Partial availability, stated plainly and without a substitute in sight.
 *
 * Swapping one medicine for another is a clinical decision, so the options here
 * are limited to continuing, removing, or going back to look.
 */
function UnavailableNotice({ items }: { items: { medicineId: string; name: string }[] }) {
  return (
    <div className="hc-card hc-unavailable" role="status">
      <p className="hc-cover-head">
        <Icon name="info" size={16} />
        {plural(items.length, "medication")} not available right now
      </p>
      <ul className="hc-unavailable-list">
        {items.map((item) => (
          <li key={item.medicineId}>
            <strong>{item.name}</strong>
            <span className="hc-chip hc-chip-off">
              <span className="hc-dot" />
              Currently unavailable
            </span>
          </li>
        ))}
      </ul>
      <p className="hc-small">
        The options below cover the rest of your basket. HealthConnect does not substitute one medication for another;
        if you need an alternative, that is a conversation with your physician or pharmacist.
      </p>
      <div className="hc-actions">
        <Link href="/cart" className="hc-btn hc-btn-secondary hc-btn-sm">
          Edit basket
        </Link>
        <Link href="/search" className="hc-btn hc-btn-quiet hc-btn-sm">
          Search alternatives
        </Link>
      </div>
    </div>
  );
}
