"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Medicine, Paginated } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ProductThumb } from "@/components/ui/ProductThumb";
import { Table } from "@/components/ui/Table";

const PAGE_SIZE = 25;

export default function AdminMedicinesPage() {
  const t = useTranslations();
  const [items, setItems] = useState<Medicine[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load(pageNum = page, search = query) {
    const params = new URLSearchParams({ page: String(pageNum) });
    if (search.trim()) params.set("search", search.trim());
    apiFetch<Paginated<Medicine>>(`/admin/medicines/?${params.toString()}`)
      .then((payload) => {
        setItems(payload.results);
        setCount(payload.count);
      })
      .catch(() => setError(t("adminMedicines.loadError")));
  }

  useEffect(() => {
    load(1, query);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  function goToPage(nextPage: number) {
    setPage(nextPage);
    load(nextPage, query);
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const aliases = String(form.get("aliases") || "")
      .split(",")
      .map((alias) => alias.trim())
      .filter(Boolean)
      .map((alias) => ({ alias, alias_type: "OTHER" }));
    const image = form.get("image");
    try {
      const created = await apiFetch<Medicine>("/admin/medicines/", {
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
      if (image instanceof File && image.size > 0) {
        await uploadImage(created.id, image);
      }
      setMessage(t("adminMedicines.created"));
      event.currentTarget.reset();
      load();
    } catch {
      setError(t("adminMedicines.createFailed"));
    }
  }

  async function uploadImage(id: string, file: File) {
    const body = new FormData();
    body.set("image", file);
    await apiFetch<Medicine>(`/admin/medicines/${id}/`, { method: "PATCH", body });
  }

  async function changeImage(id: string, event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {
      await uploadImage(id, file);
      setMessage(t("adminMedicines.imageUpdated"));
      load();
    } catch {
      setError(t("adminMedicines.imageUpdateFailed"));
    } finally {
      event.currentTarget.value = "";
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminMedicines.title")}</h1>
          <p>{t("adminMedicines.subtitle", { count })}</p>
        </div>
      </div>
      <div className="panel">
        <Field label={t("adminMedicines.searchLabel")}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("adminMedicines.searchPlaceholder")} />
        </Field>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label={t("adminMedicines.brandName")}>
          <input name="brand_name" required />
        </Field>
        <Field label={t("adminMedicines.genericName")}>
          <input name="generic_name" />
        </Field>
        <Field label={t("adminMedicines.strength")}>
          <input name="strength" placeholder={t("adminMedicines.strengthPlaceholder")} />
        </Field>
        <Field label={t("adminMedicines.form")}>
          <input name="form" placeholder={t("adminMedicines.formPlaceholder")} />
        </Field>
        <Field label={t("adminMedicines.manufacturer")}>
          <input name="manufacturer" />
        </Field>
        <Field label={t("adminMedicines.aliases")}>
          <input name="aliases" placeholder={t("adminMedicines.aliasesPlaceholder")} />
        </Field>
        <Field label={t("adminMedicines.photo")}>
          <input name="image" type="file" accept="image/*" />
        </Field>
        <Button type="submit">{t("adminMedicines.addMedicine")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {items.length === 0 ? <EmptyState title={t("adminMedicines.emptyState")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("adminMedicines.photoCol")}</th>
              <th>{t("adminMedicines.brandCol")}</th>
              <th>{t("adminMedicines.genericCol")}</th>
              <th>{t("adminMedicines.variantCol")}</th>
              <th>{t("adminMedicines.aliasesCol")}</th>
              <th>{t("adminMedicines.statusCol")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <label className="actions" style={{ cursor: "pointer" }}>
                    <ProductThumb src={item.image} alt={item.brand_name} />
                    <input type="file" accept="image/*" hidden onChange={(event) => changeImage(item.id, event)} />
                  </label>
                </td>
                <td>{item.brand_name}</td>
                <td>{item.generic_name}</td>
                <td>
                  {item.strength} {item.form}
                </td>
                <td>{item.aliases?.map((alias) => alias.alias).join(", ")}</td>
                <td>
                  <Badge tone={statusTone(item.is_active ? "Active" : "Inactive")}>
                    {item.is_active ? t("adminMedicines.active") : t("adminMedicines.inactive")}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
      <div className="actions">
        <Button type="button" variant="secondary" onClick={() => goToPage(page - 1)} disabled={page <= 1}>
          {t("adminMedicines.previous")}
        </Button>
        <span className="muted">{t("adminMedicines.pageOf", { page, totalPages })}</span>
        <Button type="button" variant="secondary" onClick={() => goToPage(page + 1)} disabled={page >= totalPages}>
          {t("adminMedicines.next")}
        </Button>
      </div>
    </>
  );
}

