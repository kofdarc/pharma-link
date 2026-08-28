"""
The complete set of lookups the assistant can run, and the only way to run one.

`execute` is a chokepoint on purpose. Nothing else in the app calls a handler directly, so
there is exactly one place where "is this persona allowed this tool" is asked - and it is
asked on every call, against the persona resolved from the auth token rather than against
anything the message said.
"""

from __future__ import annotations

from apps.assistant.tools import admin, customer, doctor, driver, pharmacy, public
from apps.assistant.tools.base import ToolContext, ToolSpec


class ToolNotAllowed(Exception):
    """A persona asked for a tool outside its allowlist. Always a bug or an attack, never routine."""


_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        # Public - no personal data, reachable by anyone including signed-out visitors.
        ToolSpec("search_availability", public.search_availability, "Which pharmacies currently stock a named medicine, and at what price."),
        ToolSpec("medicine_details", public.medicine_details, "Catalogue facts for a named product, including whether it needs a prescription."),
        ToolSpec("find_pharmacies", public.find_pharmacies, "Connected pharmacies, optionally in a named area."),
        # Patient - scoped to the signed-in customer.
        ToolSpec("my_orders", customer.my_orders, "The signed-in patient's own recent orders and their status."),
        ToolSpec("my_prescriptions_patient", customer.my_prescriptions, "The signed-in patient's own e-prescriptions, validity and remaining quantities."),
        ToolSpec("my_refills", customer.my_refills, "The signed-in patient's repeat orders and when the next one runs."),
        # Doctor - scoped to the signed-in prescriber.
        ToolSpec("catalogue_lookup", doctor.catalogue_lookup, "Registration facts for a product: form, strength, schedule, prescription status."),
        ToolSpec("my_prescriptions_doctor", doctor.my_prescriptions, "Prescriptions this doctor issued."),
        ToolSpec("renewal_requests", doctor.renewal_requests, "Renewal requests pharmacies raised against this doctor's prescriptions."),
        ToolSpec("my_patients", doctor.my_patients, "People this doctor has prescribed for."),
        # Pharmacy - scoped to the signed-in user's own pharmacy.
        ToolSpec("stock_lookup", pharmacy.stock_lookup, "How much of a named product this pharmacy holds."),
        ToolSpec("stock_alerts", pharmacy.stock_alerts, "What is running low or approaching expiry."),
        ToolSpec("sales_summary", pharmacy.sales_summary, "How the pharmacy traded over a recent window."),
        ToolSpec("business_insights", pharmacy.business_insights, "Ranked findings from the pharmacy's own analytics."),
        ToolSpec("incoming_orders", pharmacy.incoming_orders, "Online orders waiting on this pharmacy."),
        # Platform admin - aggregate only.
        ToolSpec("platform_overview", admin.platform_overview, "Current shape of the network: pharmacies, orders, drivers."),
        ToolSpec("pending_applications", admin.pending_applications, "Pharmacy applications waiting on review."),
        ToolSpec("dispatch_snapshot", admin.dispatch_snapshot, "Delivery load right now."),
        ToolSpec("recent_activity", admin.recent_activity, "The tail of the audit trail."),
        # Driver - scoped to the signed-in driver.
        ToolSpec("my_route", driver.my_route, "The driver's current route and remaining stops."),
        ToolSpec("next_stop", driver.next_stop, "Just the stop the driver is heading to."),
    )
}


def get(name: str) -> ToolSpec:
    try:
        return _TOOLS[name]
    except KeyError:
        raise ToolNotAllowed(f"Unknown assistant tool '{name}'.") from None


def execute(name: str, *, allowed: frozenset[str], context: ToolContext) -> dict:
    """
    Run one tool, having first checked the persona is entitled to it.

    `allowed` is derived from the persona, which is derived from the auth token. A tool name
    that reaches here from a mis-parsed message, or from a model that has been talked into
    asking for something else, is rejected before any handler runs - the check is membership,
    not persuasion.
    """
    if name not in allowed:
        raise ToolNotAllowed(f"Persona is not allowed tool '{name}'.")
    return get(name).handler(context)


__all__ = ["ToolContext", "ToolNotAllowed", "ToolSpec", "execute", "get"]
