export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const normalized = status.toLowerCase();
  if (normalized.includes("available") || normalized.includes("active") || normalized.includes("confirmed") || normalized.includes("completed")) return "success";
  if (normalized.includes("low") || normalized.includes("expiring") || normalized.includes("match")) return "warning";
  if (normalized.includes("expired") || normalized.includes("failed") || normalized.includes("inactive") || normalized.includes("invalid")) return "danger";
  return "neutral";
}

