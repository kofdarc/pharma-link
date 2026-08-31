"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, getToken } from "@/lib/api-client";
import { useTranslations } from "@/lib/i18n/context";
import { useToast } from "@/components/patient/Toast";
import type { NotificationItem } from "@/types/api";

/**
 * Polls the computed notification feed while a tab is open and raises a toast +
 * (with permission) a browser notification for anything it hasn't shown before.
 *
 * There is no server-side "read" state: de-duping is entirely local, keyed on the
 * feed's stable item ids in `localStorage`. The first successful poll for a user is
 * adopted silently, so switching notifications on never replays a backlog.
 */

const POLL_MS = 45_000;
const SEEN_CAP = 200;

const seenKey = (userId: string) => `pharmalink_notif_seen:${userId}`;

function readSeen(userId: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(seenKey(userId));
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function writeSeen(userId: string, ids: Set<string>): void {
  try {
    window.localStorage.setItem(seenKey(userId), JSON.stringify([...ids].slice(-SEEN_CAP)));
  } catch {
    // Private mode or storage disabled: notifications quietly degrade to none.
  }
}

type Permission = NotificationPermission | "unsupported";

export function notificationCountForHref(items: NotificationItem[], href: string): number {
  return items.reduce(
    (count, item) => count + (item.href === href || item.href.startsWith(`${href}/`) ? item.badge_count ?? 1 : 0),
    0
  );
}

export function useNotifications(userId: string | undefined) {
  const t = useTranslations();
  const router = useRouter();
  const { notify } = useToast();
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [permission, setPermission] = useState<Permission>("unsupported");
  const seenRef = useRef<Set<string> | null>(null);
  const primedRef = useRef(false);

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setPermission(Notification.permission);
    }
  }, []);

  const fire = useCallback(
    (item: NotificationItem) => {
      const title = t(`notifications.kinds.${item.kind}.title`, item.params);
      const body = t(`notifications.kinds.${item.kind}.body`, item.params);
      notify(title);
      if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
        try {
          const popup = new Notification(title, { body, tag: item.id, icon: "/icons/icon-192.png" });
          popup.onclick = () => {
            window.focus();
            router.push(item.href);
            popup.close();
          };
        } catch {
          // Some embedded/insecure contexts throw on construction; the toast already fired.
        }
      }
    },
    [t, notify, router]
  );

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    seenRef.current = readSeen(userId);
    primedRef.current = false;

    const poll = async () => {
      if (cancelled || !getToken() || document.visibilityState !== "visible") return;
      let items: NotificationItem[];
      try {
        const data = await apiFetch<{ notifications: NotificationItem[] }>("/notifications/");
        items = data.notifications ?? [];
      } catch {
        return; // a failed poll is a non-event - try again next tick
      }
      if (cancelled) return;
      setItems(items);

      const seen = seenRef.current ?? new Set<string>();
      const fresh = items.filter((item) => !seen.has(item.id));
      if (!primedRef.current) {
        primedRef.current = true; // adopt current state silently
      } else if (fresh.length) {
        fresh.forEach(fire);
        setUnreadCount((count) => count + fresh.length);
      }
      items.forEach((item) => seen.add(item.id));
      seenRef.current = seen;
      writeSeen(userId, seen);
    };

    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void poll();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [userId, fire]);

  const requestPermission = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    const result = await Notification.requestPermission();
    setPermission(result);
  }, []);

  const clearUnread = useCallback(() => setUnreadCount(0), []);

  return { items, unreadCount, permission, requestPermission, clearUnread };
}
