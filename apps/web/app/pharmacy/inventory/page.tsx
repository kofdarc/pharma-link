"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { InventoryBatch } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function InventoryPage() {
  const t = useTranslations();
  const [items, setItems] = useState<InventoryBatch[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  async function load(path = "/pharmacy/inventory/") {
    setError("");
    try {
      setItems(asList(await apiFetch<InventoryBatch[] | { results: InventoryBatch[] }>(path)));
    } catch {
      setError(t("pharmacyInventory.loadError"));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (filter) params.set(filter, "true");
    load(`/pharmacy/inventory/?${params}`);
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
        <Button type="submit">{t("pharmacyInventory.apply")}</Button>
      </form>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title={t("pharmacyInventory.noRecords")} /> : null}
      <Table>
        <table>
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
