"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Pharmacy, User } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminUsersPage() {
  const t = useTranslations();
  const [users, setUsers] = useState<User[]>([]);
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const roleLabels: Record<string, string> = {
    PHARMACY_STAFF: t("adminUsers.rolePharmacyStaff"),
    PHARMACY_OWNER: t("adminUsers.rolePharmacyOwner"),
    DOCTOR: t("adminUsers.roleDoctor"),
    PLATFORM_ADMIN: t("adminUsers.rolePlatformAdmin")
  };

  function load() {
    Promise.all([
      apiFetch<User[] | { results: User[] }>("/admin/users/"),
      apiFetch<Pharmacy[] | { results: Pharmacy[] }>("/admin/pharmacies/")
    ])
      .then(([userPayload, pharmacyPayload]) => {
        setUsers(asList(userPayload));
        setPharmacies(asList(pharmacyPayload));
      })
      .catch(() => setError(t("adminUsers.loadError")));
  }

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<User>("/admin/users/", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
          role: form.get("role"),
          pharmacy: form.get("pharmacy") || null,
          is_active: true
        })
      });
      setMessage(t("adminUsers.created"));
      event.currentTarget.reset();
      load();
    } catch {
      setError(t("adminUsers.createFailed"));
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminUsers.title")}</h1>
          <p>{t("adminUsers.subtitle")}</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label={t("adminUsers.email")}>
          <input name="email" type="email" required />
        </Field>
        <Field label={t("adminUsers.password")}>
          <input name="password" type="password" minLength={8} required />
        </Field>
        <Field label={t("adminUsers.role")}>
          <select name="role">
            <option value="PHARMACY_STAFF">{t("adminUsers.rolePharmacyStaff")}</option>
            <option value="PHARMACY_OWNER">{t("adminUsers.rolePharmacyOwner")}</option>
            <option value="DOCTOR">{t("adminUsers.roleDoctor")}</option>
            <option value="PLATFORM_ADMIN">{t("adminUsers.rolePlatformAdmin")}</option>
          </select>
        </Field>
        <Field label={t("adminUsers.pharmacy")}>
          <select name="pharmacy">
            <option value="">{t("adminUsers.noPharmacy")}</option>
            {pharmacies.map((pharmacy) => (
              <option key={pharmacy.id} value={pharmacy.id}>
                {pharmacy.name}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit">{t("adminUsers.createUser")}</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>{t("adminUsers.emailCol")}</th>
              <th>{t("adminUsers.roleCol")}</th>
              <th>{t("adminUsers.pharmacyCol")}</th>
              <th>{t("adminUsers.statusCol")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>{roleLabels[user.role] || user.role}</td>
                <td>{user.pharmacy_detail?.name || ""}</td>
                <td>
                  <Badge tone={statusTone(user.is_active ? "Active" : "Inactive")}>
                    {user.is_active ? t("adminUsers.active") : t("adminUsers.inactive")}
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

