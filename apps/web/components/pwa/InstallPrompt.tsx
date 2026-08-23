"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "@/lib/i18n/context";

const DISMISS_KEY = "pharmalink:installPromptDismissedAt";
const DISMISS_COOLDOWN_MS = 14 * 24 * 60 * 60 * 1000;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function recentlyDismissed(): boolean {
  const dismissedAt = Number(window.localStorage.getItem(DISMISS_KEY) ?? 0);
  return Date.now() - dismissedAt < DISMISS_COOLDOWN_MS;
}

export function InstallPrompt() {
  const t = useTranslations();
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (isStandalone() || recentlyDismissed()) return;

    function onBeforeInstallPrompt(event: Event) {
      event.preventDefault();
      setDeferredPrompt(event as BeforeInstallPromptEvent);
    }

    function onAppInstalled() {
      setDeferredPrompt(null);
    }

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  if (!deferredPrompt) return null;

  function dismiss() {
    window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setDeferredPrompt(null);
  }

  async function install() {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    setDeferredPrompt(null);
  }

  return (
    <div className="install-prompt" role="dialog" aria-live="polite">
      <div>
        <strong>{t("installPrompt.title")}</strong>
        <span>{t("installPrompt.body")}</span>
      </div>
      <div className="install-prompt-actions">
        <button type="button" className="button button-secondary" onClick={dismiss}>
          {t("installPrompt.dismiss")}
        </button>
        <button type="button" className="button button-primary" onClick={install}>
          {t("installPrompt.install")}
        </button>
      </div>
    </div>
  );
}
