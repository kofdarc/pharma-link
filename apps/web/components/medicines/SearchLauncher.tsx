"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { MedicineSearchBox } from "./MedicineSearchBox";
import { useRecentSearches } from "@/lib/recent-searches";

/**
 * A search box that goes somewhere: submitting runs a search, picking a
 * suggestion opens that medicine directly. Used on the patient home; the search
 * page drives `MedicineSearchBox` itself because it owns the query in the URL.
 */
export function SearchLauncher({
  size = "lg",
  autoFocus = false,
  placeholder
}: {
  size?: "md" | "lg";
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const router = useRouter();
  const { remember } = useRecentSearches();
  const [value, setValue] = useState("");

  return (
    <MedicineSearchBox
      value={value}
      onValueChange={setValue}
      size={size}
      autoFocus={autoFocus}
      placeholder={placeholder}
      onSubmit={(query) => {
        const trimmed = query.trim();
        if (!trimmed) return;
        remember(trimmed);
        router.push(`/search?q=${encodeURIComponent(trimmed)}`);
      }}
      onSelectSuggestion={(suggestion) => {
        remember([suggestion.brand, suggestion.strength].filter(Boolean).join(" "));
        router.push(`/medications/${encodeURIComponent(suggestion.id)}`);
      }}
    />
  );
}
