import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { CtaSection, SectionHeading } from "@/components/site/Section";
import { AvailabilityVisual, DeliveryVisual, RxCard, SearchVisual, SourcingVisual } from "@/components/product/Visuals";
import { Icon, type IconName } from "@/components/ui/Icon";

export const metadata = {
  title: "How it works",
  description: "How HealthConnect finds your medication across connected pharmacies, verifies prescriptions and coordinates delivery."
};

const STEPS = [
  {
    title: "Tell us the medicine, not the pharmacy",
    body: [
      "Type a brand name, a generic name, or whatever is written on the box. HealthConnect understands that Augmentin and amoxicillin / clavulanic acid are the same search, and it will suggest the strengths that exist.",
      "You are choosing a medicine. Where it comes from is our problem, not yours."
    ],
    visual: <SearchVisual />
  },
  {
    title: "We check every connected pharmacy at once",
    body: [
      "Instead of you calling around, HealthConnect asks the whole connected network. Pharmacies keep their own software and their own stock — the platform reads what they can actually supply.",
      "You see availability in plain words. Pharmacies never publish how much they hold."
    ],
    visual: <AvailabilityVisual />
  },
  {
    title: "One basket can come from more than one pharmacy",
    body: [
      "If no single pharmacy has everything you need, HealthConnect does not send you away half-served. It works out a combination that covers the basket with as few pickups as possible.",
      "You still place one order and receive one delivery. HealthConnect handles the coordination for you."
    ],
    visual: <SourcingVisual />
  },
  {
    title: "Prescription medicines are verified before they're dispensed",
    body: [
      "A prescription issued through HealthConnect travels as a code plus a protected key. The pharmacy scans it, HealthConnect confirms it is valid and unclaimed, and the pharmacy dispenses against it.",
      "Partial dispensing is normal: take what is available now, and the remainder stays claimable later — once."
    ],
    visual: <RxCard />
  },
  {
    title: "Then it comes to you",
    body: [
      "Once the pharmacies have prepared their part, a driver collects and delivers. Where several orders share a pharmacy, those pickups are combined, which is why deliveries do not need a separate trip each.",
      "You can follow the order the whole way."
    ],
    visual: <DeliveryVisual />
  }
];

const PRESCRIBING_FEATURES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "rx",
    title: "Create Rx",
    body: "Your physician writes the prescription in HealthConnect. Patient choice comes first: pick a pharmacy and it's sent straight to that pharmacy's queue, ready before you arrive. Haven't decided yet? The prescription is held in HealthConnect instead — you're handed a signed copy with a code and a QR barcode, and any connected pharmacy can pull it up by scanning that barcode or entering the code."
  },
  {
    icon: "shield",
    title: "Guaranteed delivery",
    body: "Whichever way a prescription is sent, HealthConnect makes sure it reaches you. It's emailed first where an address is on file; if that can't go through, or none was given, it's faxed instead as a back-up. Either way, the signed copy your physician hands you is always the authoritative record — digital delivery is a convenience on top of it, never a condition for it."
  },
  {
    icon: "refresh",
    title: "Renew Rx",
    body: "When a prescription is running low, a pharmacy can request a renewal directly from your physician. Once it's approved, the renewal comes back through HealthConnect as a new e-prescription."
  },
  {
    icon: "trash",
    title: "Prescription cancel",
    body: "A prescription that's already been sent to a pharmacy can still be cancelled by the physician who issued it, whether it hasn't been touched yet or has already been partly dispensed."
  },
  {
    icon: "checkCircle",
    title: "Rx status",
    body: "Your physician can see whether a prescription has been dispensed, partly filled, or cancelled — without having to call the pharmacy to ask."
  },
  {
    icon: "message",
    title: "Clinical communication",
    body: "Physicians and pharmacies can message each other about a specific prescription, and that conversation stays attached to the record for later reference."
  },
  {
    icon: "card",
    title: "Formulary services",
    body: "Before prescribing, your physician can check whether a medicine is covered under your insurance plan, so coverage isn't a surprise when you get to the pharmacy."
  }
];

export default function HowItWorksPage() {
  return (
    <div className="hc">
      <SiteHeader />

      <main className="hc-main">
        <section className="hc-hero">
          <div className="hc-wrap">
            <div style={{ maxWidth: "46rem" }}>
              <h1 className="hc-display">Getting your medication shouldn&apos;t require five phone calls.</h1>
              <p className="hc-lead" style={{ marginTop: 22 }}>
                HealthConnect sits between you and every pharmacy that has joined the network. You search once; the platform does
                the asking, the sourcing, the prescription checks and the delivery.
              </p>
            </div>
          </div>
        </section>

        <section className="hc-section hc-band">
          <div className="hc-wrap">
            <div className="hc-explain">
              {STEPS.map((step) => (
                <article className="hc-explain-row" key={step.title}>
                  <div className="hc-explain-copy">
                    <h2 className="hc-h2">{step.title}</h2>
                    {step.body.map((paragraph) => (
                      <p className="hc-body" key={paragraph.slice(0, 32)}>
                        {paragraph}
                      </p>
                    ))}
                  </div>
                  <div className="hc-explain-visual">{step.visual}</div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="hc-section">
          <div className="hc-wrap">
            <SectionHeading
              title="What your physician can do through HealthConnect."
              lead="The prescribing side works the same way the pharmacy side does — connected, verifiable, and traceable."
            />
            <div className="hc-feature-grid">
              {PRESCRIBING_FEATURES.map((feature) => (
                <article className="hc-feature" key={feature.title}>
                  <span className="hc-feature-icon">
                    <Icon name={feature.icon} size={20} />
                  </span>
                  <h3 className="hc-h3">{feature.title}</h3>
                  <p className="hc-body">{feature.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <CtaSection
          title="Ready when you are."
          lead="Start with the medicine you need. HealthConnect will work out the rest."
          primary={{ href: "/search", label: "Search for a medication" }}
          secondary={{ href: "/register", label: "Create an account" }}
        />
      </main>

      <SiteFooter />
    </div>
  );
}
