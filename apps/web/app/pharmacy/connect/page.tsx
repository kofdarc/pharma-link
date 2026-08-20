"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { IntegrationKey, Medicine, OnboardingStatus, Paginated, SkuMapping, SyncRun, WebhookEndpoint } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";

/**
 * Onboarding + the bridge to a pharmacy's existing software.
 *
 * The pitch this page has to land: you do not replace your POS, and you do not clean up
 * your data. You keep your own product codes, we map them once, and a small connector
 * keeps stock in sync.
 */
export default function ConnectPage() {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [keys, setKeys] = useState<IntegrationKey[]>([]);
  const [newSecret, setNewSecret] = useState<IntegrationKey | null>(null);
  const [mappings, setMappings] = useState<SkuMapping[]>([]);
  const [unmappedOnly, setUnmappedOnly] = useState(true);
  const [catalog, setCatalog] = useState<Medicine[]>([]);
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [webhooks, setWebhooks] = useState<WebhookEndpoint[]>([]);
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [statusData, keyData, mappingData, runData, catalogData, webhookData] = await Promise.all([
        apiFetch<OnboardingStatus>("/pharmacy/onboarding/"),
        apiFetch<Paginated<IntegrationKey> | IntegrationKey[]>("/pharmacy/integration-keys/").catch(() => []),
        apiFetch<Paginated<SkuMapping> | SkuMapping[]>(`/pharmacy/sku-mappings/${unmappedOnly ? "?unmapped=true" : ""}`),
        apiFetch<Paginated<SyncRun> | SyncRun[]>("/pharmacy/sync-runs/"),
        apiFetch<Paginated<Medicine> | Medicine[]>("/medicines/"),
        apiFetch<Paginated<WebhookEndpoint> | WebhookEndpoint[]>("/pharmacy/webhooks/")
      ]);
      setStatus(statusData);
      setKeys(asList(keyData as Paginated<IntegrationKey> | IntegrationKey[]));
      setMappings(asList(mappingData));
      setRuns(asList(runData));
      setCatalog(asList(catalogData));
      setWebhooks(asList(webhookData));
    } catch {
      setError("Could not load the connection settings.");
    }
  }, [unmappedOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createKey() {
    setError("");
    try {
      const created = await apiFetch<IntegrationKey>("/pharmacy/integration-keys/", {
        method: "POST",
        body: JSON.stringify({ name: "POS connector" })
      });
      setNewSecret(created);
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || "Only the pharmacy owner can issue integration keys.");
    }
  }

  async function revokeKey(key: IntegrationKey) {
    if (!window.confirm(`Revoke ${key.key_id}? Any software using it will stop syncing immediately.`)) return;
    try {
      await apiFetch(`/pharmacy/integration-keys/${key.id}/`, { method: "DELETE" });
      setMessage("Key revoked.");
      void load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  async function addWebhook() {
    if (!newWebhookUrl.trim()) return;
    setError("");
    try {
      await apiFetch("/pharmacy/webhooks/", { method: "POST", body: JSON.stringify({ url: newWebhookUrl.trim(), events: [] }) });
      setNewWebhookUrl("");
      setMessage("Webhook added.");
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || "Could not add that webhook.");
    }
  }

  async function removeWebhook(webhook: WebhookEndpoint) {
    if (!window.confirm(`Remove the webhook to ${webhook.url}?`)) return;
    try {
      await apiFetch(`/pharmacy/webhooks/${webhook.id}/`, { method: "DELETE" });
      setMessage("Webhook removed.");
      void load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  async function mapCode(mapping: SkuMapping, medicineId: string) {
    try {
      await apiFetch(`/pharmacy/sku-mappings/${mapping.id}/`, {
        method: "PATCH",
        body: JSON.stringify(medicineId ? { medicine: medicineId } : { is_ignored: true })
      });
      setMessage(medicineId ? `${mapping.external_code} mapped.` : `${mapping.external_code} will be ignored.`);
      void load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Connect your pharmacy software</h1>
          <p className="muted">
            Keep the system you already use. The connector reads whatever your software can export and pushes changes
            to PharmaLink; your product codes stay yours.
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {status ? (
        <section className="panel">
          <div className="section-header">
            <h3>Setup progress</h3>
            <Badge tone={status.completed_steps === status.total_steps ? "success" : "warning"}>
              {status.completed_steps} of {status.total_steps} done
            </Badge>
          </div>
          <ol className="checklist">
            {status.steps.map((step) => (
              <li key={step.key} className={step.done ? "done" : ""}>
                <span className="check">{step.done ? "✓" : ""}</span>
                <div>
                  <strong>{step.title}</strong>
                  {step.detail ? <p className="muted small">{step.detail}</p> : null}
                  {step.hint ? <p className="muted small">{step.hint}</p> : null}
                </div>
              </li>
            ))}
          </ol>
          <p className="muted small">
            Each step is checked against real data, not a tick box — so &quot;done&quot; always means it actually works.
          </p>
        </section>
      ) : null}

      {newSecret?.secret ? (
        <section className="panel panel-highlight">
          <h3>Your new integration key</h3>
          <Notice tone="danger">
            The secret is shown <strong>once</strong>. Copy it into the connector config now — there is no endpoint
            that can retrieve it again.
          </Notice>
          <dl className="detail-grid">
            <div>
              <dt>Key id</dt>
              <dd>
                <code>{newSecret.key_id}</code>
              </dd>
            </div>
            <div>
              <dt>Secret</dt>
              <dd>
                <code className="big-code">{newSecret.secret}</code>
              </dd>
            </div>
          </dl>
          <p className="muted small">{newSecret.setup_hint}</p>
          <Button type="button" variant="secondary" onClick={() => setNewSecret(null)}>
            I have saved it
          </Button>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header">
          <h3>Integration keys</h3>
          <Button type="button" onClick={createKey}>
            Issue a key
          </Button>
        </div>
        {keys.length === 0 ? (
          <EmptyState title="No keys yet." detail="Issue one, then paste it into the connector's config file." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Key id</th>
                  <th>Scopes</th>
                  <th>Requests</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id}>
                    <td>{key.name}</td>
                    <td>
                      <code>{key.key_id}</code>
                    </td>
                    <td className="muted small">{key.scopes.join(", ")}</td>
                    <td>{key.request_count}</td>
                    <td className="muted small">{key.last_used_at ? new Date(key.last_used_at).toLocaleString() : "never"}</td>
                    <td>
                      <Badge tone={key.is_active ? "success" : "neutral"}>{key.is_active ? "Active" : "Revoked"}</Badge>
                    </td>
                    <td>
                      {key.is_active ? (
                        <Button type="button" variant="danger" onClick={() => revokeKey(key)}>
                          Revoke
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
        <p className="muted small">
          Every request is signed, so no password travels and a captured request cannot be replayed or re-pointed at
          another endpoint.
        </p>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Your product codes</h3>
            <p className="muted small">
              One-time mapping per code. Obvious names are matched automatically; the rest need a single choice from
              you, and then your software syncs untouched forever.
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={() => setUnmappedOnly((current) => !current)}>
            {unmappedOnly ? "Show all codes" : "Show unmapped only"}
          </Button>
        </div>

        {mappings.length === 0 ? (
          <EmptyState title={unmappedOnly ? "Nothing left to map." : "No product codes seen yet."} detail="Codes appear here after the connector's first sync." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Your code</th>
                  <th>Your description</th>
                  <th>Matched to</th>
                  <th>How</th>
                  <th>Map it</th>
                </tr>
              </thead>
              <tbody>
                {mappings.map((mapping) => (
                  <tr key={mapping.id} className={mapping.medicine ? "" : "row-warning"}>
                    <td>
                      <code>{mapping.external_code}</code>
                    </td>
                    <td>{mapping.external_name || "—"}</td>
                    <td>{mapping.medicine_detail?.display_name || <span className="muted">unmapped</span>}</td>
                    <td>
                      <Badge tone={mapping.match_method === "UNMATCHED" ? "danger" : mapping.match_method === "AUTO_FUZZY" ? "warning" : "success"}>
                        {mapping.match_method.replace(/_/g, " ").toLowerCase()}
                      </Badge>
                    </td>
                    <td>
                      <select value={mapping.medicine || ""} onChange={(event) => mapCode(mapping, event.target.value)}>
                        <option value="">Ignore this code</option>
                        {catalog.map((medicine) => (
                          <option key={medicine.id} value={medicine.id}>
                            {medicine.display_name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <h3>Sync history</h3>
        {runs.length === 0 ? (
          <EmptyState title="No syncs yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Kind</th>
                  <th>Status</th>
                  <th>Received</th>
                  <th>Applied</th>
                  <th>Unmapped</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td className="muted small">{new Date(run.created_at).toLocaleString()}</td>
                    <td>{run.kind}</td>
                    <td>
                      <Badge tone={run.status === "APPLIED" ? "success" : run.status === "PARTIAL" ? "warning" : "neutral"}>{run.status}</Badge>
                    </td>
                    <td>{run.rows_received}</td>
                    <td>{run.rows_applied}</td>
                    <td>{run.rows_unmapped}</td>
                    <td>{run.rows_failed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Webhooks</h3>
            <p className="muted small">
              Get a signed HTTP POST to your own software when something happens on the platform (a new order,
              a stock sync completing), instead of polling for changes.
            </p>
          </div>
        </div>
        <div className="form-grid">
          <Field label="Endpoint URL">
            <input
              value={newWebhookUrl}
              onChange={(event) => setNewWebhookUrl(event.target.value)}
              placeholder="https://your-system.example.com/pharmalink-webhook"
            />
          </Field>
          <Button type="button" onClick={addWebhook}>
            Add webhook
          </Button>
        </div>
        {webhooks.length === 0 ? (
          <EmptyState title="No webhooks configured." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Last delivery</th>
                  <th>Consecutive failures</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {webhooks.map((webhook) => (
                  <tr key={webhook.id} className={webhook.consecutive_failures > 0 ? "row-warning" : ""}>
                    <td>
                      <code>{webhook.url}</code>
                    </td>
                    <td>
                      <Badge tone={webhook.is_active ? "success" : "neutral"}>{webhook.is_active ? "Active" : "Disabled"}</Badge>
                    </td>
                    <td className="muted small">{webhook.last_delivery_at ? new Date(webhook.last_delivery_at).toLocaleString() : "never"}</td>
                    <td>{webhook.consecutive_failures}</td>
                    <td>
                      <Button type="button" variant="danger" onClick={() => removeWebhook(webhook)}>
                        Remove
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      <section className="panel">
        <h3>Running the connector</h3>
        <p className="muted small">
          A single Python file with no dependencies. It runs on the counter PC, reads your existing export (CSV or a
          read-only database query), and pushes only what changed.
        </p>
        <pre className="code-block">
{`# 1. Copy the connector and its config
copy tools\\connector\\pharmalink_connector.py C:\\PharmaLink\\
copy tools\\connector\\connector.config.example.json C:\\PharmaLink\\connector.config.json

# 2. Put your key id and secret in the config, and point it at your export file

# 3. Check the connection without changing anything
python pharmalink_connector.py --config connector.config.json --check

# 4. Run it continuously (or use --once from Task Scheduler)
python pharmalink_connector.py --config connector.config.json`}
        </pre>
        <p className="muted small">
          Stock is reconciled to whatever level your software reports, and the difference is written as a stock
          movement — so your ledger still explains every change.
        </p>
      </section>
    </>
  );
}
