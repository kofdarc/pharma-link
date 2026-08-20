"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { DeliveryAddress, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

const BEIRUT = { latitude: "33.8938", longitude: "35.5018" };

export default function AddressesPage() {
  const t = useTranslations();
  const [addresses, setAddresses] = useState<DeliveryAddress[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    label: "Home",
    contact_name: "",
    phone: "",
    address: "",
    area: "",
    city: "Beirut",
    building_notes: "",
    ...BEIRUT,
    is_default: true
  });

  const load = useCallback(() => {
    apiFetch<Paginated<DeliveryAddress> | DeliveryAddress[]>("/shop/addresses/")
      .then((payload) => setAddresses(asList(payload)))
      .catch(() => setError(t("addresses.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError(t("addresses.geoUnsupported"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setForm((current) => ({
          ...current,
          latitude: position.coords.latitude.toFixed(6),
          longitude: position.coords.longitude.toFixed(6)
        }));
        setError("");
      },
      () => setError(t("addresses.geoRefused"))
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiFetch("/shop/addresses/", { method: "POST", body: JSON.stringify(form) });
      setForm((current) => ({ ...current, label: "", address: "", area: "", building_notes: "" }));
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("addresses.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("addresses.title")}</h1>
          <p className="muted">{t("addresses.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      {addresses.length === 0 ? <EmptyState title={t("addresses.noAddresses")} /> : null}

      <div className="result-grid">
        {addresses.map((entry) => (
          <article className="result-card" key={entry.id}>
            <div className="section-header">
              <h3>{entry.label}</h3>
              {entry.is_default ? <Badge tone="success">{t("addresses.default")}</Badge> : null}
            </div>
            <p>{entry.address}</p>
            <p className="muted small">
              {entry.area}, {entry.city}
            </p>
            <p className="muted small">
              {entry.contact_name} · {entry.phone}
            </p>
            <p className="muted small">
              {entry.latitude}, {entry.longitude}
            </p>
          </article>
        ))}
      </div>

      <section className="panel">
        <h3>{t("addresses.addAddress")}</h3>
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field label={t("addresses.label")}>
              <input value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} required />
            </Field>
            <Field label={t("addresses.contactName")}>
              <input value={form.contact_name} onChange={(event) => setForm({ ...form, contact_name: event.target.value })} required />
            </Field>
            <Field label={t("addresses.phone")}>
              <input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} required />
            </Field>
            <Field label={t("addresses.area")}>
              <input value={form.area} onChange={(event) => setForm({ ...form, area: event.target.value })} placeholder="Hamra" required />
            </Field>
            <Field label={t("addresses.city")}>
              <input value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} required />
            </Field>
            <Field label={t("addresses.buildingNotes")}>
              <input
                value={form.building_notes}
                onChange={(event) => setForm({ ...form, building_notes: event.target.value })}
                placeholder={t("addresses.buildingNotesPlaceholder")}
              />
            </Field>
            <Field label={t("addresses.latitude")}>
              <input value={form.latitude} onChange={(event) => setForm({ ...form, latitude: event.target.value })} required />
            </Field>
            <Field label={t("addresses.longitude")}>
              <input value={form.longitude} onChange={(event) => setForm({ ...form, longitude: event.target.value })} required />
            </Field>
          </div>
          <Field label={t("addresses.streetAddress")}>
            <input value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} required />
          </Field>
          <label className="field checkbox-field">
            <span>{t("addresses.makeDefault")}</span>
            <input type="checkbox" checked={form.is_default} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} />
          </label>
          <div className="actions">
            <Button type="submit" disabled={busy}>
              {busy ? t("addresses.saving") : t("addresses.saveAddress")}
            </Button>
            <Button type="button" variant="secondary" onClick={useMyLocation}>
              {t("addresses.useMyLocation")}
            </Button>
          </div>
        </form>
      </section>
    </>
  );
}
