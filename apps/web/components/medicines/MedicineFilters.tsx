"use client";

import { type ReactNode, useEffect, useId, useRef } from "react";
import { Icon } from "@/components/ui/Icon";
import { countActiveFilters, DEFAULT_FILTERS, type SearchFilters } from "@/lib/catalog/types";

type Group<K extends keyof SearchFilters> = {
  key: K;
  legend: string;
  options: { value: SearchFilters[K]; label: string }[];
};

/**
 * Four axes, deliberately. Patients refine a medicine search by whether they
 * can get it, whether they need a prescription, whether they want the brand,
 * and what form it comes in. Price is a sort, not a filter — a range slider
 * over "from" prices across a pharmacy network promises precision that the
 * sourcing model cannot honour.
 */
const BASE_GROUPS: [Group<"availability">, Group<"prescription">, Group<"productType">] = [
  {
    key: "availability",
    legend: "Availability",
    options: [
      { value: "any", label: "Show everything" },
      { value: "available", label: "Available only" }
    ]
  },
  {
    key: "prescription",
    legend: "Prescription",
    options: [
      { value: "any", label: "Any" },
      { value: "required", label: "Prescription required" },
      { value: "none", label: "Prescription not required" }
    ]
  },
  {
    key: "productType",
    legend: "Product",
    options: [
      { value: "any", label: "Any" },
      { value: "brand", label: "Brand" },
      { value: "generic", label: "Generic" }
    ]
  }
];

function FilterControls({
  filters,
  onChange,
  forms,
  namespace
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
  forms: string[];
  namespace: string;
}) {
  return (
    <>
      {BASE_GROUPS.map((group) => (
        <fieldset className="hc-filter-group" key={group.key}>
          <legend className="hc-card-label">{group.legend}</legend>
          {group.options.map((option) => (
            <label className="hc-radio" key={String(option.value)}>
              <input
                type="radio"
                name={`${namespace}-${group.key}`}
                value={String(option.value)}
                checked={filters[group.key] === option.value}
                onChange={() => onChange({ ...filters, [group.key]: option.value })}
              />
              {option.label}
            </label>
          ))}
        </fieldset>
      ))}

      {forms.length > 1 ? (
        <fieldset className="hc-filter-group">
          <legend className="hc-card-label">Form</legend>
          <label className="hc-radio">
            <input
              type="radio"
              name={`${namespace}-form`}
              checked={filters.form === "any"}
              onChange={() => onChange({ ...filters, form: "any" })}
            />
            Any
          </label>
          {forms.map((form) => (
            <label className="hc-radio" key={form}>
              <input
                type="radio"
                name={`${namespace}-form`}
                checked={filters.form === form}
                onChange={() => onChange({ ...filters, form })}
              />
              {form}
            </label>
          ))}
        </fieldset>
      ) : null}
    </>
  );
}

export function FilterRail({
  filters,
  onChange,
  forms,
  note
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
  forms: string[];
  /** Optional helper text pinned below the controls (e.g. an ordering caveat). */
  note?: ReactNode;
}) {
  const active = countActiveFilters(filters);
  return (
    <aside className="hc-filters" aria-label="Refine results">
      <div className="hc-filter-head">
        <h2 className="hc-h3">Refine</h2>
        {active > 0 ? (
          <button type="button" className="hc-linkbtn" onClick={() => onChange(DEFAULT_FILTERS)}>
            Clear all
          </button>
        ) : null}
      </div>
      <FilterControls filters={filters} onChange={onChange} forms={forms} namespace="rail" />
      {note ? <p className="hc-filter-note">{note}</p> : null}
    </aside>
  );
}

export function FilterSheet({
  filters,
  onChange,
  forms,
  resultCount,
  onClose
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
  forms: string[];
  resultCount: number;
  onClose: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return (
    <>
      <button type="button" className="hc-sheet-backdrop" aria-label="Close filters" onClick={onClose} />
      <div className="hc-sheet" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="hc-sheet-grip" aria-hidden="true" />
        <div className="hc-sheet-head">
          <h2 className="hc-h3" id={titleId}>
            Refine results
          </h2>
          <button type="button" ref={closeRef} className="hc-searchbox-clear" aria-label="Close filters" onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>

        <div style={{ display: "grid", gap: 24 }}>
          <FilterControls filters={filters} onChange={onChange} forms={forms} namespace="sheet" />
        </div>

        <div className="hc-sheet-foot">
          <button type="button" className="hc-btn hc-btn-secondary" onClick={() => onChange(DEFAULT_FILTERS)}>
            Clear all
          </button>
          <button type="button" className="hc-btn hc-btn-primary" onClick={onClose}>
            Show {resultCount} {resultCount === 1 ? "result" : "results"}
          </button>
        </div>
      </div>
    </>
  );
}
