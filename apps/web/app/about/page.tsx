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
