"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
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

type Turn = { role: "user" | "assistant"; body: string };

export function AssistantWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<AssistantSession | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
          body: JSON.stringify({ message: text, ...(conversationId ? { conversation_id: conversationId } : {}) })
        });
        window.sessionStorage.setItem(CONVERSATION_KEY, reply.conversation_id);
        setSession((current) => (current ? { ...current, suggestions: reply.suggestions } : current));
        setTurns((current) => [...current, { role: "assistant", body: reply.reply }]);
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
    [busy]
  );

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
        <Icon name={open ? "close" : "message"} size={20} />
      </button>

      {open ? (
        <section id="assistant-panel" className="assistant-panel" role="dialog" aria-label={session?.label || "Assistant"}>
          <header className="assistant-head">
            <strong>{session?.label || "Assistant"}</strong>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close the assistant">
              <Icon name="close" size={16} />
            </button>
          </header>

          <div className="assistant-log" ref={listRef} aria-live="polite">
            {turns.map((turn, index) => (
              <p key={index} className={`assistant-turn assistant-turn-${turn.role}`}>
                {turn.body}
              </p>
            ))}
            {busy ? (
              <p className="assistant-turn assistant-turn-assistant assistant-typing" aria-label="Thinking">
                <span />
                <span />
                <span />
              </p>
            ) : null}
            {error ? <p className="assistant-error">{error}</p> : null}
          </div>

          {session?.suggestions?.length && turns.length <= 1 ? (
            <div className="assistant-chips">
              {session.suggestions.map((suggestion) => (
                <button key={suggestion} type="button" onClick={() => send(suggestion)} disabled={busy}>
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}

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
