from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.customers.models import ClientLedgerEntry
from apps.inventory.models import InventoryBatch, StockMovement
from apps.inventory.services.stock import adjust_stock
from apps.medicines.models import Medicine
from apps.prescriptions.models import PrescriptionRecord
from apps.sales.models import Sale, SaleItem


def next_invoice_number(pharmacy_id) -> str:
    prefix = timezone.now().strftime("MS-%Y%m%d")
    count = Sale.objects.filter(pharmacy_id=pharmacy_id, invoice_number__startswith=prefix).count() + 1
    return f"{prefix}-{count:05d}"


@transaction.atomic
def create_sale(
    *,
    user,
    pharmacy,
    items: list[dict],
    payment_method: str = "",
    notes: str = "",
    prescription_record_id=None,
    client=None,
    channel: str = Sale.Channel.COUNTER,
) -> Sale:
    if not items:
        raise ValueError("A sale must contain at least one item.")

    prescription = None
    if prescription_record_id:
        prescription = PrescriptionRecord.objects.select_for_update().get(id=prescription_record_id, pharmacy=pharmacy)

    if client is not None and client.pharmacy_id != pharmacy.id:
        raise ValueError("Client belongs to another pharmacy.")
    if payment_method == Sale.PaymentMethod.ON_ACCOUNT and client is None:
        raise ValueError("Select a client before charging a sale to an account.")

    sale = Sale.objects.create(
        invoice_number=next_invoice_number(pharmacy.id),
        pharmacy=pharmacy,
        staff_user=user,
        client=client,
        channel=channel,
        payment_method=payment_method or "",
        notes=notes or "",
        prescription_record=prescription,
    )

    subtotal = Decimal("0")
    discount_total = Decimal("0")
    today = timezone.localdate()
    for raw_item in items:
        medicine = Medicine.objects.get(id=raw_item["medicine"])
        quantity_needed = int(raw_item["quantity"])
        discount = Decimal(str(raw_item.get("discount", 0) or 0))
        batches = (
            InventoryBatch.objects.select_for_update()
            .filter(
                pharmacy=pharmacy,
                medicine=medicine,
                current_quantity__gt=0,
                is_archived=False,
            )
            .exclude(expiry_date__lt=today)
            .order_by("expiry_date", "created_at")
        )
        available = sum(batch.current_quantity for batch in batches)
        if available < quantity_needed:
            raise ValueError(f"Insufficient stock for {medicine}.")

        remaining = quantity_needed
        for batch in batches:
            if remaining <= 0:
                break
            allocated = min(batch.current_quantity, remaining)
            unit_price = Decimal(str(raw_item.get("unit_price") or batch.selling_price))
            medicine.validate_selling_price(unit_price)
            line_discount = discount if remaining == quantity_needed else Decimal("0")
            line_total = max(Decimal("0"), (unit_price * allocated) - line_discount)
            SaleItem.objects.create(
                sale=sale,
                medicine=medicine,
                inventory_batch=batch,
                quantity=allocated,
                unit_price=unit_price,
                discount=line_discount,
                line_total=line_total,
            )
            subtotal += unit_price * allocated
            discount_total += line_discount
            adjust_stock(
                batch_id=batch.id,
                user=user,
                quantity_delta=-allocated,
                reason=f"Sale {sale.invoice_number}",
                movement_type=StockMovement.MovementType.SALE,
                sale=sale,
            )
            remaining -= allocated

    sale.subtotal = subtotal
    sale.discount_total = discount_total
    sale.total = max(Decimal("0"), subtotal - discount_total)
    sale.save(update_fields=["subtotal", "discount_total", "total", "updated_at"])

    if prescription:
        prescription.sale = sale
        prescription.save(update_fields=["sale", "updated_at"])

    if client is not None and sale.payment_method == Sale.PaymentMethod.ON_ACCOUNT:
        ClientLedgerEntry.objects.create(
            client=client,
            entry_type=ClientLedgerEntry.EntryType.CHARGE,
            amount=sale.total,
            sale=sale,
            memo=f"Invoice {sale.invoice_number}",
            created_by=user,
        )

    write_audit_log(
        actor_user=user,
        pharmacy=pharmacy,
        action="sales.sale_created",
        entity_type="Sale",
        entity_id=sale.id,
        summary=f"Created invoice {sale.invoice_number}",
        after_data={"total": str(sale.total), "items": len(items)},
    )
    return sale

