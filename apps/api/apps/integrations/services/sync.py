"""
Inbound sync from a pharmacy's existing software.

Design goals, in priority order:
  1. No data cleanup required on their side. They post THEIR product codes and quantities;
     SkuMapping absorbs the difference. Unmatched codes are recorded, not rejected, so a
     first sync never fails wholesale.
  2. Idempotent. The same idempotency key returns the first result instead of double-applying,
     which matters because a connector on a flaky ADSL line will retry.
  3. Absolute stock levels, not deltas. A POS is the source of truth for its own shelf; we
     reconcile to the number it reports and write a CORRECTION movement for the difference,
     so the stock ledger still explains every change.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.integrations.models import SkuMapping, SyncRun
from apps.inventory.models import InventoryBatch, ReservationShortfall, StockMovement
from apps.inventory.services.stock import adjust_stock, create_inventory_batch, flag_reservation_shortfall
from apps.medicines.services.search import best_catalog_match

SYNC_BATCH_LABEL = "POS-SYNC"


def resolve_mapping(*, pharmacy, external_code: str, external_name: str = "") -> SkuMapping:
    """Finds or creates the mapping for a pharmacy's own code, auto-matching where confident."""
    mapping = SkuMapping.objects.filter(pharmacy=pharmacy, external_code__iexact=external_code).first()
    if mapping is None:
        medicine, confidence = best_catalog_match(external_name or external_code)
        if medicine and confidence >= 1:
            method = SkuMapping.MatchMethod.AUTO_EXACT
        elif medicine:
            method = SkuMapping.MatchMethod.AUTO_FUZZY
        else:
            method = SkuMapping.MatchMethod.UNMATCHED
        mapping = SkuMapping.objects.create(
            pharmacy=pharmacy,
            external_code=external_code,
            external_name=external_name,
            medicine=medicine,
            match_method=method,
            match_confidence=Decimal(str(confidence)),
        )
    elif external_name and mapping.external_name != external_name:
        mapping.external_name = external_name
        mapping.save(update_fields=["external_name", "updated_at"])

    mapping.last_seen_at = timezone.now()
    mapping.save(update_fields=["last_seen_at", "updated_at"])
    return mapping


def _decimal_or_none(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


@transaction.atomic
def sync_stock(*, pharmacy, user, rows: list[dict], integration_key=None, idempotency_key: str) -> SyncRun:
    existing = SyncRun.objects.filter(pharmacy=pharmacy, idempotency_key=idempotency_key).first()
    if existing:
        existing.status = SyncRun.Status.REPLAYED
        return existing

    applied = unmapped = failed = 0
    details = []
    shortfall_ids = []
    observed_at = timezone.now()

    for row in rows:
        code = str(row.get("external_code") or "").strip()
        if not code:
            failed += 1
            details.append({"external_code": "", "result": "failed", "reason": "Missing external_code."})
            continue

        mapping = resolve_mapping(pharmacy=pharmacy, external_code=code, external_name=str(row.get("name") or ""))
        if mapping.is_ignored:
            details.append({"external_code": code, "result": "ignored"})
            continue
        if mapping.medicine_id is None:
            unmapped += 1
            details.append({"external_code": code, "result": "unmapped", "reason": "Needs a one-time mapping in the pharmacy workspace."})
            continue

        try:
            target_quantity = int(row["quantity"])
        except (KeyError, TypeError, ValueError):
            failed += 1
            details.append({"external_code": code, "result": "failed", "reason": "Quantity must be a whole number."})
            continue
        if target_quantity < 0:
            failed += 1
            details.append({"external_code": code, "result": "failed", "reason": "Quantity cannot be negative."})
            continue

        selling_price = _decimal_or_none(row.get("selling_price"))
        medicine = mapping.medicine
        if medicine.is_price_regulated:
            # MoPH price wins over whatever the POS believes.
            selling_price = medicine.regulated_price

        batch = (
            InventoryBatch.objects.select_for_update()
            .filter(pharmacy=pharmacy, medicine=medicine, batch_number=SYNC_BATCH_LABEL, is_archived=False)
            .first()
        )
        if batch is None:
            if selling_price is None:
                failed += 1
                details.append({"external_code": code, "result": "failed", "reason": "First sync of an item needs selling_price."})
                continue
            new_batch = create_inventory_batch(
                user=user,
                pharmacy=pharmacy,
                movement_type=StockMovement.MovementType.IMPORT,
                data={
                    "medicine": medicine,
                    "batch_number": SYNC_BATCH_LABEL,
                    "initial_quantity": target_quantity,
                    "expiry_date": row.get("expiry_date") or None,
                    "supplier_name": str(row.get("supplier_name") or ""),
                    "purchase_cost": _decimal_or_none(row.get("purchase_cost")),
                    "selling_price": selling_price,
                    "low_stock_threshold": int(row.get("low_stock_threshold") or 5),
                },
            )
            new_batch.last_pos_observed_at = observed_at
            new_batch.save(update_fields=["last_pos_observed_at"])
            applied += 1
            details.append({"external_code": code, "result": "created", "quantity": target_quantity})
            continue

        # This sync confirms the quantity regardless of whether it changed, so freshness
        # is always refreshed here - a POS reporting "still 12" is still a live observation.
        update_fields = ["last_pos_observed_at", "updated_at"]
        batch.last_pos_observed_at = observed_at
        if selling_price is not None and selling_price != batch.selling_price:
            batch.selling_price = selling_price
            update_fields.append("selling_price")
        batch.save(update_fields=update_fields)

        delta = target_quantity - batch.current_quantity
        if delta != 0:
            adjust_stock(
                batch_id=batch.id,
                user=user,
                quantity_delta=delta,
                reason=f"POS sync to absolute level {target_quantity}",
                movement_type=StockMovement.MovementType.CORRECTION,
            )

        detail_row = {"external_code": code, "result": "updated", "delta": delta, "quantity": target_quantity}
        shortfall = flag_reservation_shortfall(batch=batch, observed_on_hand=target_quantity)
        if shortfall is not None:
            shortfall_ids.append(shortfall.id)
            detail_row["reservation_shortfall_units"] = shortfall.shortfall_units

        applied += 1
        details.append(detail_row)

    run = SyncRun.objects.create(
        pharmacy=pharmacy,
        integration_key=integration_key,
        kind=SyncRun.Kind.STOCK,
        status=SyncRun.Status.PARTIAL if (unmapped or failed) else SyncRun.Status.APPLIED,
        idempotency_key=idempotency_key,
        rows_received=len(rows),
        rows_applied=applied,
        rows_unmapped=unmapped,
        rows_failed=failed,
        response_payload={"details": details[:500]},
    )
    if shortfall_ids:
        ReservationShortfall.objects.filter(id__in=shortfall_ids).update(sync_run=run)
    write_audit_log(
        actor_user=user,
        pharmacy=pharmacy,
        action="integrations.stock_synced",
        entity_type="SyncRun",
        entity_id=run.id,
        summary=f"POS stock sync: {applied} applied, {unmapped} unmapped, {failed} failed",
        after_data={"applied": applied, "unmapped": unmapped, "failed": failed},
    )
    return run


@transaction.atomic
def sync_sales(*, pharmacy, user, rows: list[dict], integration_key=None, idempotency_key: str) -> SyncRun:
    """
    Sales pushed from the till. Recorded as HealthConnect sales so analytics see the whole
    business, not just what happened through the platform.
    """
    existing = SyncRun.objects.filter(pharmacy=pharmacy, idempotency_key=idempotency_key).first()
    if existing:
        existing.status = SyncRun.Status.REPLAYED
        return existing

    from apps.sales.models import Sale
    from apps.sales.services.create_sale import create_sale

    applied = unmapped = failed = 0
    details = []
    for row in rows:
        lines = row.get("items") or []
        resolved = []
        blocked = False
        for line in lines:
            mapping = resolve_mapping(pharmacy=pharmacy, external_code=str(line.get("external_code") or ""), external_name=str(line.get("name") or ""))
            if mapping.medicine_id is None:
                unmapped += 1
                blocked = True
                break
            resolved.append({"medicine": mapping.medicine_id, "quantity": int(line.get("quantity") or 1), "unit_price": _decimal_or_none(line.get("unit_price"))})
        if blocked or not resolved:
            details.append({"external_reference": row.get("reference", ""), "result": "unmapped"})
            continue
        try:
            sale = create_sale(
                user=user,
                pharmacy=pharmacy,
                items=resolved,
                payment_method=row.get("payment_method") or Sale.PaymentMethod.OTHER,
                notes=f"POS sync {row.get('reference', '')}".strip(),
                channel=Sale.Channel.INTEGRATION,
            )
            applied += 1
            details.append({"external_reference": row.get("reference", ""), "result": "created", "invoice_number": sale.invoice_number})
        except Exception as exc:  # noqa: BLE001 - a bad row must not abort the whole sync
            failed += 1
            details.append({"external_reference": row.get("reference", ""), "result": "failed", "reason": str(exc)[:200]})

    run = SyncRun.objects.create(
        pharmacy=pharmacy,
        integration_key=integration_key,
        kind=SyncRun.Kind.SALES,
        status=SyncRun.Status.PARTIAL if (unmapped or failed) else SyncRun.Status.APPLIED,
        idempotency_key=idempotency_key,
        rows_received=len(rows),
        rows_applied=applied,
        rows_unmapped=unmapped,
        rows_failed=failed,
        response_payload={"details": details[:500]},
    )
    return run
