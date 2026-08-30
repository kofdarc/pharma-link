import { Icon } from "@/components/ui/Icon";
import { PackThumb } from "@/components/medicines/PackThumb";

/**
 * Fictional renderings of the real interface, used where a marketing page needs
 * a picture. They reuse the product's own chips, type and spacing rather than a
 * separate illustrative language, and they never show a real patient, a real
 * pharmacy's stock, or a real prescription.
 */

export function SearchVisual() {
  return (
    <div className="hc-pv">
      <div className="hc-pv-field">
        <Icon name="search" size={17} />
        <span>Augmentin 1g</span>
        <span className="hc-pv-caret" />
      </div>

      <div className="hc-pv-list">
        <div className="hc-pv-row hc-pv-row-active">
          <PackThumb brand="Augmentin" />
          <span className="hc-pv-row-main">
            <strong>Augmentin 1g</strong>
            <span>Amoxicillin · Tablet</span>
          </span>
          <span className="hc-chip hc-chip-ok hc-status">
            <span className="hc-dot" />
            Available
          </span>
        </div>

        <div className="hc-pv-row">
          <PackThumb brand="Amoclav" />
          <span className="hc-pv-row-main">
            <strong>Amoclav 1g</strong>
            <span>Amoxicillin · Tablet</span>
          </span>
          <span className="hc-chip hc-chip-limited hc-status">
            <span className="hc-dot" />
            Limited
          </span>
        </div>
      </div>

      <div className="hc-pv-foot">
        <span className="hc-prescription-status is-required">
          <Icon name="rx" size={13} />
          Prescription required
        </span>
        <span className="hc-small">7 connected pharmacies</span>
      </div>
    </div>
  );
}

export function RxCard() {
  return (
    <div className="hc-rx">
      <div className="hc-rx-top">
        <div>
          <p className="hc-card-label">Prescription</p>
          <strong>HC-RX-38292</strong>
        </div>
        <span className="hc-rx-verified hc-status">
          <Icon name="shield" size={14} />
          Verified
        </span>
      </div>

      <div className="hc-rx-body">
        <div className="hc-rx-line">
          <div>
            <strong>Dr. Sarah Haddad</strong>
            <span>Issued 18 Aug 2026 · valid to 18 Sep 2026</span>
          </div>
        </div>
        <div className="hc-rx-line">
          <div>
            <strong>Augmentin 1g</strong>
            <span>Amoxicillin / Clavulanic Acid</span>
          </div>
          <span className="hc-rx-qty">14 tablets</span>
        </div>
        <div className="hc-rx-line">
          <div>
            <strong>Ventolin 100mcg</strong>
            <span>Salbutamol</span>
          </div>
          <span className="hc-rx-qty">1 inhaler</span>
        </div>
      </div>
    </div>
  );
}

export function AvailabilityVisual() {
  const rows = [
    { name: "Cedar Care Pharmacy", area: "Hamra", state: "ok" as const, label: "Available" },
    { name: "Mar Elias Pharmacy", area: "Mar Elias", state: "off" as const, label: "Unavailable" },
    { name: "Verdun Health Pharmacy", area: "Verdun", state: "ok" as const, label: "Available" },
    { name: "Achrafieh Pharmacy", area: "Achrafieh", state: "limited" as const, label: "Limited" }
  ];

  return (
    <div className="hc-pv hc-pv-bare">
      <p className="hc-card-label">Checking connected pharmacies</p>
      <div className="hc-pv-list">
        {rows.map((row) => (
          <div className="hc-pv-row hc-pv-row-plain" key={row.name}>
            <span className="hc-ac-icon">
              <Icon name="pharmacy" size={16} />
            </span>
            <span className="hc-pv-row-main">
              <strong>{row.name}</strong>
              <span>{row.area}</span>
            </span>
            <span className={`hc-chip hc-chip-${row.state} hc-status`}>
              <span className="hc-dot" />
              {row.label}
            </span>
          </div>
        ))}
      </div>
      <p className="hc-small">HealthConnect checks this for you. You never have to.</p>
    </div>
  );
}

export function SourcingVisual() {
  const lines = [
    { name: "Augmentin 1g", source: "Pharmacy A", tone: "hc-source-a" },
    { name: "Panadol Extra", source: "Pharmacy A", tone: "hc-source-a" },
    { name: "Lipitor 20mg", source: "Pharmacy B", tone: "hc-source-b" }
  ];

  return (
    <div className="hc-pv hc-pv-bare">
      <p className="hc-card-label">Your medications</p>
      <div className="hc-source-list">
        {lines.map((line) => (
          <div className="hc-source-row" key={line.name}>
            <Icon name="pill" size={16} />
            <strong>{line.name}</strong>
            <span className={`hc-source-tag ${line.tone}`}>
              <i />
              {line.source}
            </span>
          </div>
        ))}
      </div>
      <div className="hc-source-summary">
        <Icon name="checkCircle" size={18} />
        Two pharmacies, one order. HealthConnect handles the coordination.
      </div>
    </div>
  );
}

const DELIVERY_STEPS = [
  { label: "Order confirmed", state: "done" },
  { label: "Pharmacy preparing", state: "done" },
  { label: "Driver collecting", state: "current" },
  { label: "Out for delivery", state: "todo" },
  { label: "Delivered", state: "todo" }
] as const;

export function DeliveryVisual() {
  return (
    <div className="hc-pv hc-pv-bare">
      <div className="hc-pv-foot">
        <p className="hc-card-label">Order HC-24082</p>
        <span className="hc-small">Arriving 4:30 – 5:00 PM</span>
      </div>
      <ol className="hc-track">
        {DELIVERY_STEPS.map((step) => (
          <li key={step.label} data-state={step.state}>
            <span className="hc-track-mark">
              {step.state === "done" ? <Icon name="check" size={12} strokeWidth={2.6} /> : null}
              {step.state === "current" ? <span className="hc-track-dot" /> : null}
            </span>
            {step.label}
          </li>
        ))}
      </ol>
    </div>
  );
}
