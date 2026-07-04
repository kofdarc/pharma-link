"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, asList } from "@/lib/api-client";
import type { User } from "@/types/api";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function StaffPage() {
  const [staff, setStaff] = useState<User[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    apiFetch<User[] | { results: User[] }>("/pharmacy/staff/")
      .then((payload) => setStaff(asList(payload)))
      .catch(() => setError("Staff failed to load. Pharmacy owner access is required."));
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
      setMessage("Staff user created.");
      event.currentTarget.reset();
      load();
    } catch {
      setError("Create failed. Check email, role, and password.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Staff</h1>
          <p>Owners can add or deactivate pharmacy staff.</p>
        </div>
      </div>
      <form className="panel form-grid" onSubmit={create}>
        <Field label="Email">
          <input name="email" type="email" required />
        </Field>
        <Field label="Password">
          <input name="password" type="password" minLength={8} required />
        </Field>
        <Field label="First name">
          <input name="first_name" />
        </Field>
        <Field label="Last name">
          <input name="last_name" />
        </Field>
        <Field label="Role">
          <select name="role" defaultValue="PHARMACY_STAFF">
            <option value="PHARMACY_STAFF">Pharmacy staff</option>
            <option value="PHARMACY_OWNER">Pharmacy owner</option>
          </select>
        </Field>
        <Button type="submit">Add staff</Button>
      </form>
      {message ? <Notice tone="success">{message}</Notice> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {staff.length === 0 ? <EmptyState title="No staff users added yet." /> : null}
      <Table>
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Role</th>
              <th>Status</th>
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

