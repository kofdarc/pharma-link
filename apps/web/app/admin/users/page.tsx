"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { Pharmacy, User } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    Promise.all([
      apiFetch<User[] | { results: User[] }>("/admin/users/"),
      apiFetch<Pharmacy[] | { results: Pharmacy[] }>("/admin/pharmacies/")
    ])
      .then(([userPayload, pharmacyPayload]) => {
        setUsers(asList(userPayload));
        setPharmacies(asList(pharmacyPayload));
      })
      .catch(() => setError("Users failed to load."));
  }

  useEffect(load, []);

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
      setMessage("User created.");
      event.currentTarget.reset();
      load();
    } catch {
      setError("Create failed. Pharmacy users must be assigned to a pharmacy.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Users</h1>
          <p>Manage platform admins, pharmacy owners, pharmacy staff, and optional doctors.</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label="Email">
          <input name="email" type="email" required />
        </Field>
        <Field label="Password">
          <input name="password" type="password" minLength={8} required />
        </Field>
        <Field label="Role">
          <select name="role">
            <option value="PHARMACY_STAFF">Pharmacy staff</option>
            <option value="PHARMACY_OWNER">Pharmacy owner</option>
            <option value="DOCTOR">Doctor</option>
            <option value="PLATFORM_ADMIN">Platform admin</option>
          </select>
        </Field>
        <Field label="Pharmacy">
          <select name="pharmacy">
            <option value="">No pharmacy</option>
            {pharmacies.map((pharmacy) => (
              <option key={pharmacy.id} value={pharmacy.id}>
                {pharmacy.name}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit">Create user</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Role</th>
              <th>Pharmacy</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>{user.role}</td>
                <td>{user.pharmacy_detail?.name || ""}</td>
                <td>
                  <Badge tone={statusTone(user.is_active ? "Active" : "Inactive")}>{user.is_active ? "Active" : "Inactive"}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Table>
    </>
  );
}

