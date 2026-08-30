"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
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
  const t = useTranslations();
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
  const [exportSetup, setExportSetup] = useState({
    path: "C:/PharmacyExports/stock.csv",
    delimiter: ",",
    externalCode: "item code",
    name: "item description",
    quantity: "available quantity",
    sellingPrice: "selling price",
    purchaseCost: "cost",
    expiryDate: "expiry date",
    supplierName: "supplier",
    minimumRows: "10"
  });

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
      setError(t("pharmacyConnect.loadError"));
    }
  }, [unmappedOnly]); // eslint-disable-line react-hooks/exhaustive-deps

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
      setError((exception as ApiError).message || t("pharmacyConnect.keyIssueFailed"));
    }
  }

  async function revokeKey(key: IntegrationKey) {
    if (!window.confirm(t("pharmacyConnect.revokeConfirm", { keyId: key.key_id }))) return;
    try {
      await apiFetch(`/pharmacy/integration-keys/${key.id}/`, { method: "DELETE" });
      setMessage(t("pharmacyConnect.keyRevoked"));
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
      setMessage(t("pharmacyConnect.webhookAdded"));
      void load();
    } catch (exception) {
      setError((exception as ApiError).message || t("pharmacyConnect.webhookAddFailed"));
    }
  }

  async function removeWebhook(webhook: WebhookEndpoint) {
    if (!window.confirm(t("pharmacyConnect.webhookRemoveConfirm", { url: webhook.url }))) return;
    try {
      await apiFetch(`/pharmacy/webhooks/${webhook.id}/`, { method: "DELETE" });
      setMessage(t("pharmacyConnect.webhookRemoved"));
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
      setMessage(
        medicineId
          ? t("pharmacyConnect.mappedMessage", { code: mapping.external_code })
          : t("pharmacyConnect.ignoredMessage", { code: mapping.external_code })
      );
      void load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  function updateExportSetup(field: keyof typeof exportSetup, value: string) {
    setExportSetup((current) => ({ ...current, [field]: value }));
  }

  function downloadConnectorConfig() {
    const activeKey = keys.find((key) => key.is_active);
    const minimumRows = Math.max(1, Number.parseInt(exportSetup.minimumRows, 10) || 10);
    const config = {
      api_base_url: process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/api\/?$/, "") || "http://localhost:8000",
      key_id: activeKey?.key_id || "REPLACE_WITH_INTEGRATION_KEY_ID",
      interval_seconds: 300,
      chunk_size: 500,
      timeout_seconds: 30,
      orders_out_file: "C:/HealthConnect/incoming-orders.csv",
      source: {
        type: "csv",
        path: exportSetup.path,
        encoding: "utf-8-sig",
        delimiter: exportSetup.delimiter || ",",
        minimum_file_age_seconds: 10,
        aggregate_duplicate_codes: true,
        safety: {
          enabled: true,
          minimum_rows: minimumRows,
          maximum_drop_fraction: 0.5
        },
        columns: {
          external_code: exportSetup.externalCode,
          name: exportSetup.name,
          quantity: exportSetup.quantity,
          selling_price: exportSetup.sellingPrice,
          purchase_cost: exportSetup.purchaseCost,
          expiry_date: exportSetup.expiryDate,
          supplier_name: exportSetup.supplierName
        }
      }
    };
    const blob = new Blob([`${JSON.stringify(config, null, 2)}\n`], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "connector.config.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyConnect.title")}</h1>
          <p className="muted">{t("pharmacyConnect.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {status ? (
        <section className="panel">
          <div className="section-header">
            <h3>{t("pharmacyConnect.setupProgress")}</h3>
            <Badge status tone={status.completed_steps === status.total_steps ? "success" : "warning"}>
              {t("pharmacyConnect.doneOfTotal", { done: status.completed_steps, total: status.total_steps })}
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
          <p className="muted small">{t("pharmacyConnect.eachStepChecked")}</p>
        </section>
      ) : null}

      <section className="panel panel-highlight">
        <div className="section-header">
          <div>
            <h3>{t("pharmacyConnect.existingSystemSetup")}</h3>
            <p className="muted small">{t("pharmacyConnect.existingSystemSetupHint")}</p>
          </div>
          <Badge status tone={runs.length > 0 ? "success" : keys.some((key) => key.is_active) ? "warning" : "neutral"}>
            {runs.length > 0
              ? t("pharmacyConnect.syncActive")
              : keys.some((key) => key.is_active)
                ? t("pharmacyConnect.readyForFirstSync")
                : t("pharmacyConnect.setupRequired")}
          </Badge>
        </div>

        <ol className="checklist">
          <li className={exportSetup.path ? "done" : ""}>
            <span className="check">{exportSetup.path ? "✓" : "1"}</span>
            <div>
              <strong>{t("pharmacyConnect.exportInventory")}</strong>
              <p className="muted small">{t("pharmacyConnect.exportInventoryHint")}</p>
            </div>
          </li>
          <li className={keys.some((key) => key.is_active) ? "done" : ""}>
            <span className="check">{keys.some((key) => key.is_active) ? "✓" : "2"}</span>
            <div>
              <strong>{t("pharmacyConnect.createConnectionKey")}</strong>
              <p className="muted small">{t("pharmacyConnect.createConnectionKeyHint")}</p>
            </div>
          </li>
          <li className={runs.length > 0 ? "done" : ""}>
            <span className="check">{runs.length > 0 ? "✓" : "3"}</span>
            <div>
              <strong>{t("pharmacyConnect.installAndTest")}</strong>
              <p className="muted small">{t("pharmacyConnect.installAndTestHint")}</p>
            </div>
          </li>
        </ol>

        <div className="form-grid">
          <Field label={t("pharmacyConnect.exportFilePath")} hint={t("pharmacyConnect.exportFilePathHint")}>
            <input value={exportSetup.path} onChange={(event) => updateExportSetup("path", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.delimiter")}>
            <select value={exportSetup.delimiter} onChange={(event) => updateExportSetup("delimiter", event.target.value)}>
              <option value=",">{t("pharmacyConnect.comma")}</option>
              <option value=";">{t("pharmacyConnect.semicolon")}</option>
              <option value="\t">{t("pharmacyConnect.tab")}</option>
            </select>
          </Field>
          <Field label={t("pharmacyConnect.productCodeColumn")}>
            <input value={exportSetup.externalCode} onChange={(event) => updateExportSetup("externalCode", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.descriptionColumn")}>
            <input value={exportSetup.name} onChange={(event) => updateExportSetup("name", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.quantityColumn")}>
            <input value={exportSetup.quantity} onChange={(event) => updateExportSetup("quantity", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.sellingPriceColumn")}>
            <input value={exportSetup.sellingPrice} onChange={(event) => updateExportSetup("sellingPrice", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.purchaseCostColumn")}>
            <input value={exportSetup.purchaseCost} onChange={(event) => updateExportSetup("purchaseCost", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.expiryColumn")}>
            <input value={exportSetup.expiryDate} onChange={(event) => updateExportSetup("expiryDate", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.supplierColumn")}>
            <input value={exportSetup.supplierName} onChange={(event) => updateExportSetup("supplierName", event.target.value)} />
          </Field>
          <Field label={t("pharmacyConnect.minimumRows")} hint={t("pharmacyConnect.minimumRowsHint")}>
            <input
              type="number"
              min="1"
              value={exportSetup.minimumRows}
              onChange={(event) => updateExportSetup("minimumRows", event.target.value)}
            />
          </Field>
        </div>
        <div className="actions">
          <Button type="button" onClick={downloadConnectorConfig}>
            {t("pharmacyConnect.downloadConfig")}
          </Button>
        </div>
        <Notice tone="info">{t("pharmacyConnect.safeConnectionNote")}</Notice>
      </section>

      {newSecret?.secret ? (
        <section className="panel panel-highlight">
          <h3>{t("pharmacyConnect.newIntegrationKey")}</h3>
          <Notice tone="danger">{t("pharmacyConnect.secretShownOnce")}</Notice>
          <dl className="detail-grid">
            <div>
              <dt>{t("pharmacyConnect.keyId")}</dt>
              <dd>
                <code>{newSecret.key_id}</code>
              </dd>
            </div>
            <div>
              <dt>{t("pharmacyConnect.secret")}</dt>
              <dd>
                <code className="big-code">{newSecret.secret}</code>
              </dd>
            </div>
          </dl>
          <p className="muted small">{newSecret.setup_hint}</p>
          <Button type="button" variant="secondary" onClick={() => setNewSecret(null)}>
            {t("pharmacyConnect.iHaveSavedIt")}
          </Button>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header">
          <h3>{t("pharmacyConnect.integrationKeys")}</h3>
          <Button type="button" onClick={createKey}>
            {t("pharmacyConnect.issueAKey")}
          </Button>
        </div>
        {keys.length === 0 ? (
          <EmptyState title={t("pharmacyConnect.noKeysYet")} detail={t("pharmacyConnect.issueKeyHint")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyConnect.name")}</th>
                  <th>{t("pharmacyConnect.keyId")}</th>
                  <th>{t("pharmacyConnect.scopes")}</th>
                  <th>{t("pharmacyConnect.requests")}</th>
                  <th>{t("pharmacyConnect.lastUsed")}</th>
                  <th>{t("pharmacyConnect.status")}</th>
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
                    <td className="muted small">
                      {key.last_used_at ? new Date(key.last_used_at).toLocaleString() : t("pharmacyConnect.never")}
                    </td>
                    <td>
                      <Badge status tone={key.is_active ? "success" : "neutral"}>
                        {key.is_active ? t("pharmacyConnect.active") : t("pharmacyConnect.revoked")}
                      </Badge>
                    </td>
                    <td>
                      {key.is_active ? (
                        <Button type="button" variant="danger" onClick={() => revokeKey(key)}>
                          {t("pharmacyConnect.revoke")}
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
        <p className="muted small">{t("pharmacyConnect.signedRequestsNote")}</p>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>{t("pharmacyConnect.yourProductCodes")}</h3>
            <p className="muted small">{t("pharmacyConnect.mappingHint")}</p>
          </div>
          <Button type="button" variant="secondary" onClick={() => setUnmappedOnly((current) => !current)}>
            {unmappedOnly ? t("pharmacyConnect.showAllCodes") : t("pharmacyConnect.showUnmappedOnly")}
          </Button>
        </div>

        {mappings.length === 0 ? (
          <EmptyState
            title={unmappedOnly ? t("pharmacyConnect.nothingLeftToMap") : t("pharmacyConnect.noCodesSeenYet")}
            detail={t("pharmacyConnect.codesAppearHint")}
          />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyConnect.yourCode")}</th>
                  <th>{t("pharmacyConnect.yourDescription")}</th>
                  <th>{t("pharmacyConnect.matchedTo")}</th>
                  <th>{t("pharmacyConnect.how")}</th>
                  <th>{t("pharmacyConnect.mapIt")}</th>
                </tr>
              </thead>
              <tbody>
                {mappings.map((mapping) => (
                  <tr key={mapping.id} className={mapping.medicine ? "" : "row-warning"}>
                    <td>
                      <code>{mapping.external_code}</code>
                    </td>
                    <td>{mapping.external_name || "—"}</td>
                    <td>{mapping.medicine_detail?.display_name || <span className="muted">{t("pharmacyConnect.unmapped")}</span>}</td>
                    <td>
                      <Badge status tone={mapping.match_method === "UNMATCHED" ? "danger" : mapping.match_method === "AUTO_FUZZY" ? "warning" : "success"}>
                        {mapping.match_method.replace(/_/g, " ").toLowerCase()}
                      </Badge>
                    </td>
                    <td>
                      <select value={mapping.medicine || ""} onChange={(event) => mapCode(mapping, event.target.value)}>
                        <option value="">{t("pharmacyConnect.ignoreThisCode")}</option>
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
        <h3>{t("pharmacyConnect.syncHistory")}</h3>
        {runs.length === 0 ? (
          <EmptyState title={t("pharmacyConnect.noSyncsYet")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyConnect.when")}</th>
                  <th>{t("pharmacyConnect.kind")}</th>
                  <th>{t("pharmacyConnect.status")}</th>
                  <th>{t("pharmacyConnect.received")}</th>
                  <th>{t("pharmacyConnect.applied")}</th>
                  <th>{t("pharmacyConnect.unmatched")}</th>
                  <th>{t("pharmacyConnect.failed")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td className="muted small">{new Date(run.created_at).toLocaleString()}</td>
                    <td>{run.kind}</td>
                    <td>
                      <Badge status tone={run.status === "APPLIED" ? "success" : run.status === "PARTIAL" ? "warning" : "neutral"}>{run.status}</Badge>
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
            <h3>{t("pharmacyConnect.webhooks")}</h3>
            <p className="muted small">{t("pharmacyConnect.webhooksHint")}</p>
          </div>
        </div>
        <div className="form-grid">
          <Field label={t("pharmacyConnect.endpointUrl")}>
            <input
              value={newWebhookUrl}
              onChange={(event) => setNewWebhookUrl(event.target.value)}
              placeholder="https://your-system.example.com/pharmalink-webhook"
            />
          </Field>
          <Button type="button" onClick={addWebhook}>
            {t("pharmacyConnect.addWebhook")}
          </Button>
        </div>
        {webhooks.length === 0 ? (
          <EmptyState title={t("pharmacyConnect.noWebhooksConfigured")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyConnect.url")}</th>
                  <th>{t("pharmacyConnect.status")}</th>
                  <th>{t("pharmacyConnect.lastDelivery")}</th>
                  <th>{t("pharmacyConnect.consecutiveFailures")}</th>
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
                      <Badge status tone={webhook.is_active ? "success" : "neutral"}>
                        {webhook.is_active ? t("pharmacyConnect.active") : t("pharmacyConnect.disabled")}
                      </Badge>
                    </td>
                    <td className="muted small">
                      {webhook.last_delivery_at ? new Date(webhook.last_delivery_at).toLocaleString() : t("pharmacyConnect.never")}
                    </td>
                    <td>{webhook.consecutive_failures}</td>
                    <td>
                      <Button type="button" variant="danger" onClick={() => removeWebhook(webhook)}>
                        {t("pharmacyConnect.remove")}
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
        <h3>{t("pharmacyConnect.runningConnector")}</h3>
        <p className="muted small">{t("pharmacyConnect.connectorDescription")}</p>
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
        <p className="muted small">{t("pharmacyConnect.stockReconciledNote")}</p>
      </section>
    </>
  );
}
