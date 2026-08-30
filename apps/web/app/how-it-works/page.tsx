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
      "Search by brand or generic name. HealthConnect knows Augmentin and amoxicillin / clavulanic acid are the same, and shows the strengths that exist.",
      "You pick the medicine. Finding it is our job."
    ],
    visual: <SearchVisual />
  },
  {
    title: "We check every connected pharmacy at once",
    body: [
      "Instead of you calling around, HealthConnect asks the whole network and reads what each pharmacy can actually supply.",
      "You see availability in plain words, never how much a pharmacy holds."
    ],
    visual: <AvailabilityVisual />
  },
  {
    title: "One basket can come from more than one pharmacy",
    body: [
      "If no single pharmacy has everything, HealthConnect combines pharmacies to cover your basket.",
      "You still place one order and get one delivery."
    ],
    visual: <SourcingVisual />
  },
  {
    title: "Set up medicines you take regularly",
    body: [
      "For an ongoing medication, schedule a recurring order so it's ready before you run out.",
      "Pause, skip, or cancel it any time. A valid prescription is still checked each time it's filled."
    ],
    visual: <DeliveryVisual />
  },
  {
    title: "Prescriptions are verified before dispensing",
    body: [
      "A prescription from HealthConnect is confirmed as valid and unclaimed before a pharmacy fills it.",
      "If only part is in stock, take what's available now and claim the rest later."
    ],
    visual: <RxCard />
  },
  {
    title: "Then it comes to you",
    body: [
      "Once a pharmacy has your order ready, a driver collects it and brings it to you.",
      "You can follow it the whole way."
    ],
    visual: <DeliveryVisual />
  }
];

const PRESCRIBING_FEATURES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "rx",
    title: "Create Rx",
    body: "Your physician writes the prescription and sends it straight to your chosen pharmacy, or holds it for you to use at any connected pharmacy with a code."
  },
  {
    icon: "shield",
    title: "Guaranteed delivery",
    body: "However a prescription is sent, HealthConnect makes sure it reaches you and the pharmacy. The signed copy from your physician stays the authoritative record."
  },
  {
    icon: "refresh",
    title: "Renew Rx",
    body: "When a prescription runs low, the pharmacy can request a renewal from your physician, and the approved renewal returns as a new e-prescription."
  },
  {
    icon: "trash",
    title: "Prescription cancel",
    body: "The physician who issued a prescription can cancel it, even after it has been partly dispensed."
  },
  {
    icon: "checkCircle",
    title: "Rx status",
    body: "Your physician can see whether a prescription was dispensed, partly filled, or cancelled, without calling the pharmacy."
  },
  {
    icon: "message",
    title: "Clinical communication",
    body: "Physicians and pharmacies can message each other about a prescription, and it stays attached to the record."
  },
  {
    icon: "card",
    title: "Formulary services",
    body: "Before prescribing, your physician can check whether a medicine is covered by your insurance."
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
                You search once. HealthConnect handles the asking, the sourcing, the prescription checks, and the delivery.
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
