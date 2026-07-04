"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import type { Pharmacy } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function PharmacySettingsPage() {
  const [profile, setProfile] = useState<Pharmacy | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Pharmacy>("/pharmacy/profile/").then(setProfile).catch(() => setError("Profile failed to load."));
  }, []);

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
          latitude: form.get("latitude") || null,
          longitude: form.get("longitude") || null,
          is_public: form.get("is_public") === "on"
        })
      });
      setProfile(updated);
      setMessage("Settings saved.");
    } catch {
      setError("Save failed. Check contact and location fields.");
    }
  }

  if (!profile) return error ? <Notice tone="danger">{error}</Notice> : <div className="skeleton-card" />;

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h1>Settings</h1>
          <p>{profile.name}</p>
        </div>
      </div>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Address">
          <input name="address" defaultValue={profile.address} />
        </Field>
        <Field label="City">
          <input name="city" defaultValue={profile.city} required />
        </Field>
        <Field label="Area">
          <input name="area" defaultValue={profile.area} required />
        </Field>
        <Field label="Phone">
          <input name="phone" defaultValue={profile.phone} required />
        </Field>
        <Field label="WhatsApp">
          <input name="whatsapp" defaultValue={profile.whatsapp} />
        </Field>
        <Field label="Email">
          <input name="email" type="email" defaultValue={profile.email} />
        </Field>
        <Field label="Latitude">
          <input name="latitude" type="number" step="0.000001" defaultValue={profile.latitude || ""} />
        </Field>
        <Field label="Longitude">
          <input name="longitude" type="number" step="0.000001" defaultValue={profile.longitude || ""} />
        </Field>
        <label className="field">
          <span>Public visibility</span>
          <input name="is_public" type="checkbox" defaultChecked={profile.is_public} />
        </label>
        <Button type="submit">Save settings</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
    </section>
  );
}

