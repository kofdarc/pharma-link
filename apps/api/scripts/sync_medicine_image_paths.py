#!/usr/bin/env python3
"""Sync local Medicine.image values from UUID-named objects in an S3 prefix.

The bucket object::

    product-images/medicines/<medicine-uuid>.webp

is stored in the database as::

    medicines/<medicine-uuid>.webp

Usage:
    python scripts/sync_medicine_image_paths.py \
        --bucket pharmalink-423401347463-eu-central-1-an \
        --region eu-central-1 --apply
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from uuid import UUID

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import transaction

from apps.medicines.models import Medicine


DEFAULT_PREFIX = "product-images/medicines/"
SUPPORTED_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}
EXTENSION_PRIORITY = {".webp": 0, ".avif": 1, ".png": 2, ".jpg": 3, ".jpeg": 4}


def medicine_id_from_key(key: str, prefix: str) -> UUID | None:
    if not key.startswith(prefix):
        return None
    relative = PurePosixPath(key.removeprefix(prefix))
    if len(relative.parts) != 1 or relative.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None
    try:
        return UUID(relative.stem)
    except ValueError:
        return None


def list_image_keys(bucket: str, prefix: str, region: str, unsigned: bool) -> dict[UUID, str]:
    config = Config(signature_version=UNSIGNED) if unsigned else None
    client = boto3.client("s3", region_name=region or None, config=config)
    paginator = client.get_paginator("list_objects_v2")
    matches: dict[UUID, str] = {}

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            medicine_id = medicine_id_from_key(key, prefix)
            if medicine_id is None:
                continue
            current = matches.get(medicine_id)
            if current is None or EXTENSION_PRIORITY[PurePosixPath(key).suffix.lower()] < EXTENSION_PRIORITY[PurePosixPath(current).suffix.lower()]:
                matches[medicine_id] = key

    return matches


def probe_webp_keys(bucket: str, prefix: str, region: str, medicine_ids: list[UUID], workers: int) -> dict[UUID, str]:
    """Find UUID-named WebP objects when the bucket permits reads but not listing."""
    client = boto3.client(
        "s3",
        region_name=region or None,
        config=Config(signature_version=UNSIGNED, max_pool_connections=workers, retries={"max_attempts": 2}),
    )

    def existing_key(medicine_id: UUID) -> tuple[UUID, str] | None:
        key = f"{prefix}{medicine_id}.webp"
        try:
            client.head_object(Bucket=bucket, Key=key)
            return medicine_id, key
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status in {403, 404}:
                return None
            raise

    matches: dict[UUID, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for result in executor.map(existing_key, medicine_ids):
            if result is not None:
                matches[result[0]] = result[1]
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill local Medicine.image fields from UUID-named S3 objects.")
    parser.add_argument("--bucket", required=True, help="S3 bucket name (not an s3:// URI)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help=f"Object prefix (default: {DEFAULT_PREFIX})")
    parser.add_argument("--region", default="", help="AWS region, for example eu-central-1")
    parser.add_argument("--unsigned", action="store_true", help="List a publicly listable bucket without AWS credentials")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Probe <UUID>.webp for each local medicine instead of listing the bucket; no credentials required",
    )
    parser.add_argument("--workers", type=int, default=32, help="Concurrent S3 requests used with --probe (default: 32)")
    parser.add_argument("--overwrite", action="store_true", help="Replace image paths that are already populated")
    parser.add_argument("--apply", action="store_true", help="Write changes; without this flag the command is a dry run")
    args = parser.parse_args()

    prefix = args.prefix.strip("/") + "/"
    local_ids = list(Medicine.objects.values_list("id", flat=True))
    if args.probe:
        keys_by_id = probe_webp_keys(args.bucket, prefix, args.region, local_ids, max(1, args.workers))
    else:
        keys_by_id = list_image_keys(args.bucket, prefix, args.region, args.unsigned)
    medicines = Medicine.objects.in_bulk(keys_by_id.keys())
    updates: list[Medicine] = []
    skipped_existing = 0

    for medicine_id, key in keys_by_id.items():
        medicine = medicines.get(medicine_id)
        if medicine is None:
            continue
        if medicine.image and not args.overwrite:
            skipped_existing += 1
            continue
        medicine.image = key.removeprefix("product-images/")
        updates.append(medicine)

    print(f"S3 image objects matched by UUID: {len(keys_by_id)}")
    print(f"Matching medicines in local database: {len(medicines)}")
    print(f"Existing image paths skipped: {skipped_existing}")
    print(f"Medicine image paths to update: {len(updates)}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to update the local database.")
        return 0

    with transaction.atomic():
        Medicine.objects.bulk_update(updates, ["image"], batch_size=500)
    print(f"Updated {len(updates)} local medicine records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
