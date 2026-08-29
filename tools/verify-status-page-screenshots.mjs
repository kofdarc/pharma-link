import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";

const outputDir = process.argv[2];
if (!outputDir) throw new Error("Usage: node tools/verify-status-page-screenshots.mjs <output-dir>");

const manifest = JSON.parse(await readFile(new URL("./status-page-screenshot-manifest.json", import.meta.url), "utf8"));
const report = JSON.parse(await readFile(path.join(outputDir, "audit-report.json"), "utf8"));
const pngs = (await readdir(outputDir)).filter((name) => name.endsWith(".png") && !name.startsWith("contact-sheet"));

if (manifest.length !== 36) throw new Error(`Expected 36 edited pages, manifest has ${manifest.length}`);
if (report.length !== manifest.length) throw new Error(`Expected ${manifest.length} audit rows, found ${report.length}`);

for (const expected of manifest) {
  const row = report.find((item) => item.source === expected.source);
  if (!row) throw new Error(`Missing audit row for ${expected.source}`);
  if (row.file !== expected.file) throw new Error(`Unexpected screenshot filename for ${expected.source}`);
  if (row.finalPath === "/login") throw new Error(`${expected.source} redirected to login`);
  if (row.frameworkOverlay) throw new Error(`${expected.source} rendered a framework overlay`);
  if (row.horizontalOverflow) throw new Error(`${expected.source} has horizontal overflow`);
  if (row.pillViolations.length) throw new Error(`${expected.source} has pill-shaped status labels: ${row.pillViolations.join(", ")}`);
  if (row.suspiciousPills.length) throw new Error(`${expected.source} has unscoped status-like pills: ${row.suspiciousPills.join(", ")}`);
  if (row.consoleErrors.length) throw new Error(`${expected.source} logged console errors: ${row.consoleErrors.join(" | ")}`);

  const image = await readFile(path.join(outputDir, expected.file));
  if (image.subarray(1, 4).toString("ascii") !== "PNG") throw new Error(`${expected.file} is not a PNG`);
  if ((await stat(path.join(outputDir, expected.file))).size < 5000) throw new Error(`${expected.file} is unexpectedly small`);
}

if (pngs.length !== manifest.length) throw new Error(`Expected exactly ${manifest.length} page PNGs, found ${pngs.length}`);
console.log(`STATUS PAGE SCREENSHOTS VERIFIED: ${manifest.length}`);
