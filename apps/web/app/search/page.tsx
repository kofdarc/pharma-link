"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { PatientShell } from "@/components/site/PatientShell";
import { MedicineSearchBox } from "@/components/medicines/MedicineSearchBox";
import { MedicineResult } from "@/components/medicines/MedicineResult";
import { FilterRail, FilterSheet } from "@/components/medicines/MedicineFilters";
import { ResultSkeletons, StateBlock } from "@/components/medicines/SearchStates";
import { Icon } from "@/components/ui/Icon";
import { useOptionalUser } from "@/lib/auth";
import { useRecentSearches } from "@/lib/recent-searches";
import { COMMON_SEARCH_TERMS } from "@/lib/catalog/prompts";
import { applyFilters, applySort, availableForms, searchMedicines } from "@/lib/catalog/service";
import { countActiveFilters, DEFAULT_FILTERS, type MedicineSummary, type SearchFilters, type SortMode } from "@/lib/catalog/types";
import type { User } from "@/types/api";

/**
 * Search is the one screen that belongs to both sites.
 *
 * It is a public page, and it is also a tab in the patient app. Rendering the
 * marketing header for a signed-in patient dropped them out of the app shell
 * mid-flow - no tab bar, no basket, and a "Sign in" button while they were
 * already signed in. So the chrome follows the visitor rather than the route.
 */
function SearchChrome({ user, children }: { user: User | null; children: React.ReactNode }) {
  if (user) return <PatientShell user={user}>{children}</PatientShell>;

  return (
    <div className="hc">
      <SiteHeader />
      <main className="hc-main">{children}</main>
      <SiteFooter />
    </div>
  );
}

function SearchScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const query = params.get("q") ?? "";
  const { recent, remember, clear } = useRecentSearches();
  const user = useOptionalUser();

  const [input, setInput] = useState(query);
  const [results, setResults] = useState<MedicineSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortMode>("recommended");
  const [sheetOpen, setSheetOpen] = useState(false);

  // The URL is the source of truth for the query, so back/forward and shared
  // links behave, and the input follows it.
  useEffect(() => setInput(query), [query]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setError(false);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(false);
    remember(query);

    searchMedicines(query, controller.signal)
      .then((found) => {
        setResults(found);
        setFilters(DEFAULT_FILTERS);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setResults([]);
        setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
    // `remember` is stable; re-running on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const forms = useMemo(() => availableForms(results), [results]);
  const visible = useMemo(() => applySort(applyFilters(results, filters), sort), [results, filters, sort]);
  const activeFilters = countActiveFilters(filters);

  function runSearch(next: string) {
    const trimmed = next.trim();
    router.push(trimmed ? `/search?q=${encodeURIComponent(trimmed)}` : "/search");
  }

  return (
    <SearchChrome user={user}>
      <div className="hc-searchtop">
        <div className="hc-wrap">
          <MedicineSearchBox
            value={input}
            onValueChange={setInput}
            onSubmit={runSearch}
            onSelectSuggestion={(suggestion) => router.push(`/medications/${encodeURIComponent(suggestion.id)}`)}
            size="lg"
            autoFocus={!query}
          />
        </div>
      </div>

      {!query.trim() ? (
        <div className="hc-wrap" style={{ paddingBlock: "clamp(28px, 5vw, 56px) 64px" }}>
          <div style={{ maxWidth: "42rem" }}>
            <h1 className="hc-h2">What medication are you looking for?</h1>
            <p className="hc-lead" style={{ marginTop: 14 }}>
              Search by brand name, generic name, or whatever is printed on the box. HealthConnect works out which connected
              pharmacies can supply it.
            </p>
          </div>

          {recent.length > 0 ? (
            <section style={{ marginTop: 40 }}>
              <div className="hc-filter-head">
                <p className="hc-card-label">Recent searches</p>
                <button type="button" className="hc-linkbtn" onClick={clear}>
                  Clear
                </button>
              </div>
              <div className="hc-chiplist">
                {recent.map((term) => (
                  <button type="button" className="hc-chip-btn" key={term} onClick={() => runSearch(term)}>
                    <Icon name="search" size={14} />
                    {term}
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {/* Search terms, not results: nothing has been asked of any
              pharmacy yet, so nothing here may imply availability. */}
          <section style={{ marginTop: 40 }}>
            <p className="hc-card-label" style={{ marginBottom: 14 }}>
              People often search for
            </p>
            <div className="hc-chiplist">
              {COMMON_SEARCH_TERMS.map((term) => (
                <button type="button" className="hc-chip-btn" key={term} onClick={() => runSearch(term)}>
                  <Icon name="pill" size={14} />
                  {term}
                </button>
              ))}
            </div>
          </section>

          <div className="hc-card hc-card-quiet" style={{ marginTop: 40, maxWidth: "42rem" }}>
            <h2 className="hc-h3">Searching by generic name works too</h2>
            <p className="hc-body" style={{ marginTop: 8 }}>
              If you only know the active ingredient — paracetamol, atorvastatin, salbutamol — search that. HealthConnect will
              show the products listed under it.
            </p>
          </div>
        </div>
      ) : (
        <div className="hc-wrap hc-search-layout">
          <FilterRail filters={filters} onChange={setFilters} forms={forms} />

          <div>
            <div className="hc-results-bar">
              <div>
                <h1 className="hc-h3" aria-live="polite">
                  {loading ? "Searching…" : `${visible.length} ${visible.length === 1 ? "result" : "results"} for “${query}”`}
                </h1>
                {!loading && results.length > 0 ? (
                  <p className="hc-small" style={{ marginTop: 4 }}>
                    Availability is confirmed when you continue with your order.
                  </p>
                ) : null}
              </div>

              <div className="hc-actions">
                <button
                  type="button"
                  className="hc-btn hc-btn-secondary hc-btn-sm hc-mobile-filter-btn"
                  onClick={() => setSheetOpen(true)}
                >
                  <Icon name="filters" size={16} />
                  Filters{activeFilters > 0 ? ` (${activeFilters})` : ""}
                </button>
                <label className="hc-sort">
                  <span>Sort</span>
                  <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)}>
                    <option value="recommended">Recommended</option>
                    <option value="price">Price</option>
                    <option value="availability">Availability</option>
                  </select>
                </label>
              </div>
            </div>

            {loading ? <ResultSkeletons /> : null}

            {!loading && error ? (
              <StateBlock
                icon="alert"
                tone="alert"
                title="We couldn't run that search"
                body="Something went wrong on our side. Your search wasn't saved, so nothing is lost."
              >
                <button type="button" className="hc-btn hc-btn-primary" onClick={() => runSearch(query)}>
                  Try again
                </button>
                <Link href="/search" className="hc-btn hc-btn-secondary">
                  Start over
                </Link>
              </StateBlock>
            ) : null}

            {!loading && !error && results.length === 0 ? (
              <StateBlock
                icon="search"
                title={`We couldn't find “${query}”`}
                body="It might be listed under a different name, or it may not be in the catalogue yet."
                hints={[
                  "Check the spelling on the box",
                  "Try the generic name — for example, paracetamol instead of Panadol",
                  "Try the brand without the strength"
                ]}
              >
                <Link href="/search" className="hc-btn hc-btn-secondary">
                  Clear search
                </Link>
              </StateBlock>
            ) : null}

            {!loading && !error && results.length > 0 && visible.length === 0 ? (
              <StateBlock
                icon="filters"
                title="No results match these filters"
                body={`${results.length} ${results.length === 1 ? "medicine matches" : "medicines match"} “${query}”, but none fit the filters you've applied.`}
              >
                <button type="button" className="hc-btn hc-btn-primary" onClick={() => setFilters(DEFAULT_FILTERS)}>
                  Clear filters
                </button>
              </StateBlock>
            ) : null}

            {!loading && visible.length > 0 ? (
              <div className="hc-results">
                {visible.map((medicine) => (
                  <MedicineResult medicine={medicine} key={medicine.id} />
                ))}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {sheetOpen ? (
        <FilterSheet
          filters={filters}
          onChange={setFilters}
          forms={forms}
          resultCount={visible.length}
          onClose={() => setSheetOpen(false)}
        />
      ) : null}
    </SearchChrome>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="hc">
          <div className="hc-wrap" style={{ paddingBlock: 80 }}>
            <ResultSkeletons count={3} />
          </div>
        </div>
      }
    >
      <SearchScreen />
    </Suspense>
  );
}
