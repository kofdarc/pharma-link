"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { DeliveryRoute, Driver, RouteStop } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

/**
 * Driver console.
 *
 * The design principle: a driver should never have to work out the order themselves. They
 * see ONE next action at a time, and at each pharmacy they see every order to collect there
 * in a single list - which is the whole point of consolidating pickups.
 */
export default function DriverConsolePage() {
  const t = useTranslations();
  const [driver, setDriver] = useState<Driver | null>(null);
  const [route, setRoute] = useState<DeliveryRoute | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [codes, setCodes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const [me, current] = await Promise.all([
        apiFetch<Driver>("/driver/me/"),
        apiFetch<{ route: DeliveryRoute | null }>("/driver/routes/current/")
      ]);
      setDriver(me);
      setRoute(current.route);
    } catch {
      setError(t("driver.loadError"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(action: () => Promise<unknown>, successMessage: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(successMessage);
      await load();
    } catch (exception) {
      setError((exception as ApiError).message || t("driver.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  function toggleOnline() {
    if (!driver) return;
    void act(
      () => apiFetch("/driver/me/", { method: "PATCH", body: JSON.stringify({ is_online: !driver.is_online }) }),
      driver.is_online ? t("driver.nowOffline") : t("driver.nowOnline")
    );
  }

  function shareLocation() {
    if (!navigator.geolocation) {
      setError(t("driver.locationUnsupported"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        void act(
          () =>
            apiFetch("/driver/ping/", {
              method: "POST",
              body: JSON.stringify({
                latitude: position.coords.latitude.toFixed(6),
                longitude: position.coords.longitude.toFixed(6)
              })
            }),
          t("driver.locationUpdated")
        ),
      () => setError(t("driver.locationDenied"))
    );
  }

  if (loading) return <div className="skeleton-card" />;

  const stops = route?.stops ?? [];
  const nextStop = stops.find((stop) => stop.status === "PENDING" || stop.status === "ARRIVED");
  const completed = stops.filter((stop) => stop.status === "DONE").length;

  return (
    <>
      <div className="section-header">
        <div>
          <h1>{driver?.full_name}</h1>
          <p className="muted small">
            {driver?.vehicle_type.toLowerCase()} · {t("driver.capacityUnits", { capacity: driver?.capacity_units ?? 0 })}
            {driver?.last_ping_at
              ? ` · ${t("driver.lastLocation", { when: new Date(driver.last_ping_at).toLocaleTimeString() })}`
              : ""}
          </p>
        </div>
        <div className="actions">
          <Badge status tone={driver?.is_online ? "success" : "neutral"}>{driver?.is_online ? t("driver.online") : t("driver.offline")}</Badge>
          <Button type="button" variant="secondary" onClick={toggleOnline} disabled={busy}>
            {driver?.is_online ? t("driver.goOffline") : t("driver.goOnline")}
          </Button>
          <Button type="button" variant="secondary" onClick={shareLocation} disabled={busy}>
            {t("driver.updateLocation")}
          </Button>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {!route ? (
        <EmptyState
          title={t("driver.noRouteYet")}
          detail={driver?.is_online ? t("driver.onlineWaitingHint") : t("driver.goOnlineHint")}
        />
      ) : null}

      {route ? (
        <>
          <section className="panel route-summary">
            <div>
              <span className="muted">{t("driver.ordersOnRoute")}</span>
              <strong>{route.orders_count}</strong>
            </div>
            <div>
              <span className="muted">{t("driver.stops")}</span>
              <strong>{t("driver.stopsDone", { completed, total: stops.length })}</strong>
            </div>
            <div>
              <span className="muted">{t("driver.plannedDistance")}</span>
              <strong>{route.planned_distance_km} km</strong>
            </div>
            <div>
              <span className="muted">{t("driver.savedVsOneTrip")}</span>
              <strong className="price">{route.distance_saved_km.toFixed(1)} km</strong>
            </div>
            <div>
              <span className="muted">{t("driver.estDuration")}</span>
              <strong>{route.planned_duration_minutes} min</strong>
            </div>
            <Badge status tone={route.status === "ACTIVE" ? "success" : "info"}>{route.status}</Badge>
          </section>

          {route.planner_notes ? <Notice>{route.planner_notes}</Notice> : null}

          {route.status === "PROPOSED" || route.status === "OFFERED" ? (
            <section className="panel">
              <h3>{t("driver.acceptThisRoute")}</h3>
              <p className="muted">
                {t("driver.routeSummaryLine", {
                  orders: route.orders_count,
                  stops: stops.length,
                  distance: route.planned_distance_km,
                  duration: route.planned_duration_minutes
                })}
              </p>
              <Button
                type="button"
                onClick={() => void act(() => apiFetch(`/driver/routes/${route.id}/accept/`, { method: "POST" }), t("driver.routeAccepted"))}
                disabled={busy}
              >
                {t("driver.acceptRoute")}
              </Button>
            </section>
          ) : null}

          {nextStop && route.status === "ACTIVE" ? (
            <section className="panel panel-highlight">
              <div className="section-header">
                <div>
                  <span className="muted small">{t("driver.nextStop", { sequence: nextStop.sequence })}</span>
                  <h2>
                    {nextStop.kind === "PICKUP" ? t("driver.collectAt") : t("driver.deliverTo")} {nextStop.label}
                  </h2>
                  <p className="muted">{nextStop.address}</p>
                </div>
                <Badge tone={nextStop.kind === "PICKUP" ? "info" : "warning"}>{nextStop.kind}</Badge>
              </div>

              {nextStop.kind === "PICKUP" && nextStop.orders_served > 1 ? (
                <Notice tone="success">{t("driver.oneVisitMultiCustomer", { count: nextStop.orders_served })}</Notice>
              ) : null}

              <p className="muted small">
                {nextStop.planned_arrival
                  ? t("driver.plannedArrival", { when: new Date(nextStop.planned_arrival).toLocaleTimeString() })
                  : ""}
                {nextStop.window_end ? ` · ${t("driver.dueBy", { when: new Date(nextStop.window_end).toLocaleTimeString() })}` : ""}
              </p>

              <div className="stop-tasks">
                {nextStop.tasks.map((task) => (
                  <div className="task-card" key={task.id}>
                    <div className="section-header">
                      <div>
                        <strong>{task.order_reference}</strong>
                        <p className="muted small">
                          {nextStop.kind === "PICKUP" ? t("driver.forContact", { name: task.contact_name }) : task.contact_phone}
                        </p>
                      </div>
                      <span className="muted small">{t("driver.unitsCount", { count: task.units })}</span>
                    </div>
                    {nextStop.kind === "PICKUP" ? (
                      <label className="field">
                        <span>{t("driver.handoverCodeLabel")}</span>
                        <input
                          value={codes[task.order_fulfillment] ?? ""}
                          onChange={(event) => setCodes((current) => ({ ...current, [task.order_fulfillment]: event.target.value.replace(/\D/g, "").slice(0, 6) }))}
                          inputMode="numeric"
                          placeholder="000000"
                        />
                        <small>{t("driver.handoverCodeHint")}</small>
                      </label>
                    ) : null}
                  </div>
                ))}
              </div>

              <div className="actions">
                {nextStop.status === "PENDING" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void act(() => apiFetch(`/driver/stops/${nextStop.id}/arrive/`, { method: "POST" }), t("driver.arrivalRecorded"))}
                    disabled={busy}
                  >
                    {t("driver.iHaveArrived")}
                  </Button>
                ) : null}

                {nextStop.kind === "PICKUP" ? (
                  <Button
                    type="button"
                    onClick={() =>
                      void act(
                        () =>
                          apiFetch(`/driver/stops/${nextStop.id}/pickup/`, {
                            method: "POST",
                            body: JSON.stringify({
                              handover_codes: Object.fromEntries(
                                nextStop.tasks.map((task) => [task.order_fulfillment, codes[task.order_fulfillment] || ""])
                              )
                            })
                          }),
                        t("driver.collected")
                      )
                    }
                    disabled={busy}
                  >
                    {t("driver.confirmEverythingCollected")}
                  </Button>
                ) : (
                  <Button
                    type="button"
                    onClick={() => void act(() => apiFetch(`/driver/stops/${nextStop.id}/deliver/`, { method: "POST", body: JSON.stringify({ recipient_note: "" }) }), t("driver.delivered"))}
                    disabled={busy}
                  >
                    {t("driver.confirmDelivered")}
                  </Button>
                )}

                <Button
                  type="button"
                  variant="danger"
                  onClick={() => {
                    const reason = window.prompt(t("driver.whatWentWrongPrompt"));
                    if (reason) void act(() => apiFetch(`/driver/stops/${nextStop.id}/fail/`, { method: "POST", body: JSON.stringify({ reason }) }), t("driver.stopFailed"));
                  }}
                  disabled={busy}
                >
                  {t("driver.cannotComplete")}
                </Button>

                <a
                  className="button button-secondary"
                  href={`https://www.google.com/maps/dir/?api=1&destination=${nextStop.latitude},${nextStop.longitude}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("driver.navigate")}
                </a>
              </div>
            </section>
          ) : null}

          <section className="panel">
            <div className="section-header">
              <h3>{t("driver.fullRoute")}</h3>
              {route.status === "ACTIVE" ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void act(() => apiFetch(`/driver/routes/${route.id}/reoptimise/`, { method: "POST" }), t("driver.reoptimised"))}
                  disabled={busy || stops.filter((stop) => stop.status === "PENDING").length < 2}
                  title={
                    stops.filter((stop) => stop.status === "PENDING").length < 2
                      ? t("driver.nothingToReoptimise")
                      : t("driver.reoptimiseHint")
                  }
                >
                  {t("driver.reoptimiseWhatIsLeft")}
                </Button>
              ) : null}
            </div>
            <ol className="route-list">
              {stops.map((stop) => (
                <StopRow key={stop.id} stop={stop} isNext={stop.id === nextStop?.id} t={t} />
              ))}
            </ol>
            <p className="muted small">{t("driver.planVersionNote", { version: route.plan_version })}</p>
          </section>
        </>
      ) : null}
    </>
  );
}

function StopRow({ stop, isNext, t }: { stop: RouteStop; isNext: boolean; t: ReturnType<typeof useTranslations> }) {
  const tone = stop.status === "DONE" ? "success" : stop.status === "FAILED" ? "danger" : isNext ? "warning" : "neutral";
  return (
    <li className={isNext ? "route-item route-item-next" : "route-item"}>
      <div>
        <strong>
          {stop.sequence}. {stop.kind === "PICKUP" ? t("driver.pickUp") : t("driver.deliver")} — {stop.label}
        </strong>
        <p className="muted small">
          {stop.orders_served > 1 ? t("driver.ordersInOneVisit", { count: stop.orders_served }) : ""}
          {t("driver.unitsCount", { count: stop.units })}
          {stop.planned_arrival ? ` · ~${new Date(stop.planned_arrival).toLocaleTimeString()}` : ""}
        </p>
        {stop.failure_reason ? <p className="muted small">{t("driver.failedReason", { reason: stop.failure_reason })}</p> : null}
      </div>
      <Badge status tone={tone}>{stop.status}</Badge>
    </li>
  );
}
