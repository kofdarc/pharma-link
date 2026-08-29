/**
 * Instant, in-browser legibility feedback on a prescription photo, before it is
 * uploaded. Advisory only: the API re-runs the real check (see
 * apps/api/apps/prescriptions/services/quality.py) and is the only authority.
 * Nothing here blocks a submit.
 *
 * Adapted from the beymun CMS `photo_check.js`, minus the face-detection half:
 * a prescription is a document, so the useful signals are resolution, exposure
 * and sharpness. Thresholds are kept in step with the server module so the two
 * layers never contradict each other in front of the patient.
 */

export type ScanSeverity = "block" | "warn";

export interface ScanFinding {
  code: string;
  message: string;
  severity: ScanSeverity;
}

const MIN_DIMENSION = 600;
const MIN_MEAN_LUMA = 45;
const MAX_MEAN_LUMA = 248;
const SOFT_FOCUS_VARIANCE = 120;

// "No writing" heuristic - not OCR, just "is there ink here". Kept in step with
// the server's quality.py: two signals must agree, so a faint or sparse
// prescription is never mistaken for a blank frame.
const INK_DARKER_THAN_PAPER = 40;
const MIN_INK_FRACTION = 0.002;
const MIN_EDGE_ACTIVITY = 2.0;

/** Findings about a picked file. Empty means "looks fine" or "could not check" -
 * both let the upload proceed. PDFs are never inspected here. */
export async function inspectScan(file: File): Promise<ScanFinding[]> {
  if (typeof document === "undefined") return [];
  if (!file || !file.type.startsWith("image/")) return [];

  const url = URL.createObjectURL(file);
  try {
    const image = await loadImage(url);
    const findings: ScanFinding[] = [];

    if (Math.min(image.naturalWidth, image.naturalHeight) < MIN_DIMENSION) {
      findings.push({
        code: "too_small",
        severity: "block",
        message: `This image is small (${image.naturalWidth}×${image.naturalHeight}px) and may be unreadable. Move closer or use a higher-resolution photo.`
      });
    }

    const grey = toGreyscale(image);
    if (!grey) return findings;

    const mean = meanLuma(grey.data);
    const tooDark = mean < MIN_MEAN_LUMA;
    const tooBright = mean > MAX_MEAN_LUMA;

    if (!tooDark && !tooBright) {
      const edge = laplacianStats(grey);
      if (edge.variance < SOFT_FOCUS_VARIANCE) {
        findings.push({
          code: "soft_focus",
          severity: "warn",
          message: "This photo looks soft. A sharper one is easier for the pharmacy to dispense from."
        });
      }
      if (inkFraction(grey.data, mean) < MIN_INK_FRACTION && edge.meanAbs < MIN_EDGE_ACTIVITY) {
        findings.push({
          code: "no_text",
          severity: "warn",
          message:
            "We couldn't see any writing in this photo. Make sure the whole prescription is in frame, filling most of it, and in focus."
        });
      }
    }

    if (tooDark) {
      findings.push({ code: "too_dark", severity: "block", message: "This photo is too dark to read. Move to better light and try again." });
    } else if (tooBright) {
      findings.push({
        code: "too_bright",
        severity: "block",
        message: "This photo is washed out by glare. Tilt the paper away from the light and try again."
      });
    }

    return findings;
  } catch {
    return [];
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function blockingFindings(findings: ScanFinding[]): ScanFinding[] {
  return findings.filter((f) => f.severity === "block");
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("not decodable"));
    img.src = url;
  });
}

interface Grey {
  data: Float64Array;
  width: number;
  height: number;
}

/** Rec.601 luma on a canvas downscaled so the work is bounded regardless of
 * how large the phone photo is. */
function toGreyscale(image: HTMLImageElement): Grey | null {
  const longest = Math.max(image.naturalWidth, image.naturalHeight);
  const scale = longest > 1024 ? 1024 / longest : 1;
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, width, height);

  let pixels: Uint8ClampedArray;
  try {
    pixels = context.getImageData(0, 0, width, height).data;
  } catch {
    return null;
  }

  const data = new Float64Array(width * height);
  for (let i = 0, p = 0; i < pixels.length; i += 4, p += 1) {
    data[p] = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
  }
  return { data, width, height };
}

function meanLuma(data: Float64Array): number {
  let total = 0;
  for (let i = 0; i < data.length; i += 1) total += data[i];
  return total / data.length;
}

/** Share of pixels distinctly darker than the paper - a proxy for "ink". */
function inkFraction(data: Float64Array, mean: number): number {
  const cut = mean - INK_DARKER_THAN_PAPER;
  let ink = 0;
  for (let i = 0; i < data.length; i += 1) if (data[i] < cut) ink += 1;
  return data.length ? ink / data.length : 0;
}

/** Variance and mean magnitude of a 3x3 Laplacian over the interior pixels. */
function laplacianStats(grey: Grey): { variance: number; meanAbs: number } {
  const { data, width, height } = grey;
  let sum = 0;
  let sumSquares = 0;
  let sumAbs = 0;
  let count = 0;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const i = y * width + x;
      const value = data[i - width] + data[i + width] + data[i - 1] + data[i + 1] - 4 * data[i];
      sum += value;
      sumSquares += value * value;
      sumAbs += Math.abs(value);
      count += 1;
    }
  }
  if (!count) return { variance: Number.POSITIVE_INFINITY, meanAbs: Number.POSITIVE_INFINITY };
  const mean = sum / count;
  return { variance: sumSquares / count - mean * mean, meanAbs: sumAbs / count };
}
