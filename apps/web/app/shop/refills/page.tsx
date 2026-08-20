"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch, asList } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { Paginated, RecurringOrder } from "@/types/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";

export default function RefillsPage() {
  const t = useTranslations();
  const [schedules, setSchedules] = useState<RecurringOrder[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    apiFetch<Paginated<RecurringOrder> | RecurringOrder[]>("/shop/recurring-orders/")
      .then((payload) => setSchedules(asList(payload)))
      .catch(() => setError(t("refills.loadError")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <h1>{t("refills.title")}</h1>
          <p className="muted">{t("refills.subtitle")}</p>
        </div>
      </div>

      {error ? <Notice tone="danger">{error}</Notice> : null}
      {loading ? <div className="skeleton-card" /> : null}
      {!loading && schedules.length === 0 ? (
        <EmptyState title={t("refills.noSchedules")} detail={t("refills.noSchedulesHint")} />
      ) : null}

      {schedules.map((schedule) => (
        <section className="panel" key={schedule.id}>
          <div className="section-header">
            <div>
              <h3>{schedule.label}</h3>
              <p className="muted small">
                {t("refills.everyDays", {
                  days: schedule.interval_days,
                  date: new Date(schedule.next_run_at).toLocaleDateString(),
                  hour: schedule.preferred_hour,
                  count: schedule.occurrences_created
                })}
              </p>
            </div>
            <Badge tone={schedule.is_active ? "success" : "neutral"}>{schedule.is_active ? t("refills.active") : t("refills.paused")}</Badge>
          </div>
          <p className="muted small">{t("refills.itemsPerCycle", { count: schedule.items.length })}</p>
          {schedule.last_error ? <Notice tone="danger">{t("refills.lastCycleError", { error: schedule.last_error })}</Notice> : null}
          <Button type="button" variant="secondary" onClick={() => toggle(schedule)}>
            {schedule.is_active ? t("refills.pause") : t("refills.resume")}
          </Button>
        </section>
      ))}

      <Notice>
        {t("refills.footerNoticeBefore")} <Link href="/shop/orders">{t("refills.myOrdersLink")}</Link>.
      </Notice>
    </>
  );
}
