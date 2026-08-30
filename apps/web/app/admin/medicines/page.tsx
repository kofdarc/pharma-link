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
  const [nssfFilter, setNssfFilter] = useState<"all" | "covered" | "not">("all");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load(pageNum = page, search = query, nssf = nssfFilter) {
    const params = new URLSearchParams({ page: String(pageNum) });
    if (search.trim()) params.set("search", search.trim());
    if (nssf === "covered") params.set("nssf_covered", "true");
    if (nssf === "not") params.set("nssf_covered", "false");
    apiFetch<Paginated<Medicine>>(`/admin/medicines/?${params.toString()}`)
      .then((payload) => {
        setItems(payload.results);
        setCount(payload.count);
      })
      .catch(() => setError(t("adminMedicines.loadError")));
  }

  useEffect(() => {
    load(1, query, nssfFilter);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, nssfFilter]);

  function goToPage(nextPage: number) {
    setPage(nextPage);
    load(nextPage, query);
  }

  async function saveNssf(id: string, patch: Partial<Pick<Medicine, "nssf_covered" | "nssf_reference_price" | "nssf_reimbursement_rate" | "nssf_source_reference">>) {
    try {
      const updated = await apiFetch<Medicine>(`/admin/medicines/${id}/`, { method: "PATCH", body: JSON.stringify(patch) });
      setItems((rows) => rows.map((row) => (row.id === id ? updated : row)));
      setMessage(t("adminMedicines.nssfSaved"));
    } catch {
      setError(t("adminMedicines.nssfSaveFailed"));
    }
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
    const nssfCovered = form.get("nssf_covered") === "on";
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
          nssf_covered: nssfCovered,
          nssf_reimbursement_rate: nssfCovered ? form.get("nssf_reimbursement_rate") || null : null,
          nssf_reference_price: nssfCovered ? form.get("nssf_reference_price") || null : null,
          nssf_source_reference: nssfCovered ? form.get("nssf_source_reference") || "" : "",
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
        <Field label={t("adminMedicines.nssfFilterLabel")}>
          <select value={nssfFilter} onChange={(event) => setNssfFilter(event.target.value as "all" | "covered" | "not")}>
            <option value="all">{t("adminMedicines.nssfFilterAll")}</option>
            <option value="covered">{t("adminMedicines.nssfFilterCovered")}</option>
            <option value="not">{t("adminMedicines.nssfFilterNot")}</option>
          </select>
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
        <Field label={t("adminMedicines.nssfCovered")}>
          <label className="actions" style={{ gap: 8 }}>
            <input name="nssf_covered" type="checkbox" />
            <span className="muted">{t("adminMedicines.nssfCoveredHint")}</span>
          </label>
        </Field>
        <Field label={t("adminMedicines.nssfRate")}>
          <input name="nssf_reimbursement_rate" type="number" step="0.01" min="0" max="100" placeholder="80" />
        </Field>
        <Field label={t("adminMedicines.nssfReferencePrice")}>
          <input name="nssf_reference_price" type="number" step="0.01" min="0" />
        </Field>
        <Field label={t("adminMedicines.nssfSource")}>
          <input name="nssf_source_reference" placeholder={t("adminMedicines.nssfSourcePlaceholder")} />
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
              <th>{t("adminMedicines.nssfCol")}</th>
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
                  <Badge status tone={statusTone(item.is_active ? "Active" : "Inactive")}>
                    {item.is_active ? t("adminMedicines.active") : t("adminMedicines.inactive")}
                  </Badge>
                </td>
                <td>
                  <div style={{ display: "grid", gap: 6, minWidth: 180 }}>
                    <label className="actions" style={{ gap: 6 }}>
                      <input
                        type="checkbox"
                        checked={Boolean(item.nssf_covered)}
                        onChange={(event) => saveNssf(item.id, { nssf_covered: event.target.checked })}
                      />
                      <span>{item.nssf_covered ? t("adminMedicines.nssfOn") : t("adminMedicines.nssfOff")}</span>
                    </label>
                    {item.nssf_covered ? (
                      <div className="actions" style={{ gap: 6 }}>
                        <input
                          key={`rate-${item.id}-${item.nssf_reimbursement_rate ?? ""}`}
                          type="number"
                          step="0.01"
                          min="0"
                          max="100"
                          defaultValue={item.nssf_reimbursement_rate ?? ""}
                          aria-label={t("adminMedicines.nssfRate")}
                          placeholder="%"
                          style={{ width: 64 }}
                          onBlur={(event) => {
                            const next = event.target.value || null;
                            if (next !== (item.nssf_reimbursement_rate ?? null)) saveNssf(item.id, { nssf_reimbursement_rate: next });
                          }}
                        />
                        <input
                          key={`ref-${item.id}-${item.nssf_reference_price ?? ""}`}
                          type="number"
                          step="0.01"
                          min="0"
                          defaultValue={item.nssf_reference_price ?? ""}
                          aria-label={t("adminMedicines.nssfReferencePrice")}
                          placeholder={t("adminMedicines.nssfRefShort")}
                          style={{ width: 84 }}
                          onBlur={(event) => {
                            const next = event.target.value || null;
                            if (next !== (item.nssf_reference_price ?? null)) saveNssf(item.id, { nssf_reference_price: next });
                          }}
                        />
                      </div>
                    ) : null}
                  </div>
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
