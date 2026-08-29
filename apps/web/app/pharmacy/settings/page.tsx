"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Pharmacy } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function PharmacySettingsPage() {
  const t = useTranslations();
  const [profile, setProfile] = useState<Pharmacy | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // The two coordinate inputs are controlled while the rest of the form is not, because
  // "use this device's location" has to write into them. Everything else is only ever typed.
  const [coordinates, setCoordinates] = useState({ latitude: "", longitude: "" });
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    apiFetch<Pharmacy>("/pharmacy/profile/")
      .then((loaded) => {
        setProfile(loaded);
        setCoordinates({ latitude: loaded.latitude || "", longitude: loaded.longitude || "" });
      })
      .catch(() => setError(t("pharmacySettings.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Fill the coordinates from the device the pharmacist is holding.
   *
   * This is the whole reason the pharmacy's position gets filled in at all. Latitude and
   * longitude are not numbers anybody knows about their own shop, and an empty pair here is
   * not a cosmetic gap: a pharmacy with no coordinates cannot be ranked by distance, so it
   * never appears as "the closest one that has this" no matter what it stocks.
   */
  function fillCoordinatesFromDevice() {
    if (!("geolocation" in navigator)) {
      setError(t("pharmacySettings.locationFailed"));
      return;
    }
    setLocating(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      (fix) => {
        setCoordinates({ latitude: fix.coords.latitude.toFixed(6), longitude: fix.coords.longitude.toFixed(6) });
        setLocating(false);
      },
      () => {
        setLocating(false);
        setError(t("pharmacySettings.locationFailed"));
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    setMessage("");
    try {
      const updated = await apiFetch<Pharmacy>("/pharmacy/profile/", {
        method: "PATCH",
        body: JSON.stringify({
          address: form.get("address"),
          city: form.get("city"),
          area: form.get("area"),
          phone: form.get("phone"),
          whatsapp: form.get("whatsapp"),
          email: form.get("email"),
          latitude: coordinates.latitude || null,
          longitude: coordinates.longitude || null,
          is_public: form.get("is_public") === "on",
          is_on_call: form.get("is_on_call") === "on"
        })
      });
      setProfile(updated);
      setCoordinates({ latitude: updated.latitude || "", longitude: updated.longitude || "" });
      setMessage(t("pharmacySettings.saved"));
    } catch {
      setError(t("pharmacySettings.saveFailed"));
    }
  }

  if (!profile) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>{t("pharmacySettings.title")}</h1>
          <p>{profile.name}</p>
        </div>
      </div>
      <form className="form-grid" onSubmit={submit}>
        <Field label={t("pharmacySettings.address")}>
          <input name="address" defaultValue={profile.address} />
        </Field>
        <Field label={t("pharmacySettings.city")}>
          <input name="city" defaultValue={profile.city} required />
        </Field>
        <Field label={t("pharmacySettings.area")}>
          <input name="area" defaultValue={profile.area} required />
        </Field>
        <Field label={t("pharmacySettings.phone")}>
          <input name="phone" defaultValue={profile.phone} required />
        </Field>
        <Field label={t("pharmacySettings.whatsapp")}>
          <input name="whatsapp" defaultValue={profile.whatsapp} />
        </Field>
        <Field label={t("pharmacySettings.email")}>
          <input name="email" type="email" defaultValue={profile.email} />
        </Field>
        <Field label={t("pharmacySettings.latitude")} hint={t("pharmacySettings.locationHelp")}>
          <input
            name="latitude"
            type="number"
            step="0.000001"
            value={coordinates.latitude}
            onChange={(event) => setCoordinates({ ...coordinates, latitude: event.target.value })}
          />
        </Field>
        <Field label={t("pharmacySettings.longitude")}>
          <input
            name="longitude"
            type="number"
            step="0.000001"
            value={coordinates.longitude}
            onChange={(event) => setCoordinates({ ...coordinates, longitude: event.target.value })}
          />
        </Field>
        <Button type="button" variant="secondary" onClick={fillCoordinatesFromDevice} disabled={locating}>
          {locating ? t("pharmacySettings.locating") : t("pharmacySettings.useCurrentLocation")}
        </Button>
        <label className="field">
          <span>{t("pharmacySettings.publicVisibility")}</span>
          <input name="is_public" type="checkbox" defaultChecked={profile.is_public} />
        </label>
        <label className="field">
          <span>{t("pharmacySettings.onCall")}</span>
          <input name="is_on_call" type="checkbox" defaultChecked={profile.is_on_call} />
        </label>
        <Button type="submit">{t("pharmacySettings.saveSettings")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}

