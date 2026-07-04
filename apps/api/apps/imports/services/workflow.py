from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.imports.models import InventoryImport, InventoryImportRow
from apps.imports.services.parser import ImportParseError, normalize_row, read_rows
from apps.inventory.models import StockMovement
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.services.search import best_catalog_match, normalize_name


def create_import_preview(*, uploaded_file, user):
    inventory_import = InventoryImport.objects.create(
        pharmacy=user.pharmacy,
        uploaded_by=user,
        original_filename=uploaded_file.name,
        status=InventoryImport.Status.UPLOADED,
    )
    try:
        raw_rows = read_rows(uploaded_file)
    except ImportParseError as exc:
        inventory_import.status = InventoryImport.Status.FAILED
        inventory_import.error_summary = str(exc)
        inventory_import.save(update_fields=["status", "error_summary", "updated_at"])
        return inventory_import

    stats = {"total": 0, "valid": 0, "invalid": 0, "matched": 0, "unmatched": 0}
    for index, raw in enumerate(raw_rows, start=2):
        stats["total"] += 1
        try:
            row = normalize_row(raw)
            if not row["medicine_name"]:
                raise ValueError("Medicine name is required.")
            if row["quantity"] is None or row["quantity"] <= 0:
                raise ValueError("Quantity must be greater than zero.")
            if row["selling_price"] is None:
                raise ValueError("Selling price is required for MVP imports.")
            medicine, confidence = best_catalog_match(row["medicine_name"])
            status = InventoryImportRow.Status.VALID_MATCHED if medicine else InventoryImportRow.Status.VALID_UNMATCHED
            stats["valid"] += 1
            stats["matched" if medicine else "unmatched"] += 1
            InventoryImportRow.objects.create(
                inventory_import=inventory_import,
                row_number=index,
                raw_medicine_name=row["medicine_name"],
                normalized_name=normalize_name(row["medicine_name"]),
                matched_medicine=medicine,
                match_confidence=confidence,
                quantity=row["quantity"],
                batch_number=row["batch_number"],
                expiry_date=row["expiry_date"],
                supplier_name=row["supplier_name"],
                purchase_cost=row["purchase_cost"],
                selling_price=row["selling_price"],
                status=status,
                raw_data=raw,
            )
        except Exception as exc:
            stats["invalid"] += 1
            InventoryImportRow.objects.create(
                inventory_import=inventory_import,
                row_number=index,
                raw_medicine_name=str(raw.get("medicine name", "")),
                normalized_name=normalize_name(str(raw.get("medicine name", ""))),
                status=InventoryImportRow.Status.INVALID,
                error_message=str(exc),
                raw_data=raw,
            )

    inventory_import.status = InventoryImport.Status.PARSED
    inventory_import.total_rows = stats["total"]
    inventory_import.valid_rows = stats["valid"]
    inventory_import.invalid_rows = stats["invalid"]
    inventory_import.matched_rows = stats["matched"]
    inventory_import.unmatched_rows = stats["unmatched"]
    inventory_import.save()
    write_audit_log(
        actor_user=user,
        pharmacy=user.pharmacy,
        action="inventory.import_uploaded",
        entity_type="InventoryImport",
        entity_id=inventory_import.id,
        summary=f"Uploaded inventory import with {stats['total']} rows",
        after_data=stats,
    )
    return inventory_import


@transaction.atomic
def confirm_import(*, inventory_import: InventoryImport, user):
    inventory_import = InventoryImport.objects.select_for_update().get(id=inventory_import.id)
    if inventory_import.status != InventoryImport.Status.PARSED:
        raise ValueError("Only parsed imports can be confirmed.")
    created = 0
    skipped = 0
    rows = inventory_import.rows.select_for_update().all()
    for row in rows:
        if row.status != InventoryImportRow.Status.VALID_MATCHED or not row.matched_medicine_id:
            row.status = InventoryImportRow.Status.SKIPPED
            row.save(update_fields=["status", "updated_at"])
            skipped += 1
            continue
        create_inventory_batch(
            user=user,
            pharmacy=inventory_import.pharmacy,
            movement_type=StockMovement.MovementType.IMPORT,
            data={
                "medicine": row.matched_medicine,
                "batch_number": row.batch_number,
                "initial_quantity": row.quantity,
                "expiry_date": row.expiry_date,
                "supplier_name": row.supplier_name,
                "purchase_cost": row.purchase_cost,
                "selling_price": row.selling_price,
            },
        )
        row.status = InventoryImportRow.Status.IMPORTED
        row.save(update_fields=["status", "updated_at"])
        created += 1
    inventory_import.status = InventoryImport.Status.CONFIRMED
    inventory_import.created_count = created
    inventory_import.skipped_count = skipped
    inventory_import.confirmed_at = timezone.now()
    inventory_import.save()
    write_audit_log(
        actor_user=user,
        pharmacy=inventory_import.pharmacy,
        action="inventory.import_confirmed",
        entity_type="InventoryImport",
        entity_id=inventory_import.id,
        summary=f"Confirmed import: {created} created, {skipped} skipped",
        after_data={"created": created, "skipped": skipped},
    )
    return inventory_import

