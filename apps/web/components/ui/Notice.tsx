export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "danger" | "success" }) {
  return <div className={`notice notice-${tone}`}>{children}</div>;
}

