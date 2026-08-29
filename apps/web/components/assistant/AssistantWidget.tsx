"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { usePathname } from "next/navigation";
import { AUTH_CHANGED_EVENT, apiFetch } from "@/lib/api-client";
import { useShopperLocation } from "@/lib/location";
import { Icon } from "@/components/ui/Icon";
import type { AssistantReply, AssistantSession } from "@/types/api";

/**
 * The assistant, everywhere it belongs and nowhere it doesn't.
 *
 * Mounted once in the root layout rather than per shell, because the same widget serves a
 * signed-out visitor on the search page and a pharmacist on the dashboard - what differs is
 * the persona, and the persona is decided by the API from the auth token, never here. This
 * component does not know or care which role it is talking to; it renders whatever greeting
 * and suggestions the session endpoint hands back.
 */

/** Screens where a floating panel would be in the way or actively unwelcome. */
const HIDDEN_ON = ["/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/activate", "/checkout", "/cart"];

/** Survives client-side navigation without following the person into a new browser session. */
const CONVERSATION_KEY = "pharmalink_assistant_conversation";

/** How many of the persona's suggestion pool are on screen at once, and how often they rotate. */
const CHIP_VISIBLE = 3;
const CHIP_CYCLE_MS = 6000;

type Turn = { role: "user" | "assistant"; body: string };

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

/** A fresh random slice of the pool, up to CHIP_VISIBLE items, in shuffled order. */
function sampleChips(pool: readonly string[]): string[] {
  const copy = [...pool];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, CHIP_VISIBLE);
}

export function AssistantWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<AssistantSession | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visibleChips, setVisibleChips] = useState<string[]>([]);
  const [chipCycle, setChipCycle] = useState(0);
  // What the last reply said it measured from, so "the closest is..." is checkable rather
  // than taken on trust - and so a stale saved address can be spotted and replaced.
  const [locationUsed, setLocationUsed] = useState<string | null>(null);
  const location = useShopperLocation();
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Set while the pointer or keyboard focus is inside the chip strip, so rotation holds and a
  // chip is never pulled out from under a click.
  const chipsPaused = useRef(false);

  const hidden = HIDDEN_ON.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  // Nothing is fetched until someone actually opens the panel. The assistant costs a request
  // when it is used, not on every page view of the whole product.
  useEffect(() => {
    if (!open || session) return;
    let cancelled = false;
    apiFetch<AssistantSession>("/assistant/session/")
      .then((value) => {
        if (cancelled) return;
        setSession(value);
        setTurns((current) => (current.length ? current : [{ role: "assistant", body: value.greeting }]));
      })
      .catch(() => {
        if (!cancelled) setError("The assistant is unavailable right now.");
      });
    return () => {
      cancelled = true;
    };
  }, [open, session]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Signing in or out swaps the persona behind this widget, but the component is mounted once
  // in the root layout and survives that client-side navigation. Without this, a pharmacist's
  // thread and greeting would stay on screen for whoever signs in next on the same tab. Wipe
  // every trace - the visible turns, the cached persona, and the stored conversation id - and
  // let the session endpoint rebuild it for the new caller when the panel is next opened.
  useEffect(() => {
    function onAuthChange() {
      setOpen(false);
      setSession(null);
      setTurns([]);
      setDraft("");
      setError("");
      setBusy(false);
      setVisibleChips([]);
      setLocationUsed(null);
      window.sessionStorage.removeItem(CONVERSATION_KEY);
    }
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChange);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChange);
  }, []);

  // The persona hands back a large pool of openers; only a few fit. Show a random few and
  // rotate them every several seconds while the thread is still empty - re-seeded on open and
  // on "New chat", frozen once the person has said anything or while they're reaching for one.
  useEffect(() => {
    const pool = session?.suggestions ?? [];
    const showing = open && pool.length > 0 && turns.length <= 1 && !busy;
    if (!showing) {
      setVisibleChips([]);
      return;
    }

    setVisibleChips(sampleChips(pool));
    setChipCycle((n) => n + 1);

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion || pool.length <= CHIP_VISIBLE) return;

    const timer = window.setInterval(() => {
      if (chipsPaused.current) return;
      setVisibleChips(sampleChips(pool));
      setChipCycle((n) => n + 1);
    }, CHIP_CYCLE_MS);
    return () => window.clearInterval(timer);
  }, [open, session?.suggestions, turns.length, busy]);

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

  const send = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text || busy) return;

      setDraft("");
      setError("");
      setBusy(true);
      setTurns((current) => [...current, { role: "user", body: text }]);

      const conversationId = window.sessionStorage.getItem(CONVERSATION_KEY);
      try {
        const reply = await apiFetch<AssistantReply>("/assistant/chat/", {
          method: "POST",
          body: JSON.stringify({
            message: text,
            ...(conversationId ? { conversation_id: conversationId } : {}),
            // Sent only when the person has already shared it. Asking for a location because
            // somebody typed a message would be a prompt they did not ask for; the API falls
            // back to whatever the account has on file, or to no ranking by distance at all.
            ...(location.position
              ? { latitude: location.position.latitude, longitude: location.position.longitude }
              : {})
          })
        });
        window.sessionStorage.setItem(CONVERSATION_KEY, reply.conversation_id);
        setSession((current) => (current ? { ...current, suggestions: reply.suggestions } : current));
        setTurns((current) => [...current, { role: "assistant", body: reply.reply }]);
        setLocationUsed(reply.location_used);
      } catch {
        // A stored id can go stale - the account signed out, or the thread belongs to a
        // different persona now. Drop it so the next message starts a fresh thread rather
        // than failing forever against an id this caller can no longer use.
        window.sessionStorage.removeItem(CONVERSATION_KEY);
        setError("I couldn't send that. Try again in a moment.");
      } finally {
        setBusy(false);
      }
    },
    [busy, location.position]
  );

  // Start over without closing the panel or losing the persona: drop the thread id so the
  // next message opens a fresh conversation, and fall back to just the greeting. The chip
  // effect re-seeds off the shortened turn list.
  const startNewChat = useCallback(() => {
    window.sessionStorage.removeItem(CONVERSATION_KEY);
    setError("");
    setDraft("");
    setBusy(false);
    setLocationUsed(null);
    setTurns(session ? [{ role: "assistant", body: session.greeting }] : []);
  }, [session]);

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
                <button type="button" className="assistant-newchat" onClick={startNewChat}>
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
            {error ? <p className="assistant-error">{error}</p> : null}
          </div>

          {visibleChips.length > 0 && turns.length <= 1 ? (
            <div
              className="assistant-chips"
              onMouseEnter={() => {
                chipsPaused.current = true;
              }}
              onMouseLeave={() => {
                chipsPaused.current = false;
              }}
              onFocusCapture={() => {
                chipsPaused.current = true;
              }}
              onBlurCapture={() => {
                chipsPaused.current = false;
              }}
            >
              {visibleChips.map((suggestion, index) => (
                <button
                  key={`${chipCycle}:${suggestion}`}
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
