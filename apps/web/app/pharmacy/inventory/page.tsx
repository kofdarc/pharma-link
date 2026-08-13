"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { InventoryBatch } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryBatch[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  async function load(path = "/pharmacy/inventory/") {
    setError("");
    try {
      setItems(asList(await apiFetch<InventoryBatch[] | { results: InventoryBatch[] }>(path)));
    } catch {
      setError("Inventory failed to load.");
    }
  }

  useEffect(() => {
    load();
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
          <h1>Inventory</h1>
          <p>Manage medicine batches, stock status, expiry, and public availability.</p>
        </div>
        <div className="actions">
          <LinkButton href="/pharmacy/inventory/new" variant="primary">
            Add batch
          </LinkButton>
          <LinkButton href="/pharmacy/imports">Import</LinkButton>
        </div>
      </div>
      <form className="toolbar panel" onSubmit={submit}>
        <Field label="Search">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Medicine or batch" />
        </Field>
        <Field label="Filter">
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="">All inventory</option>
            <option value="low_stock">Low stock</option>
            <option value="expiring_soon">Expiring soon</option>
            <option value="expired">Expired</option>
            <option value="public">Public availability</option>
          </select>
        </Field>
        <Button type="submit">Apply</Button>
      </form>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title="No inventory records found." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Medicine</th>
              <th>Batch</th>
              <th>Stock</th>
              <th>Expiry</th>
              <th>Public</th>
              <th>Price</th>
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
                <td>{item.batch_number || "Not recorded"}</td>
                <td>
                  <Badge tone={item.is_low_stock ? "warning" : item.current_quantity > 0 ? "success" : "danger"}>
                    {item.is_low_stock ? "Low stock" : item.current_quantity > 0 ? "Available" : "Unavailable"}
                  </Badge>
                </td>
                <td>
                  <Badge tone={statusTone(item.is_expired ? "Expired" : item.is_expiring_soon ? "Expiring soon" : "Active")}>
                    {item.expiry_date || "Not recorded"}
                  </Badge>
                </td>
                <td>{item.public_availability_enabled ? "Published" : "Hidden"}</td>
                <td>${item.selling_price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

