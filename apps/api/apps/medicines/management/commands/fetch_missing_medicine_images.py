"""
Fetch product images for medicines that are missing one.

Designed to run locally AND as a one-off ECS task in prod. In prod (USE_S3=True),
django-storages writes each image directly to the product-images S3 prefix and
stores the storage-relative path in Medicine.image. Locally it writes to the
public media root on disk.

    python manage.py fetch_missing_medicine_images --limit 10          # quick test
    python manage.py fetch_missing_medicine_images                     # all missing
    python manage.py fetch_missing_medicine_images --dry-run           # report only
    python manage.py fetch_missing_medicine_images --abort-after 20    # stop on streak

Natural resume: every successful save sets Medicine.image, so re-running
simply picks up the remaining records. No checkpoint file needed.
"""

from __future__ import annotations

import io
import json
import logging
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import models
from PIL import Image

from apps.medicines.models import Medicine, ProductCategory

logger = logging.getLogger(__name__)

BING_IMAGES_URL = "https://www.bing.com/images/search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_WIDTH = 100
MIN_HEIGHT = 100
MAX_IMAGE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = 20


def _build_search_query(medicine: Medicine) -> str:
    parts = [medicine.brand_name]
    if medicine.strength:
        parts.append(medicine.strength)
    if medicine.form:
        parts.append(medicine.form)
    if medicine.manufacturer:
        parts.append(medicine.manufacturer)
    return " ".join(parts) + " medicine"


def _search_bing_images(query: str) -> list[str]:
    """Return up to 10 full-size image URLs from a Bing Images search."""
    url = f"{BING_IMAGES_URL}?{urlencode({'q': query, 'form': 'HDRSC3'})}"
    req = Request(url, headers=_HEADERS)
    with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(html, "html.parser")
    image_urls: list[str] = []

    # Primary: extract original image URLs from a.iusc elements (JSON in 'm' attr)
    for a_tag in soup.find_all("a", class_="iusc"):
        m_attr = a_tag.get("m")
        if not m_attr:
            continue
        try:
            data = json.loads(m_attr)
            murl = data.get("murl", "")
            if murl and murl.startswith("http"):
                image_urls.append(murl)
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: extract murl from script tags
    if not image_urls:
        for script in soup.find_all("script"):
            if script.string and "murl" in str(script.string):
                image_urls = re.findall(r'"murl":"(https?://[^"]+)"', script.string)
                break

    # Deduplicate, keep order
    seen: set[str] = set()
    unique: list[str] = []
    for u in image_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:10]


def _download_and_convert(image_url: str) -> tuple[bytes, str] | None:
    """Download an image, convert to RGB WebP, return (bytes, 'webp') or None."""
    req = Request(image_url, headers=_HEADERS)
    with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        content_type = resp.headers.get("Content-Type", "")
        if "html" in content_type or "text" in content_type:
            return None
        data = resp.read()

    if len(data) > MAX_IMAGE_BYTES or len(data) < 1000:
        return None

    img = Image.open(io.BytesIO(data))
    img.load()

    if img.width < MIN_WIDTH or img.height < MIN_HEIGHT:
        return None

    # Flatten alpha onto white background
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    max_dim = 1200
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=80, method=4)
    return buf.getvalue(), "webp"


def _fetch_one(medicine: Medicine, *, delay: float = 1.5) -> bool:
    """Try to find and save an image for one medicine. Returns True on success."""
    query = _build_search_query(medicine)
    logger.info("[%s] Searching: %s", medicine.brand_name, query)

    image_urls = _search_bing_images(query)
    if not image_urls:
        logger.warning("[%s] No image URLs found", medicine.brand_name)
        return False

    for url in image_urls:
        try:
            result = _download_and_convert(url)
        except Exception as exc:
            logger.debug("[%s] Download failed %s: %s", medicine.brand_name, url, exc)
            result = None

        if result is None:
            time.sleep(0.3)
            continue

        image_bytes, ext = result
        filename = f"{medicine.pk}.{ext}"
        medicine.image.save(filename, ContentFile(image_bytes), save=True)
        logger.info("[%s] Saved: %s", medicine.brand_name, filename)
        return True

    logger.warning("[%s] All %d candidates failed", medicine.brand_name, len(image_urls))
    return False


class Command(BaseCommand):
    help = (
        "Fetch product images from Bing for medicines that are missing one. "
        "In prod (USE_S3=True) images are written directly to S3; locally to disk."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Max medicines to process this run.")
        parser.add_argument("--delay", type=float, default=1.5, help="Seconds between Bing searches (default: 1.5).")
        parser.add_argument("--abort-after", type=int, default=50, help="Stop after N consecutive failures (0 disables, default: 50).")
        parser.add_argument("--dry-run", action="store_true", help="List candidates without downloading or saving.")
        parser.add_argument(
            "--category",
            choices=[c.value for c in ProductCategory],
            help="Only process medicines in this category (e.g. SUPPLEMENT).",
        )
        parser.add_argument(
            "--brand-contains",
            help="Only process medicines whose brand_name contains this substring (case-insensitive).",
        )

    def handle(self, *args, **options):
        queryset = Medicine.objects.filter(
            (models.Q(image="") | models.Q(image__isnull=True)),
            is_active=True,
        )
        if options["category"]:
            queryset = queryset.filter(category=options["category"])
        if options["brand_contains"]:
            queryset = queryset.filter(brand_name__icontains=options["brand_contains"])
        medicines = list(queryset.order_by("brand_name"))

        if options["limit"]:
            medicines = medicines[: options["limit"]]

        self.stdout.write(self.style.NOTICE(f"Candidates: {len(medicines)}"))

        if options["dry_run"]:
            for med in medicines:
                self.stdout.write(f"  would fetch image for: {med.brand_name} ({med.pk})")
            return

        delay = options["delay"]
        abort_after = options["abort_after"]
        success = 0
        failed = 0
        consecutive_failures = 0

        for i, med in enumerate(medicines, 1):
            try:
                if _fetch_one(med, delay=delay):
                    success += 1
                    consecutive_failures = 0
                else:
                    failed += 1
                    consecutive_failures += 1
            except Exception as exc:
                logger.error("[%s] Unexpected error: %s", med.brand_name, exc)
                failed += 1
                consecutive_failures += 1

            if abort_after and consecutive_failures >= abort_after:
                self.stderr.write(
                    self.style.ERROR(
                        f"Aborting after {consecutive_failures} consecutive failures "
                        f"({i}/{len(medicines)} processed). Re-run to resume."
                    )
                )
                break

            if i % 10 == 0:
                self.stdout.write(f"Progress: {i}/{len(medicines)} (success={success}, failed={failed})")

            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(f"Done. success={success}, failed={failed}, total_attempted={success+failed}"))
