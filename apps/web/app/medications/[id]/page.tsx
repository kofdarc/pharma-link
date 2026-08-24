"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { AvailabilityBadge, MetaChip, PrescriptionBadge } from "@/components/medicines/Badges";
import { PackThumb } from "@/components/medicines/PackThumb";
import { formatPrice, sourcingLine } from "@/components/medicines/MedicineResult";
import { StateBlock } from "@/components/medicines/SearchStates";
import { FormAlert } from "@/components/site/FormField";
import { Icon } from "@/components/ui/Icon";
import { getMedicine } from "@/lib/catalog/service";
import { medicineLabel, type MedicineDetail } from "@/lib/catalog/types";
import { useBasket } from "@/lib/basket";

const MAX_QUANTITY = 10;

export default function MedicationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === "string" ? params.id : "";
  const basket = useBasket();

  const [medicine, setMedicine] = useState<MedicineDetail | null>(null);
  const [degraded, setDegraded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [quantity, setQuantity] = useState(1);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setLoading(true);
    setDegraded(false);
    getMedicine(id, controller.signal)
      .then((outcome) => {
        setMedicine(outcome.medicine);
        // Only worth saying when there is something on screen to qualify.
        setDegraded(outcome.usedFallback && outcome.medicine !== null);
      })
      .catch(() => setMedicine(null))
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [id]);

  if (loading) {
    return (
      <div className="hc">
        <SiteHeader />
        <main className="hc-main hc-wrap" style={{ paddingBlock: 56 }}>
          <div style={{ display: "grid", gap: 18, maxWidth: 620 }}>
            <span className="hc-skel" style={{ width: 140, height: 140, borderRadius: 28 }} />
            <span className="hc-skel" style={{ width: "70%", height: 38 }} />
            <span className="hc-skel" style={{ width: "45%", height: 18 }} />
            <span className="hc-skel" style={{ width: 260, height: 26, borderRadius: 999 }} />
          </div>
        </main>
        <SiteFooter />
      </div>
    );
  }

  if (!medicine) {
    return (
      <div className="hc">
        <SiteHeader />
        <main className="hc-main hc-wrap" style={{ paddingBlock: 64 }}>
          <StateBlock
            icon="search"
            title="We couldn't find that medication"
            body="The link may be out of date, or the product may no longer be listed."
          >
            <Link href="/search" className="hc-btn hc-btn-primary">
              Search medications
            </Link>
          </StateBlock>
        </main>
        <SiteFooter />
      </div>
    );
  }

  const orderable = medicine.availability !== "unavailable";

  return (
    <div className="hc">
      <SiteHeader />

      <main className="hc-main">
        <div className="hc-wrap">
          <nav className="hc-crumbs" aria-label="Breadcrumb">
            <Link href="/search">Search</Link>
            <Icon name="chevronRight" size={13} />
            <span aria-current="page">{medicineLabel(medicine)}</span>
          </nav>

          <header className="hc-med-head" style={{ marginTop: 24 }}>
            <PackThumb brand={medicine.brand} image={medicine.image} size="xl" />
            <div>
              <h1 className="hc-med-title">
                {medicine.brand} {medicine.strength ? <span>{medicine.strength}</span> : null}
              </h1>
              {medicine.generic ? <p className="hc-med-generic">{medicine.generic}</p> : null}
              <div className="hc-med-chips">
                <AvailabilityBadge state={medicine.availability} />
                <PrescriptionBadge required={medicine.requiresPrescription} />
                {medicine.form ? <MetaChip>{medicine.form}</MetaChip> : null}
                {medicine.packSize ? <MetaChip>{medicine.packSize}</MetaChip> : null}
              </div>
            </div>
          </header>

          {degraded ? (
            <div style={{ marginTop: 20 }}>
              <FormAlert tone="info">
                Live availability isn&apos;t reachable right now, so this is a sample listing. The price and the pharmacies
                shown may not reflect what is currently stocked.
              </FormAlert>
            </div>
          ) : null}
        </div>

        <div className="hc-wrap hc-med">
          <div>
            <section>
              <h2 className="hc-h3">Product details</h2>
              <dl className="hc-kv" style={{ marginTop: 14 }}>
                <div>
                  <dt>Active ingredient</dt>
                  <dd>{medicine.generic || "Not listed"}</dd>
                </div>
                <div>
                  <dt>Form</dt>
                  <dd>{medicine.form || "Not listed"}</dd>
                </div>
                <div>
                  <dt>Pack size</dt>
                  <dd>{medicine.packSize || "Varies by pharmacy"}</dd>
                </div>
                <div>
                  <dt>Manufacturer</dt>
                  <dd>{medicine.manufacturer || "Not listed"}</dd>
                </div>
              </dl>
              <p className="hc-small" style={{ marginTop: 18 }}>
                Product information only. HealthConnect does not provide dosage, treatment or medical advice — follow the
                instructions from your physician or pharmacist.
              </p>
            </section>

            {medicine.requiresPrescription ? (
              <section className="hc-med-section">
                <h2 className="hc-h3">Prescription</h2>
                <div className="hc-card hc-card-quiet" style={{ marginTop: 14 }}>
                  <div className="hc-rxnotice-head">
                    <Icon name="rx" size={17} />
                    A prescription is required
                  </div>
                  <p className="hc-body" style={{ marginTop: 8 }}>
                    A valid prescription will be needed before this medicine can be dispensed. If your physician issued one
                    through HealthConnect it can be attached to your order; otherwise the pharmacy will ask for it at hand-over.
                  </p>
                </div>
              </section>
            ) : null}

            {medicine.related.length > 0 ? (
              <section className="hc-med-section">
                <h2 className="hc-h3">Other products with the same listed active ingredient</h2>
                <p className="hc-small" style={{ margin: "6px 0 14px" }}>
                  Listed for reference. Whether one product can be used in place of another is a decision for your physician or
                  pharmacist.
                </p>
                <div className="hc-related">
                  {medicine.related.map((option) => (
                    <Link className="hc-related-item" href={`/medications/${encodeURIComponent(option.id)}`} key={option.id}>
                      <PackThumb brand={option.brand} image={option.image} />
                      <span className="hc-related-body">
                        <strong>{medicineLabel(option)}</strong>
                        <span className="hc-related-sub">
                          {option.form}
                          {option.fromPrice !== null ? ` · from ${formatPrice(option.fromPrice)}` : ""}
                        </span>
                      </span>
                      <AvailabilityBadge state={option.availability} />
                    </Link>
                  ))}
                </div>
              </section>
            ) : null}
          </div>

          <aside className="hc-buybox" aria-label="Order this medication">
            <div className="hc-buybox-price">
              {medicine.fromPrice !== null ? (
                <>
                  <strong>{formatPrice(medicine.fromPrice)}</strong>
                  <span className="hc-small">from, per pack</span>
                </>
              ) : (
                <span className="hc-body">Price confirmed when a pharmacy is matched</span>
              )}
            </div>

            <div className="hc-avail">
              <p className="hc-avail-head">
                <Icon name={orderable ? "checkCircle" : "info"} size={17} />
                {orderable ? "Available through HealthConnect" : "Not available right now"}
              </p>
              <p className="hc-small">{sourcingLine(medicine)}.</p>
              <p className="hc-small">
                {orderable
                  ? "Availability is confirmed when you continue with your order."
                  : "Try a different strength, or check back — connected pharmacies update throughout the day."}
              </p>
            </div>

            {orderable ? (
              <>
                <div className="hc-qty">
                  <span className="hc-label" id="qty-label">
                    Quantity
                  </span>
                  <div className="hc-stepper" role="group" aria-labelledby="qty-label">
                    <button
                      type="button"
                      onClick={() => setQuantity((value) => Math.max(1, value - 1))}
                      disabled={quantity <= 1}
                      aria-label="Decrease quantity"
                    >
                      <Icon name="minus" size={16} />
                    </button>
                    <output aria-live="polite">{quantity}</output>
                    <button
                      type="button"
                      onClick={() => setQuantity((value) => Math.min(MAX_QUANTITY, value + 1))}
                      disabled={quantity >= MAX_QUANTITY}
                      aria-label="Increase quantity"
                    >
                      <Icon name="plus" size={16} />
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  className="hc-btn hc-btn-primary hc-btn-lg hc-btn-block"
                  onClick={() => {
                    basket.add({
                      medicine: medicine.id,
                      name: medicineLabel(medicine),
                      generic: medicine.generic,
                      quantity,
                      requires_prescription: medicine.requiresPrescription,
                      unit_price: medicine.fromPrice
                    });
                    setAdded(true);
                  }}
                >
                  Add to basket
                </button>

                {added ? (
                  <p className="hc-field-hint" role="status" style={{ textAlign: "center" }}>
                    Added to your basket. <Link href="/cart" className="hc-textlink">View basket</Link>
                  </p>
                ) : null}
              </>
            ) : (
              <Link href="/search" className="hc-btn hc-btn-secondary hc-btn-lg hc-btn-block">
                Search for an alternative
              </Link>
            )}

            {medicine.requiresPrescription ? (
              <div className="hc-rxnotice">
                <p className="hc-rxnotice-head">
                  <Icon name="rx" size={16} />
                  Prescription required
                </p>
                <p>A valid prescription will be needed before this medicine can be dispensed.</p>
              </div>
            ) : null}
          </aside>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
