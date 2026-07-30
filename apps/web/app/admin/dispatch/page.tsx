"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import type { DeliveryRoute, DispatchSummary } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

interface Board {
  pending_jobs: number;
  drivers_online: number;
  routes: DeliveryRoute[];
  totals: { planned_km: number; naive_km: number };
}

interface Preview {
  summary: DispatchSummary | null;
  detail?: string;
  routes?: { driver: string; distance_km: number; orders: string[]; stops: { kind: string; location: string; orders_served: number; units: number; arrival_minute: number }[] }[];
  unassigned?: string[];
}

export default function DispatchBoardPage() {
  const [board, setBoard] = useState<Board | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [boardData, previewData] = await Promise.all([
        apiFetch<Board>("/dispatch/board/"),
        apiFetch<Preview>("/dispatch/preview/")
      ]);
      setBoard(boardData);
      setPreview(previewData);
    } catch {
      setError("Could not load the dispatch board.");
    }
  }, []);

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
      setError((exception as ApiError).message || "Planning failed.");
    } finally {
      setBusy(false);
    }
  }

  const summary = preview?.summary;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Dispatch board</h1>
          <p className="muted">
            Orders are batched into routes that share pharmacy visits. The saving shown is measured against the same
            orders delivered one dedicated trip each.
          </p>
        </div>
        <Button type="button" onClick={plan} disabled={busy}>
          {busy ? "Planning..." : "Plan routes now"}
        </Button>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      <section className="metric-grid">
        <div className="metric-card">
          <span>Orders waiting</span>
          <strong>{board?.pending_jobs ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>Drivers online</span>
          <strong>{board?.drivers_online ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>Naive distance</span>
          <strong>{summary ? `${summary.naive_distance_km} km` : "—"}</strong>
          <small className="muted">one trip per order</small>
        </div>
        <div className="metric-card metric-card-good">
          <span>Optimised distance</span>
          <strong>{summary ? `${summary.optimised_distance_km} km` : "—"}</strong>
          <small className="muted">{summary ? `${summary.routes_used} route(s)` : ""}</small>
        </div>
        <div className="metric-card metric-card-good">
          <span>Distance saved</span>
          <strong>{summary ? `${summary.distance_saved_percent}%` : "—"}</strong>
          <small className="muted">{summary ? `${summary.distance_saved_km} km` : ""}</small>
        </div>
        <div className="metric-card metric-card-good">
          <span>Pharmacy visits avoided</span>
          <strong>{summary?.pickup_visits_avoided ?? 0}</strong>
          <small className="muted">{summary ? `${summary.shared_pickup_stops} shared stop(s)` : ""}</small>
        </div>
      </section>

      {summary ? (
        <Notice>
          {summary.assigned_jobs} of {summary.jobs} order(s) fit into {summary.routes_used} route(s) across{" "}
          {summary.stops} stops, using {summary.pickup_stops} pharmacy visits instead of{" "}
          {summary.pickup_stops + summary.pickup_visits_avoided}. Baseline: {summary.baseline_scope}.
          {summary.unassigned_jobs > 0
            ? ` ${summary.unassigned_jobs} order(s) could not be scheduled within their promised window — add a driver or widen the window.`
            : ""}
        </Notice>
      ) : (
        <Notice>{preview?.detail || "Nothing to plan yet."}</Notice>
      )}

      {preview?.routes && preview.routes.length > 0 ? (
        <section className="panel">
          <h3>Proposed plan (not yet committed)</h3>
          {preview.routes.map((route, index) => (
            <div className="allocation-card" key={index}>
              <div className="section-header">
                <strong>Driver {route.driver.slice(0, 8)}</strong>
                <span className="muted small">
                  {route.distance_km} km · {route.orders.length} order(s)
                </span>
              </div>
              <ol className="route-list compact">
                {route.stops.map((stop, stopIndex) => (
                  <li key={stopIndex} className="route-item">
                    <div>
                      <strong>
                        {stop.kind === "PICKUP" ? "Pick up" : "Deliver"} · {stop.location.split(":")[0]}
                      </strong>
                      <p className="muted small">
                        {stop.orders_served > 1 ? `${stop.orders_served} orders together · ` : ""}
                        {stop.units} unit(s) · +{Math.round(stop.arrival_minute)} min
                      </p>
                    </div>
                    {stop.orders_served > 1 ? <Badge tone="success">shared</Badge> : null}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </section>
      ) : null}

      <section className="panel">
        <h3>Committed routes</h3>
        {!board || board.routes.length === 0 ? <EmptyState title="No routes yet. Plan one above." /> : null}
        {board?.routes.map((route) => (
          <div className="allocation-card" key={route.id}>
            <div className="section-header">
              <div>
                <strong>{route.driver_name || "Unassigned"}</strong>
                <p className="muted small">
                  {route.orders_count} order(s) · {route.stops.length} stops · {route.planned_distance_km} km (naive{" "}
                  {route.naive_distance_km} km, saved {route.distance_saved_km.toFixed(1)} km) ·{" "}
                  {route.planned_duration_minutes} min · v{route.plan_version}
                </p>
              </div>
              <div className="actions">
                <Badge tone={route.status === "ACTIVE" ? "success" : route.status === "COMPLETED" ? "neutral" : "info"}>{route.status}</Badge>
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
                    Re-optimise remainder
                  </Button>
                ) : null}
              </div>
            </div>
            <ol className="route-list compact">
              {route.stops.map((stop) => (
                <li className="route-item" key={stop.id}>
                  <div>
                    <strong>
                      {stop.sequence}. {stop.kind === "PICKUP" ? "Pick up" : "Deliver"} — {stop.label}
                    </strong>
                    <p className="muted small">
                      {stop.orders_served > 1 ? `${stop.orders_served} orders in one visit · ` : ""}
                      {stop.units} unit(s)
                      {stop.planned_arrival ? ` · ~${new Date(stop.planned_arrival).toLocaleTimeString()}` : ""}
                    </p>
                  </div>
                  <Badge tone={stop.status === "DONE" ? "success" : stop.status === "FAILED" ? "danger" : "neutral"}>{stop.status}</Badge>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </section>
    </>
  );
}
