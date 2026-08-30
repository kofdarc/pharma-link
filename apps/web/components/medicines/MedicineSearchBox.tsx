"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { PackThumb } from "@/components/medicines/PackThumb";
import { Icon } from "@/components/ui/Icon";
import { suggestMedicines, type MedicineSuggestion } from "@/lib/catalog/service";

const DEBOUNCE_MS = 180;

/** Wraps the part of `text` matching `query` so the match reads as the reason the row is here. */
function highlight(text: string, query: string) {
  const index = text.toLowerCase().indexOf(query.trim().toLowerCase());
  if (!query.trim() || index < 0) return text;
  const end = index + query.trim().length;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, end)}</mark>
      {text.slice(end)}
    </>
  );
}

/**
 * The search entry point, used on the landing hero, patient home and the search
 * page itself.
 *
 * Suggestions come from the catalogue, not from pharmacies: patients pick a
 * medicine and HealthConnect works out where it can be sourced.
 */
export function MedicineSearchBox({
  value,
  onValueChange,
  onSubmit,
  onSelectSuggestion,
  size = "md",
  autoFocus = false,
  label = "Search medicines",
  placeholder = "Search medicine, brand, or generic name"
}: {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: (query: string) => void;
  onSelectSuggestion?: (suggestion: MedicineSuggestion) => void;
  size?: "md" | "lg";
  autoFocus?: boolean;
  label?: string;
  placeholder?: string;
}) {
  const listId = useId();
  const optionId = (index: number) => `${listId}-option-${index}`;

  const rootRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [suggestions, setSuggestions] = useState<MedicineSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  // Set while a suggestion is being committed, so the request that is already
  // in flight cannot re-open the panel over the top of the navigation.
  const committing = useRef(false);

  useEffect(() => {
    if (committing.current) {
      committing.current = false;
      return;
    }
    if (value.trim().length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      suggestMedicines(value, controller.signal)
        .then((next) => {
          setSuggestions(next);
          setActiveIndex(-1);
          // A request can finish after the user submits or chooses a search
          // chip. Only reopen the panel when they are still interacting with
          // the input; otherwise suggestions would cover the search results.
          setOpen(next.length > 0 && document.activeElement === inputRef.current);
        })
        .catch(() => undefined);
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [value]);

  function close() {
    setOpen(false);
    setActiveIndex(-1);
  }

  useEffect(() => {
    if (!open) return;

    function dismissOnOutsidePointer(event: PointerEvent) {
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
      setActiveIndex(-1);
    }

    document.addEventListener("pointerdown", dismissOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", dismissOnOutsidePointer);
  }, [open]);

  function commit(suggestion: MedicineSuggestion) {
    committing.current = true;
    close();
    onValueChange([suggestion.brand, suggestion.strength].filter(Boolean).join(" "));
    if (onSelectSuggestion) onSelectSuggestion(suggestion);
    else onSubmit([suggestion.brand, suggestion.strength].filter(Boolean).join(" "));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (open && activeIndex >= 0 && suggestions[activeIndex]) {
      commit(suggestions[activeIndex]);
      return;
    }
    close();
    inputRef.current?.blur();
    onSubmit(value);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      close();
      return;
    }
    if (!open || suggestions.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1));
    } else if (event.key === "Tab") {
      close();
    }
  }

  return (
    <form
      ref={rootRef}
      className={`hc-searchbox${size === "lg" ? " hc-searchbox-lg" : ""}`}
      onSubmit={submit}
      role="search"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) close();
      }}
    >
      <label className="hc-sr" htmlFor={`${listId}-input`}>
        {label}
      </label>
      <div className="hc-searchbox-field">
        <Icon name="search" size={19} />
        <input
          id={`${listId}-input`}
          ref={inputRef}
          type="search"
          role="combobox"
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
          placeholder={placeholder}
          value={value}
          autoFocus={autoFocus}
          onChange={(event) => onValueChange(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
        />
        <div className="hc-searchbox-end">
          {value ? (
            <button
              type="button"
              className="hc-searchbox-clear"
              aria-label="Clear search"
              onClick={() => {
                onValueChange("");
                close();
                inputRef.current?.focus();
              }}
            >
              <Icon name="close" size={15} />
            </button>
          ) : null}
          <button type="submit" className="hc-btn hc-btn-primary hc-btn-sm">
            Search
          </button>
        </div>
      </div>

      {open ? (
        <div className="hc-ac">
          <div className="hc-ac-head">
            <span>Medicines</span>
            <button type="button" className="hc-ac-dismiss" aria-label="Close suggestions" onClick={close}>
              <span>Close</span>
              <Icon name="close" size={13} />
            </button>
          </div>
          <ul className="hc-ac-list" id={listId} role="listbox" aria-label="Medicine suggestions">
            {suggestions.map((suggestion, index) => (
              <li
                key={suggestion.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === activeIndex}
                data-active={index === activeIndex}
                className="hc-ac-item"
                onMouseEnter={() => setActiveIndex(index)}
                // mousedown, not click: the input's blur would otherwise close the
                // panel before the click ever lands.
                onMouseDown={(event) => {
                  event.preventDefault();
                  commit(suggestion);
                }}
              >
                <PackThumb brand={suggestion.brand} image={suggestion.image} />
                <span className="hc-ac-main">
                  <strong>{highlight([suggestion.brand, suggestion.strength].filter(Boolean).join(" "), value)}</strong>
                  <span>{suggestion.generic || suggestion.form}</span>
                </span>
                <span
                  className={`hc-prescription-status hc-prescription-status-compact ${
                    suggestion.requiresPrescription ? "is-required" : "is-not-required"
                  }`}
                >
                  <Icon name={suggestion.requiresPrescription ? "rx" : "check"} size={12} />
                  {suggestion.requiresPrescription ? "Prescription required" : "Prescription not required"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </form>
  );
}
