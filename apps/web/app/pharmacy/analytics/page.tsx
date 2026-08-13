"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import type {
  AnalyticsOverview,
  DemandSignals,
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

type Tab = "overview" | "inventory" | "replenishment" | "demand";

const TABS: [Tab, string][] = [
  ["overview", "Overview"],
  ["inventory", "Inventory health"],
  ["replenishment", "What to reorder"],
  ["demand", "Demand you missed"]
];

export default function PharmacyAnalyticsPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [inventory, setInventory] = useState<{ stock: StockSnapshot; turnover: TurnoverMetrics; movement: MovementClassification } | null>(null);
  const [replenishment, setReplenishment] = useState<ReplenishmentPlan | null>(null);
  const [demand, setDemand] = useState<DemandSignals | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<AnalyticsOverview>("/pharmacy/analytics/overview/").then(setOverview).catch(() => setError("Could not load analytics."));
  }, []);

  useEffect(() => {
    if (tab === "inventory" && !inventory) {
      apiFetch<typeof inventory>("/pharmacy/analytics/inventory/").then(setInventory).catch(() => setError("Could not load inventory analytics."));
    }
    if (tab === "replenishment" && !replenishment) {
      apiFetch<ReplenishmentPlan>("/pharmacy/analytics/replenishment/").then(setReplenishment).catch(() => setError("Could not load replenishment."));
    }
    if (tab === "demand" && !demand) {
      apiFetch<DemandSignals>("/pharmacy/analytics/demand/").then(setDemand).catch(() => setError("Could not load demand signals."));
    }
  }, [tab, inventory, replenishment, demand]);

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Analytics</h1>
          <p className="muted">
            {overview ? `${overview.pharmacy.name} · generated ${new Date(overview.generated_at).toLocaleString()}` : "Loading..."}
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

      {tab === "overview" ? <OverviewTab data={overview} /> : null}
      {tab === "inventory" ? <InventoryTab data={inventory} /> : null}
      {tab === "replenishment" ? <ReplenishmentTab data={replenishment} /> : null}
      {tab === "demand" ? <DemandTab data={demand} /> : null}
    </>
  );
}

function OverviewTab({ data }: { data: AnalyticsOverview | null }) {
  if (!data) return <div className="skeleton-card" />;
  const { stock, sales_30d: sales, turnover, platform, revenue_series: series } = data;

  return (
    <>
      <section className="metric-grid">
        <Metric label="Revenue (30d)" value={`$${sales.revenue}`} note={`${sales.transactions} transactions`} />
        <Metric label="Gross margin" value={`$${sales.gross_margin}`} note={`${sales.gross_margin_percent}% of revenue`} />
        <Metric label="Average basket" value={`$${sales.average_basket}`} note={`${sales.average_units_per_basket} units`} />
        <Metric label="Stock at cost" value={`$${stock.stock_value_at_cost}`} note={`${stock.sku_count} SKUs, ${stock.units_on_hand} units`} />
        <Metric label="Inventory turnover" value={`${turnover.inventory_turnover_annualised}×`} note="annualised" />
        <Metric
          label="GMROI"
          value={`${turnover.gmroi}`}
          note="margin per $ of stock"
          tone={turnover.gmroi >= 2 ? "good" : turnover.gmroi >= 1 ? undefined : "bad"}
        />
      </section>

      <section className="panel">
        <h3>Revenue, last 30 days</h3>
        <Sparkline
          points={series.map((point) => ({ label: point.date, value: Number(point.revenue) }))}
          valueFormatter={(value) => `$${value.toFixed(2)}`}
        />
      </section>

      <div className="panel-row">
        <section className="panel">
          <h3>Where the money comes from</h3>
          {/* Two nominal categories sharing one hue: the labels carry identity, so no
              two-colour palette is invented here. */}
          <BarMeter
            label="MoPH-regulated products"
            value={sales.regulated_share_percent}
            max={100}
            caption={`$${sales.regulated_revenue} — price fixed by the ministry, so margin here is not yours to set`}
          />
          <BarMeter
            label="Free-priced products"
            value={100 - sales.regulated_share_percent}
            max={100}
            caption={`$${sales.free_priced_revenue} — the part of the business where pricing is actually a lever`}
          />
          <p className="muted small">
            Revenue by channel:{" "}
            {Object.entries(sales.revenue_by_channel).length === 0
              ? "no sales in the window"
              : Object.entries(sales.revenue_by_channel)
                  .map(([channel, amount]) => `${channel.replace(/_/g, " ").toLowerCase()} $${amount}`)
                  .join(" · ")}
          </p>
        </section>

        <section className="panel">
          <h3>Risk on the shelf</h3>
          <ul className="kpi-list">
            <li>
              <span>Expiring within 30 days</span>
              <strong className={stock.units_expiring_30d > 0 ? "text-danger" : ""}>
                ${stock.value_expiring_30d} ({stock.units_expiring_30d} units)
              </strong>
            </li>
            <li>
              <span>Expiring within 90 days</span>
              <strong>
                ${stock.value_expiring_90d} ({stock.units_expiring_90d} units)
              </strong>
            </li>
            <li>
              <span>Already expired</span>
              <strong className={stock.expired_batches > 0 ? "text-danger" : ""}>
                ${stock.expired_value_at_cost} ({stock.expired_batches} batches)
              </strong>
            </li>
            <li>
              <span>Low stock SKUs</span>
              <strong>{stock.low_stock_skus}</strong>
            </li>
            <li>
              <span>Held for online orders</span>
              <strong>{stock.units_reserved} units</strong>
            </li>
            <li>
              <span>Days of inventory outstanding</span>
              <strong>{turnover.days_inventory_outstanding ?? "—"}</strong>
            </li>
          </ul>
        </section>
      </div>

      <section className="panel">
        <h3>Platform performance</h3>
        <div className="metric-grid">
          <Metric label="Online orders (30d)" value={`${platform.orders_received}`} note={`${platform.orders_accepted} accepted`} />
          <Metric
            label="Acceptance rate"
            value={`${platform.acceptance_rate_percent}%`}
            tone={platform.acceptance_rate_percent >= 90 ? "good" : platform.acceptance_rate_percent >= 70 ? undefined : "bad"}
          />
          <Metric
            label="Median time to accept"
            value={platform.median_acceptance_minutes !== null ? `${platform.median_acceptance_minutes} min` : "—"}
            note="shoppers see this as responsiveness"
          />
          <Metric
            label="Shopper rating"
            value={platform.rating_count > 0 ? `★ ${platform.rating_average}` : "not yet rated"}
            note={`${platform.rating_count} rating(s)`}
          />
          <Metric
            label="Fulfilment success"
            value={`${platform.fulfillment_success_rate}%`}
            note="feeds your search ranking"
            tone={platform.fulfillment_success_rate >= 95 ? "good" : undefined}
          />
        </div>
        <Notice>
          Acceptance speed, fulfilment rate and shopper ratings all feed the ranking a shopper sees. Improving them
          moves you up the results list.
        </Notice>
      </section>
    </>
  );
}

function InventoryTab({ data }: { data: { stock: StockSnapshot; turnover: TurnoverMetrics; movement: MovementClassification } | null }) {
  if (!data) return <div className="skeleton-card" />;
  const { stock, turnover, movement } = data;
  const deadValue = movement.dead_stock.reduce((sum, row) => sum + Number(row.value_at_cost || 0), 0);
  const abcTotal = Math.max(1, movement.counts.A + movement.counts.B + movement.counts.C);

  return (
    <>
      <section className="metric-grid">
        <Metric label="Stock at cost" value={`$${stock.stock_value_at_cost}`} />
        <Metric label="Stock at retail" value={`$${stock.stock_value_at_retail}`} note={`$${stock.potential_margin_value} potential margin`} />
        <Metric label="Turnover" value={`${turnover.inventory_turnover}×`} note={`over ${turnover.window_days} days`} />
        <Metric label="Sell-through" value={`${turnover.sell_through_percent}%`} />
        <Metric label="Dead stock" value={`$${deadValue.toFixed(2)}`} note={`no sale in ${movement.dead_stock_days} days`} tone={deadValue > 0 ? "bad" : "good"} />
        <Metric label="Never sold" value={`${movement.skus_with_no_sales}`} note="SKUs in stock with no sales" />
      </section>

      <section className="panel">
        <h3>ABC classification</h3>
        <p className="muted small">
          A = the products driving 80% of revenue, B = the next 15%, C = the long tail. Protect A from stockouts;
          question whether C deserves shelf space and cash.
        </p>
        {/* A/B/C is ordinal, so the three meters step one hue dark to light rather than
            using three arbitrary colours. */}
        <div className="abc-row">
          <BarMeter
            label={`Class A — ${movement.counts.A} SKUs`}
            value={movement.counts.A}
            max={abcTotal}
            intensity="dark"
            valueLabel={`${movement.counts.A}`}
            caption="drives 80% of revenue — never let these stock out"
          />
          <BarMeter
            label={`Class B — ${movement.counts.B} SKUs`}
            value={movement.counts.B}
            max={abcTotal}
            intensity="base"
            valueLabel={`${movement.counts.B}`}
            caption="the next 15% of revenue"
          />
          <BarMeter
            label={`Class C — ${movement.counts.C} SKUs`}
            value={movement.counts.C}
            max={abcTotal}
            intensity="light"
            valueLabel={`${movement.counts.C}`}
            caption="the long tail — question the shelf space and the cash"
          />
        </div>
      </section>

      <section className="panel">
        <h3>Top movers</h3>
        {movement.top_movers.length === 0 ? (
          <EmptyState title="No sales recorded in this window yet." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Class</th>
                  <th>Units</th>
                  <th>Revenue</th>
                  <th>Share</th>
                  <th>Units/day</th>
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
          <h3>Cash trapped in dead stock</h3>
          <p className="muted small">No movement in {movement.dead_stock_days} days. Consider returning, discounting or delisting.</p>
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Units</th>
                  <th>Value at cost</th>
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
  if (!data) return <div className="skeleton-card" />;
  return (
    <>
      <section className="panel">
        <div className="section-header">
          <div>
            <h3>Reorder suggestions</h3>
            <p className="muted small">
              Reorder point = average daily demand × {data.lead_time_days} day lead time + safety stock, sized for a{" "}
              {data.service_level_percent}% service level over the last {data.window_days} days. Anything at or below
              its reorder point is a buy-now line.
            </p>
          </div>
          <Badge tone={data.reorder_now_count > 0 ? "warning" : "success"}>{data.reorder_now_count} to reorder</Badge>
        </div>

        {data.suggestions.length === 0 ? (
          <EmptyState title="Not enough sales history yet to compute reorder points." />
        ) : (
          <Table>
            <table className="table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>On hand</th>
                  <th>Demand/day</th>
                  <th>Variability</th>
                  <th>Safety stock</th>
                  <th>Reorder point</th>
                  <th>Days of cover</th>
                  <th>Suggested order</th>
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
  if (!data) return <div className="skeleton-card" />;
  return (
    <section className="panel">
      <h3>Demand your till never saw</h3>
      <p className="muted small">
        Searches and baskets in {data.area || "your area"} over the last {data.window_days} days that no nearby
        pharmacy could fill. This is revenue that walked away before it reached a counter.
      </p>
      {data.signals.length === 0 ? (
        <EmptyState title="No unmet demand recorded in your area yet." />
      ) : (
        <Table>
          <table className="table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Requests</th>
                <th>Units wanted</th>
                <th>Source</th>
                <th>Do you stock it?</th>
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
                      <Badge tone="warning">In stock — you may have been out at the time</Badge>
                    ) : (
                      <Badge tone="danger">Not stocked</Badge>
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

function Metric({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "good" | "bad" }) {
  return (
    <div className={`metric-card${tone === "good" ? " metric-card-good" : tone === "bad" ? " metric-card-bad" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {note ? <small className="muted">{note}</small> : null}
    </div>
  );
}
