"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { AvailabilityBadge, MetaChip, NssfBadge, PrescriptionBadge } from "@/components/medicines/Badges";
import { PackThumb } from "@/components/medicines/PackThumb";
import { formatPrice, sourcingLine } from "@/components/medicines/MedicineResult";
import { StateBlock } from "@/components/medicines/SearchStates";
import { Icon } from "@/components/ui/Icon";
import { getMedicine } from "@/lib/catalog/service";
import { medicineLabel, type MedicineDetail } from "@/lib/catalog/types";
import { useBasket } from "@/lib/basket";

const MAX_QUANTITY = 10;

// How many same-composition products the detail page previews inline. The rest
// stay one tap away on /search?composition=, which shows the full, filterable set.
const SAME_COMPOSITION_PREVIEW = 8;

/**
 * Rough out-of-pocket estimate for an NSSF-covered medicine: the Fund pays its rate
 * against the cheaper of the shelf price and the NSSF reference price, and the patient
 * pays the rest plus anything the shelf price runs over the reference. Needs a rate and
 * at least one price to say anything, so returns null otherwise.
 */
function nssfEstimate(medicine: MedicineDetail): number | null {
  if (!medicine.nssfCovered || typeof medicine.nssfReimbursementRate !== "number") return null;
  const shelf = medicine.fromPrice;
  const reference = medicine.nssfReferencePrice;
  const basis = typeof reference === "number" ? reference : shelf;
  if (typeof basis !== "number") return null;
  const reimbursableBase = typeof shelf === "number" ? Math.min(shelf, basis) : basis;
  const reimbursed = (medicine.nssfReimbursementRate / 100) * reimbursableBase;
  const total = typeof shelf === "number" ? shelf : basis;
  return Math.max(0, Number((total - reimbursed).toFixed(2)));
}

export default function MedicationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = typeof params.id === "string" ? params.id : "";
  const basket = useBasket();

  const [medicine, setMedicine] = useState<MedicineDetail | null>(null);
  // Distinct from `medicine === null`: "we couldn't ask" is not "no such
  // medicine", and telling a patient a product doesn't exist because a request
  // failed is the wrong answer.
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [added, setAdded] = useState(false);
  const [showCompositionNote, setShowCompositionNote] = useState(false);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    getMedicine(id, controller.signal)
      .then((found) => setMedicine(found))
      .catch(() => {
        if (controller.signal.aborted) return;
        setMedicine(null);
        setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [id, attempt]);

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

  if (error) {
    return (
      <div className="hc">
        <SiteHeader />
        <main className="hc-main hc-wrap" style={{ paddingBlock: 64 }}>
          <StateBlock
            icon="alert"
            tone="alert"
            title="We couldn't load this medication"
            body="Something went wrong on our side, so we can't show what pharmacies currently hold. Nothing about this product has changed."
          >
            <button type="button" className="hc-btn hc-btn-primary" onClick={() => setAttempt((value) => value + 1)}>
              Try again
            </button>
            <Link href="/search" className="hc-btn hc-btn-secondary">
              Search medications
            </Link>
          </StateBlock>
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

  const addCurrentToBasket = () => {
    basket.add({
      medicine: medicine.id,
      name: medicineLabel(medicine),
      generic: medicine.generic,
      quantity,
      requires_prescription: medicine.requiresPrescription,
      unit_price: medicine.fromPrice
    });
  };

  // Same query the "Same composition" rail is built from, handed to /search so the
  // full list there is guaranteed to match the preview here.
  const sameCompositionHref = `/search?composition=${encodeURIComponent(medicine.id)}&ref=${encodeURIComponent(
    medicine.brand
  )}`;

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
              {medicine.activeIngredient || medicine.generic ? (
                <p className="hc-med-generic">{medicine.activeIngredient || medicine.generic}</p>
              ) : null}
              <div className="hc-med-chips">
                <AvailabilityBadge state={medicine.availability} />
                <PrescriptionBadge required={medicine.requiresPrescription} />
                <NssfBadge covered={medicine.nssfCovered} rate={medicine.nssfReimbursementRate} />
                {medicine.form ? <MetaChip>{medicine.form}</MetaChip> : null}
                {medicine.packSize ? <MetaChip>{medicine.packSize}</MetaChip> : null}
              </div>
            </div>
          </header>

        </div>

        <div className="hc-wrap hc-med">
          <div>
            <section>
              <h2 className="hc-h3">Product details</h2>
              <dl className="hc-spec" style={{ marginTop: 14 }}>
                <div className="hc-spec-row">
                  <dt>Active ingredient</dt>
                  <dd>
                    {medicine.activeIngredient || medicine.generic || <span className="hc-spec-empty">Not listed</span>}
                  </dd>
                </div>
                <div className="hc-spec-row">
                  <dt>Form</dt>
                  <dd>{medicine.form || <span className="hc-spec-empty">Not listed</span>}</dd>
                </div>
                <div className="hc-spec-row">
                  <dt>Pack size</dt>
                  <dd>{medicine.packSize || <span className="hc-spec-empty">Varies by pharmacy</span>}</dd>
                </div>
                <div className="hc-spec-row">
                  <dt>Manufacturer</dt>
                  <dd>{medicine.manufacturer || <span className="hc-spec-empty">Not listed</span>}</dd>
                </div>
              </dl>

              <details className="hc-spec-accordion">
                <summary>
                  <span>Sourcing &amp; regulatory details</span>
                  <Icon name="chevronDown" className="hc-spec-accordion-icon" size={16} />
                </summary>
                <dl className="hc-spec hc-spec-nested">
                  <div className="hc-spec-row">
                    <dt>Country of origin</dt>
                    <dd>{medicine.country || <span className="hc-spec-empty">Not listed</span>}</dd>
                  </div>
                  <div className="hc-spec-row">
                    <dt>Local agent</dt>
                    <dd>{medicine.agent || <span className="hc-spec-empty">Not listed</span>}</dd>
                  </div>
                  <div className="hc-spec-row">
                    <dt>MoPH registration</dt>
                    <dd>{medicine.registrationNumber || <span className="hc-spec-empty">Not listed</span>}</dd>
                  </div>
                  {medicine.atcCode ? (
                    <div className="hc-spec-row">
                      <dt>WHO classification (ATC)</dt>
                      <dd>{medicine.atcCode}</dd>
                    </div>
                  ) : null}
                </dl>
              </details>

              <p className="hc-small" style={{ marginTop: 18 }}>
                Product pricing and details are sourced from the <a href="https://moph.gov.lb/en/Drugs/index/3/3974/lebanon-national-drugs-database" target="_blank" rel="noopener noreferrer">Lebanon National Drugs Database</a> maintained by the Ministry of Public Health (MoPH).
              </p>
            </section>

            <section className="hc-med-section">
              <h2 className="hc-h3">Insurance (NSSF)</h2>
              {medicine.nssfCovered ? (
                <div className="hc-card hc-card-quiet" style={{ marginTop: 14 }}>
                  <div className="hc-rxnotice-head">
                    <Icon name="shield" size={17} />
                    Reimbursed by the National Social Security Fund
                  </div>
                  <dl className="hc-spec hc-spec-nested" style={{ marginTop: 12 }}>
                    <div className="hc-spec-row">
                      <dt>Reimbursement rate</dt>
                      <dd>
                        {typeof medicine.nssfReimbursementRate === "number" ? (
                          `${medicine.nssfReimbursementRate % 1 === 0 ? medicine.nssfReimbursementRate : medicine.nssfReimbursementRate.toFixed(2)}% of the reference price`
                        ) : (
                          <span className="hc-spec-empty">On the NSSF list; rate not on file</span>
                        )}
                      </dd>
                    </div>
                    <div className="hc-spec-row">
                      <dt>NSSF reference price</dt>
                      <dd>
                        {typeof medicine.nssfReferencePrice === "number" ? (
                          formatPrice(medicine.nssfReferencePrice)
                        ) : (
                          <span className="hc-spec-empty">Not on file</span>
                        )}
                      </dd>
                    </div>
                    {nssfEstimate(medicine) !== null ? (
                      <div className="hc-spec-row">
                        <dt>Estimated you pay</dt>
                        <dd>
                          {formatPrice(nssfEstimate(medicine) as number)}
                          <span className="hc-spec-empty"> · estimate before any private top-up cover</span>
                        </dd>
                      </div>
                    ) : null}
                  </dl>
                  <p className="hc-small" style={{ marginTop: 10 }}>
                    Since 2024 the NSSF reimburses against the cheapest equivalent formulation, so a more expensive brand
                    leaves a larger share with you. Any private or employer top-up cover applies on top of this.
                  </p>
                </div>
              ) : (
                <p className="hc-small" style={{ marginTop: 10 }}>
                  This medicine is not on the platform&apos;s NSSF reimbursable list. That is not confirmation the Fund
                  refuses it, as coverage may simply not be recorded here yet. Check with your pharmacy or the NSSF.
                </p>
              )}
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
              <section className="hc-med-section hc-comp" aria-labelledby="same-composition-heading">
                <div className="hc-comp-head">
                  <h2 className="hc-h3" id="same-composition-heading">
                    Same composition
                  </h2>
                  <Link href={sameCompositionHref} className="hc-comp-seeall">
                    See all
                    <Icon name="arrowRight" size={15} />
                  </Link>
                </div>

                <ul className="hc-comp-rail">
                  {medicine.related.slice(0, SAME_COMPOSITION_PREVIEW).map((option) => (
                    <li className="hc-comp-item" key={option.id}>
                      <Link className="hc-comp-card" href={`/medications/${encodeURIComponent(option.id)}`}>
                        <PackThumb brand={option.brand} image={option.image} size="result" />
                        <span className="hc-comp-name">{medicineLabel(option)}</span>
                        <span className="hc-comp-meta">
                          {option.form || "Details on product page"}
                        </span>
                        <span className="hc-comp-foot">
                          <span className="hc-comp-price">
                            {option.fromPrice !== null ? formatPrice(option.fromPrice) : "Price at checkout"}
                          </span>
                          <AvailabilityBadge state={option.availability} />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>

                <p className="hc-small hc-comp-intro">
                  <button
                    type="button"
                    className="hc-linkbtn"
                    aria-expanded={showCompositionNote}
                    onClick={() => setShowCompositionNote((value) => !value)}
                  >
                    {showCompositionNote ? "Show less" : "What does this mean?"}
                  </button>
                </p>
                {showCompositionNote ? (
                  <p className="hc-small hc-comp-note">
                    Same composition is not the same as interchangeable, as formulation or manufacturing differences can still
                    matter. This is not a recommendation to switch, only your physician or pharmacist can advise on
                    substitution.
                  </p>
                ) : null}
              </section>
            ) : null}
          </div>

          <aside className="hc-buybox" aria-label="Order this medication">
            <div className="hc-buybox-price">
              {medicine.fromPrice !== null ? (
                <>
                  <strong>{formatPrice(medicine.fromPrice)}</strong>
                  <span className="hc-small">per pack</span>
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
                    addCurrentToBasket();
                    router.push("/cart/fulfillment");
                  }}
                >
                  Buy now
                </button>

                <button
                  type="button"
                  className="hc-btn hc-btn-secondary hc-btn-lg hc-btn-block"
                  onClick={() => {
                    addCurrentToBasket();
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
