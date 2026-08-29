"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, AUTH_CHANGED_EVENT, getToken } from "./api-client";
import type { ShopperLocation } from "@/types/api";

/**
 * Where the shopper is, for every screen that says "near me".
 *
 * One hook rather than a `navigator.geolocation` call per page, because the browser
 * permission prompt is a scarce resource: ask on the search page and again in the assistant
 * and again at checkout, and the third prompt gets denied out of irritation. The position is
 * fetched once, cached, and shared.
 *
 * Three layers, deliberately:
 *   - `localStorage` so a returning visitor keeps their position without a second prompt,
 *     and so a signed-out visitor gets "near me" at all;
 *   - the API (`/shop/location/`) for signed-in shoppers, so the same position is there on
 *     their phone and is available to the assistant server-side;
 *   - `navigator.geolocation`, only ever on an explicit user action.
 *
 * Nothing here asks for the position on page load. `request()` is called from a button the
 * person pressed, which is the only honest way to ask for someone's location: a prompt that
 * appears unbidden reads as the site taking something rather than offering something.
 */

const STORAGE_KEY = "pharmalink_shopper_location";
/** After this, a cached fix is stale enough to be worth refreshing on the next explicit ask. */
const FRESH_FOR_MS = 12 * 60 * 60 * 1000;

export type Position = {
  latitude: number;
  longitude: number;
  accuracy_metres?: number | null;
  /** Area name resolved by the API, shown so the person can see what "near me" means. */
  label?: string;
  capturedAt: number;
};

export type LocationState = {
  position: Position | null;
  /** True while the browser prompt is open or the fix is being taken. */
  pending: boolean;
  /** Set when the person refused, the device has no fix, or it timed out. */
  error: string;
  /** Whether this browser can offer a position at all. */
  supported: boolean;
  request: () => void;
  clear: () => void;
};

function read(): Position | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Position;
    if (typeof parsed?.latitude !== "number" || typeof parsed?.longitude !== "number") return null;
    return parsed;
  } catch {
    // A corrupted or unreadable entry is the same as never having one. Never throw from a
    // read of a cache: the whole point of this value is that the page works without it.
    return null;
  }
}

function write(position: Position | null) {
  try {
    if (position) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(position));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Private mode, or storage full. The in-memory value still works for this visit.
  }
}

/**
 * The current position without asking for one, for callers that only want to attach it to a
 * request if it happens to exist (the assistant, the search page). Never prompts.
 */
export function currentPosition(): Position | null {
  const cached = read();
  if (!cached) return null;
  return cached;
}

export function isStale(position: Position | null): boolean {
  return !position || Date.now() - position.capturedAt > FRESH_FOR_MS;
}

export function useShopperLocation(): LocationState {
  const [position, setPosition] = useState<Position | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const supported = typeof window !== "undefined" && "geolocation" in navigator;

  // Read the cache after mount rather than in the initial state, so the server-rendered and
  // first client render agree. A hydration mismatch here would flash the wrong affordance.
  useEffect(() => setPosition(read()), []);

  // A position saved on another device belongs to the account, so pull it once on sign-in.
  // It only ever fills a gap: a fresher fix taken on this device is not overwritten.
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    apiFetch<ShopperLocation | undefined>("/shop/location/")
      .then((saved) => {
        if (cancelled || !saved) return;
        setPosition((current) => {
          if (current) return current;
          return {
            latitude: Number(saved.latitude),
            longitude: Number(saved.longitude),
            label: saved.label,
            capturedAt: Date.parse(saved.updated_at) || Date.now()
          };
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Signing out must not leave the previous person's position in the next person's browser.
  useEffect(() => {
    function onAuthChange() {
      if (!getToken()) {
        write(null);
        setPosition(null);
      }
    }
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChange);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChange);
  }, []);

  const request = useCallback(() => {
    if (!supported) {
      setError("This browser can't share a location.");
      return;
    }
    setPending(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      (fix) => {
        const next: Position = {
          latitude: Number(fix.coords.latitude.toFixed(6)),
          longitude: Number(fix.coords.longitude.toFixed(6)),
          accuracy_metres: fix.coords.accuracy ? Math.round(fix.coords.accuracy) : null,
          capturedAt: Date.now()
        };
        setPosition(next);
        write(next);
        setPending(false);

        // Persisted for signed-in shoppers only, and best-effort: the position already works
        // for this browser whether or not the account keeps a copy.
        if (getToken()) {
          apiFetch<ShopperLocation>("/shop/location/", {
            method: "PUT",
            body: JSON.stringify({
              latitude: next.latitude.toFixed(6),
              longitude: next.longitude.toFixed(6),
              accuracy_metres: next.accuracy_metres,
              source: "DEVICE"
            })
          })
            .then((saved) => {
              const labelled = { ...next, label: saved.label };
              setPosition(labelled);
              write(labelled);
            })
            .catch(() => undefined);
        }
      },
      (failure) => {
        setPending(false);
        setError(
          failure.code === failure.PERMISSION_DENIED
            ? "Location is off for this site. You can still search by area."
            : "Couldn't get your location. You can still search by area."
        );
      },
      // A rough fix is plenty: this ranks pharmacies kilometres apart, and asking for high
      // accuracy costs seconds and battery to buy precision nothing here uses.
      { enableHighAccuracy: false, timeout: 10000, maximumAge: FRESH_FOR_MS }
    );
  }, [supported]);

  const clear = useCallback(() => {
    write(null);
    setPosition(null);
    setError("");
    if (getToken()) apiFetch("/shop/location/", { method: "DELETE" }).catch(() => undefined);
  }, []);

  return { position, pending, error, supported, request, clear };
}
