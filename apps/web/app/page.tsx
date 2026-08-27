import Link from "next/link";
import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { ArrowLink, CtaSection, SectionHeading } from "@/components/site/Section";
import { ConnectedHeadline } from "@/components/site/ConnectedHeadline";
import { RxCard, SearchVisual } from "@/components/product/Visuals";
import { Icon, type IconName } from "@/components/ui/Icon";

export const metadata = {
  title: "HealthConnect — healthcare, finally connected",
  description:
    "Find medication across connected pharmacies, handle prescription requirements, and get what you need without calling pharmacy after pharmacy."
};

const CAPABILITIES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "search",
    title: "Find medication",
    body: "Search once by brand or generic name and see what is actually available across connected pharmacies — not a list of shops to call."
  },
  {
    icon: "shield",
    title: "Use secure prescriptions",
    body: "Prescriptions your physician issues through HealthConnect are digital, verifiable, and can be dispensed in full or in part."
  },
  {
    icon: "truck",
    title: "Get it delivered",
    body: "HealthConnect works out where each medicine comes from and coordinates a single delivery to your door."
  }
];

const STEPS = [
  { title: "Search", body: "Find the medication you need by brand, generic name or what the box says." },
  { title: "HealthConnect sources it", body: "Availability is checked across every connected pharmacy at once." },
  { title: "Confirm", body: "Review the option HealthConnect found and choose how you want it." },
  { title: "Receive", body: "Your medication is prepared and delivered, with the order traceable throughout." }
];

const TRUST: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "rx",
    title: "Secure prescriptions",
    body: "A prescription code on its own reveals nothing. Dispensing needs the accompanying key, and every attempt is recorded."
  },
  {
    icon: "network",
    title: "Connected pharmacies",
    body: "Pharmacies join with the software they already run, so what you see reflects their real counter."
  },
  {
    icon: "lock",
    title: "Protected information",
    body: "Your details are visible only to the people fulfilling your order, and pharmacies never expose their stock depth to you."
  },
  {
    icon: "checkCircle",
    title: "Traceable fulfilment",
    body: "Every dispense, correction and hand-over is written to an append-only record that can be reviewed."
  }
];

export default function LandingPage() {
  return (
    <div className="hc">
      <SiteHeader />

      <main className="hc-main">
        {/* --- hero ------------------------------------------------------- */}
        <section className="hc-hero">
          <div className="hc-wrap hc-hero-grid">
            <div className="hc-hero-copy">
              <ConnectedHeadline />
              <p className="hc-lead">
                Find medication across connected pharmacies, handle prescription requirements, and get what you need — without
                calling pharmacy after pharmacy.
              </p>
              <div className="hc-actions">
                <Link href="/search" className="hc-btn hc-btn-primary hc-btn-lg">
                  <Icon name="search" size={18} />
                  Search medications
                </Link>
                <Link href="/how-it-works" className="hc-btn hc-btn-secondary hc-btn-lg">
                  See how it works
                </Link>
              </div>
              <p className="hc-hero-note">
                <Icon name="info" size={16} />
                Searching is free and does not need an account.
              </p>
            </div>

            <div className="hc-hero-visual">
              <SearchVisual />
            </div>
          </div>
        </section>

        {/* --- the problem ------------------------------------------------ */}
        <section className="hc-section hc-band">
          <div className="hc-wrap">
            <SectionHeading
              title="Finding one medicine shouldn't take five phone calls."
              lead="Pharmacy stock lives in disconnected systems, so the only way to find out who has something is to ask each one. That falls hardest on people who need medication regularly."
            />

            <div className="hc-compare">
              <div className="hc-compare-col">
                <p className="hc-card-label">Today</p>
                <div className="hc-call">
                  <Icon name="phoneOff" size={17} className="hc-call-x" />
                  <em>Pharmacy one</em> — out of stock
                </div>
                <div className="hc-call">
                  <Icon name="phoneOff" size={17} className="hc-call-x" />
                  <em>Pharmacy two</em> — out of stock
                </div>
                <div className="hc-call">
                  <Icon name="phoneOff" size={17} className="hc-call-x" />
                  <em>Pharmacy three</em> — closed
                </div>
                <p className="hc-call-more" aria-hidden="true">
                  · · ·
                </p>
              </div>

              <span className="hc-compare-arrow" aria-hidden="true">
                <Icon name="arrowRight" size={20} />
              </span>

              <div className="hc-compare-col">
                <p className="hc-card-label">With HealthConnect</p>
                <div className="hc-solved">
                  <strong>One search, every connected pharmacy.</strong>
                  <p>You tell HealthConnect what you need. HealthConnect works out where it can come from.</p>
                  <div className="hc-solved-net">
                    <span>Availability checked</span>
                    <span>Prescription handled</span>
                    <span>Delivery arranged</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* --- capabilities ----------------------------------------------- */}
        <section className="hc-section">
          <div className="hc-wrap">
            <SectionHeading title="Built around the medicine, not the pharmacy." />
            <div className="hc-feature-grid">
              {CAPABILITIES.map((capability) => (
                <article className="hc-feature" key={capability.title}>
                  <span className="hc-feature-icon">
                    <Icon name={capability.icon} size={20} />
                  </span>
                  <h3 className="hc-h3">{capability.title}</h3>
                  <p className="hc-body">{capability.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* --- digital prescriptions -------------------------------------- */}
        <section className="hc-section hc-band">
          <div className="hc-wrap hc-explain-row">
            <div className="hc-explain-copy">
              <h2 className="hc-h2">A prescription that can&apos;t be lost, copied or reused.</h2>
              <p className="hc-body">
                When your physician prescribes through HealthConnect you receive a prescription you can keep on your phone. The
                pharmacy scans it, dispenses what you need, and anything left stays claimable — once, and only once.
              </p>
              <p className="hc-body">
                The code alone does not open the prescription: a pharmacy needs the key that comes with it, and every lookup is
                recorded.
              </p>
              <div className="hc-actions" style={{ marginTop: 26 }}>
                <ArrowLink href="/how-it-works">See how verification works</ArrowLink>
              </div>
            </div>
            <div className="hc-explain-visual">
              <RxCard />
              <p className="hc-small" style={{ marginTop: 14, textAlign: "center" }}>
                Illustration. Not a real prescription.
              </p>
            </div>
          </div>
        </section>

        {/* --- how it works ------------------------------------------------ */}
        <section className="hc-section">
          <div className="hc-wrap">
            <SectionHeading title="Four steps, and most of them are ours." />
            <ol className="hc-steps">
              {STEPS.map((step, index) => (
                <li className="hc-step" key={step.title}>
                  <span className="hc-step-num" aria-hidden="true">
                    {index + 1}
                  </span>
                  <h3 className="hc-h3">{step.title}</h3>
                  <p className="hc-body">{step.body}</p>
                </li>
              ))}
            </ol>
            <div className="hc-actions" style={{ marginTop: 40 }}>
              <ArrowLink href="/how-it-works">Learn how HealthConnect works</ArrowLink>
            </div>
          </div>
        </section>

        {/* --- trust -------------------------------------------------------- */}
        <section className="hc-section hc-band">
          <div className="hc-wrap">
            <SectionHeading
              title="Health information deserves more than a login screen."
              lead="HealthConnect carries prescriptions and medication history, so access is narrow by default and everything consequential leaves a record."
            />
            <div className="hc-trust-grid">
              {TRUST.map((item) => (
                <div className="hc-trust" key={item.title}>
                  <Icon name={item.icon} size={22} />
                  <h3 className="hc-h3">{item.title}</h3>
                  <p className="hc-body">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <CtaSection
          title="Looking for a medication?"
          lead="Search the connected pharmacy network. No account needed to look."
          primary={{ href: "/search", label: "Search HealthConnect" }}
          secondary={{ href: "/register", label: "Create an account" }}
        />
      </main>

      <SiteFooter />
    </div>
  );
}
