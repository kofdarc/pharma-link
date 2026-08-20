"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Pharmacy } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminPharmaciesPage() {
  const t = useTranslations();
  const [items, setItems] = useState<Pharmacy[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<Pharmacy[] | { results: Pharmacy[] }>("/admin/pharmacies/")
      .then((payload) => setItems(asList(payload)))
      .catch(() => setError(t("adminPharmacies.loadError")));
  }

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

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
      setMessage(t("adminPharmacies.created"));
      event.currentTarget.reset();
      load();
    } catch {
      setError(t("adminPharmacies.createFailed"));
    }
  }

  async function toggleActive(item: Pharmacy) {
    if (item.is_active && !window.confirm(t("adminPharmacies.deactivateConfirm", { name: item.name }))) return;
    setError("");
    setMessage("");
    try {
      await apiFetch(`/admin/pharmacies/${item.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !item.is_active }) });
      setMessage(t(item.is_active ? "adminPharmacies.deactivated" : "adminPharmacies.reactivated", { name: item.name }));
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("adminPharmacies.statusChangeFailed"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminPharmacies.title")}</h1>
          <p>{t("adminPharmacies.subtitle")}</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label={t("adminPharmacies.name")}>
          <input name="name" required />
        </Field>
        <Field label={t("adminPharmacies.city")}>
          <input name="city" required />
        </Field>
        <Field label={t("adminPharmacies.area")}>
          <input name="area" required />
        </Field>
        <Field label={t("adminPharmacies.phone")}>
          <input name="phone" required />
        </Field>
        <Field label={t("adminPharmacies.email")}>
          <input name="email" type="email" />
        </Field>
        <Field label={t("adminPharmacies.address")}>
          <input name="address" />
        </Field>
        <label className="field">
          <span>{t("adminPharmacies.publicVisibility")}</span>
          <input name="is_public" type="checkbox" defaultChecked />
        </label>
        <Button type="submit">{t("adminPharmacies.createPharmacy")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title={t("adminPharmacies.noPharmacies")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("adminPharmacies.name")}</th>
              <th>{t("adminPharmacies.area")}</th>
              <th>{t("adminPharmacies.phone")}</th>
              <th>{t("adminPharmacies.status")}</th>
              <th>{t("adminPharmacies.public")}</th>
              <th />
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
                  <Badge tone={statusTone(item.is_active ? "Active" : "Inactive")}>
                    {item.is_active ? t("adminPharmacies.active") : t("adminPharmacies.inactive")}
                  </Badge>
                </td>
                <td>{item.is_public ? t("adminPharmacies.visible") : t("adminPharmacies.hidden")}</td>
                <td>
                  <Button type="button" variant={item.is_active ? "danger" : "secondary"} onClick={() => toggleActive(item)}>
                    {item.is_active ? t("adminPharmacies.deactivate") : t("adminPharmacies.reactivate")}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

