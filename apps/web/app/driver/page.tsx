"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
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
      setError("Could not load your route.");
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
      setError((exception as ApiError).message || "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  function toggleOnline() {
    if (!driver) return;
    void act(
      () => apiFetch("/driver/me/", { method: "PATCH", body: JSON.stringify({ is_online: !driver.is_online }) }),
      driver.is_online ? "You are now offline." : "You are online and will be included in the next plan."
    );
  }

  function shareLocation() {
    if (!navigator.geolocation) {
      setError("This browser cannot share your location.");
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
          "Location updated. Future plans will start from where you are."
        ),
      () => setError("Location permission refused.")
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
            {driver?.vehicle_type.toLowerCase()} · capacity {driver?.capacity_units} units
            {driver?.last_ping_at ? ` · last location ${new Date(driver.last_ping_at).toLocaleTimeString()}` : ""}
          </p>
        </div>
        <div className="actions">
          <Badge tone={driver?.is_online ? "success" : "neutral"}>{driver?.is_online ? "Online" : "Offline"}</Badge>
          <Button type="button" variant="secondary" onClick={toggleOnline} disabled={busy}>
            {driver?.is_online ? "Go offline" : "Go online"}
          </Button>
          <Button type="button" variant="secondary" onClick={shareLocation} disabled={busy}>
            Update my location
          </Button>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {!route ? (
        <EmptyState
          title="No route assigned yet."
          detail={driver?.is_online ? "You are online. A route will appear when dispatch plans the next batch." : "Go online to be included in the next plan."}
        />
      ) : null}

      {route ? (
        <>
          <section className="panel route-summary">
            <div>
              <span className="muted">Orders on this route</span>
              <strong>{route.orders_count}</strong>
            </div>
            <div>
              <span className="muted">Stops</span>
              <strong>
                {completed}/{stops.length} done
              </strong>
            </div>
            <div>
              <span className="muted">Planned distance</span>
              <strong>{route.planned_distance_km} km</strong>
            </div>
            <div>
              <span className="muted">Saved vs one trip each</span>
              <strong className="price">{route.distance_saved_km.toFixed(1)} km</strong>
            </div>
            <div>
              <span className="muted">Est. duration</span>
              <strong>{route.planned_duration_minutes} min</strong>
            </div>
            <Badge tone={route.status === "ACTIVE" ? "success" : "info"}>{route.status}</Badge>
          </section>

          {route.planner_notes ? <Notice>{route.planner_notes}</Notice> : null}

          {route.status === "PROPOSED" || route.status === "OFFERED" ? (
            <section className="panel">
              <h3>Accept this route?</h3>
              <p className="muted">
                {route.orders_count} order(s) across {stops.length} stops, {route.planned_distance_km} km in about{" "}
                {route.planned_duration_minutes} minutes.
              </p>
              <Button type="button" onClick={() => void act(() => apiFetch(`/driver/routes/${route.id}/accept/`, { method: "POST" }), "Route accepted. Head to your first stop.")} disabled={busy}>
                Accept route
              </Button>
            </section>
          ) : null}

          {nextStop && route.status === "ACTIVE" ? (
            <section className="panel panel-highlight">
              <div className="section-header">
                <div>
                  <span className="muted small">NEXT STOP {nextStop.sequence}</span>
                  <h2>
                    {nextStop.kind === "PICKUP" ? "Collect at" : "Deliver to"} {nextStop.label}
                  </h2>
                  <p className="muted">{nextStop.address}</p>
                </div>
                <Badge tone={nextStop.kind === "PICKUP" ? "info" : "warning"}>{nextStop.kind}</Badge>
              </div>

              {nextStop.kind === "PICKUP" && nextStop.orders_served > 1 ? (
                <Notice tone="success">
                  One visit, {nextStop.orders_served} customers. Collect everything below before you leave.
                </Notice>
              ) : null}

              <p className="muted small">
                {nextStop.planned_arrival ? `Planned arrival ${new Date(nextStop.planned_arrival).toLocaleTimeString()}` : ""}
                {nextStop.window_end ? ` · due by ${new Date(nextStop.window_end).toLocaleTimeString()}` : ""}
              </p>

              <div className="stop-tasks">
                {nextStop.tasks.map((task) => (
                  <div className="task-card" key={task.id}>
                    <div className="section-header">
                      <div>
                        <strong>{task.order_reference}</strong>
                        <p className="muted small">
                          {nextStop.kind === "PICKUP" ? `For ${task.contact_name}` : task.contact_phone}
                        </p>
                      </div>
                      <span className="muted small">{task.units} unit(s)</span>
                    </div>
                    <ul className="clean-list">
                      {task.lines.map((line, index) => (
                        <li key={index}>
                          {line.quantity} × {line.medicine}
                        </li>
                      ))}
                    </ul>
                    {nextStop.kind === "PICKUP" ? (
                      <label className="field">
                        <span>Handover code from the pharmacist</span>
                        <input
                          value={codes[task.order_fulfillment] ?? ""}
                          onChange={(event) => setCodes((current) => ({ ...current, [task.order_fulfillment]: event.target.value.replace(/\D/g, "").slice(0, 6) }))}
                          inputMode="numeric"
                          placeholder="000000"
                        />
                        <small>Ask the pharmacist for the 6-digit code shown on their screen.</small>
                      </label>
                    ) : null}
                  </div>
                ))}
              </div>

              <div className="actions">
                {nextStop.status === "PENDING" ? (
                  <Button type="button" variant="secondary" onClick={() => void act(() => apiFetch(`/driver/stops/${nextStop.id}/arrive/`, { method: "POST" }), "Arrival recorded.")} disabled={busy}>
                    I have arrived
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
                        "Collected. On to the next stop."
                      )
                    }
                    disabled={busy}
                  >
                    Confirm everything collected
                  </Button>
                ) : (
                  <Button
                    type="button"
                    onClick={() => void act(() => apiFetch(`/driver/stops/${nextStop.id}/deliver/`, { method: "POST", body: JSON.stringify({ recipient_note: "" }) }), "Delivered.")}
                    disabled={busy}
                  >
                    Confirm delivered
                  </Button>
                )}

                <Button
                  type="button"
                  variant="danger"
                  onClick={() => {
                    const reason = window.prompt("What went wrong at this stop?");
                    if (reason) void act(() => apiFetch(`/driver/stops/${nextStop.id}/fail/`, { method: "POST", body: JSON.stringify({ reason }) }), "Stop marked as failed.");
                  }}
                  disabled={busy}
                >
                  Cannot complete
                </Button>

                <a
                  className="button button-secondary"
                  href={`https://www.google.com/maps/dir/?api=1&destination=${nextStop.latitude},${nextStop.longitude}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Navigate
                </a>
              </div>
            </section>
          ) : null}

          <section className="panel">
            <div className="section-header">
              <h3>Full route</h3>
              {route.status === "ACTIVE" && stops.filter((stop) => stop.status === "PENDING").length >= 3 ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void act(() => apiFetch(`/driver/routes/${route.id}/reoptimise/`, { method: "POST" }), "Remaining stops re-sequenced from your current position.")}
                  disabled={busy}
                >
                  Re-optimise what is left
                </Button>
              ) : null}
            </div>
            <ol className="route-list">
              {stops.map((stop) => (
                <StopRow key={stop.id} stop={stop} isNext={stop.id === nextStop?.id} />
              ))}
            </ol>
            <p className="muted small">
              Plan version {route.plan_version}. Completed stops are never re-ordered, so re-optimising mid-shift is
              always safe.
            </p>
          </section>
        </>
      ) : null}
    </>
  );
}

function StopRow({ stop, isNext }: { stop: RouteStop; isNext: boolean }) {
  const tone = stop.status === "DONE" ? "success" : stop.status === "FAILED" ? "danger" : isNext ? "warning" : "neutral";
  return (
    <li className={isNext ? "route-item route-item-next" : "route-item"}>
      <div>
        <strong>
          {stop.sequence}. {stop.kind === "PICKUP" ? "Pick up" : "Deliver"} — {stop.label}
        </strong>
        <p className="muted small">
          {stop.orders_served > 1 ? `${stop.orders_served} orders in one visit · ` : ""}
          {stop.units} unit(s)
          {stop.planned_arrival ? ` · ~${new Date(stop.planned_arrival).toLocaleTimeString()}` : ""}
        </p>
        {stop.failure_reason ? <p className="muted small">Failed: {stop.failure_reason}</p> : null}
      </div>
      <Badge tone={tone}>{stop.status}</Badge>
    </li>
  );
}
