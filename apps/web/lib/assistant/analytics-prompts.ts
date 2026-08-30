/**
 * The suggestion pool for the analytics "Ask" panel.
 *
 * Kept separate from the persona's own `suggestions` (which are general pharmacy openers -
 * stock counts, order status, "is X over the counter") because on the analytics page the
 * person is interrogating their numbers, not asking for support. Every line here maps onto
 * one of the pharmacy assistant's analytics-facing intents: sales_summary, business_insights,
 * stock_alerts, stock_lookup. English only, like the persona suggestions themselves - the
 * assistant answers in English regardless of the UI locale.
 *
 * Module-level constant so `useRotatingChips` gets a stable reference and does not reshuffle
 * on every render.
 */
export const ANALYTICS_PROMPTS: readonly string[] = [
  "How did we trade over the last 30 days?",
  "What is my revenue this month?",
  "Where is my revenue coming from?",
  "What is my gross margin this month?",
  "How is my inventory turnover looking?",
  "Why is my stock turnover low?",
  "What should I reorder first?",
  "Which products are about to run out?",
  "How many days of cover do I have on my fast movers?",
  "What is expiring in the next 30 days?",
  "Which SKUs are tying up the most cash?",
  "Which products have not sold in 60 days?",
  "What are my top movers this month?",
  "Which slow movers should I discount?",
  "Is my stock value going up or down?",
  "How is my online acceptance rate trending?",
  "Any analytics findings worth acting on?",
  "What unmet demand is there in my area?"
];
