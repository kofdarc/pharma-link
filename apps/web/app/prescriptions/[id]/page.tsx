"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead } from "@/components/patient/Page";
import { PrescriptionAccessDialog } from "@/components/prescriptions/PrescriptionAccessDialog";
import { PrescriptionMedicationRow, PrescriptionStatusChip } from "@/components/prescriptions/PrescriptionParts";
import { useToast } from "@/components/patient/Toast";
import { Icon } from "@/components/ui/Icon";
import { useBasket } from "@/lib/basket";
import { usePrescriptions } from "@/lib/patient/store";
import { formatDate, plural } from "@/lib/patient/format";
import { isClaimable, remaining, type Prescription } from "@/lib/patient/types";

/**
 * A single prescription.
 *
 * This is the trust screen of the patient area, so it is built to read like a
 * document: a header that states what it is and how long it lasts, the person
 * who wrote it, and then the medications. The security treatment is deliberately
 * quiet, a line of text and a small mark rather than a large green tick, because
 * a document that shouts about being genuine reads as less genuine.
 */
function PrescriptionDetailScreen() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === "string" ? decodeURIComponent(params.id) : "";
  const router = useRouter();
  const search = useSearchParams();
  const { prescriptions, ready } = usePrescriptions();
  const basket = useBasket();
  const { notify } = useToast();

  const [accessOpen, setAccessOpen] = useState(false);
  const orderButton = useRef<HTMLButtonElement>(null);

  const prescription = prescriptions.find((entry) => entry.id === id);

  // Arriving from the "Order medications" action on the list: bring the patient
  // to the action rather than firing it for them, so nothing lands in a basket
  // without them seeing what and how much.
  useEffect(() => {
    if (ready && search.get("order") === "1") orderButton.current?.focus();
  }, [ready, search]);


  if (!ready) {
    return (
      <PatientShell>
        <div className="hc-wrap hc-page">
          <CardSkeletons count={2} lines={5} />
        </div>
      </PatientShell>
    );
  }

  if (!prescription) {
    return (
      <PatientShell>
        <div className="hc-wrap hc-page">
          <PageHead title="Prescription" back={{ href: "/prescriptions", label: "Prescriptions" }} />
          <EmptyPanel
            icon="search"
            title="We could not find that prescription"
            body="The link may be out of date, or the prescription may no longer be on your account."
          >
            <Link href="/prescriptions" className="hc-btn hc-btn-primary">
              Back to prescriptions
            </Link>
          </EmptyPanel>
        </div>
      </PatientShell>
    );
  }

  const claimable = isClaimable(prescription);
  const claimableItems = prescription.items.filter((item) => remaining(item) > 0);
  const partlyStarted = prescription.items.some((item) => item.dispensed > 0);

  function orderClaimable(target: Prescription) {
    const items = target.items.filter((item) => remaining(item) > 0);
    for (const item of items) {
      basket.add({
        medicine: item.medicineId,
        name: item.name,
        generic: item.generic,
        quantity: 1,
        requires_prescription: true,
        // A prescription records what was authorised, not what anything costs.
        // The price comes from the sourcing quote once pharmacies are matched.
        unit_price: null,
        prescription_id: target.id
      });
    }
    notify(`${plural(items.length, "medication")} added to your basket`);
    router.push("/cart");
  }

  return (
    <PatientShell>
      <div className="hc-wrap hc-page hc-rxdetail">
        <PageHead title="Digital prescription" back={{ href: "/prescriptions", label: "Prescriptions" }} />

        <div className="hc-rxdoc">
          <header className="hc-rxdoc-head">
            <div className="hc-rxdoc-ident">
              <p className="hc-card-label hc-num">{prescription.id}</p>
              <p className="hc-rxdoc-verified">
                <Icon name="shield" size={14} />
                Issued and verified through HealthConnect
              </p>
            </div>
            <PrescriptionStatusChip status={prescription.status} />
          </header>

          <dl className="hc-kv hc-rxdoc-dates">
            <div>
              <dt>Issued</dt>
              <dd>{formatDate(prescription.issuedOn)}</dd>
            </div>
            <div>
              <dt>Valid until</dt>
              <dd>{formatDate(prescription.validUntil)}</dd>
            </div>
            <div>
              <dt>Prescribed by</dt>
              <dd>{prescription.prescriber.name}</dd>
            </div>
            <div>
              <dt>Practice</dt>
              <dd>{prescription.prescriber.specialty}</dd>
            </div>
          </dl>

          <hr className="hc-rule" />

          <section aria-labelledby="rx-meds">
            <h2 className="hc-h3" id="rx-meds">
              Prescribed medications
            </h2>
            <ul className="hc-rxmeds">
              {prescription.items.map((item) => (
                <PrescriptionMedicationRow key={item.medicineId} item={item} claimable={claimable} />
              ))}
            </ul>
          </section>

          <div className="hc-rxdoc-actions">
            <button
              ref={orderButton}
              type="button"
              className="hc-btn hc-btn-primary hc-btn-lg"
              disabled={!claimable}
              onClick={() => orderClaimable(prescription)}
            >
              {partlyStarted && claimable ? "Order remaining medications" : "Order available medications"}
            </button>
            <button type="button" className="hc-btn hc-btn-secondary hc-btn-lg" onClick={() => setAccessOpen(true)}>
              <Icon name="qr" size={17} />
              Show prescription access
            </button>
          </div>

          {/* A disabled button that does not say why is just a dead end. */}
          {!claimable ? (
            <p className="hc-inline-note hc-inline-note-warn">
              <Icon name="info" size={16} />
              {prescription.status === "expired"
                ? `This prescription expired on ${formatDate(prescription.validUntil)}. Your physician can issue a new one.`
                : "Everything on this prescription has been collected, so there is nothing left to order."}
            </p>
          ) : claimableItems.length < prescription.items.length ? (
            <p className="hc-inline-note">
              <Icon name="info" size={16} />
              {plural(claimableItems.length, "medication")} on this prescription can still be collected. Fully collected
              items are left out of the order.
            </p>
          ) : null}

          <p className="hc-small hc-rxdoc-foot">
            Dosage and duration are set by your physician. HealthConnect passes the prescription to the pharmacy and does
            not change what was prescribed.
          </p>
        </div>
      </div>

      <PrescriptionAccessDialog prescription={prescription} open={accessOpen} onClose={() => setAccessOpen(false)} />
    </PatientShell>
  );
}

/**
 * `useSearchParams` opts a client route out of static prerendering unless it is
 * inside a boundary, so the shell renders immediately and the screen resolves
 * once the query string is known. Same pattern as `/search` and `/login`.
 */
export default function PrescriptionDetailPage() {
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
      <PrescriptionDetailScreen />
    </Suspense>
  );
}
