import { Icon, type IconName } from "@/components/ui/Icon";

export function StateBlock({
  icon,
  tone = "neutral",
  title,
  body,
  hints,
  children
}: {
  icon: IconName;
  tone?: "neutral" | "alert";
  title: string;
  body?: string;
  hints?: string[];
  children?: React.ReactNode;
}) {
  return (
    <div className="hc-state" role={tone === "alert" ? "alert" : undefined}>
      <span className={`hc-state-icon${tone === "alert" ? " hc-state-icon-alert" : ""}`}>
        <Icon name={icon} size={22} />
      </span>
      <h2 className="hc-h3">{title}</h2>
      {body ? <p className="hc-body">{body}</p> : null}
      {hints?.length ? (
        <ul>
          {hints.map((hint) => (
            <li key={hint}>
              <Icon name="check" size={13} />
              {hint}
            </li>
          ))}
        </ul>
      ) : null}
      {children ? <div className="hc-actions">{children}</div> : null}
    </div>
  );
}

/**
 * Result-shaped skeletons rather than a spinner: the list keeps its geometry,
 * so nothing jumps when the real rows arrive.
 */
export function ResultSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div className="hc-results" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div className="hc-skel-row" key={index}>
          <span className="hc-skel" style={{ width: 44, height: 44, borderRadius: 12 }} />
          <span style={{ display: "grid", gap: 9 }}>
            <span className="hc-skel" style={{ width: `${44 + ((index * 13) % 26)}%`, height: 15 }} />
            <span className="hc-skel" style={{ width: `${32 + ((index * 17) % 22)}%`, height: 12 }} />
            <span className="hc-skel" style={{ width: 168, height: 20, borderRadius: 999 }} />
          </span>
          <span className="hc-skel" style={{ width: 96, height: 34, borderRadius: 999 }} />
        </div>
      ))}
    </div>
  );
}
