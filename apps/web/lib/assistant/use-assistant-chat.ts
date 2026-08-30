"use client";

import { useCallback, useEffect, useState } from "react";
import { AUTH_CHANGED_EVENT, apiFetch } from "@/lib/api-client";
import type { AssistantReply, AssistantSession } from "@/types/api";

/**
 * The conversation half of the in-app assistant, with no opinion about where it is drawn.
 *
 * The floating `AssistantWidget` and the analytics "Ask" panel are the same conversation -
 * same `/assistant/session/` persona, same `/assistant/chat/` endpoint, same stored thread
 * id - rendered in two places. Everything that is genuinely shared (fetching the session,
 * appending turns, POSTing a message, wiping the thread when the persona changes under a
 * sign-in/out) lives here; each surface keeps only its own chrome and open/close state.
 */

export type AssistantTurn = { role: "user" | "assistant"; body: string };

/** Survives client-side navigation without following the person into a new browser session. */
const CONVERSATION_KEY = "pharmalink_assistant_conversation";

type Coordinates = { latitude: number; longitude: number };

type Options = {
  /**
   * Nothing is fetched until this is true. The widget passes `open` so the assistant costs
   * a request when it is used, not on every page view; an always-visible embedded panel
   * passes `true` once it is on screen.
   */
  enabled: boolean;
  /**
   * Attached to each message when present, for "nearest to me" answers. Pass the shared
   * `useShopperLocation().position` from the calling component - this hook deliberately does
   * not call that hook itself, because it holds local state and a second copy here would
   * diverge from the one driving the location buttons.
   */
  position?: Coordinates | null;
  unavailableMessage?: string;
  sendErrorMessage?: string;
};

export function useAssistantChat({
  enabled,
  position = null,
  unavailableMessage = "The assistant is unavailable right now.",
  sendErrorMessage = "I couldn't send that. Try again in a moment."
}: Options) {
  const [session, setSession] = useState<AssistantSession | null>(null);
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // What the last reply said it measured from, so "the closest is..." is checkable rather
  // than taken on trust - and so a stale saved address can be spotted and replaced.
  const [locationUsed, setLocationUsed] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || session) return;
    let cancelled = false;
    apiFetch<AssistantSession>("/assistant/session/")
      .then((value) => {
        if (cancelled) return;
        setSession(value);
        setTurns((current) => (current.length ? current : [{ role: "assistant", body: value.greeting }]));
      })
      .catch(() => {
        if (!cancelled) setError(unavailableMessage);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, session, unavailableMessage]);

  // Signing in or out swaps the persona behind the assistant. Wipe every trace - the visible
  // turns, the cached persona, and the stored thread id - and let the session endpoint
  // rebuild it for the new caller. Surfaces that own open/close state reset that themselves.
  const reset = useCallback(() => {
    setSession(null);
    setTurns([]);
    setError("");
    setBusy(false);
    setLocationUsed(null);
    window.sessionStorage.removeItem(CONVERSATION_KEY);
  }, []);

  useEffect(() => {
    window.addEventListener(AUTH_CHANGED_EVENT, reset);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, reset);
  }, [reset]);

  const send = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text || busy) return;

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
            // Sent only when the person has already shared it. The API falls back to whatever
            // the account has on file, or to no ranking by distance at all.
            ...(position ? { latitude: position.latitude, longitude: position.longitude } : {})
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
        setError(sendErrorMessage);
      } finally {
        setBusy(false);
      }
    },
    [busy, position, sendErrorMessage]
  );

  // Start over without losing the persona: drop the thread id so the next message opens a
  // fresh conversation, and fall back to just the greeting.
  const startNewChat = useCallback(() => {
    window.sessionStorage.removeItem(CONVERSATION_KEY);
    setError("");
    setBusy(false);
    setLocationUsed(null);
    setTurns(session ? [{ role: "assistant", body: session.greeting }] : []);
  }, [session]);

  return { session, turns, busy, error, locationUsed, send, startNewChat, reset };
}
