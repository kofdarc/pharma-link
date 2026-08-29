# Gates: status-label pill redesign

Scope: replace status-pill containers with the approved plain-text and square-marker treatment across the web app, without changing unrelated rounded controls, and provide readable before/after evidence for affected pages and tabs

- [x] G0: this ledger states outcomes that can fail
  CHECK: node /home/kofdarelli/.codex/skills/unlazy/scripts/gate-lint.mjs GATES.md
  EXPECT: LINT OK
  EVIDENCE: exit 0; LINT OK (2 manual-gate warnings)

- [x] G1: all shared and patient-facing status renderers use the approved metadata treatment while Rx/OTC labels, identifiers, filters, tabs, and buttons retain their existing component treatment
  CHECK: node tools/verify-pill-redesign.mjs
  EXPECT: STATUS LABEL REDESIGN VERIFIED
  EVIDENCE: STATUS LABEL REDESIGN VERIFIED

- [x] G2: the production web application builds successfully after the redesign
  CHECK: pnpm web:build
  EXPECT: Compiled successfully
  EVIDENCE: Next.js compiled successfully, type checking passed, and all 68 static pages generated

- [x] G3: every rendered status element on every affected page and affected tab computes to transparent background, zero radius, zero padding, and a square marker
  EVIDENCE: 36-route seeded-role browser audit found zero pill-style violations and zero unscoped status-like pills

- [ ] G4: every genuinely changed page and affected tab has a clear, authentic before/after comparison
  CHECK: node tools/verify-status-page-screenshots.mjs /home/kofdarelli/.codex/visualizations/2026/08/28/01a04882-600e-71e3-9540-c6c0b3366c61/status-pages
  EXPECT: STATUS PAGE SCREENSHOTS VERIFIED: 36
  EVIDENCE: fresh rendered after-state verification passes for 36 directly edited pages; 22 authentic zoomed before/after comparisons exist; 7 pages with visible fixed statuses have no matching old capture, and empty affected tabs have no visible seeded status to compare

- [x] G5: rendered desktop pages have no relevant console errors, framework overlays, clipping, or broken affected tab interactions
  EVIDENCE: 36-route audit found zero console errors, zero framework overlays, zero login redirects, and zero horizontal-overflow failures
