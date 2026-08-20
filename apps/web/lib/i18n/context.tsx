"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import en from "./messages/en.json";
import ar from "./messages/ar.json";
import fr from "./messages/fr.json";

export const LOCALES = ["en", "ar", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = { en: "English", ar: "العربية", fr: "Français" };
const RTL_LOCALES: Locale[] = ["ar"];

// Deep string-value dictionaries, one per locale. English is the fallback for any key
// missing from ar/fr, so a partially-translated page still reads correctly rather than
// showing a raw key.
const MESSAGES: Record<Locale, Record<string, unknown>> = { en, ar, fr };
const STORAGE_KEY = "pharmalink_locale";

function lookup(dict: Record<string, unknown>, path: string[]): string | undefined {
  let current: unknown = dict;
  for (const segment of path) {
    if (typeof current !== "object" || current === null) return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return typeof current === "string" ? current : undefined;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in vars ? String(vars[key]) : match));
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  dir: "ltr" | "rtl";
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const stored = typeof window !== "undefined" ? (window.localStorage.getItem(STORAGE_KEY) as Locale | null) : null;
    if (stored && LOCALES.includes(stored)) setLocaleState(stored);
  }, []);

  const dir: "ltr" | "rtl" = RTL_LOCALES.includes(locale) ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
  }, [locale, dir]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const path = key.split(".");
      const value = lookup(MESSAGES[locale], path) ?? lookup(MESSAGES.en, path) ?? key;
      return interpolate(value, vars);
    },
    [locale]
  );

  const value = useMemo(() => ({ locale, setLocale, dir, t }), [locale, setLocale, dir, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useTranslations() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useTranslations must be used within I18nProvider");
  return context.t;
}

export function useLocale() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useLocale must be used within I18nProvider");
  return context;
}
