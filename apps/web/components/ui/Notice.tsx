export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "danger" | "success" | "muted" }) {
  if (tone === "muted") {
    return (
      <p className="notice-muted">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.3" />
          <path d="M8 7.2v4.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <circle cx="8" cy="4.7" r="0.9" fill="currentColor" />
        </svg>
        <span>{children}</span>
      </p>
    );
  }
  return <div className={`notice notice-${tone}`}>{children}</div>;
}

