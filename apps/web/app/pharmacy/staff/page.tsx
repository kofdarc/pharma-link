"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { User } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function StaffPage() {
  const t = useTranslations();
  const [staff, setStaff] = useState<User[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<User[] | { results: User[] }>("/pharmacy/staff/")
      .then((payload) => setStaff(asList(payload)))
      .catch(() => setError(t("pharmacyStaff.loadError")));
  }

  useEffect(load, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<User>("/pharmacy/staff/", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          role: form.get("role"),
          is_active: true
        })
      });
      setMessage(t("pharmacyStaff.created"));
      event.currentTarget.reset();
      load();
    } catch {
      setError(t("pharmacyStaff.createFailed"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyStaff.title")}</h1>
          <p>{t("pharmacyStaff.subtitle")}</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label={t("pharmacyStaff.email")}>
          <input name="email" type="email" required />
        </Field>
        <Field label={t("pharmacyStaff.password")}>
          <input name="password" type="password" minLength={8} required />
        </Field>
        <Field label={t("pharmacyStaff.firstName")}>
          <input name="first_name" />
        </Field>
        <Field label={t("pharmacyStaff.lastName")}>
          <input name="last_name" />
        </Field>
        <Field label={t("pharmacyStaff.role")}>
          <select name="role" defaultValue="PHARMACY_STAFF">
            <option value="PHARMACY_STAFF">{t("pharmacyStaff.rolePharmacyStaff")}</option>
            <option value="PHARMACY_OWNER">{t("pharmacyStaff.rolePharmacyOwner")}</option>
          </select>
        </Field>
        <Button type="submit">{t("pharmacyStaff.addStaff")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {staff.length === 0 ? <EmptyState title={t("pharmacyStaff.noStaff")} /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("pharmacyStaff.email")}</th>
              <th>{t("pharmacyStaff.name")}</th>
              <th>{t("pharmacyStaff.role")}</th>
              <th>{t("pharmacyStaff.status")}</th>
            </tr>
          </thead>
          <tbody>
            {staff.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>
                  {user.first_name} {user.last_name}
                </td>
                <td>{user.role}</td>
                <td>
                  <Badge status tone={statusTone(user.is_active ? "Active" : "Inactive")}>
                    {user.is_active ? t("pharmacyStaff.active") : t("pharmacyStaff.inactive")}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}
