"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Client, ClientHistory, ClientLedgerEntry, Paginated } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

export default function ClientsPage() {
  const t = useTranslations();
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
      .catch(() => setError(t("pharmacyClients.loadError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      setMessage(t("pharmacyClients.addedNotice", { name: form.full_name }));
      setShowForm(false);
      setForm({ ...form, full_name: "", phone: "", email: "", allergies: "", chronic_conditions: "", notes: "" });
      load();
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyClients.saveFailed"));
    }
  }

  async function postPayment() {
    if (!selected) return;
    const amount = window.prompt(t("pharmacyClients.paymentPrompt"));
    if (!amount) return;
    try {
      await apiFetch(`/pharmacy/clients/${selected.id}/ledger/`, {
        method: "POST",
        body: JSON.stringify({ entry_type: "PAYMENT", amount, memo: "Counter payment" })
      });
      setMessage(t("pharmacyClients.paymentRecorded"));
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
          <h1>{t("pharmacyClients.title")}</h1>
          <p className="muted">{t("pharmacyClients.subtitle")}</p>
        </div>
        <Button type="button" onClick={() => setShowForm((current) => !current)}>
          {showForm ? t("pharmacyClients.close") : t("pharmacyClients.addClient")}
        </Button>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {showForm ? (
        <section className="panel">
          <h3>{t("pharmacyClients.newClient")}</h3>
          <form onSubmit={createClient}>
            <div className="form-grid">
              <Field label={t("pharmacyClients.fullName")}>
                <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required />
              </Field>
              <Field label={t("pharmacyClients.phone")} hint={t("pharmacyClients.phoneHint")}>
                <input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} required />
              </Field>
              <Field label={t("pharmacyClients.email")}>
                <input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
              </Field>
              <Field label={t("pharmacyClients.area")}>
                <input value={form.area} onChange={(event) => setForm({ ...form, area: event.target.value })} />
              </Field>
              <Field label={t("pharmacyClients.insuranceProvider")}>
                <input value={form.insurance_provider} onChange={(event) => setForm({ ...form, insurance_provider: event.target.value })} />
              </Field>
              <Field label={t("pharmacyClients.creditLimit")}>
                <input value={form.credit_limit} onChange={(event) => setForm({ ...form, credit_limit: event.target.value })} />
              </Field>
            </div>
            <Field label={t("pharmacyClients.allergies")} hint={t("pharmacyClients.allergiesHint")}>
              <input
                value={form.allergies}
                onChange={(event) => setForm({ ...form, allergies: event.target.value })}
                placeholder={t("pharmacyClients.allergiesPlaceholder")}
              />
            </Field>
            <Field label={t("pharmacyClients.chronicConditions")}>
              <input value={form.chronic_conditions} onChange={(event) => setForm({ ...form, chronic_conditions: event.target.value })} />
            </Field>
            <Field label={t("pharmacyClients.notes")}>
              <input value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
            </Field>
            <Button type="submit">{t("pharmacyClients.saveClient")}</Button>
          </form>
        </section>
      ) : null}

      <section className="panel">
        <div className="search-bar">
          <Field label={t("pharmacyClients.search")}>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("pharmacyClients.searchPlaceholder")} />
          </Field>
        </div>

        {clients.length === 0 ? (
          <EmptyState title={t("pharmacyClients.noClientsTitle")} detail={t("pharmacyClients.noClientsDetail")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyClients.name")}</th>
                  <th>{t("pharmacyClients.phone")}</th>
                  <th>{t("pharmacyClients.area")}</th>
                  <th>{t("pharmacyClients.flags")}</th>
                  <th>{t("pharmacyClients.balanceDue")}</th>
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
                      {client.allergies ? <Badge tone="danger">{t("pharmacyClients.allergyBadge")}</Badge> : null}
                      {client.chronic_conditions ? <Badge tone="info">{t("pharmacyClients.chronicBadge")}</Badge> : null}
                    </td>
                    <td>{Number(client.balance_due) > 0 ? <strong className="text-danger">${client.balance_due}</strong> : <span className="muted">$0.00</span>}</td>
                    <td>
                      <Button type="button" variant="secondary" onClick={() => open(client)}>
                        {t("pharmacyClients.open")}
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
              {t("pharmacyClients.close")}
            </Button>
          </div>

          {selected.allergies ? <Notice tone="danger">{t("pharmacyClients.allergiesLabel", { allergies: selected.allergies })}</Notice> : null}
          {selected.chronic_conditions ? <Notice>{t("pharmacyClients.chronicLabel", { conditions: selected.chronic_conditions })}</Notice> : null}

          {history ? (
            <>
              <div className="metric-grid">
                <div className="metric-card">
                  <span>{t("pharmacyClients.visits")}</span>
                  <strong>{history.visits}</strong>
                </div>
                <div className="metric-card">
                  <span>{t("pharmacyClients.totalSpent")}</span>
                  <strong>${history.total_spent}</strong>
                </div>
                <div className="metric-card">
                  <span>{t("pharmacyClients.averageBasket")}</span>
                  <strong>${history.average_basket}</strong>
                </div>
                <div className="metric-card">
                  <span>{t("pharmacyClients.balanceDue")}</span>
                  <strong>${history.balance_due}</strong>
                </div>
                <div className="metric-card">
                  <span>{t("pharmacyClients.lastVisit")}</span>
                  <strong>{history.last_visit ? new Date(history.last_visit).toLocaleDateString() : "—"}</strong>
                  {history.days_since_last_visit !== null ? (
                    <small className="muted">{t("pharmacyClients.daysAgo", { days: history.days_since_last_visit })}</small>
                  ) : null}
                </div>
              </div>

              {history.top_products.length > 0 ? (
                <>
                  <h3>{t("pharmacyClients.whatTheyUsuallyBuy")}</h3>
                  <ul className="clean-list">
                    {history.top_products.map((product) => (
                      <li key={product.medicine_id}>
                        {t("pharmacyClients.unitsSpend", { name: product.name, units: product.units, spend: product.spend })}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}

              <div className="section-header">
                <h3>{t("pharmacyClients.account")}</h3>
                <Button type="button" variant="secondary" onClick={postPayment}>
                  {t("pharmacyClients.recordPayment")}
                </Button>
              </div>
              {ledger.length === 0 ? (
                <p className="muted small">{t("pharmacyClients.noAccountActivity")}</p>
              ) : (
                <Table>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t("pharmacyClients.date")}</th>
                        <th>{t("pharmacyClients.type")}</th>
                        <th>{t("pharmacyClients.amount")}</th>
                        <th>{t("pharmacyClients.memo")}</th>
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
              <p className="muted small">{t("pharmacyClients.ledgerNote")}</p>
            </>
          ) : (
            <div className="skeleton-card" />
          )}
        </section>
      ) : null}
    </>
  );
}
