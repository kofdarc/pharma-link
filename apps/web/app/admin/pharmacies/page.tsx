"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { Pharmacy } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminPharmaciesPage() {
  const [items, setItems] = useState<Pharmacy[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<Pharmacy[] | { results: Pharmacy[] }>("/admin/pharmacies/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError("Pharmacies failed to load."));
  }

  useEffect(load, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    setMessage("");
    try {
      await apiFetch<Pharmacy>("/admin/pharmacies/", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          city: form.get("city"),
          area: form.get("area"),
          phone: form.get("phone"),
          email: form.get("email"),
          address: form.get("address"),
          is_active: true,
          is_public: form.get("is_public") === "on"
        })
      });
      setMessage("Pharmacy created.");
      event.currentTarget.reset();
      load();
    } catch {
      setError("Create failed. Check required fields and duplicates.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Pharmacies</h1>
          <p>Create, activate, and manage connected pharmacies.</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label="Name">
          <input name="name" required />
        </Field>
        <Field label="City">
          <input name="city" required />
        </Field>
        <Field label="Area">
          <input name="area" required />
        </Field>
        <Field label="Phone">
          <input name="phone" required />
        </Field>
        <Field label="Email">
          <input name="email" type="email" />
        </Field>
        <Field label="Address">
          <input name="address" />
        </Field>
        <label className="field">
          <span>Public visibility</span>
          <input name="is_public" type="checkbox" defaultChecked />
        </label>
        <Button type="submit">Create pharmacy</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title="No pharmacies created yet." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Area</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Public</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>
                  {item.area}, {item.city}
                </td>
                <td>{item.phone}</td>
                <td>
                  <Badge tone={statusTone(item.is_active ? "Active" : "Inactive")}>{item.is_active ? "Active" : "Inactive"}</Badge>
                </td>
                <td>{item.is_public ? "Visible" : "Hidden"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

