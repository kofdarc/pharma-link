"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { Medicine } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminMedicinesPage() {
  const [items, setItems] = useState<Medicine[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<Medicine[] | { results: Medicine[] }>("/admin/medicines/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError("Medicines failed to load."));
  }

  useEffect(load, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const aliases = String(form.get("aliases") || "")
      .split(",")
      .map((alias) => alias.trim())
      .filter(Boolean)
      .map((alias) => ({ alias, alias_type: "OTHER" }));
    try {
      await apiFetch<Medicine>("/admin/medicines/", {
        method: "POST",
        body: JSON.stringify({
          brand_name: form.get("brand_name"),
          generic_name: form.get("generic_name"),
          strength: form.get("strength"),
          form: form.get("form"),
          manufacturer: form.get("manufacturer"),
          is_active: true,
          aliases
        })
      });
      setMessage("Medicine created.");
      event.currentTarget.reset();
      load();
    } catch {
      setError("Create failed. Duplicate brand, strength, and form combinations are blocked.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Medicine catalog</h1>
          <p>Canonical records support search, imports, sales, and availability publishing.</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label="Brand name">
          <input name="brand_name" required />
        </Field>
        <Field label="Generic name">
          <input name="generic_name" />
        </Field>
        <Field label="Strength">
          <input name="strength" placeholder="500mg" />
        </Field>
        <Field label="Form">
          <input name="form" placeholder="Tablet, capsule, syrup" />
        </Field>
        <Field label="Manufacturer">
          <input name="manufacturer" />
        </Field>
        <Field label="Aliases">
          <input name="aliases" placeholder="Comma-separated aliases" />
        </Field>
        <Button type="submit">Add medicine</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title="Empty catalog state." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Brand</th>
              <th>Generic</th>
              <th>Variant</th>
              <th>Aliases</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.brand_name}</td>
                <td>{item.generic_name}</td>
                <td>
                  {item.strength} {item.form}
                </td>
                <td>{item.aliases?.map((alias) => alias.alias).join(", ")}</td>
                <td>
                  <Badge tone={statusTone(item.is_active ? "Active" : "Inactive")}>{item.is_active ? "Active" : "Inactive"}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

