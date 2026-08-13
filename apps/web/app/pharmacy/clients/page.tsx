"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { Client, ClientHistory, ClientLedgerEntry, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Client | null>(null);
  const [history, setHistory] = useState<ClientHistory | null>(null);
  const [ledger, setLedger] = useState<ClientLedgerEntry[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    area: "",
    address: "",
    allergies: "",
    chronic_conditions: "",
    insurance_provider: "",
    credit_limit: "0",
    notes: ""
  });

  const load = useCallback(() => {
    apiFetch<Paginated<Client> | Client[]>(`/pharmacy/clients/${query ? `?q=${encodeURIComponent(query)}` : ""}`)
      .then((payload) => setClients(asList(payload)))
      .catch(() => setError("Could not load clients."));
  }, [query]);

  useEffect(load, [load]);

  async function open(client: Client) {
    setSelected(client);
    setHistory(null);
    setLedger([]);
    const [historyData, ledgerData] = await Promise.all([
      apiFetch<ClientHistory>(`/pharmacy/clients/${client.id}/history/`).catch(() => null),
      apiFetch<ClientLedgerEntry[]>(`/pharmacy/clients/${client.id}/ledger/`).catch(() => [])
    ]);
    setHistory(historyData);
    setLedger(ledgerData);
  }

  async function createClient(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await apiFetch("/pharmacy/clients/", { method: "POST", body: JSON.stringify(form) });
      setMessage(`${form.full_name} added.`);
      setShowForm(false);
      setForm({ ...form, full_name: "", phone: "", email: "", allergies: "", chronic_conditions: "", notes: "" });
      load();
    } catch (exception) {
      setError((exception as ApiError).message || "Could not save the client.");
    }
  }

  async function postPayment() {
    if (!selected) return;
    const amount = window.prompt("Payment amount received?");
    if (!amount) return;
    try {
      await apiFetch(`/pharmacy/clients/${selected.id}/ledger/`, {
        method: "POST",
        body: JSON.stringify({ entry_type: "PAYMENT", amount, memo: "Counter payment" })
      });
      setMessage("Payment recorded.");
      open(selected);
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Clients</h1>
          <p className="muted">
            Your own client records, private to this pharmacy. Shoppers who order online are added here
            automatically the first time they buy from you.
          </p>
        </div>
        <Button type="button" onClick={() => setShowForm((current) => !current)}>
          {showForm ? "Close" : "Add a client"}
        </Button>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {showForm ? (
        <section className="panel">
          <h3>New client</h3>
          <form onSubmit={createClient}>
            <div className="form-grid">
              <Field label="Full name">
                <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required />
              </Field>
              <Field label="Phone" hint="Used to recognise returning customers.">
                <input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} required />
              </Field>
              <Field label="Email">
                <input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
              </Field>
              <Field label="Area">
                <input value={form.area} onChange={(event) => setForm({ ...form, area: event.target.value })} />
              </Field>
              <Field label="Insurance provider">
                <input value={form.insurance_provider} onChange={(event) => setForm({ ...form, insurance_provider: event.target.value })} />
              </Field>
              <Field label="Credit limit">
                <input value={form.credit_limit} onChange={(event) => setForm({ ...form, credit_limit: event.target.value })} />
              </Field>
            </div>
            <Field label="Allergies" hint="Shown prominently whenever this client is selected on a sale.">
              <input value={form.allergies} onChange={(event) => setForm({ ...form, allergies: event.target.value })} placeholder="Penicillin" />
            </Field>
            <Field label="Chronic conditions">
              <input value={form.chronic_conditions} onChange={(event) => setForm({ ...form, chronic_conditions: event.target.value })} />
            </Field>
            <Field label="Notes">
              <input value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
            </Field>
            <Button type="submit">Save client</Button>
          </form>
        </section>
      ) : null}

      <section className="panel">
        <div className="search-bar">
          <Field label="Search">
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, phone or email" />
          </Field>
        </div>

        {clients.length === 0 ? (
          <EmptyState title="No clients yet." detail="Add one above, or they appear as soon as someone orders from you online." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Area</th>
                  <th>Flags</th>
                  <th>Balance due</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.id}>
                    <td>
                      <strong>{client.full_name}</strong>
                    </td>
                    <td>{client.phone}</td>
                    <td className="muted">{client.area || "—"}</td>
                    <td>
                      {client.allergies ? <Badge tone="danger">Allergy</Badge> : null}
                      {client.chronic_conditions ? <Badge tone="info">Chronic</Badge> : null}
                    </td>
                    <td>{Number(client.balance_due) > 0 ? <strong className="text-danger">${client.balance_due}</strong> : <span className="muted">$0.00</span>}</td>
                    <td>
                      <Button type="button" variant="secondary" onClick={() => open(client)}>
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      {selected ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2>{selected.full_name}</h2>
              <p className="muted small">
                {selected.phone}
                {selected.email ? ` · ${selected.email}` : ""}
                {selected.area ? ` · ${selected.area}` : ""}
              </p>
            </div>
            <Button type="button" variant="secondary" onClick={() => setSelected(null)}>
              Close
            </Button>
          </div>

          {selected.allergies ? <Notice tone="danger">Allergies: {selected.allergies}</Notice> : null}
          {selected.chronic_conditions ? <Notice>Chronic conditions: {selected.chronic_conditions}</Notice> : null}

          {history ? (
            <>
              <div className="metric-grid">
                <div className="metric-card">
                  <span>Visits</span>
                  <strong>{history.visits}</strong>
                </div>
                <div className="metric-card">
                  <span>Total spent</span>
                  <strong>${history.total_spent}</strong>
                </div>
                <div className="metric-card">
                  <span>Average basket</span>
                  <strong>${history.average_basket}</strong>
                </div>
                <div className="metric-card">
                  <span>Balance due</span>
                  <strong>${history.balance_due}</strong>
                </div>
                <div className="metric-card">
                  <span>Last visit</span>
                  <strong>{history.last_visit ? new Date(history.last_visit).toLocaleDateString() : "—"}</strong>
                  {history.days_since_last_visit !== null ? <small className="muted">{history.days_since_last_visit} days ago</small> : null}
                </div>
              </div>

              {history.top_products.length > 0 ? (
                <>
                  <h3>What they usually buy</h3>
                  <ul className="clean-list">
                    {history.top_products.map((product) => (
                      <li key={product.medicine_id}>
                        {product.name} — {product.units} units, ${product.spend}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}

              <div className="section-header">
                <h3>Account</h3>
                <Button type="button" variant="secondary" onClick={postPayment}>
                  Record a payment
                </Button>
              </div>
              {ledger.length === 0 ? (
                <p className="muted small">No account activity. Charges appear here when a sale is put on account.</p>
              ) : (
                <Table>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Memo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ledger.map((entry) => (
                        <tr key={entry.id}>
                          <td className="muted small">{new Date(entry.created_at).toLocaleString()}</td>
                          <td>
                            <Badge tone={entry.entry_type === "PAYMENT" ? "success" : entry.entry_type === "CHARGE" ? "warning" : "neutral"}>
                              {entry.entry_type}
                            </Badge>
                          </td>
                          <td>${entry.amount}</td>
                          <td className="muted">{entry.memo}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Table>
              )}
              <p className="muted small">
                The ledger is append-only: a mistake is corrected with a balancing entry, never by editing history.
              </p>
            </>
          ) : (
            <div className="skeleton-card" />
          )}
        </section>
      ) : null}
    </>
  );
}
