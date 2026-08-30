"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import { useAssistantChat } from "@/lib/assistant/use-assistant-chat";
import { useRotatingChips } from "@/lib/assistant/use-rotating-chips";
import { ANALYTICS_PROMPTS } from "@/lib/assistant/analytics-prompts";
import type {
  AnalyticsDigest,
  AnalyticsInsights,
  AnalyticsOverview,
  DemandSignals,
  Insight,
  InsightSeverity,
  MovementClassification,
  ReplenishmentPlan,
  StockSnapshot,
  TurnoverMetrics
} from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { Table } from "@/components/ui/Table";
import { Sparkline } from "@/components/charts/Sparkline";
import { BarMeter } from "@/components/charts/BarMeter";
import { Icon } from "@/components/ui/Icon";

type Tab = "digest" | "overview" | "inventory" | "replenishment" | "demand" | "insights" | "ask";

export default function PharmacyAnalyticsPage() {
  const t = useTranslations();
  const TABS: [Tab, string][] = [
    ["digest", t("pharmacyAnalytics.tabDigest")],
    ["overview", t("pharmacyAnalytics.tabOverview")],
    ["inventory", t("pharmacyAnalytics.tabInventory")],
    ["replenishment", t("pharmacyAnalytics.tabReplenishment")],
    ["demand", t("pharmacyAnalytics.tabDemand")],
    ["insights", t("pharmacyAnalytics.tabInsights")],
    ["ask", t("pharmacyAnalytics.tabAsk")]
  ];
  const [tab, setTab] = useState<Tab>("digest");
  // The assistant lives at page level, like every other tab's data, so its transcript
  // survives switching away and back. Nothing is fetched until the Ask tab is first opened.
  const [askOpened, setAskOpened] = useState(false);
  const chat = useAssistantChat({
    enabled: askOpened,
    unavailableMessage: t("pharmacyAnalytics.askUnavailable"),
    sendErrorMessage: t("pharmacyAnalytics.askSendError")
  });
  const [digest, setDigest] = useState<AnalyticsDigest | null>(null);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [inventory, setInventory] = useState<{ stock: StockSnapshot; turnover: TurnoverMetrics; movement: MovementClassification } | null>(null);
  const [replenishment, setReplenishment] = useState<ReplenishmentPlan | null>(null);
  const [demand, setDemand] = useState<DemandSignals | null>(null);
  const [insights, setInsights] = useState<AnalyticsInsights | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<AnalyticsOverview>("/pharmacy/analytics/overview/").then(setOverview).catch(() => setError(t("pharmacyAnalytics.loadOverviewError")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (tab === "ask") setAskOpened(true);
  }, [tab]);

  useEffect(() => {
    if (tab === "digest" && !digest) {
      apiFetch<AnalyticsDigest>("/pharmacy/analytics/digest/").then(setDigest).catch(() => setError(t("pharmacyAnalytics.loadDigestError")));
    }
    if (tab === "inventory" && !inventory) {
      apiFetch<typeof inventory>("/pharmacy/analytics/inventory/")
        .then(setInventory)
        .catch(() => setError(t("pharmacyAnalytics.loadInventoryError")));
    }
    if (tab === "replenishment" && !replenishment) {
      apiFetch<ReplenishmentPlan>("/pharmacy/analytics/replenishment/")
        .then(setReplenishment)
        .catch(() => setError(t("pharmacyAnalytics.loadReplenishmentError")));
    }
    if (tab === "demand" && !demand) {
      apiFetch<DemandSignals>("/pharmacy/analytics/demand/").then(setDemand).catch(() => setError(t("pharmacyAnalytics.loadDemandError")));
    }
    if (tab === "insights" && !insights) {
      apiFetch<AnalyticsInsights>("/pharmacy/analytics/insights/").then(setInsights).catch(() => setError(t("pharmacyAnalytics.loadInsightsError")));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, digest, inventory, replenishment, demand, insights]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("pharmacyAnalytics.title")}</h1>
          <p className="muted">
            {overview
              ? t("pharmacyAnalytics.subtitle", { pharmacy: overview.pharmacy.name, when: new Date(overview.generated_at).toLocaleString() })
              : t("pharmacyAnalytics.loading")}
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}

      <nav className="tab-bar">
        {TABS.map(([key, label]) => (
          <button key={key} type="button" className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      {tab === "digest" ? <DigestTab data={digest} /> : null}
      {tab === "overview" ? <OverviewTab data={overview} /> : null}
      {tab === "inventory" ? <InventoryTab data={inventory} /> : null}
      {tab === "replenishment" ? <ReplenishmentTab data={replenishment} /> : null}
      {tab === "demand" ? <DemandTab data={demand} /> : null}
      {tab === "insights" ? <InsightsTab data={insights} /> : null}
      {tab === "ask" ? <AskTab chat={chat} /> : null}
    </>
  );
}

/**
 * A dedicated home for the natural-language assistant on the analytics page, instead of the
 * floating widget (which is suppressed on this route). Same conversation as the floating
 * assistant - same persona, same `/assistant/chat/` endpoint, same stored thread - but the
 * suggestion chips are drawn from an analytics-specific pool rather than the persona's
 * general pharmacy openers, and rotate the way the floating widget's do.
 */
function AskTab({ chat }: { chat: ReturnType<typeof useAssistantChat> }) {
  const t = useTranslations();
  const { turns, busy, error, send, startNewChat } = chat;
  const { chips, cycle, holdHandlers } = useRotatingChips(ANALYTICS_PROMPTS, turns.length <= 1 && !busy);
  const started = turns.length > 1;

  return (
    <section className="panel analytics-ask">
      <div className="analytics-ask__head section-header">
        <div>
          <h3>{t("pharmacyAnalytics.askHeading")}</h3>
          <p className="muted small">{t("pharmacyAnalytics.askIntro")}</p>
        </div>
        {started ? (
          <button type="button" className="assistant-newchat" onClick={startNewChat}>
            {t("pharmacyAnalytics.askNewChat")}
          </button>
        ) : null}
      </div>

      <div className="assistant-log" aria-live="polite">
        {turns.map((turn, index) => (
          <p
            key={index}
            className={`assistant-turn ${turn.role === "assistant" ? "assistant-turn-assistant" : "assistant-turn-user"}`}
          >
            {turn.body}
          </p>
        ))}
        {busy ? (
          <p className="assistant-turn assistant-turn-assistant assistant-typing" aria-label="Thinking">
            <span />
            <span />
            <span />
          </p>
        ) : null}
        {error ? <p className="assistant-error">{error}</p> : null}
      </div>

      {chips.length > 0 && !started ? (
        <div className="assistant-chips" {...holdHandlers}>
          {chips.map((suggestion, index) => (
            <button
              key={`${cycle}:${suggestion}`}
              type="button"
              className="assistant-chip"
              style={{ "--chip-index": index } as CSSProperties}
              onClick={() => send(suggestion)}
              disabled={busy}
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}

      <AskComposer onSend={send} busy={busy} placeholder={t("pharmacyAnalytics.askPlaceholder")} />

      <p className="assistant-foot">{t("pharmacyAnalytics.askDisclaimer")}</p>
    </section>
  );
}

function AskComposer({ onSend, busy, placeholder }: { onSend: (message: string) => void; busy: boolean; placeholder: string }) {
  const [draft, setDraft] = useState("");
  return (
    <form
      className="assistant-composer"
      onSubmit={(event) => {
        event.preventDefault();
        onSend(draft);
        setDraft("");
      }}
    >
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        maxLength={500}
        disabled={busy}
      />
      <button type="submit" disabled={busy || !draft.trim()} aria-label="Send">
        <Icon name="arrowRight" size={18} />
      </button>
    </form>
  );
}

function DigestTab({ data }: { data: AnalyticsDigest | null }) {
  const t = useTranslations();
  if (!data) return <div className="skeleton-card" />;
  return (
    <section className="panel">
      <div className="section-header">
        <h3>{data.headline}</h3>
        {data.stale ? (
          <Badge status tone="neutral">
            {t("pharmacyAnalytics.digestStale")}
          </Badge>
        ) : null}
      </div>
      {data.paragraphs.map((paragraph, index) => (
        <p key={index}>{paragraph}</p>
      ))}
      <p className="muted small">{t("pharmacyAnalytics.digestGeneratedAt", { when: new Date(data.generated_at).toLocaleString() })}</p>
    </section>
  );
}

function OverviewTab({ data }: { data: AnalyticsOverview | null }) {
  const t = useTranslations();
  if (!data) return <div className="skeleton-card" />;
  const { stock, sales_30d: sales, turnover, platform, revenue_series: series } = data;

  return (
    <>
      <section className="metric-grid">
        <Metric label={t("pharmacyAnalytics.revenue30d")} value={`$${sales.revenue}`} note={t("pharmacyAnalytics.transactionsNote", { count: sales.transactions })} />
        <Metric
          label={t("pharmacyAnalytics.grossMargin")}
          value={`$${sales.gross_margin}`}
          note={t("pharmacyAnalytics.grossMarginNote", { percent: sales.gross_margin_percent })}
        />
        <Metric
          label={t("pharmacyAnalytics.averageBasket")}
          value={`$${sales.average_basket}`}
          note={t("pharmacyAnalytics.averageBasketNote", { units: sales.average_units_per_basket })}
        />
        <Metric
          label={t("pharmacyAnalytics.stockAtCost")}
          value={`$${stock.stock_value_at_cost}`}
          note={t("pharmacyAnalytics.stockAtCostNote", { skus: stock.sku_count, units: stock.units_on_hand })}
        />
        <Metric
          label={t("pharmacyAnalytics.inventoryTurnover")}
          value={`${turnover.inventory_turnover_annualised}×`}
          note={t("pharmacyAnalytics.annualised")}
        />
        <Metric
          label={t("pharmacyAnalytics.gmroi")}
          value={`${turnover.gmroi}`}
          note={t("pharmacyAnalytics.marginPerDollar")}
          tone={turnover.gmroi >= 2 ? "good" : turnover.gmroi >= 1 ? undefined : "bad"}
        />
      </section>

      <section className="panel">
        <h3>{t("pharmacyAnalytics.revenueChartTitle")}</h3>
        <Sparkline
          points={series.map((point) => ({ label: point.date, value: Number(point.revenue) }))}
          valueFormatter={(value) => `$${value.toFixed(2)}`}
        />
      </section>

      <div className="panel-row">
        <section className="panel">
          <h3>{t("pharmacyAnalytics.whereMoneyComesFrom")}</h3>
          {/* Two nominal categories sharing one hue: the labels carry identity, so no
              two-colour palette is invented here. */}
          <BarMeter
            label={t("pharmacyAnalytics.mophRegulated")}
            value={sales.regulated_share_percent}
            max={100}
            caption={t("pharmacyAnalytics.mophRegulatedCaption", { amount: sales.regulated_revenue })}
          />
          <BarMeter
            label={t("pharmacyAnalytics.freePriced")}
            value={100 - sales.regulated_share_percent}
            max={100}
            caption={t("pharmacyAnalytics.freePricedCaption", { amount: sales.free_priced_revenue })}
          />
          <p className="muted small">
            {t("pharmacyAnalytics.revenueByChannel", {
              breakdown:
                Object.entries(sales.revenue_by_channel).length === 0
                  ? t("pharmacyAnalytics.noSalesInWindow")
                  : Object.entries(sales.revenue_by_channel)
                      .map(([channel, amount]) => `${channel.replace(/_/g, " ").toLowerCase()} $${amount}`)
                      .join(" · ")
            })}
          </p>
        </section>

        <section className="panel">
          <h3>{t("pharmacyAnalytics.riskOnShelf")}</h3>
          <ul className="kpi-list">
            <li>
              <span>{t("pharmacyAnalytics.expiring30")}</span>
              <strong className={stock.units_expiring_30d > 0 ? "text-danger" : ""}>
                ${stock.value_expiring_30d} {t("pharmacyAnalytics.unitsSuffix", { units: stock.units_expiring_30d })}
              </strong>
            </li>
            <li>
              <span>{t("pharmacyAnalytics.expiring90")}</span>
              <strong>
                ${stock.value_expiring_90d} {t("pharmacyAnalytics.unitsSuffix", { units: stock.units_expiring_90d })}
              </strong>
            </li>
            <li>
              <span>{t("pharmacyAnalytics.alreadyExpired")}</span>
              <strong className={stock.expired_batches > 0 ? "text-danger" : ""}>
                ${stock.expired_value_at_cost} {t("pharmacyAnalytics.batchesSuffix", { count: stock.expired_batches })}
              </strong>
            </li>
            <li>
              <span>{t("pharmacyAnalytics.lowStockSkus")}</span>
              <strong>{stock.low_stock_skus}</strong>
            </li>
            <li>
              <span>{t("pharmacyAnalytics.heldForOnline")}</span>
              <strong>{t("pharmacyAnalytics.heldUnits", { units: stock.units_reserved })}</strong>
            </li>
            <li>
              <span>{t("pharmacyAnalytics.daysInventoryOutstanding")}</span>
              <strong>{turnover.days_inventory_outstanding ?? "—"}</strong>
            </li>
          </ul>
        </section>
      </div>

      <section className="panel">
        <h3>{t("pharmacyAnalytics.platformPerformance")}</h3>
        <div className="metric-grid">
          <Metric
            label={t("pharmacyAnalytics.onlineOrders30d")}
            value={`${platform.orders_received}`}
            note={t("pharmacyAnalytics.acceptedNote", { count: platform.orders_accepted })}
          />
          <Metric
            label={t("pharmacyAnalytics.acceptanceRate")}
            value={`${platform.acceptance_rate_percent}%`}
            tone={platform.acceptance_rate_percent >= 90 ? "good" : platform.acceptance_rate_percent >= 70 ? undefined : "bad"}
          />
          <Metric
            label={t("pharmacyAnalytics.medianTimeToAccept")}
            value={platform.median_acceptance_minutes !== null ? t("pharmacyAnalytics.minutesValue", { min: platform.median_acceptance_minutes }) : "—"}
            note={t("pharmacyAnalytics.respondNote")}
          />
          <Metric
            label={t("pharmacyAnalytics.shopperRating")}
            value={platform.rating_count > 0 ? `★ ${platform.rating_average}` : t("pharmacyAnalytics.notYetRated")}
            note={t("pharmacyAnalytics.ratingCountNote", { count: platform.rating_count })}
          />
          <Metric
            label={t("pharmacyAnalytics.fulfilmentSuccess")}
            value={`${platform.fulfillment_success_rate}%`}
            note={t("pharmacyAnalytics.feedsRankingNote")}
            tone={platform.fulfillment_success_rate >= 95 ? "good" : undefined}
          />
        </div>
        <Notice>{t("pharmacyAnalytics.rankingNotice")}</Notice>
      </section>
    </>
  );
}

function InventoryTab({ data }: { data: { stock: StockSnapshot; turnover: TurnoverMetrics; movement: MovementClassification } | null }) {
  const t = useTranslations();
  if (!data) return <div className="skeleton-card" />;
  const { stock, turnover, movement } = data;
  const deadValue = movement.dead_stock.reduce((sum, row) => sum + Number(row.value_at_cost || 0), 0);
  const abcTotal = Math.max(1, movement.counts.A + movement.counts.B + movement.counts.C);

  return (
    <>
      <section className="metric-grid">
        <Metric label={t("pharmacyAnalytics.stockAtCost")} value={`$${stock.stock_value_at_cost}`} />
        <Metric
          label={t("pharmacyAnalytics.stockAtRetail")}
          value={`$${stock.stock_value_at_retail}`}
          note={t("pharmacyAnalytics.potentialMarginNote", { amount: stock.potential_margin_value })}
        />
        <Metric label={t("pharmacyAnalytics.turnover")} value={`${turnover.inventory_turnover}×`} note={t("pharmacyAnalytics.overDaysNote", { days: turnover.window_days })} />
        <Metric label={t("pharmacyAnalytics.sellThrough")} value={`${turnover.sell_through_percent}%`} />
        <Metric
          label={t("pharmacyAnalytics.deadStock")}
          value={`$${deadValue.toFixed(2)}`}
          note={t("pharmacyAnalytics.noSaleInDaysNote", { days: movement.dead_stock_days })}
          tone={deadValue > 0 ? "bad" : "good"}
        />
        <Metric label={t("pharmacyAnalytics.neverSold")} value={`${movement.skus_with_no_sales}`} note={t("pharmacyAnalytics.skusNoSalesNote")} />
      </section>

      <section className="panel">
        <h3>{t("pharmacyAnalytics.abcClassification")}</h3>
        <p className="muted small">{t("pharmacyAnalytics.abcDescription")}</p>
        {/* A/B/C is ordinal, so the three meters step one hue dark to light rather than
            using three arbitrary colours. */}
        <div className="abc-row">
          <BarMeter
            label={t("pharmacyAnalytics.classA", { count: movement.counts.A })}
            value={movement.counts.A}
            max={abcTotal}
            intensity="dark"
            valueLabel={`${movement.counts.A}`}
            caption={t("pharmacyAnalytics.classACaption")}
          />
          <BarMeter
            label={t("pharmacyAnalytics.classB", { count: movement.counts.B })}
            value={movement.counts.B}
            max={abcTotal}
            intensity="base"
            valueLabel={`${movement.counts.B}`}
            caption={t("pharmacyAnalytics.classBCaption")}
          />
          <BarMeter
            label={t("pharmacyAnalytics.classC", { count: movement.counts.C })}
            value={movement.counts.C}
            max={abcTotal}
            intensity="light"
            valueLabel={`${movement.counts.C}`}
            caption={t("pharmacyAnalytics.classCCaption")}
          />
        </div>
      </section>

      <section className="panel">
        <h3>{t("pharmacyAnalytics.topMovers")}</h3>
        {movement.top_movers.length === 0 ? (
          <EmptyState title={t("pharmacyAnalytics.noSalesInWindowYet")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyAnalytics.product")}</th>
                  <th>{t("pharmacyAnalytics.class")}</th>
                  <th>{t("pharmacyAnalytics.units")}</th>
                  <th>{t("pharmacyAnalytics.revenue")}</th>
                  <th>{t("pharmacyAnalytics.share")}</th>
                  <th>{t("pharmacyAnalytics.unitsPerDay")}</th>
                </tr>
              </thead>
              <tbody>
                {movement.top_movers.slice(0, 15).map((row) => (
                  <tr key={row.medicine_id}>
                    <td>{row.name}</td>
                    <td>
                      <Badge tone={row.abc_class === "A" ? "success" : row.abc_class === "B" ? "warning" : "neutral"}>{row.abc_class}</Badge>
                    </td>
                    <td>{row.units}</td>
                    <td>${row.revenue}</td>
                    <td>{row.revenue_share_percent}%</td>
                    <td>{row.daily_velocity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>

      {movement.dead_stock.length > 0 ? (
        <section className="panel">
          <h3>{t("pharmacyAnalytics.cashTrapped")}</h3>
          <p className="muted small">{t("pharmacyAnalytics.noMovementNote", { days: movement.dead_stock_days })}</p>
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyAnalytics.product")}</th>
                  <th>{t("pharmacyAnalytics.units")}</th>
                  <th>{t("pharmacyAnalytics.valueAtCost")}</th>
                </tr>
              </thead>
              <tbody>
                {movement.dead_stock.map((row) => (
                  <tr key={row.medicine_id}>
                    <td>{row.name}</td>
                    <td>{row.units}</td>
                    <td>${row.value_at_cost}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        </section>
      ) : null}
    </>
  );
}

function ReplenishmentTab({ data }: { data: ReplenishmentPlan | null }) {
  const t = useTranslations();
  if (!data) return <div className="skeleton-card" />;
  return (
    <>
      <section className="panel">
        <div className="section-header">
          <div>
            <h3>{t("pharmacyAnalytics.reorderSuggestions")}</h3>
            <p className="muted small">
              {t("pharmacyAnalytics.reorderDescription", {
                leadTime: data.lead_time_days,
                serviceLevel: data.service_level_percent,
                windowDays: data.window_days
              })}
            </p>
          </div>
          <Badge tone={data.reorder_now_count > 0 ? "warning" : "success"}>{t("pharmacyAnalytics.toReorder", { count: data.reorder_now_count })}</Badge>
        </div>

        {data.suggestions.length === 0 ? (
          <EmptyState title={t("pharmacyAnalytics.notEnoughHistory")} />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pharmacyAnalytics.product")}</th>
                  <th>{t("pharmacyAnalytics.onHand")}</th>
                  <th>{t("pharmacyAnalytics.demandPerDay")}</th>
                  <th>{t("pharmacyAnalytics.variability")}</th>
                  <th>{t("pharmacyAnalytics.safetyStock")}</th>
                  <th>{t("pharmacyAnalytics.reorderPoint")}</th>
                  <th>{t("pharmacyAnalytics.daysOfCover")}</th>
                  <th>{t("pharmacyAnalytics.suggestedOrder")}</th>
                </tr>
              </thead>
              <tbody>
                {data.suggestions.map((row) => (
                  <tr key={row.medicine_id} className={row.needs_reorder ? "row-warning" : ""}>
                    <td>{row.name}</td>
                    <td>{row.units_on_hand}</td>
                    <td>{row.avg_daily_demand}</td>
                    <td>± {row.demand_std_dev}</td>
                    <td>{row.safety_stock}</td>
                    <td>{row.reorder_point}</td>
                    <td>{row.days_of_cover ?? "—"}</td>
                    <td>
                      {row.needs_reorder ? <strong>{row.suggested_order_quantity}</strong> : <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Table>
        )}
      </section>
    </>
  );
}

function DemandTab({ data }: { data: DemandSignals | null }) {
  const t = useTranslations();
  if (!data) return <div className="skeleton-card" />;
  return (
    <section className="panel">
      <h3>{t("pharmacyAnalytics.demandTitle")}</h3>
      <p className="muted small">
        {t("pharmacyAnalytics.demandDescription", { area: data.area || t("pharmacyAnalytics.yourArea"), windowDays: data.window_days })}
      </p>
      {data.signals.length === 0 ? (
        <EmptyState title={t("pharmacyAnalytics.noUnmetDemand")} />
      ) : (
        <Table>
          <table className="table">
            <thead>
              <tr>
                <th>{t("pharmacyAnalytics.product")}</th>
                <th>{t("pharmacyAnalytics.requests")}</th>
                <th>{t("pharmacyAnalytics.unitsWanted")}</th>
                <th>{t("pharmacyAnalytics.source")}</th>
                <th>{t("pharmacyAnalytics.doYouStock")}</th>
              </tr>
            </thead>
            <tbody>
              {data.signals.map((row) => (
                <tr key={`${row.medicine_id}-${row.source}`}>
                  <td>{row.name}</td>
                  <td>
                    <strong>{row.requests}</strong>
                  </td>
                  <td>{row.units_requested}</td>
                  <td className="muted">{row.source.toLowerCase()}</td>
                  <td>
                    {row.you_stock_it ? (
                      <Badge status tone="warning">{t("pharmacyAnalytics.inStockNote")}</Badge>
                    ) : (
                      <Badge status tone="danger">{t("pharmacyAnalytics.notStocked")}</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Table>
      )}
    </section>
  );
}

const INSIGHT_TONE: Record<InsightSeverity, "danger" | "warning" | "success" | "neutral"> = {
  critical: "danger",
  warning: "warning",
  opportunity: "success",
  info: "neutral"
};

function InsightsTab({ data }: { data: AnalyticsInsights | null }) {
  const t = useTranslations();
  if (!data) return <div className="skeleton-card" />;
  const severityLabel = (severity: InsightSeverity) =>
    t(`pharmacyAnalytics.severity${severity.charAt(0).toUpperCase()}${severity.slice(1)}`);

  return (
    <section className="panel">
      <h3>{t("pharmacyAnalytics.insightsTitle")}</h3>
      <p className="muted small">{t("pharmacyAnalytics.insightsDescription")}</p>
      {data.insights.length === 0 ? (
        <EmptyState title={t("pharmacyAnalytics.noInsights")} />
      ) : (
        <ul className="insight-list">
          {data.insights.map((insight: Insight) => (
            <li key={insight.id} className="insight-card">
              <div className="section-header">
                <strong>{insight.title}</strong>
                <Badge status tone={INSIGHT_TONE[insight.severity]}>{severityLabel(insight.severity)}</Badge>
              </div>
              {insight.detail ? <p className="muted small">{insight.detail}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Metric({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "good" | "bad" }) {
  return (
    <div className={`metric-card${tone === "good" ? " metric-card-good" : tone === "bad" ? " metric-card-bad" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {note ? <small className="muted">{note}</small> : null}
    </div>
  );
}
