"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";

/**
 * Transient confirmation for actions that leave no trace on screen.
 *
 * Deliberately narrow. A toast is for "the thing you did happened and you
 * cannot see it from here" (a refill paused on a card that then re-renders
 * identically, a payment method removed). Anything the page already shows the
 * result of does not get one, and errors that need a decision stay inline where
 * the decision is.
 */

interface Toast {
  id: number;
  message: string;
  tone: "ok" | "alert";
}

interface ToastApi {
  notify: (message: string, tone?: Toast["tone"]) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const DURATION = 3600;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const notify = useCallback((message: string, tone: Toast["tone"] = "ok") => {
    const id = (nextId.current += 1);
    setToasts((current) => [...current.slice(-2), { id, message, tone }]);
    timers.current.push(setTimeout(() => setToasts((current) => current.filter((entry) => entry.id !== id)), DURATION));
  }, []);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const api = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Polite: a confirmation should not interrupt whatever is being read. */}
      <div className="hc-toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div className={`hc-toast${toast.tone === "alert" ? " hc-toast-alert" : ""}`} key={toast.id}>
            <Icon name={toast.tone === "alert" ? "alert" : "check"} size={16} strokeWidth={2.2} />
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Falls back to a no-op outside the patient shell, so a shared component can
 * confirm an action without knowing which chrome it was mounted inside.
 */
export function useToast(): ToastApi {
  return useContext(ToastContext) ?? { notify: () => undefined };
}
