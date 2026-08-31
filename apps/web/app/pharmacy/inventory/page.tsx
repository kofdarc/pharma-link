"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InventoryBatch, Paginated } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

// Mirrors DRF's PAGE_SIZE in apps/api/config/settings.py. Only used to render the
// "page X of Y" hint; navigation itself relies on the count returned per request.
const PAGE_SIZE = 25;

type AppliedFilters = { q: string; filter: string };

// Up to 5 page numbers centred on the current page, clamped to [1, total].
function pageWindow(current: number, total: number): number[] {
  const span = 5;
  let start = Math.max(1, current - Math.floor(span / 2));
  const end = Math.min(total, start + span - 1);
  start = Math.max(1, end - span + 1);
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

export default function InventoryPage() {
  const t = useTranslations();
  const [items, setItems] = useState<InventoryBatch[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  // Filters actually in effect. Only updated on submit, so paging through results
  // never picks up half-typed search text.
  const [applied, setApplied] = useState<AppliedFilters>({ q: "", filter: "" });

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  async function load(nextPage: number, filters: AppliedFilters) {
    setError("");
    setLoading(true);
    const params = new URLSearchParams();
    if (filters.q) params.set("q", filters.q);
    if (filters.filter) params.set(filters.filter, "true");
    params.set("page", String(nextPage));
    try {
      const payload = await apiFetch<Paginated<InventoryBatch>>(`/pharmacy/inventory/?${params}`);
      setItems(payload.results);
      setCount(payload.count);
      setPage(nextPage);
    } catch {
      setError(t("pharmacyInventory.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(1, { q: "", filter: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const filters = { q: query, filter };
    setApplied(filters);
    load(1, filters);
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyInventory.title")}</h1>
          <p>{t("pharmacyInventory.subtitle")}</p>
        </div>
        <div className="actions">
          <LinkButton href="/pharmacy/inventory/new" variant="primary">
            {t("pharmacyInventory.addBatch")}
          </LinkButton>
          <LinkButton href="/pharmacy/imports">{t("pharmacyInventory.import")}</LinkButton>
        </div>
      </div>
      <form className="toolbar panel" onSubmit={submit}>
        <Field label={t("pharmacyInventory.search")}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("pharmacyInventory.searchPlaceholder")} />
        </Field>
        <Field label={t("pharmacyInventory.filter")}>
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="">{t("pharmacyInventory.allInventory")}</option>
            <option value="low_stock">{t("pharmacyInventory.lowStock")}</option>
            <option value="expiring_soon">{t("pharmacyInventory.expiringSoon")}</option>
            <option value="expired">{t("pharmacyInventory.expired")}</option>
            <option value="public">{t("pharmacyInventory.publicAvailability")}</option>
          </select>
        </Field>
        <Button type="submit" disabled={loading}>
          {t("pharmacyInventory.apply")}
        </Button>
        {totalPages > 1 ? (
          <div className="actions" style={{ marginInlineStart: "auto", alignItems: "center" }}>
            {totalPages > 2 ? <span className="muted">{t("pharmacyInventory.pageStatus", { page, totalPages, count })}</span> : null}
            <Button type="button" variant="secondary" disabled={loading || page <= 1} onClick={() => load(page - 1, applied)}>
              {t("pharmacyInventory.previous")}
            </Button>
            {totalPages > 2
              ? pageWindow(page, totalPages).map((n) => (
                  <Button
                    key={n}
                    type="button"
                    variant={n === page ? "primary" : "secondary"}
                    disabled={loading || n === page}
                    onClick={() => load(n, applied)}
                  >
                    {n}
                  </Button>
                ))
              : null}
            <Button type="button" variant="secondary" disabled={loading || page >= totalPages} onClick={() => load(page + 1, applied)}>
              {t("pharmacyInventory.next")}
            </Button>
          </div>
        ) : null}
      </form>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {!loading && items.length === 0 ? <EmptyState title={t("pharmacyInventory.noRecords")} /> : null}
      <Table>
        <table aria-busy={loading}>
          <thead>
            <tr>
              <th>{t("pharmacyInventory.medicine")}</th>
              <th>{t("pharmacyInventory.batch")}</th>
              <th>{t("pharmacyInventory.stock")}</th>
              <th>{t("pharmacyInventory.expiry")}</th>
              <th>{t("pharmacyInventory.public")}</th>
              <th>{t("pharmacyInventory.price")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link href={`/pharmacy/inventory/${item.id}`}>
                    <strong>{item.medicine_detail.display_name}</strong>
                  </Link>
                  <br />
                  <span className="muted">{item.medicine_detail.generic_name}</span>
                </td>
                <td>{item.batch_number || t("pharmacyInventory.notRecorded")}</td>
                <td>
                  <Badge status tone={item.is_low_stock ? "warning" : item.current_quantity > 0 ? "success" : "danger"}>
                    {item.is_low_stock ? t("pharmacyInventory.lowStock") : item.current_quantity > 0 ? t("pharmacyInventory.available") : t("pharmacyInventory.unavailable")}
                  </Badge>
                </td>
                <td>
                  <Badge status tone={statusTone(item.is_expired ? "Expired" : item.is_expiring_soon ? "Expiring soon" : "Active")}>
                    {item.expiry_date || t("pharmacyInventory.notRecorded")}
                  </Badge>
                </td>
                <td>{item.public_availability_enabled ? t("pharmacyInventory.published") : t("pharmacyInventory.hidden")}</td>
                <td>${item.selling_price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}
