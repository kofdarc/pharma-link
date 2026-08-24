/**
 * The one icon system for the patient-facing surface.
 *
 * Inline SVG rather than an icon dependency: the set is small, it inherits
 * `currentColor` and the surrounding font size, and adding a library would be
 * the third styling system in this app. Everything is drawn on a 24x24 grid
 * with a 1.6 stroke so weights match across sizes.
 */

export type IconName =
  | "search"
  | "arrowRight"
  | "arrowLeft"
  | "check"
  | "checkCircle"
  | "close"
  | "phoneOff"
  | "shield"
  | "truck"
  | "pill"
  | "rx"
  | "pin"
  | "clock"
  | "plus"
  | "minus"
  | "chevronDown"
  | "chevronRight"
  | "menu"
  | "eye"
  | "eyeOff"
  | "alert"
  | "info"
  | "network"
  | "people"
  | "stethoscope"
  | "pharmacy"
  | "home"
  | "box"
  | "user"
  | "filters"
  | "refresh"
  | "lock"
  | "spark"
  | "card"
  | "bell"
  | "star"
  | "calendar"
  | "trash"
  | "pencil"
  | "help"
  | "pause"
  | "play"
  | "qr"
  | "receipt";

const PATHS: Record<IconName, React.ReactNode> = {
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.6-3.6" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M4 12h15" />
      <path d="M13 6l6 6-6 6" />
    </>
  ),
  arrowLeft: (
    <>
      <path d="M20 12H5" />
      <path d="M11 6l-6 6 6 6" />
    </>
  ),
  check: <path d="M4.5 12.5l5 5 10-11" />,
  checkCircle: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.4l2.7 2.7L16 9.5" />
    </>
  ),
  close: (
    <>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </>
  ),
  phoneOff: (
    <>
      <path d="M10.7 5.2 12 8.2l-2 1.4a12 12 0 0 0 4.4 4.4l1.4-2 3 1.3a2 2 0 0 1 1.2 2.1l-.3 1.8a1.7 1.7 0 0 1-1.9 1.4A15.6 15.6 0 0 1 4 6.5 1.7 1.7 0 0 1 5.4 4.6l1.8-.3a2 2 0 0 1 2.1 1.2Z" />
      <path d="M3 3l18 18" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.2 19 6v5.4c0 4.3-2.8 7.6-7 9.4-4.2-1.8-7-5.1-7-9.4V6Z" />
      <path d="M9.2 12.2l2 2 3.6-4" />
    </>
  ),
  truck: (
    <>
      <path d="M3 7.5h10.5v9H3z" />
      <path d="M13.5 10.5H17l3 3v3h-6.5z" />
      <circle cx="7" cy="17.5" r="1.9" />
      <circle cx="16.5" cy="17.5" r="1.9" />
    </>
  ),
  pill: (
    <>
      <rect x="2.6" y="8.6" width="18.8" height="6.8" rx="3.4" transform="rotate(-45 12 12)" />
      <path d="M9.2 9.2l5.6 5.6" />
    </>
  ),
  rx: (
    <>
      <path d="M6 3.5h8.5L19 8v12.5H6z" />
      <path d="M14 3.5V8h5" />
      <path d="M9 18v-7h2.4a1.9 1.9 0 0 1 0 3.8H9" />
      <path d="M11.3 14.8 14.4 18" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21c4-4.4 6-7.6 6-10a6 6 0 1 0-12 0c0 2.4 2 5.6 6 10Z" />
      <circle cx="12" cy="11" r="2.2" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.2V12l3 1.8" />
    </>
  ),
  plus: (
    <>
      <path d="M12 5.5v13" />
      <path d="M5.5 12h13" />
    </>
  ),
  minus: <path d="M5.5 12h13" />,
  chevronDown: <path d="M6 9.5l6 6 6-6" />,
  chevronRight: <path d="M9.5 6l6 6-6 6" />,
  menu: (
    <>
      <path d="M4 8h16" />
      <path d="M4 16h16" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 6.2 12 6.2 21.5 12 21.5 12 18 17.8 12 17.8 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  eyeOff: (
    <>
      <path d="M4 4l16 16" />
      <path d="M9.7 5.6A9.6 9.6 0 0 1 12 5.4c6 0 9.5 6.6 9.5 6.6a17 17 0 0 1-3.2 4" />
      <path d="M6.4 7.9A16.8 16.8 0 0 0 2.5 12S6 18.6 12 18.6a9.5 9.5 0 0 0 4-.9" />
      <path d="M9.9 10.2a3 3 0 0 0 4.1 4.2" />
    </>
  ),
  alert: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.8v4.8" />
      <path d="M12 16.1h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11.4v4.8" />
      <path d="M12 8h.01" />
    </>
  ),
  network: (
    <>
      <circle cx="12" cy="5" r="2.4" />
      <circle cx="5" cy="18.5" r="2.4" />
      <circle cx="19" cy="18.5" r="2.4" />
      <path d="M10.4 7.1 6.3 16.4" />
      <path d="M13.6 7.1l4.1 9.3" />
      <path d="M7.4 18.5h9.2" />
    </>
  ),
  people: (
    <>
      <circle cx="9.2" cy="8.5" r="3.2" />
      <path d="M3.5 19.4a5.8 5.8 0 0 1 11.4 0" />
      <path d="M16 5.8a3.2 3.2 0 0 1 0 5.6" />
      <path d="M17.4 14.6a5.8 5.8 0 0 1 3.1 4.8" />
    </>
  ),
  stethoscope: (
    <>
      <path d="M6 3.5v4.8a4 4 0 0 0 8 0V3.5" />
      <path d="M4.4 3.5h3.2" />
      <path d="M12.4 3.5h3.2" />
      <path d="M10 12.3v2.4a4.6 4.6 0 0 0 9.2 0v-1.1" />
      <circle cx="19.2" cy="11.3" r="2.1" />
    </>
  ),
  pharmacy: (
    <>
      <path d="M4 20.5V9.2l8-5.4 8 5.4v11.3z" />
      <path d="M12 9.6v6.4" />
      <path d="M8.8 12.8h6.4" />
    </>
  ),
  home: (
    <>
      <path d="M4 10.6 12 4l8 6.6v9.4h-5.6v-5.2H9.6V20H4z" />
    </>
  ),
  box: (
    <>
      <path d="M12 3.4 20 7.6v8.8L12 20.6 4 16.4V7.6z" />
      <path d="M4 7.6 12 12l8-4.4" />
      <path d="M12 12v8.6" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.4" r="3.6" />
      <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" />
    </>
  ),
  filters: (
    <>
      <path d="M4 7h16" />
      <path d="M7 12h10" />
      <path d="M10 17h4" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 12a8 8 0 1 1-2.6-5.9" />
      <path d="M20 4.5V10h-5.5" />
    </>
  ),
  lock: (
    <>
      <rect x="4.8" y="10.4" width="14.4" height="9.6" rx="2.2" />
      <path d="M8.4 10.4V7.8a3.6 3.6 0 0 1 7.2 0v2.6" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3.5 13.9 9 19.5 11 13.9 13 12 18.5 10.1 13 4.5 11 10.1 9z" />
    </>
  ),
  card: (
    <>
      <rect x="2.8" y="5.4" width="18.4" height="13.2" rx="2.4" />
      <path d="M2.8 10h18.4" />
      <path d="M6.4 14.6h3.4" />
    </>
  ),
  bell: (
    <>
      <path d="M18 9a6 6 0 1 0-12 0c0 5-2 6.2-2 6.2h16S18 14 18 9z" />
      <path d="M13.7 19a2 2 0 0 1-3.4 0" />
    </>
  ),
  star: (
    <>
      <path d="m12 3.6 2.6 5.4 5.9.85-4.25 4.15 1 5.9L12 17.05 6.75 19.9l1-5.9L3.5 9.85 9.4 9z" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.6" y="5" width="16.8" height="15.4" rx="2.4" />
      <path d="M3.6 9.8h16.8" />
      <path d="M8.2 3.4v3.2M15.8 3.4v3.2" />
    </>
  ),
  trash: (
    <>
      <path d="M4.4 6.6h15.2" />
      <path d="M9 6.6V4.9a1.4 1.4 0 0 1 1.4-1.4h3.2A1.4 1.4 0 0 1 15 4.9v1.7" />
      <path d="M6.4 6.6 7.3 19a1.6 1.6 0 0 0 1.6 1.5h6.2a1.6 1.6 0 0 0 1.6-1.5l.9-12.4" />
    </>
  ),
  pencil: (
    <>
      <path d="M4.4 19.6h3.4L18.9 8.5a1.9 1.9 0 0 0 0-2.7l-.7-.7a1.9 1.9 0 0 0-2.7 0L4.4 16.2z" />
      <path d="M14.4 6.8l2.8 2.8" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M9.7 9.6a2.35 2.35 0 0 1 4.6.7c0 1.6-2.3 1.9-2.3 3.3" />
      <path d="M12 17.1h.01" />
    </>
  ),
  pause: (
    <>
      <path d="M9.4 5.2v13.6M14.6 5.2v13.6" />
    </>
  ),
  play: (
    <>
      <path d="M8.4 5.3 18.6 12 8.4 18.7z" />
    </>
  ),
  qr: (
    <>
      <rect x="3.8" y="3.8" width="6.4" height="6.4" rx="1.4" />
      <rect x="13.8" y="3.8" width="6.4" height="6.4" rx="1.4" />
      <rect x="3.8" y="13.8" width="6.4" height="6.4" rx="1.4" />
      <path d="M14 14h2.6M20.2 14v2.7M14 20.2h2.6M20.2 20.2h.01M17.6 17.4h2.6" />
    </>
  ),
  receipt: (
    <>
      <path d="M5.4 3.6h13.2v17.2l-2.6-1.6-2.2 1.6-2.4-1.6-2.2 1.6-2.6-1.6z" />
      <path d="M9 8.4h6M9 12.4h6" />
    </>
  )
};

export function Icon({
  name,
  size = 18,
  className,
  strokeWidth = 1.6
}: {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
