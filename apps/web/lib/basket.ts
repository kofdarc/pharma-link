"use client";

import { useCallback, useEffect, useState } from "react";

export interface BasketItem {
  medicine: string;
  name: string;
  quantity: number;
  requires_prescription?: boolean;
}

const STORAGE_KEY = "pharmalink_basket";
const CHANGED_EVENT = "pharmalink:basket-changed";

function read(): BasketItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as BasketItem[]) : [];
  } catch {
    return [];
  }
}

function write(items: BasketItem[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  // Same-tab listeners: the storage event only fires in OTHER tabs.
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

/**
 * Basket state lives in localStorage rather than on the server.
 *
 * A basket is not a commitment: no stock is held until checkout, so keeping it client-side
 * avoids creating server state (and phantom reservations) for browsing that may never
 * convert. Stock is only reserved when the order is placed.
 */
export function useBasket() {
  const [items, setItems] = useState<BasketItem[]>([]);

  useEffect(() => {
    setItems(read());
    const sync = () => setItems(read());
    window.addEventListener(CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const add = useCallback((item: BasketItem) => {
    const current = read();
    const existing = current.find((entry) => entry.medicine === item.medicine);
    const next = existing
      ? current.map((entry) => (entry.medicine === item.medicine ? { ...entry, quantity: entry.quantity + item.quantity } : entry))
      : [...current, item];
    write(next);
  }, []);

  const setQuantity = useCallback((medicine: string, quantity: number) => {
    const next = read()
      .map((entry) => (entry.medicine === medicine ? { ...entry, quantity } : entry))
      .filter((entry) => entry.quantity > 0);
    write(next);
  }, []);

  const remove = useCallback((medicine: string) => {
    write(read().filter((entry) => entry.medicine !== medicine));
  }, []);

  const clear = useCallback(() => write([]), []);

  const count = items.reduce((sum, entry) => sum + entry.quantity, 0);
  return { items, add, setQuantity, remove, clear, count };
}
