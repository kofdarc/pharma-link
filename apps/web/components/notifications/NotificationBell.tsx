"use client";

import { Icon } from "@/components/ui/Icon";
import { useTranslations } from "@/lib/i18n/context";
import { useNotifications } from "@/lib/notifications/useNotifications";

/**
 * The one notification control, shown in both the workspace topbar and the patient
 * header. It is deliberately quiet: an icon, an unread dot, and a click that either
 * asks for browser-notification permission (first time) or just clears the dot.
 * There is no dropdown - live items surface as toasts, not a list to manage.
 */
export function NotificationBell({ userId }: { userId?: string }) {
  const t = useTranslations();
  const { unreadCount, permission, requestPermission, clearUnread } = useNotifications(userId);

  const label =
    permission === "default"
      ? t("notifications.enablePrompt")
      : unreadCount > 0
        ? t("notifications.unreadLabel", { count: unreadCount })
        : t("notifications.bellLabel");

  return (
    <button
      type="button"
      className="notif-bell"
      aria-label={label}
      title={label}
      data-unread={unreadCount > 0 ? "true" : undefined}
      onClick={() => {
        if (permission === "default") void requestPermission();
        clearUnread();
      }}
    >
      <Icon name="bell" size={18} />
      {unreadCount > 0 ? <span className="notif-bell-dot" aria-hidden="true" /> : null}
    </button>
  );
}
