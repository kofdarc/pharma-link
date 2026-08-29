import { readFileSync } from "node:fs";

const files = {
  global: readFileSync("apps/web/app/globals.css", "utf8"),
  patient: readFileSync("apps/web/app/patient.css", "utf8"),
  patientApp: readFileSync("apps/web/app/patient-app.css", "utf8"),
  patientUi: readFileSync("apps/web/app/patient-ui.css", "utf8"),
  home: readFileSync("apps/web/app/home/page.tsx", "utf8"),
  badges: readFileSync("apps/web/components/ui/Badge.tsx", "utf8"),
  availability: readFileSync("apps/web/components/medicines/Badges.tsx", "utf8"),
  prescriptions: readFileSync("apps/web/components/prescriptions/PrescriptionParts.tsx", "utf8"),
  orders: readFileSync("apps/web/components/orders/OrderParts.tsx", "utf8"),
  refills: readFileSync("apps/web/components/refills/RefillParts.tsx", "utf8"),
  settings: readFileSync("apps/web/components/account/SettingsParts.tsx", "utf8"),
  visuals: readFileSync("apps/web/components/product/Visuals.tsx", "utf8")
};

const selectors = [["patient", ".hc-status"], ["global", ".badge-status"]];

function ruleBody(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  if (!match) throw new Error(`Missing rule for ${selector}`);
  return match[1];
}

for (const [file, selector] of selectors) {
  const body = ruleBody(files[file], selector);
  for (const declaration of ["padding: 0", "border: 0", "border-radius: 0", "background: transparent", "box-shadow: none"]) {
    if (!body.includes(declaration)) throw new Error(`${selector} is missing ${declaration}`);
  }
}

if (!/\.badge\s*\{[^}]*border-radius:\s*999px/s.test(files.global)) {
  throw new Error("Non-status Badge pills were changed outside the approved scope");
}

if (!/--hc-pill:\s*999px/.test(files.patient)) {
  throw new Error("Unrelated rounded controls were changed outside the status-label scope");
}

for (const file of ["home", "availability", "prescriptions", "orders", "refills", "settings", "visuals"]) {
  if (!/hc-status/.test(files[file])) throw new Error(`${file} has no scoped status treatment`);
}

if (!/status \? " badge-status" : ""/.test(files.badges)) throw new Error("Shared Badge renderer is not status-scoped");

if (!/hc-chip hc-chip-rx/.test(files.home) || !/hc-chip hc-chip-rx/.test(files.availability)) {
  throw new Error("Rx labels or identifiers were changed outside the status scope");
}

if (!/\.hc-segmented\s*\{[^}]*border-radius:\s*var\(--hc-pill\)/s.test(files.patientApp)) {
  throw new Error("Segmented controls were changed outside the status-label scope");
}

console.log("STATUS LABEL REDESIGN VERIFIED");
