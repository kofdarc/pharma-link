"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import type { ChatMessage } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

export function ChatPanel({ basePath, orderFulfillmentId }: { basePath: string; orderFulfillmentId: string }) {
  const t = useTranslations();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const endpoint = `${basePath}/${orderFulfillmentId}/messages/`;

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError("");
    apiFetch<ChatMessage[]>(endpoint)
      .then(setMessages)
      .catch(() => setError(t("chat.loadError")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    setSending(true);
    setError("");
    try {
      const message = await apiFetch<ChatMessage>(endpoint, { method: "POST", body: JSON.stringify({ body: draft }) });
      setMessages((current) => [...current, message]);
      setDraft("");
    } catch (exception) {
      setError((exception as ApiError).message || t("chat.sendFailed"));
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
        {t("chat.open")}
      </Button>
    );
  }

  return (
    <div className="chat-panel">
      <div className="section-header">
        <strong>{t("chat.title")}</strong>
        <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
          {t("chat.close")}
        </Button>
      </div>
      {loading ? <div className="skeleton-card" /> : null}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {!loading && messages.length === 0 ? <p className="muted small">{t("chat.empty")}</p> : null}
      <ul className="clean-list chat-messages">
        {messages.map((message) => (
          <li key={message.id} className={`chat-message chat-message-${message.direction.toLowerCase()}`}>
            <p>{message.body}</p>
            <small className="muted">{new Date(message.created_at).toLocaleString()}</small>
          </li>
        ))}
      </ul>
      <form className="chat-composer" onSubmit={submit}>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={t("chat.placeholder")} disabled={sending} />
        <Button type="submit" disabled={sending || !draft.trim()}>
          {t("chat.send")}
        </Button>
      </form>
    </div>
  );
}
