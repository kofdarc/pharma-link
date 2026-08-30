import Link from "next/link";
import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { ArrowLink, CtaSection, SectionHeading } from "@/components/site/Section";
import { ConnectedHeadline } from "@/components/site/ConnectedHeadline";
import { RxCard, SearchVisual } from "@/components/product/Visuals";
import { Icon, type IconName } from "@/components/ui/Icon";

export const metadata = {
  title: "HealthConnect: healthcare, finally connected",
  description:
    "Find medication across pharmacies near you, handle prescription requirements, and get your medicine delivered with automatic refills on your schedule."
};

const CAPABILITIES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "search",
    title: "Find medication",
    body: "Search once by brand or generic name and see what is actually available across connected pharmacies. You do not get a list of shops to call."
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

const REASONS: { icon: IconName; title: string; items: string[] }[] = [
  {
    icon: "stethoscope",
    title: "Prescribers",
    items: [
      "Issue prescriptions digitally instead of a handwritten slip that can be lost, altered or faxed back and forth.",
      "Approve or deny a pharmacy's renewal request from one queue, without a phone call chasing you down between patients.",
      "Prescribe against the same medicine catalog pharmacies dispense from, so what you write and what's on the shelf line up.",
      "Every prescription you issue and every renewal decision is written to a reviewable record. There is no need to explain yourself from memory.",
      "More time for patient care, with less paperwork chasing pharmacies for stock or confirming what was actually dispensed."
    ]
  },
  {
    icon: "pharmacy",
    title: "Pharmacists",
    items: [
      "Scan a prescription's code and key to confirm it is genuine and unclaimed before you dispense. No signature is taken on faith.",
      "Pull structured drug, dose and quantity lines off a photographed paper prescription instead of retyping it by hand.",
      "Keep the point-of-sale system you already run. HealthConnect syncs stock and sales through it instead of asking you to replace it.",
      "Request a renewal straight from the counter when a patient's script has run out, instead of calling the clinic.",
      "A plain-language insights digest flags what needs attention, including reorder-now items, dead stock and unmet demand, instead of making you build the spreadsheet yourself.",
      "More time for patient consultations and less time on transcription and stock-chasing."
    ]
  },
  {
    icon: "people",
    title: "Patients",
    items: [
      "Search once and see what is actually available across every connected pharmacy, instead of calling pharmacy after pharmacy.",
      "One order can be sourced from more than one pharmacy and still arrive as a single delivery.",
      "Fewer lost or damaged prescriptions. Your script lives on your phone, not a slip of paper.",
      "Decreased risk of a prescription being seen by the wrong person, with no fax line, no unsecured email and every lookup logged.",
      "Set up a recurring refill for an ongoing medication so it is ready before you run out.",
      "Improved patient safety because a pharmacy can only dispense against a prescription confirmed valid and unclaimed."
    ]
  },
  {
    icon: "shield",
    title: "Health care system",
    items: [
      "Reduce duplicate or inappropriately filled prescriptions. A script can be claimed exactly once across the network, in full or in part.",
      "Reduce fraud and potential for abuse because every access to a prescription is logged, with lockouts after repeated failed attempts.",
      "Improve medication cost management through tracked insurance claim adjudication, from submission to payment.",
      "Reduce shortages by making reorder points, dead stock and expiry exposure visible before they are discovered at the register.",
      "Keep catalog pricing aligned to Ministry of Public Health rates when pharmacies import their stock."
    ]
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
                Find medication across pharmacies near you, handle prescription requirements, and get your medicine delivered.
                Set up automatic refills weekly, monthly, or on the schedule that works for you.
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
                  <em>Pharmacy one</em>: out of stock
                </div>
                <div className="hc-call">
                  <Icon name="phoneOff" size={17} className="hc-call-x" />
                  <em>Pharmacy two</em>: out of stock
                </div>
                <div className="hc-call">
                  <Icon name="phoneOff" size={17} className="hc-call-x" />
                  <em>Pharmacy three</em>: closed
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
                pharmacy scans it, dispenses what you need, and anything left stays claimable. It can be claimed once, and only once.
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

        {/* --- reasons ------------------------------------------------------ */}
        <section className="hc-section hc-band">
          <div className="hc-wrap">
            <SectionHeading
              title="Reasons to use HealthConnect."
              lead="Every participant in the medication journey gets something concrete from being connected."
            />
            <div className="hc-reasons-grid">
              {REASONS.map((role) => (
                <div className="hc-reason-card" key={role.title}>
                  <div className="hc-reason-head">
                    <span className="hc-reason-icon">
                      <Icon name={role.icon} size={19} />
                    </span>
                    <h3 className="hc-h3">{role.title}</h3>
                  </div>
                  <ul className="hc-reason-list">
                    {role.items.map((item) => (
                      <li key={item.slice(0, 40)}>
                        <Icon name="check" size={15} />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
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
