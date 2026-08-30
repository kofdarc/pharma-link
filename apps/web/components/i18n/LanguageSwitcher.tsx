"use client";

import { LOCALES, LOCALE_LABELS, useLocale } from "@/lib/i18n/context";

export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale } = useLocale();

  return (
    <select
      className={`language-switcher ${className}`.trim()}
      value={locale}
      onChange={(event) => setLocale(event.target.value as (typeof LOCALES)[number])}
      aria-label="Language"
    >
      {LOCALES.map((entry) => (
        <option key={entry} value={entry}>
          {LOCALE_LABELS[entry]}
        </option>
      ))}
    </select>
  );
}
