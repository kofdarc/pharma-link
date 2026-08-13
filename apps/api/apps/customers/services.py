from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.customers.models import Client, ClientLedgerEntry
from apps.sales.models import Sale, SaleItem


def client_balance(client: Client) -> Decimal:
    totals = client.ledger_entries.aggregate(
        charges=Sum("amount", filter=Q(entry_type=ClientLedgerEntry.EntryType.CHARGE)),
        payments=Sum("amount", filter=Q(entry_type=ClientLedgerEntry.EntryType.PAYMENT)),
        adjustments=Sum("amount", filter=Q(entry_type=ClientLedgerEntry.EntryType.ADJUSTMENT)),
    )
    charges = totals["charges"] or Decimal("0")
    payments = totals["payments"] or Decimal("0")
    adjustments = totals["adjustments"] or Decimal("0")
    return charges - payments + adjustments


def client_history(client: Client, *, limit: int = 20) -> dict:
    sales = Sale.objects.filter(client=client, status=Sale.Status.COMPLETED)
    aggregate = sales.aggregate(total_spent=Sum("total"), visits=Count("id"))
    total_spent = aggregate["total_spent"] or Decimal("0")
    visits = aggregate["visits"] or 0
    top_items = (
        SaleItem.objects.filter(sale__client=client, sale__status=Sale.Status.COMPLETED)
        .values("medicine_id", "medicine__brand_name", "medicine__strength", "medicine__form")
        .annotate(units=Sum("quantity"), spend=Sum("line_total"))
        .order_by("-units")[:8]
    )
    last_sale = sales.order_by("-sale_datetime").first()
    return {
        "visits": visits,
        "total_spent": total_spent,
        "average_basket": (total_spent / visits) if visits else Decimal("0"),
        "balance_due": client_balance(client),
        "last_visit": last_sale.sale_datetime if last_sale else None,
        "days_since_last_visit": (timezone.now() - last_sale.sale_datetime).days if last_sale else None,
        "top_products": [
            {
                "medicine_id": row["medicine_id"],
                "name": " ".join(filter(None, [row["medicine__brand_name"], row["medicine__strength"], row["medicine__form"]])),
                "units": row["units"],
                "spend": row["spend"],
            }
            for row in top_items
        ],
        "recent_sales": [
            {"id": sale.id, "invoice_number": sale.invoice_number, "total": sale.total, "sale_datetime": sale.sale_datetime}
            for sale in sales.order_by("-sale_datetime")[:limit]
        ],
    }


def link_or_create_client_for_shopper(*, pharmacy, user, contact_name: str = "", phone: str = "", address: str = "", area: str = "") -> Client:
    """Keeps the pharmacy CRM in sync when a platform shopper orders from them for the first time."""
    existing = Client.objects.filter(pharmacy=pharmacy, platform_user=user).first()
    if existing:
        return existing
    if phone:
        by_phone = Client.objects.filter(pharmacy=pharmacy, phone=phone, is_active=True).first()
        if by_phone:
            by_phone.platform_user = user
            by_phone.save(update_fields=["platform_user", "updated_at"])
            return by_phone
    return Client.objects.create(
        pharmacy=pharmacy,
        platform_user=user,
        full_name=contact_name or user.get_full_name() or user.email,
        phone=phone or "",
        email=user.email,
        address=address,
        area=area,
        created_by=user,
    )
