"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "healthconnect_recent_searches";
const LIMIT = 6;

function read(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((entry): entry is string => typeof entry === "string") : [];
  } catch {
    return [];
  }
}

/**
 * Recent searches, kept in localStorage.
 *
 * Search history is a browsing convenience, not account state, and putting it
 * on the server would mean storing a health signal per user for no product
 * benefit. Reads happen after mount so server and client markup agree.
 */
export function useRecentSearches() {
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    setRecent(read());
  }, []);

  const remember = useCallback((term: string) => {
    const trimmed = term.trim();
    if (!trimmed) return;
    const next = [trimmed, ...read().filter((entry) => entry.toLowerCase() !== trimmed.toLowerCase())].slice(0, LIMIT);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setRecent(next);
  }, []);

  const clear = useCallback(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([]));
    setRecent([]);
  }, []);

  return { recent, remember, clear };
}
