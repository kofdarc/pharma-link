from __future__ import annotations

from django.db import transaction

from apps.audit.services import write_audit_log
from apps.inventory.models import InventoryBatch, StockMovement


@transaction.atomic
def create_inventory_batch(*, user, pharmacy, data: dict, movement_type=StockMovement.MovementType.MANUAL_ADJUSTMENT) -> InventoryBatch:
    initial_quantity = int(data.get("initial_quantity", data.get("current_quantity", 0)) or 0)
    if initial_quantity < 0:
        raise ValueError("Quantity cannot be negative.")
    batch = InventoryBatch.objects.create(
        pharmacy=pharmacy,
        medicine=data["medicine"],
        batch_number=data.get("batch_number", ""),
        initial_quantity=initial_quantity,
        current_quantity=initial_quantity,
        expiry_date=data.get("expiry_date"),
        supplier_name=data.get("supplier_name", ""),
        purchase_cost=data.get("purchase_cost"),
        selling_price=data["selling_price"],
        low_stock_threshold=data.get("low_stock_threshold", 5),
        public_availability_enabled=data.get("public_availability_enabled", True),
        is_archived=data.get("is_archived", False),
        created_by=user,
        updated_by=user,
    )
    StockMovement.objects.create(
        pharmacy=pharmacy,
        inventory_batch=batch,
        medicine=batch.medicine,
        movement_type=movement_type,
        quantity_delta=initial_quantity,
        quantity_before=0,
        quantity_after=initial_quantity,
        reason="Initial stock",
        created_by=user,
    )
    write_audit_log(
        actor_user=user,
        pharmacy=pharmacy,
        action="inventory.batch_created",
        entity_type="InventoryBatch",
        entity_id=batch.id,
        summary=f"Created stock batch for {batch.medicine}",
        after_data={"current_quantity": batch.current_quantity},
    )
    return batch


@transaction.atomic
def adjust_stock(*, batch_id, user, quantity_delta: int, reason: str = "", movement_type=StockMovement.MovementType.MANUAL_ADJUSTMENT, sale=None) -> InventoryBatch:
    batch = InventoryBatch.objects.select_for_update().get(id=batch_id)
    if user.is_pharmacy_user and batch.pharmacy_id != user.pharmacy_id:
        raise PermissionError("Cannot adjust stock for another pharmacy.")
    before = batch.current_quantity
    after = before + int(quantity_delta)
    if after < 0:
        raise ValueError("Quantity cannot become negative.")
    batch.current_quantity = after
    batch.updated_by = user
    batch.save(update_fields=["current_quantity", "updated_by", "updated_at"])
    StockMovement.objects.create(
        pharmacy=batch.pharmacy,
        inventory_batch=batch,
        medicine=batch.medicine,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        sale=sale,
        created_by=user,
    )
    write_audit_log(
        actor_user=user,
        pharmacy=batch.pharmacy,
        action="inventory.stock_adjusted",
        entity_type="InventoryBatch",
        entity_id=batch.id,
        summary=f"Adjusted {batch.medicine} by {quantity_delta}",
        before_data={"current_quantity": before},
        after_data={"current_quantity": after},
    )
    return batch

