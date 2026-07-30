"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import type { Paginated, RecurringOrder } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

export default function RefillsPage() {
  const [schedules, setSchedules] = useState<RecurringOrder[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    apiFetch<Paginated<RecurringOrder> | RecurringOrder[]>("/shop/recurring-orders/")
      .then((payload) => setSchedules(asList(payload)))
      .catch(() => setError("Could not load your repeat schedules."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  async function toggle(schedule: RecurringOrder) {
    try {
      await apiFetch(`/shop/recurring-orders/${schedule.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !schedule.is_active, items: schedule.items, address: schedule.address })
      });
      load();
    } catch (exception) {
      setError((exception as ApiError).message);
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1>Repeat refills</h1>
          <p className="muted">
            For chronic medication. Each cycle is sourced fresh, so if your usual pharmacy is out of stock or closed,
            the refill still happens from somewhere else.
          </p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && schedules.length === 0 ? (
        <EmptyState
          title="No repeat schedules yet."
          detail="Tick 'Repeat this order automatically' at checkout to create one."
        />
      ) : null}

      {schedules.map((schedule) => (
        <section className="panel" key={schedule.id}>
          <div className="section-header">
            <div>
              <h3>{schedule.label}</h3>
              <p className="muted small">
                Every {schedule.interval_days} days · next on {new Date(schedule.next_run_at).toLocaleDateString()} around{" "}
                {schedule.preferred_hour}:00 · {schedule.occurrences_created} order(s) created so far
              </p>
            </div>
            <Badge tone={schedule.is_active ? "success" : "neutral"}>{schedule.is_active ? "Active" : "Paused"}</Badge>
          </div>
          <p className="muted small">{schedule.items.length} item(s) per cycle</p>
          {schedule.last_error ? <Notice tone="danger">Last cycle: {schedule.last_error}</Notice> : null}
          <Button type="button" variant="secondary" onClick={() => toggle(schedule)}>
            {schedule.is_active ? "Pause" : "Resume"}
          </Button>
        </section>
      ))}

      <Notice>
        Scheduled orders only enter the delivery pool shortly before their window, so your stock is not held for
        days and your delivery can be batched with others going the same way. See <Link href="/shop/orders">my orders</Link>.
      </Notice>
    </>
  );
}
