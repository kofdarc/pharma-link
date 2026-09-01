"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AUTH_CHANGED_EVENT } from "@/lib/api-client";
import { useShopperLocation } from "@/lib/location";
import { useAssistantChat } from "@/lib/assistant/use-assistant-chat";
import { ANALYTICS_PROMPTS } from "@/lib/assistant/analytics-prompts";
import { useRotatingChips } from "@/lib/assistant/use-rotating-chips";
import { useBasket } from "@/lib/basket";
import { Icon } from "@/components/ui/Icon";
import type { AssistantAction } from "@/types/api";

/**
 * The assistant, everywhere it belongs and nowhere it doesn't.
 *
 * Mounted once in the root layout rather than per shell, because the same widget serves a
 * signed-out visitor on the search page and a pharmacist on the dashboard - what differs is
 * the persona, and the persona is decided by the API from the auth token, never here. This
 * component does not know or care which role it is talking to; it renders whatever greeting
 * and suggestions the session endpoint hands back.
 *
 * The conversation itself lives in `useAssistantChat`; this file is the floating launcher
 * and dialog around it.
 */

/**
 * Screens where a floating panel would be in the way or actively unwelcome.
 */
const HIDDEN_ON = [
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/activate",
  "/checkout",
  "/cart"
];

/** Stable empty reference so `useRotatingChips` doesn't reshuffle while the session loads. */
const EMPTY_POOL: string[] = [];

function AssistantAvatar({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`assistant-avatar${compact ? " assistant-avatar-compact" : ""}`} aria-hidden="true">
      <Image src="/brand/mark-primary.webp" alt="" width={205} height={243} />
      <span className="assistant-avatar-spark">
        <Icon name="spark" size={compact ? 7 : 8} />
      </span>
    </span>
  );
}

export function AssistantWidget() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const location = useShopperLocation();

  // The cart lives in localStorage; the assistant only ever resolves an item and hands it
  // here. A ref so the action handler below can stay stable while `basket` gets a new
  // identity on every render.
  const basket = useBasket();
  const basketRef = useRef(basket);
  basketRef.current = basket;
  // The most recent assistant-driven add, kept so the person can take it straight back out.
  const [lastAdd, setLastAdd] = useState<{ item: AssistantAction["item"]; priorQuantity: number } | null>(null);

  const handleAction = useCallback((action: AssistantAction) => {
    if (action.type !== "add_to_basket") return;
    const b = basketRef.current;
    const priorQuantity = b.items.find((entry) => entry.medicine === action.item.medicine)?.quantity ?? 0;
    b.add({
      medicine: action.item.medicine,
      name: action.item.name,
      quantity: action.item.quantity,
      requires_prescription: action.item.requires_prescription,
      generic: action.item.generic ?? undefined,
      image: action.item.image,
      unit_price: action.item.unit_price
    });
    setLastAdd({ item: action.item, priorQuantity });
  }, []);

  // Nothing is fetched until the panel is opened - the assistant costs a request when it is
  // used, not on every page view of the whole product.
  const { session, turns, busy, error, locationUsed, send, startNewChat } = useAssistantChat({
    enabled: open,
    position: location.position,
    onAction: handleAction
  });

  const undoLastAdd = useCallback(() => {
    setLastAdd((current) => {
      if (!current) return null;
      const b = basketRef.current;
      if (current.priorQuantity > 0) b.setQuantity(current.item.medicine, current.priorQuantity);
      else b.remove(current.item.medicine);
      return null;
    });
  }, []);
  const generalSuggestions = session?.suggestions ?? EMPTY_POOL;
  const onAnalytics = pathname === "/pharmacy/analytics";
  const { chips, cycle, holdHandlers } = useRotatingChips(
    onAnalytics ? ANALYTICS_PROMPTS : generalSuggestions,
    open && turns.length <= 1 && !busy,
    // Analytics is the current context, not the assistant's entire capability. Reserve one
    // of the three rotating chips for the pharmacy persona's broader suggestions.
    onAnalytics ? generalSuggestions : EMPTY_POOL
  );
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const hidden = HIDDEN_ON.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Signing in or out swaps the persona behind this widget. The conversation hook wipes the
  // thread and cached persona itself; here we only drop the panel's own view state so a
  // pharmacist's open panel and half-typed draft don't carry over to whoever signs in next
  // on the same tab.
  useEffect(() => {
    function onAuthChange() {
      setOpen(false);
      setDraft("");
      setLastAdd(null);
    }
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChange);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChange);
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  // Esc closes, matching every other dismissible surface in the app.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (hidden) return null;

  return (
    <>
      <button
        type="button"
        className="assistant-launcher"
        aria-expanded={open}
        aria-controls="assistant-panel"
        aria-label={open ? "Close the assistant" : "Open the assistant"}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <Icon name="close" size={20} /> : <AssistantAvatar />}
      </button>

      {open ? (
        <section id="assistant-panel" className="assistant-panel" role="dialog" aria-label={session?.label || "Assistant"}>
          <header className="assistant-head">
            <div className="assistant-identity">
              <AssistantAvatar compact />
              <strong>{session?.label || "Assistant"}</strong>
            </div>
            <div className="assistant-head-actions">
              {turns.length > 1 ? (
                <button
                  type="button"
                  className="assistant-newchat"
                  onClick={() => {
                    startNewChat();
                    setDraft("");
                    setLastAdd(null);
                  }}
                >
                  New chat
                </button>
              ) : null}
              <button type="button" onClick={() => setOpen(false)} aria-label="Close the assistant">
                <Icon name="close" size={16} />
              </button>
            </div>
          </header>

          <div className="assistant-log" ref={listRef} aria-live="polite">
            {turns.map((turn, index) =>
              turn.role === "assistant" ? (
                <div key={index} className="assistant-reply">
                  <AssistantAvatar compact />
                  <p className="assistant-turn assistant-turn-assistant">{turn.body}</p>
                </div>
              ) : (
                <p key={index} className="assistant-turn assistant-turn-user">
                  {turn.body}
                </p>
              )
            )}
            {busy ? (
              <div className="assistant-reply">
                <AssistantAvatar compact />
                <p className="assistant-turn assistant-turn-assistant assistant-typing" aria-label="Thinking">
                  <span />
                  <span />
                  <span />
                </p>
              </div>
            ) : null}
            {lastAdd && !busy ? (
              <div className="assistant-cart-added">
                <Icon name="check" size={13} />
                <span>Added to your cart.</span>
                <button type="button" onClick={undoLastAdd}>
                  Undo
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setLastAdd(null);
                    setOpen(false);
                    router.push("/cart");
                  }}
                >
                  View cart
                </button>
              </div>
            ) : null}
            {error ? <p className="assistant-error">{error}</p> : null}
          </div>

          {chips.length > 0 && turns.length <= 1 ? (
            <div className="assistant-chips" {...holdHandlers}>
              {chips.map((suggestion, index) => (
                <button
                  key={`${cycle}:${suggestion}`}
                  type="button"
                  className="assistant-chip"
                  style={{ "--chip-index": index } as CSSProperties}
                  onClick={() => send(suggestion)}
                  disabled={busy}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}

          <div className="assistant-location">
            {locationUsed ? (
              <>
                <Icon name="pin" size={12} />
                <span>Ranked from {locationUsed}.</span>
                <button type="button" onClick={location.request} disabled={location.pending}>
                  {location.pending ? "Locating…" : "Use my location"}
                </button>
              </>
            ) : location.position ? (
              <>
                <Icon name="pin" size={12} />
                <span>Using your location{location.position.label ? ` near ${location.position.label}` : ""}.</span>
                <button type="button" onClick={location.clear}>
                  Forget it
                </button>
              </>
            ) : location.supported ? (
              <>
                <Icon name="pin" size={12} />
                <span>{location.error || "Share your location for “nearest to me” answers."}</span>
                <button type="button" onClick={location.request} disabled={location.pending}>
                  {location.pending ? "Locating…" : "Share"}
                </button>
              </>
            ) : null}
          </div>

          <form
            className="assistant-composer"
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
              setDraft("");
            }}
          >
            <input
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask about stock, orders or prescriptions"
              aria-label="Message the assistant"
              maxLength={500}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !draft.trim()} aria-label="Send">
              <Icon name="arrowRight" size={18} />
            </button>
          </form>

          <p className="assistant-foot">
            Not medical advice. For anything about how to take a medicine, ask a pharmacist or your doctor.
          </p>
        </section>
      ) : null}
    </>
  );
}
