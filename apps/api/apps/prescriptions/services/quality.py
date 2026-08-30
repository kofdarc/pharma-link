"""Server-side legibility gate for an uploaded prescription scan.

Adapted from the beymun CMS photo-quality checks, but for a *document* not a
portrait: no face detection, just "can a pharmacist actually read this". Each
finding carries a severity:

- ``block`` - the upload is refused; nothing is stored and the caller reports why.
- ``warn``  - the upload is accepted; the finding is shown as advice.

**Fail-open is deliberate.** If Pillow is missing, the payload is not a decodable
image (a PDF, most obviously), or any check raises, the result is an empty list -
no findings, therefore no block. A missing optional path or a bug in this file
must never cost a patient their upload; the pharmacy still reviews every scan by
hand before dispensing.

**Only the deterministic arithmetic checks block.** Resolution and exposure are
plain arithmetic over pixels - a 200x150 crop or a mean luma of 12 is unusable
for everybody. Blur is measured with Pillow's 8-bit Laplacian, which clamps the
kernel's negative lobe to zero and so undercounts variance on smooth images;
that bias is toward false "blurry" positives, so blur is advisory only here
rather than a refusal.
"""

import io

SEVERITY_BLOCK = "block"
SEVERITY_WARN = "warn"

# Smallest side, in pixels, worth a pharmacist's time. A modern phone camera
# clears this by an order of magnitude; anything under it is a crop or a
# thumbnail.
MIN_DIMENSION = 200

# Mean luma, 0-255. Measured on phone photos of paper scripts: a normal indoor
# capture sits near 150, a dim one near 55. The upper bound is deliberately high
# - a prescription is mostly white paper, so a perfectly readable bright photo
# can still average 235+; only a genuinely clipped frame with no text left
# crosses 248.
MIN_MEAN_LUMA = 45.0
MAX_MEAN_LUMA = 248.0

# Variance of the (clamped) Laplacian over the greyscale frame. Measured on a
# gaussian-blur ramp of a scanned script: sharp ~900, mild shake ~180,
# unreadable ~40. Used for a soft-focus nudge only - see the module docstring.
SOFT_FOCUS_VARIANCE = 120.0

# "No writing" heuristic - NOT OCR, just "is there ink here". Two signals have to
# agree before we say anything, so a faint pencil script or a sparse two-line Rx
# is never mistaken for a blank frame:
#   - ink fraction: share of pixels distinctly darker than the paper around them.
#     A page of handwriting sits around 1-8%; a wall, a blank sheet or a thumb
#     over the lens is far below 0.2%.
#   - edge activity: mean magnitude of the clamped Laplacian. Text and rules put
#     this well above 2; a featureless surface leaves it near 0.
# Advisory only: the pharmacy still looks at every scan.
INK_DARKER_THAN_PAPER = 40
MIN_INK_FRACTION = 0.002
MIN_EDGE_ACTIVITY = 2.0

_SEVERITIES = {
    "too_small": SEVERITY_BLOCK,
    "too_dark": SEVERITY_BLOCK,
    "too_bright": SEVERITY_BLOCK,
    "soft_focus": SEVERITY_WARN,
    "no_text": SEVERITY_WARN,
}


def _finding(code, message):
    return {"code": code, "message": message, "severity": _SEVERITIES[code]}


def check_scan_bytes(data, *, mime_type=""):
    """Findings about an uploaded scan: a list of {code, message, severity}.

    An empty list means either "the scan looks fine" or "we could not check it"
    - deliberately indistinguishable, because both let the upload through.
    """
    if not data or (mime_type or "").lower() == "application/pdf":
        return []

    try:
        from PIL import Image, ImageFilter, ImageStat
    except Exception:
        return []

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        # Not decodable as an image. The upload path already enforces the
        # format, so say nothing rather than double-reporting.
        return []

    try:
        width, height = image.size
        findings = []

        if min(width, height) < MIN_DIMENSION:
            findings.append(
                _finding(
                    "too_small",
                    f"This image is small ({width}x{height}px) and may be unreadable. "
                    "Move closer or use a higher-resolution photo.",
                )
            )

        grey = image.convert("L")
        mean_luma = ImageStat.Stat(grey).mean[0]
        too_dark = mean_luma < MIN_MEAN_LUMA
        too_bright = mean_luma > MAX_MEAN_LUMA

        # Both the sharpness and the "no writing" checks need an exposed image:
        # on a dark or blown-out frame the exposure finding already says why the
        # pixels carry no detail.
        if not too_dark and not too_bright:
            edges = grey.filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1))
            edge_stat = ImageStat.Stat(edges)
            if edge_stat.var[0] < SOFT_FOCUS_VARIANCE:
                findings.append(
                    _finding("soft_focus", "This photo looks soft. A sharper one is easier for the pharmacy to dispense from.")
                )

            total = width * height
            ink_cut = max(0, int(mean_luma) - INK_DARKER_THAN_PAPER)
            ink_fraction = (sum(grey.histogram()[: ink_cut + 1]) / total) if total else 0.0
            if ink_fraction < MIN_INK_FRACTION and edge_stat.mean[0] < MIN_EDGE_ACTIVITY:
                findings.append(
                    _finding(
                        "no_text",
                        "We couldn't see any writing in this photo. Make sure the whole prescription is in frame, "
                        "filling most of it, and in focus.",
                    )
                )

        if too_dark:
            findings.append(_finding("too_dark", "This photo is too dark to read. Move to better light and try again."))
        elif too_bright:
            findings.append(
                _finding("too_bright", "This photo is washed out by glare. Tilt the paper away from the light and try again.")
            )

        return findings
    except Exception:
        # A check that crashes must never cost someone their upload.
        return []


def blocking(findings):
    """The findings that refuse the scan."""
    return [f for f in findings or [] if f.get("severity") == SEVERITY_BLOCK]


def rejection_message(findings):
    """One message naming every blocking problem, or None if nothing blocks."""
    blockers = blocking(findings)
    if not blockers:
        return None
    return " ".join(f["message"] for f in blockers)


def warnings(findings):
    """The advisory messages, for surfacing on an accepted upload."""
    return [f["message"] for f in findings or [] if f.get("severity") == SEVERITY_WARN]
