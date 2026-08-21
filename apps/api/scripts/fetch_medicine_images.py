#!/usr/bin/env python3
"""
Fetch medicine images from Bing Images for medicines that don't have one.

Usage:
    python fetch_medicine_images.py --batch-id 0 --num-batches 8
    python fetch_medicine_images.py --medicine-ids uuid1 uuid2 uuid3
    python fetch_medicine_images.py --all
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from apps.medicines.models import Medicine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

MEDIA_DIR = Path(settings.PUBLIC_MEDIA_ROOT) / "medicines"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

BING_IMAGES_URL = "https://www.bing.com/images/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_WIDTH = 100
MIN_HEIGHT = 100
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def build_search_query(medicine: Medicine) -> str:
    parts = [medicine.brand_name]
    if medicine.strength:
        parts.append(medicine.strength)
    if medicine.form:
        parts.append(medicine.form)
    if medicine.manufacturer:
        parts.append(medicine.manufacturer)
    return " ".join(parts) + " medicine"


def search_bing_images(query: str, session: requests.Session) -> list[str]:
    """Search Bing Images and return a list of full-size image URLs."""
    params = {"q": query, "form": "HDRSC3"}
    try:
        resp = session.get(BING_IMAGES_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Bing search failed for '{query}': {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    image_urls = []

    # Primary: extract original image URLs from a.iusc elements (JSON in 'm' attribute)
    for a_tag in soup.find_all("a", class_="iusc"):
        m_attr = a_tag.get("m")
        if m_attr:
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
                murls = re.findall(r'"murl":"(https?://[^"]+)"', script.string)
                for u in murls:
                    image_urls.append(u)
                break

    # Fallback: extract from img tags with data-src (Bing thumbnail CDN)
    if not image_urls:
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if src.startswith("http") and "bing.net/th" in src:
                # Try to get a larger version
                large_url = re.sub(r"&w=\d+&h=\d+", "&w=800&h=800", src)
                image_urls.append(large_url)

    # Deduplicate
    seen = set()
    unique = []
    for url in image_urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)

    return unique[:10]


def download_and_convert_image(image_url: str, session: requests.Session) -> tuple[io.BytesIO, str] | None:
    try:
        resp = session.get(image_url, headers=HEADERS, timeout=15, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "html" in content_type or "text" in content_type:
            return None

        data = resp.content
        if len(data) > MAX_IMAGE_BYTES or len(data) < 1000:
            return None

        img = Image.open(io.BytesIO(data))
        img.load()

        if img.width < MIN_WIDTH or img.height < MIN_HEIGHT:
            return None

        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        max_dim = 1200
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        output = io.BytesIO()
        img.save(output, format="WEBP", quality=80, method=4)
        output.seek(0)
        return output, "webp"

    except Exception as e:
        logger.debug(f"Failed to download/convert {image_url}: {e}")
        return None


def fetch_image_for_medicine(medicine: Medicine, session: requests.Session, delay: float = 1.0) -> bool:
    query = build_search_query(medicine)
    logger.info(f"[{medicine.brand_name}] Searching: {query}")

    image_urls = search_bing_images(query, session)
    if not image_urls:
        logger.warning(f"[{medicine.brand_name}] No image URLs found")
        return False

    for url in image_urls:
        result = download_and_convert_image(url, session)
        if result:
            image_data, ext = result
            filename = f"{medicine.pk}.{ext}"
            filepath = MEDIA_DIR / filename

            with open(filepath, "wb") as f:
                f.write(image_data.read())

            medicine.image = f"medicines/{filename}"
            medicine.save(update_fields=["image"])
            logger.info(f"[{medicine.brand_name}] Saved: {filename}")
            return True

        time.sleep(0.3)

    logger.warning(f"[{medicine.brand_name}] All {len(image_urls)} candidates failed")
    return False


def get_medicines_without_images() -> list[Medicine]:
    return list(Medicine.objects.filter(image="", is_active=True).order_by("brand_name"))


def main():
    parser = argparse.ArgumentParser(description="Fetch medicine images from Bing Images")
    parser.add_argument("--batch-id", type=int, help="Batch index (0-based)")
    parser.add_argument("--num-batches", type=int, help="Total number of batches")
    parser.add_argument("--medicine-ids", nargs="+", help="Specific medicine UUIDs to process")
    parser.add_argument("--batch-file", type=str, help="File with one medicine UUID per line")
    parser.add_argument("--all", action="store_true", help="Process all medicines without images")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between searches (seconds)")
    parser.add_argument("--log-file", type=str, help="Also write results to a log file")
    args = parser.parse_args()

    if args.log_file:
        fh = logging.FileHandler(args.log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

    if args.medicine_ids:
        medicines = [Medicine.objects.get(pk=pid) for pid in args.medicine_ids]
    elif args.batch_file:
        with open(args.batch_file) as f:
            ids = [line.strip() for line in f if line.strip()]
        medicines = [Medicine.objects.get(pk=pid) for pid in ids]
    elif args.all:
        medicines = get_medicines_without_images()
    elif args.batch_id is not None and args.num_batches:
        all_meds = get_medicines_without_images()
        batch_size = len(all_meds) // args.num_batches
        start = args.batch_id * batch_size
        end = start + batch_size if args.batch_id < args.num_batches - 1 else len(all_meds)
        medicines = all_meds[start:end]
    else:
        logger.error("Specify --all, --medicine-ids, or --batch-id/--num-batches")
        sys.exit(1)

    logger.info(f"Processing {len(medicines)} medicines")

    session = requests.Session()
    success = 0
    failed = 0
    failed_names = []

    for i, med in enumerate(medicines):
        try:
            if fetch_image_for_medicine(med, session, delay=args.delay):
                success += 1
            else:
                failed += 1
                failed_names.append(med.brand_name)
        except Exception as e:
            logger.error(f"[{med.brand_name}] Unexpected error: {e}")
            failed += 1
            failed_names.append(med.brand_name)

        if (i + 1) % 10 == 0:
            logger.info(f"Progress: {i + 1}/{len(medicines)} (success={success}, failed={failed})")

        time.sleep(args.delay)

    logger.info(f"Done! Success: {success}, Failed: {failed}")
    if failed_names:
        logger.info(f"Failed medicines ({len(failed_names)}): {', '.join(failed_names[:50])}")


if __name__ == "__main__":
    main()
