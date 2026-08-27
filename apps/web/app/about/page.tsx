import { SiteHeader } from "@/components/site/SiteHeader";
import { SiteFooter } from "@/components/site/SiteFooter";
import { CtaSection, SectionHeading } from "@/components/site/Section";
import { Icon, type IconName } from "@/components/ui/Icon";

export const metadata = {
  title: "About",
  description: "Why HealthConnect exists: making medication access in Lebanon simpler and more connected."
};

const FRAGMENTS = [
  "Prescriptions written on paper, which can be lost, altered or reused.",
  "Stock checks that happen by phone, one pharmacy at a time.",
  "Pharmacy systems that do not talk to each other, or to anything else.",
  "Deliveries arranged manually, if they are arranged at all."
];

const ECOSYSTEM: { icon: IconName; title: string; body: string; center?: boolean }[] = [
  { icon: "stethoscope", title: "Physicians", body: "Issue prescriptions digitally" },
  { icon: "pharmacy", title: "Pharmacies", body: "Keep their own software" },
  { icon: "people", title: "Patients", body: "Find and receive medication", center: true },
  { icon: "truck", title: "Delivery", body: "Coordinated, not improvised" },
  { icon: "shield", title: "Oversight", body: "A reviewable record" }
];

const REASONS: { icon: IconName; title: string; items: string[] }[] = [
  {
    icon: "stethoscope",
    title: "Prescribers",
    items: [
      "Issue prescriptions digitally instead of a handwritten slip that can be lost, altered or faxed back and forth.",
      "Approve or deny a pharmacy's renewal request from one queue, without a phone call chasing you down between patients.",
      "Prescribe against the same medicine catalog pharmacies dispense from, so what you write and what's on the shelf line up.",
      "Every prescription you issue and every renewal decision is written to a reviewable record — no explaining yourself from memory.",
      "More time for patient care: less paperwork chasing pharmacies for stock or confirming what was actually dispensed."
    ]
  },
  {
    icon: "pharmacy",
    title: "Pharmacists",
    items: [
      "Scan a prescription's code and key to confirm it's genuine and unclaimed before you dispense — not a signature taken on faith.",
      "Pull structured drug, dose and quantity lines off a photographed paper prescription instead of retyping it by hand.",
      "Keep the point-of-sale system you already run — HealthConnect syncs stock and sales through it rather than asking you to replace it.",
      "Request a renewal straight from the counter when a patient's script has run out, instead of a call to the clinic.",
      "A plain-language insights digest flags what needs attention — reorder-now items, dead stock, unmet demand — instead of building the spreadsheet yourself.",
      "More time for patient consultations, less time on transcription and stock-chasing."
    ]
  },
  {
    icon: "people",
    title: "Patients",
    items: [
      "Search once and see what's actually available across every connected pharmacy, instead of calling pharmacy after pharmacy.",
      "One order can be sourced from more than one pharmacy and still arrive as a single delivery.",
      "Fewer lost or damaged prescriptions — your script lives on your phone, not a slip of paper.",
      "Decreased risk of a prescription being seen by the wrong person: no fax line, no unsecured email, and every lookup is logged.",
      "Set up a recurring refill for an ongoing medication so it's ready before you run out.",
      "Improved patient safety: a pharmacy can only dispense against a prescription confirmed valid and unclaimed."
    ]
  },
  {
    icon: "shield",
    title: "Health care system",
    items: [
      "Reduction of duplicate or inappropriately filled prescriptions — a script can be claimed exactly once across the network, in full or in part.",
      "Less fraud and potential for abuse: every access to a prescription is logged, with lockouts after repeated failed attempts.",
      "Improved medication cost management through tracked insurance claim adjudication, from submission to payment.",
      "Fewer shortages: reorder points, dead stock and expiry exposure are visible instead of discovered at the register.",
      "Catalog pricing stays aligned to Ministry of Public Health rates when pharmacies import their stock."
    ]
  }
];

const PRINCIPLES = [
  {
    title: "Accessible",
    body: "Finding a medicine should not depend on how many pharmacies you are able to call, or how far you can travel to reach them."
  },
  {
    title: "Secure",
    body: "Prescriptions and patient information are handled narrowly: shown to the people who need them, recorded when they are used."
  },
  {
    title: "Connected",
    body: "Patients, physicians, pharmacies and delivery are part of one journey. They should not each be working from a different picture of it."
  },
  {
    title: "Practical",
    body: "Pharmacies keep the software they already run. HealthConnect is designed to work with real operations rather than asking the whole system to change first."
  }
];

export default function AboutPage() {
  return (
    <div className="hc">
      <SiteHeader />

      <main className="hc-main">
        <section className="hc-hero">
          <div className="hc-wrap">
            <div style={{ maxWidth: "44rem" }}>
              <h1 className="hc-display">Making medication access simpler and more connected.</h1>
              <p className="hc-lead" style={{ marginTop: 22 }}>
                HealthConnect is a platform for the whole medication journey in Lebanon — from the moment a prescription is
                written to the moment the medicine reaches the person who needs it.
              </p>
            </div>
          </div>
        </section>

        <section className="hc-section hc-band">
          <div className="hc-wrap hc-explain-row">
            <div className="hc-explain-copy">
              <h2 className="hc-h2">Medication access is fragmented.</h2>
              <p className="hc-body">
                Every part of the journey works — and none of them are joined up. The cost of that lands on patients, and hardest
                on the people least able to absorb it: older adults, people with limited mobility, and anyone managing a chronic
                condition on a repeating prescription.
              </p>
            </div>
            <div className="hc-explain-visual">
              <div className="hc-pv hc-pv-bare">
                <p className="hc-card-label">What patients deal with today</p>
                <div className="hc-source-list">
                  {FRAGMENTS.map((fragment) => (
                    <div className="hc-source-row" key={fragment}>
                      <Icon name="alert" size={17} />
                      <span>{fragment}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="hc-section">
          <div className="hc-wrap">
            <SectionHeading
              title="One journey, five participants."
              lead="HealthConnect connects the roles that already exist in the medication journey. This site is the patient's part of it."
            />
            <div className="hc-ecosystem">
              {ECOSYSTEM.map((node) => (
                <div className={`hc-eco${node.center ? " hc-eco-center" : ""}`} key={node.title}>
                  <Icon name={node.icon} size={22} />
                  <h3 className="hc-h3">{node.title}</h3>
                  <p className="hc-small">{node.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="hc-section hc-band">
          <div className="hc-wrap">
            <SectionHeading
              title="Reasons to use HealthConnect."
              lead="Every participant in the journey gets something concrete out of being connected — not just the patient at the end of it."
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

        <section className="hc-section">
          <div className="hc-wrap">
            <SectionHeading title="What we hold to." />
            <div className="hc-principles">
              {PRINCIPLES.map((principle) => (
                <div className="hc-principle" key={principle.title}>
                  <h3 className="hc-h3">{principle.title}</h3>
                  <p className="hc-body">{principle.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="hc-section-tight">
          <div className="hc-wrap hc-wrap-narrow">
            <div className="hc-card hc-card-quiet">
              <h2 className="hc-h3">Where the project stands</h2>
              <p className="hc-body" style={{ marginTop: 10 }}>
                HealthConnect is being built at the Maroun Semaan Faculty of Engineering and Architecture, American University of
                Beirut. It does not provide medical advice, and it does not recommend substituting one medicine for another.
              </p>
            </div>
          </div>
        </section>

        <CtaSection
          title="Start with what you need."
          lead="Search the connected pharmacy network, or create an account to keep your prescriptions and orders in one place."
          primary={{ href: "/search", label: "Search medications" }}
          secondary={{ href: "/register", label: "Create an account" }}
        />
      </main>

      <SiteFooter />
    </div>
  );
}
