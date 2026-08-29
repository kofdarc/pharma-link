"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { DeliveryRoute, DispatchSummary, OrderFulfillment, OrderOffer } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

interface Board {
  pending_jobs: number;
  drivers_online: number;
  routes: DeliveryRoute[];
  needs_redispatch: OrderFulfillment[];
  totals: { planned_km: number; naive_km: number };
}

interface Preview {
  summary: DispatchSummary | null;
  detail?: string;
  routes?: { driver: string; distance_km: number; orders: string[]; stops: { kind: string; location: string; orders_served: number; units: number; arrival_minute: number }[] }[];
  unassigned?: string[];
}

export default function DispatchBoardPage() {
  const t = useTranslations();
  const [board, setBoard] = useState<Board | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [offersFor, setOffersFor] = useState<string | null>(null);
  const [offers, setOffers] = useState<{ order: string; offers: OrderOffer[] } | null>(null);

  const load = useCallback(async () => {
    try {
      const [boardData, previewData] = await Promise.all([
        apiFetch<Board>("/dispatch/board/"),
        apiFetch<Preview>("/dispatch/preview/")
      ]);
      setBoard(boardData);
      setPreview(previewData);
    } catch {
      setError(t("adminDispatch.loadError"));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function plan() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiFetch<{ detail: string; summary: DispatchSummary }>("/dispatch/plan/", { method: "POST" });
      setMessage(result.detail);
      await load();
    } catch (exception) {
      setError((exception as ApiError).message || t("adminDispatch.planningFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function viewOffers(orderId: string) {
    setOffersFor(orderId);
    setOffers(null);
    try {
      setOffers(await apiFetch<{ order: string; offers: OrderOffer[] }>(`/dispatch/orders/${orderId}/offers/`));
    } catch (exception) {
      setError((exception as ApiError).message || t("adminDispatch.offersFailed"));
    }
  }

  const summary = preview?.summary;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{t("adminDispatch.title")}</h1>
          <p className="muted">{t("adminDispatch.subtitle")}</p>
        </div>
        <Button type="button" onClick={plan} disabled={busy}>
          {busy ? t("adminDispatch.planning") : t("adminDispatch.planRoutesNow")}
        </Button>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      <section className="metric-grid">
        <div className="metric-card">
          <span>{t("adminDispatch.ordersWaiting")}</span>
          <strong>{board?.pending_jobs ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>{t("adminDispatch.driversOnline")}</span>
          <strong>{board?.drivers_online ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>{t("adminDispatch.naiveDistance")}</span>
          <strong>{summary ? `${summary.naive_distance_km} km` : "—"}</strong>
          <small className="muted">{t("adminDispatch.onePerOrder")}</small>
        </div>
        <div className="metric-card metric-card-good">
          <span>{t("adminDispatch.optimisedDistance")}</span>
          <strong>{summary ? `${summary.optimised_distance_km} km` : "—"}</strong>
          <small className="muted">{summary ? t("adminDispatch.routesCount", { count: summary.routes_used }) : ""}</small>
        </div>
        <div className="metric-card metric-card-good">
          <span>{t("adminDispatch.distanceSaved")}</span>
          <strong>{summary ? `${summary.distance_saved_percent}%` : "—"}</strong>
          <small className="muted">{summary ? `${summary.distance_saved_km} km` : ""}</small>
        </div>
        <div className="metric-card metric-card-good">
          <span>{t("adminDispatch.pharmacyVisitsAvoided")}</span>
          <strong>{summary?.pickup_visits_avoided ?? 0}</strong>
          <small className="muted">{summary ? t("adminDispatch.sharedStops", { count: summary.shared_pickup_stops }) : ""}</small>
        </div>
      </section>

      {summary ? (
        <Notice>
          {t("adminDispatch.summaryLine", {
            assigned: summary.assigned_jobs,
            total: summary.jobs,
            routes: summary.routes_used,
            stops: summary.stops,
            pickupStops: summary.pickup_stops,
            pickupStopsTotal: summary.pickup_stops + summary.pickup_visits_avoided,
            baseline: summary.baseline_scope
          })}
          {summary.unassigned_jobs > 0 ? t("adminDispatch.unassignedNote", { count: summary.unassigned_jobs }) : ""}
        </Notice>
      ) : (
        <Notice>{preview?.detail || t("adminDispatch.nothingToPlan")}</Notice>
      )}

      {preview?.routes && preview.routes.length > 0 ? (
        <section className="panel">
          <h3>{t("adminDispatch.proposedPlan")}</h3>
          {preview.routes.map((route, index) => (
            <div className="allocation-card" key={index}>
              <div className="section-header">
                <strong>{t("adminDispatch.driver", { id: route.driver.slice(0, 8) })}</strong>
                <span className="muted small">
                  {route.distance_km} km · {route.orders.length} order(s)
                </span>
              </div>
              <ol className="route-list compact">
                {route.stops.map((stop, stopIndex) => (
                  <li key={stopIndex} className="route-item">
                    <div>
                      <strong>
                        {stop.kind === "PICKUP" ? t("adminDispatch.pickUp") : t("adminDispatch.deliver")} · {stop.location.split(":")[0]}
                      </strong>
                      <p className="muted small">
                        {stop.orders_served > 1 ? t("adminDispatch.ordersTogether", { count: stop.orders_served }) : ""}
                        {stop.units} unit(s) · +{Math.round(stop.arrival_minute)} min
                      </p>
                    </div>
                    {stop.orders_served > 1 ? <Badge tone="success">{t("adminDispatch.shared")}</Badge> : null}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </section>
      ) : null}

      {board && board.needs_redispatch.length > 0 ? (
        <section className="panel panel-highlight">
          <h3>{t("adminDispatch.needsRedispatch")}</h3>
          <p className="muted small">{t("adminDispatch.needsRedispatchHint")}</p>
          {board.needs_redispatch.map((fulfillment) => (
            <div className="allocation-card" key={fulfillment.id}>
              <div className="section-header">
                <div>
                  <strong>{fulfillment.order_reference}</strong>
                  <p className="muted small">
                    {fulfillment.pharmacy_name} · {fulfillment.contact_name} · {fulfillment.order_area}
                  </p>
                </div>
                <Button type="button" variant="secondary" onClick={() => fulfillment.order && void viewOffers(fulfillment.order)}>
                  {t("adminDispatch.viewDriverOffers")}
                </Button>
              </div>
              {offersFor === fulfillment.order && offers ? (
                offers.offers.length === 0 ? (
                  <Notice>{t("adminDispatch.noDriverAvailable")}</Notice>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t("adminDispatch.driverCol")}</th>
                        <th>{t("adminDispatch.marginalDistance")}</th>
                        <th>{t("adminDispatch.totalRouteDistance")}</th>
                        <th>{t("adminDispatch.stopsAfter")}</th>
                        <th>{t("adminDispatch.sharesPickup")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {offers.offers.map((offer) => (
                        <tr key={offer.driver}>
                          <td>{offer.driver_name}</td>
                          <td>{offer.marginal_distance_km} km</td>
                          <td>{offer.total_distance_km} km</td>
                          <td>{offer.stops_after}</td>
                          <td>{offer.shares_a_pickup ? t("adminDispatch.yes") : t("adminDispatch.no")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              ) : null}
            </div>
          ))}
        </section>
      ) : null}

      <section className="panel">
        <h3>{t("adminDispatch.committedRoutes")}</h3>
        {!board || board.routes.length === 0 ? <EmptyState title={t("adminDispatch.noRoutesYet")} /> : null}
        {board?.routes.map((route) => (
          <div className="allocation-card" key={route.id}>
            <div className="section-header">
              <div>
                <strong>{route.driver_name || t("adminDispatch.unassigned")}</strong>
                <p className="muted small">
                  {route.orders_count} order(s) · {route.stops.length} stops · {route.planned_distance_km} km (naive{" "}
                  {route.naive_distance_km} km, saved {route.distance_saved_km.toFixed(1)} km) ·{" "}
                  {route.planned_duration_minutes} min · v{route.plan_version}
                </p>
              </div>
              <div className="actions">
                <Badge status tone={route.status === "ACTIVE" ? "success" : route.status === "COMPLETED" ? "neutral" : "info"}>{route.status}</Badge>
                {route.status === "ACTIVE" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() =>
                      void apiFetch(`/dispatch/routes/${route.id}/reoptimise/`, { method: "POST" })
                        .then((result) => setMessage((result as { detail: string }).detail))
                        .then(load)
                        .catch((exception) => setError((exception as ApiError).message))
                    }
                  >
                    {t("adminDispatch.reoptimiseRemainder")}
                  </Button>
                ) : null}
              </div>
            </div>
            <ol className="route-list compact">
              {route.stops.map((stop) => (
                <li className="route-item" key={stop.id}>
                  <div>
                    <strong>
                      {stop.sequence}. {stop.kind === "PICKUP" ? t("adminDispatch.pickUp") : t("adminDispatch.deliver")} — {stop.label}
                    </strong>
                    <p className="muted small">
                      {stop.orders_served > 1 ? t("adminDispatch.ordersInOneVisit", { count: stop.orders_served }) : ""}
                      {stop.units} unit(s)
                      {stop.planned_arrival ? ` · ~${new Date(stop.planned_arrival).toLocaleTimeString()}` : ""}
                    </p>
                  </div>
                  <Badge status tone={stop.status === "DONE" ? "success" : stop.status === "FAILED" ? "danger" : "neutral"}>{stop.status}</Badge>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </section>
    </>
  );
}
