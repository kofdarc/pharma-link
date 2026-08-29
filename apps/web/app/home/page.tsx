"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PatientShell } from "@/components/site/PatientShell";
import { usePatientUser } from "@/components/site/PatientGuard";
import { SearchLauncher } from "@/components/medicines/SearchLauncher";
import { ArrowLink } from "@/components/site/Section";
import { CardSkeletons } from "@/components/patient/Page";
import { OrderStatusTimeline, stageLabel } from "@/components/orders/OrderParts";
import { Icon } from "@/components/ui/Icon";
import { useRecentSearches } from "@/lib/recent-searches";
import { usePatientState } from "@/lib/patient/store";
import { daysUntil, formatDate, plural } from "@/lib/patient/format";
import { isClaimable, isOrderActive } from "@/lib/patient/types";

function greeting(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/**
 * The patient's landing screen.
 *
 * Three questions, in the order they are usually asked: what do I need to find,
 * where is what I already ordered, and what is coming up. Everything on it is a
 * doorway into a section rather than a place to do work, so each panel shows the
 * least it can and links onward.
 */
export default function PatientHomePage() {
  const router = useRouter();
  const user = usePatientUser();
  const { recent } = useRecentSearches();
  const { state, ready } = usePatientState();

  const firstName = user.first_name || state.profile.firstName;

  const currentOrder = state.orders.find(isOrderActive) ?? null;
  const activePrescription = state.prescriptions.find(isClaimable) ?? null;
  const nextRefill = state.refills
    .filter((refill) => refill.status === "active")
    .sort((a, b) => a.nextRefill.localeCompare(b.nextRefill))[0];

  return (
    <PatientShell>
      <section className="hc-home-top">
        <div className="hc-wrap">
          <h1 className="hc-display">
            <ClientGreeting name={firstName} />
          </h1>
          <p className="hc-body">What medication do you need today?</p>
          <div className="hc-home-search">
            <SearchLauncher placeholder="Search by medicine or generic name…" />
          </div>
        </div>
      </section>

      <div className="hc-wrap hc-home-grid">
        <div className="hc-home-col">
          {!ready ? (
            <CardSkeletons count={2} />
          ) : (
            <>
              {currentOrder ? (
                <section className="hc-card" aria-labelledby="home-order">
                  <div className="hc-card-head">
                    <div>
                      <p className="hc-card-label">Current order</p>
                      <h2 className="hc-h3 hc-home-cardtitle" id="home-order">
                        Order {currentOrder.id}
                      </h2>
                    </div>
                    <span className="hc-chip hc-chip-ok hc-status">
                      <span className="hc-dot" />
                      {stageLabel(currentOrder.stage)}
                    </span>
                  </div>

                  <dl className="hc-kv">
                    <div>
                      <dt>{currentOrder.scheduled ? "Delivery window" : "Estimated arrival"}</dt>
                      <dd>{currentOrder.arrivalWindow}</dd>
                    </div>
                  </dl>

                  <OrderStatusTimeline order={currentOrder} />

                  <hr className="hc-rule" />
                  <div className="hc-home-cardfoot">
                    <Link href={`/orders/${currentOrder.id}`} className="hc-btn hc-btn-secondary hc-btn-sm">
                      Track order
                    </Link>
                    <ArrowLink href="/orders">All orders</ArrowLink>
                  </div>
                </section>
              ) : null}

              {activePrescription ? (
                <section className="hc-card" aria-labelledby="home-rx">
                  <div className="hc-card-head">
                    <div>
                      <p className="hc-card-label">Active prescription</p>
                      <h2 className="hc-h3 hc-home-cardtitle" id="home-rx">
                        {activePrescription.prescriber.name}
                      </h2>
                    </div>
                    <span className="hc-chip hc-chip-rx">
                      <Icon name="rx" size={13} />
                      {activePrescription.id}
                    </span>
                  </div>

                  <dl className="hc-kv">
                    <div>
                      <dt>Issued</dt>
                      <dd>{formatDate(activePrescription.issuedOn)}</dd>
                    </div>
                    <div>
                      <dt>Valid until</dt>
                      <dd>{formatDate(activePrescription.validUntil)}</dd>
                    </div>
                    <div>
                      <dt>Medications</dt>
                      <dd>{plural(activePrescription.items.length, "medication")}</dd>
                    </div>
                  </dl>

                  <div className="hc-rxcard-items">
                    {activePrescription.items.map((item) => (
                      <p className="hc-rxcard-item" key={item.medicineId}>
                        <Icon name="pill" size={15} />
                        {item.name}
                        <span className="hc-num">
                          {item.prescribed} {item.unit}
                        </span>
                      </p>
                    ))}
                  </div>

                  <ArrowLink href={`/prescriptions/${activePrescription.id}`}>View prescription</ArrowLink>
                </section>
              ) : null}

              {!currentOrder && !activePrescription ? (
                <section className="hc-card">
                  <p className="hc-card-label">Getting started</p>
                  <h2 className="hc-h3 hc-home-cardtitle">Nothing in progress</h2>
                  <p className="hc-body" style={{ marginTop: 8 }}>
                    Search for a medication and HealthConnect will find which connected pharmacies can supply it, handle
                    the prescription if one is needed, and deliver it.
                  </p>
                  <Link href="/search" className="hc-btn hc-btn-primary" style={{ marginTop: 16 }}>
                    <Icon name="search" size={17} />
                    Search medications
                  </Link>
                </section>
              ) : null}
            </>
          )}
        </div>

        <div className="hc-home-col">
          {ready && nextRefill ? (
            <section className="hc-card" aria-labelledby="home-refill">
              <p className="hc-card-label">Refill coming up</p>
              <div className="hc-refill">
                <span className="hc-feature-icon">
                  <Icon name="refresh" size={19} />
                </span>
                <div>
                  <h2 className="hc-h3" id="home-refill">
                    {nextRefill.name}
                  </h2>
                  <p className="hc-small" style={{ marginTop: 3 }}>
                    {refillCopy(nextRefill.nextRefill)}
                  </p>
                </div>
              </div>
              <Link href="/refills" className="hc-btn hc-btn-secondary hc-btn-block">
                Manage refills
              </Link>
            </section>
          ) : null}

          {recent.length > 0 ? (
            <section className="hc-card" aria-labelledby="home-recent">
              <p className="hc-card-label" id="home-recent">
                Recently searched
              </p>
              <div className="hc-chiplist">
                {recent.map((term) => (
                  <button
                    type="button"
                    className="hc-chip-btn"
                    key={term}
                    onClick={() => router.push(`/search?q=${encodeURIComponent(term)}`)}
                  >
                    <Icon name="search" size={14} />
                    {term}
                  </button>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </PatientShell>
  );
}

function refillCopy(iso: string): string {
  const days = daysUntil(iso);
  if (days < 0) return `Was due ${formatDate(iso)}`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Next refill in ${days} days`;
}

/**
 * The time of day is only known on the client, so the greeting resolves after
 * mount. Until then the name alone is shown, which is stable on both sides.
 */
function ClientGreeting({ name }: { name: string }) {
  const [prefix, setPrefix] = useState<string | null>(null);
  useEffect(() => setPrefix(greeting(new Date().getHours())), []);
  return <>{prefix ? `${prefix}, ${name}` : name}</>;
}
