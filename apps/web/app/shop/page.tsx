"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, asList } from "@/lib/api-client";
import { useBasket } from "@/lib/basket";
import { useTranslations } from "@/lib/i18n/context";
import { useShopperLocation } from "@/lib/location";
import type { DeliveryAddress, Paginated, PublicAvailability } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ProductThumb } from "@/components/ui/ProductThumb";

type SortMode = "best" | "distance" | "price" | "rating";

/**
 * Unified availability search for shoppers.
 *
 * The point is that the shopper does NOT care which pharmacy it comes from. Results are
 * ranked by distance from their saved address, past shopper experience (rating), fulfilment
 * reliability and price, and quantities are shown only up to an orderable ceiling.
 */
export default function ShopSearchPage() {
  const basket = useBasket();
  const t = useTranslations();
  const location = useShopperLocation();
  const [addresses, setAddresses] = useState<DeliveryAddress[]>([]);
  const [addressId, setAddressId] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("best");
  const [results, setResults] = useState<PublicAvailability[]>([]);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

  /**
   * Where to rank from: the device if the shopper has shared it, otherwise the address
   * they picked to deliver to.
   *
   * The device wins because it answers a different question. The delivery address is where
   * the order should end up; the device is where the shopper is standing, and "which of
   * these can I walk to right now" is the question this page gets asked most.
   */
  const origin = location.position
    ? { lat: String(location.position.latitude), lng: String(location.position.longitude) }
    : address
      ? { lat: address.latitude, lng: address.longitude }
      : null;

  async function search(event?: FormEvent) {
    event?.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    setSearched(true);
    const params = new URLSearchParams({ q: query.trim(), sort });
    if (origin) {
      params.set("lat", origin.lat);
      params.set("lng", origin.lng);
    }
    try {
      setResults(await apiFetch<PublicAvailability[]>(`/public/search/?${params.toString()}`));
    } catch {
      setError(t("search.searchFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (searched && query.trim()) void search();
    // Re-run when the sort or the point we measure from changes, so ranking updates
    // immediately - including the moment a shared device location supersedes the address.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort, addressId, origin?.lat, origin?.lng]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("shop.browseTitle")}</h1>
          <p className="muted">{t("shop.browseSubtitle")}</p>
        </div>
        <Link className="button button-primary" href="/shop/basket">
          {t("shop.basketCount", { count: basket.count })}
        </Link>
      </div>

      <section className="panel">
        <form className="search-bar" onSubmit={search}>
          <Field label={t("shop.medicineOrIngredient")}>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("shop.medicineSearchPlaceholder")}
            />
          </Field>
          <Field label={t("shop.deliverTo")}>
            <select value={addressId} onChange={(event) => setAddressId(event.target.value)}>
              <option value="">{t("shop.noAddressSelected")}</option>
              {addresses.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label} — {entry.area}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("shop.sortBy")}>
            <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)}>
              <option value="best">{t("shop.sortBest")}</option>
              <option value="distance">{t("shop.sortClosest")}</option>
              <option value="price">{t("shop.sortCheapest")}</option>
              <option value="rating">{t("shop.sortRated")}</option>
            </select>
          </Field>
          <Button type="submit">{t("common.search")}</Button>
        </form>

        <p className="hc-locate" style={{ marginTop: 10 }}>
          {location.position ? (
            <>
              <span>
                {t("shop.usingMyLocation", { label: location.position.label ? ` (${location.position.label})` : "" })}
              </span>
              <button type="button" onClick={location.clear}>
                {t("shop.locationOff")}
              </button>
            </>
          ) : location.supported ? (
            <>
              <span>{location.error ? t("shop.locationFailed") : ""}</span>
              <button type="button" onClick={location.request} disabled={location.pending}>
                {location.pending ? t("pharmacySettings.locating") : t("shop.useMyLocation")}
              </button>
            </>
          ) : null}
        </p>

        {addresses.length === 0 ? (
          <Notice>
            <Link href="/shop/addresses">{t("shop.addAddress")}</Link> {t("shop.addAddressHint")}
          </Notice>
        ) : null}
      </section>

      {loading ? <div className="skeleton-card" /> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {searched && !loading && results.length === 0 && !error ? (
        <EmptyState title={t("shop.noResultsTitle")} detail={t("shop.noResultsDetail")} />
      ) : null}

      <section className="result-grid">
        {results.map((result) => (
          <article className="result-card" key={`${result.medicine.id}-${result.pharmacy.id}`}>
            <div className="section-header">
              <div className="actions">
                <ProductThumb src={result.medicine.image} alt={result.medicine.brand_name} />
                <div>
                  <h3>{result.medicine.brand_name}</h3>
                  <p className="muted">
                    {[result.medicine.generic_name, result.medicine.strength, result.medicine.form].filter(Boolean).join(" ")}
                  </p>
                </div>
              </div>
              <Badge status tone={statusTone(result.availability_status)}>{result.availability_status}</Badge>
            </div>

            <div className="price-row">
              <strong className="price">{result.unit_price ? `$${result.unit_price}` : "—"}</strong>
              <span className={result.is_price_regulated ? "tag tag-regulated" : "tag"}>{result.price_note}</span>
            </div>

            <div>
              <strong>{result.pharmacy.name}</strong>
              <p className="muted small">
                {result.pharmacy.area}
                {result.distance_km !== null ? ` · ${t("shop.distanceAway", { distance: result.distance_km })}` : ""}
                {result.pharmacy.rating_count > 0
                  ? ` · ★ ${result.pharmacy.rating} (${result.pharmacy.rating_count})`
                  : ` · ${t("shop.notYetRated")}`}
              </p>
              <p className="muted small">
                {t("shop.fulfillmentRate", { rate: result.pharmacy.fulfillment_success_rate, minutes: result.pharmacy.preparation_minutes })}
              </p>
            </div>

            {result.medicine.requires_prescription ? <Notice tone="danger">{t("shop.prescriptionRequired")}</Notice> : null}

            <div className="actions">
              <Button
                type="button"
                onClick={() =>
                  basket.add({
                    medicine: result.medicine.id,
                    name: `${result.medicine.brand_name} ${result.medicine.strength}`.trim(),
                    quantity: 1,
                    requires_prescription: result.medicine.requires_prescription
                  })
                }
                disabled={!result.pharmacy.accepts_online_orders || result.available_up_to === 0}
              >
                {t("shop.addToBasket")}
              </Button>
              <a className="button button-secondary" href={`tel:${result.pharmacy.phone}`}>
                {t("shop.call")}
              </a>
            </div>
            <small className="muted">
              {t("shop.orderableUpTo", {
                count: result.available_up_to,
                when: result.last_updated ? new Date(result.last_updated).toLocaleString() : t("shop.recently")
              })}
            </small>
          </article>
        ))}
      </section>

      {results.length > 0 ? <Notice tone="muted">{results[0].disclaimer}</Notice> : null}
    </>
  );
}
