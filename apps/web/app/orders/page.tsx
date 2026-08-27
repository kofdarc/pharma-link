"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { PatientShell } from "@/components/site/PatientShell";
import { CardSkeletons, EmptyPanel, PageHead, Segmented } from "@/components/patient/Page";
import { OrderCard } from "@/components/orders/OrderParts";
import { Icon } from "@/components/ui/Icon";
import { useOrders } from "@/lib/patient/store";
import { isOrderActive } from "@/lib/patient/types";

type Tab = "active" | "past";

export default function OrdersPage() {
  const { orders, ready } = useOrders();
  const [tab, setTab] = useState<Tab>("active");

  const { active, past } = useMemo(
    () => ({
      active: orders.filter(isOrderActive),
      past: orders.filter((order) => !isOrderActive(order)).sort((a, b) => b.placedAt.localeCompare(a.placedAt))
    }),
    [orders]
  );

  const visible = tab === "active" ? active : past;

  return (
    <PatientShell>
      <div className="hc-wrap hc-page">
        <PageHead title="Orders" lead="Everything on its way to you, and everything that has already arrived." />

        <Segmented
          label="Order status"
          value={tab}
          onChange={setTab}
          options={[
            { value: "active", label: "Active", count: active.length },
            { value: "past", label: "Past", count: past.length }
          ]}
        />

        <div className="hc-page-body">
          {!ready ? (
            <CardSkeletons count={2} />
          ) : visible.length > 0 ? (
            <div className="hc-cardgrid">
              {visible.map((order) => (
                <OrderCard key={order.id} order={order} />
              ))}
            </div>
          ) : tab === "active" ? (
            <EmptyPanel
              icon="box"
              title="Nothing on its way"
              body="Orders you place appear here while your pharmacies prepare them and until they reach your door."
            >
              <Link href="/search" className="hc-btn hc-btn-primary">
                <Icon name="search" size={17} />
                Search medications
              </Link>
            </EmptyPanel>
          ) : (
            <EmptyPanel
              icon="clock"
              title="No past orders yet"
              body="Once an order has been delivered it moves here, with its receipt."
            />
          )}
        </div>
      </div>
    </PatientShell>
  );
}
