"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, asList } from "@/lib/api-client";
import { useBasket } from "@/lib/basket";
import type { DeliveryAddress, Paginated, PublicAvailability } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

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

  async function search(event?: FormEvent) {
    event?.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    setSearched(true);
    const params = new URLSearchParams({ q: query.trim(), sort });
    if (address) {
      params.set("lat", address.latitude);
      params.set("lng", address.longitude);
    }
    try {
      setResults(await apiFetch<PublicAvailability[]>(`/public/search/?${params.toString()}`));
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (searched && query.trim()) void search();
    // Re-run when the sort or address changes so ranking updates immediately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort, addressId]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Find a medicine near you</h1>
          <p className="muted">
            Search once across every connected pharmacy. We rank by how close it is, how well the pharmacy has
            served people before, and price where the pharmacy sets it.
          </p>
        </div>
        <Link className="button button-primary" href="/shop/basket">
          Basket ({basket.count})
        </Link>
      </div>

      <section className="panel">
        <form className="search-bar" onSubmit={search}>
          <Field label="Medicine or active ingredient">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="paracetamol, Panadol, vitamin D..."
            />
          </Field>
          <Field label="Deliver to">
            <select value={addressId} onChange={(event) => setAddressId(event.target.value)}>
              <option value="">No address selected</option>
              {addresses.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label} — {entry.area}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sort by">
            <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)}>
              <option value="best">Best match</option>
              <option value="distance">Closest</option>
              <option value="price">Cheapest</option>
              <option value="rating">Best rated</option>
            </select>
          </Field>
          <Button type="submit">Search</Button>
        </form>

        {addresses.length === 0 ? (
          <Notice>
            <Link href="/shop/addresses">Add a delivery address</Link> to get distance-based ranking and to order.
          </Notice>
        ) : null}
      </section>

      {loading ? <div className="skeleton-card" /> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {searched && !loading && results.length === 0 && !error ? (
        <EmptyState
          title="No connected pharmacy nearby has this right now."
          detail="We recorded the request so pharmacies in your area can see the demand they are missing."
        />
      ) : null}

      <section className="result-grid">
        {results.map((result) => (
          <article className="result-card" key={`${result.medicine.id}-${result.pharmacy.id}`}>
            <div className="section-header">
              <div>
                <h3>{result.medicine.brand_name}</h3>
                <p className="muted">
                  {[result.medicine.generic_name, result.medicine.strength, result.medicine.form].filter(Boolean).join(" ")}
                </p>
              </div>
              <Badge tone={statusTone(result.availability_status)}>{result.availability_status}</Badge>
            </div>

            <div className="price-row">
              <strong className="price">{result.unit_price ? `$${result.unit_price}` : "—"}</strong>
              <span className={result.is_price_regulated ? "tag tag-regulated" : "tag"}>{result.price_note}</span>
            </div>

            <div>
              <strong>{result.pharmacy.name}</strong>
              <p className="muted small">
                {result.pharmacy.area}
                {result.distance_km !== null ? ` · ${result.distance_km} km away` : ""}
                {result.pharmacy.rating_count > 0
                  ? ` · ★ ${result.pharmacy.rating} (${result.pharmacy.rating_count})`
                  : " · not yet rated"}
              </p>
              <p className="muted small">
                {result.pharmacy.fulfillment_success_rate}% of accepted orders fulfilled · ready in ~
                {result.pharmacy.preparation_minutes} min
              </p>
            </div>

            {result.medicine.requires_prescription ? (
              <Notice tone="danger">Prescription required. Add your prescription code at checkout.</Notice>
            ) : null}

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
                Add to basket
              </Button>
              <a className="button button-secondary" href={`tel:${result.pharmacy.phone}`}>
                Call
              </a>
            </div>
            <small className="muted">
              Orderable up to {result.available_up_to} unit(s) at a time. Updated{" "}
              {result.last_updated ? new Date(result.last_updated).toLocaleString() : "recently"}.
            </small>
          </article>
        ))}
      </section>

      {results.length > 0 ? <Notice>{results[0].disclaimer}</Notice> : null}
    </>
  );
}
