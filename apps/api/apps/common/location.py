"""
What "near me" resolves to, in one place.

Several surfaces now need a shopper's position - the availability search, the assistant's
"nearest pharmacy that has all of this", the pharmacy finder - and each of them can be
reached by a signed-in shopper, a signed-in shopper on a device that refused the location
permission, or a signed-out visitor. Left to themselves they would each invent a slightly
different fallback chain, and the answers would quietly disagree.

The chain, best first:

  1. Coordinates supplied with the request. The person is on a device that just told us
     where it is; nothing on file is fresher than that.
  2. The shopper's saved `ShopperLocation` - what they shared last time and have not
     cleared.
  3. Their default delivery address. Not where they are standing, but it is where their
     orders go, and for ranking pharmacies a few kilometres apart that is usually the same
     answer.
  4. Nothing. Callers rank without distance rather than inventing a position.

Note what is NOT in the chain: guessing from an IP address, or silently substituting a city
centroid. A coarse guess that looks like a real position is worse than no position, because
the shopper cannot tell the difference and every surface here says "nearest to you".
`Origin.label` exists so they can: it names what the platform believes, out loud.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_LATITUDE, MAX_LATITUDE = -90.0, 90.0
MIN_LONGITUDE, MAX_LONGITUDE = -180.0, 180.0


@dataclass(frozen=True)
class Origin:
    """A position to measure from, and an honest account of where it came from."""

    latitude: float
    longitude: float
    source: str
    label: str = ""

    @property
    def position(self) -> tuple[float, float]:
        return self.latitude, self.longitude

    def describe(self) -> str:
        """How to name this origin to the person, e.g. "your location near Hamra"."""
        base = {
            "request": "your current location",
            "saved": "the location you shared",
            "address": "your default delivery address",
        }.get(self.source, "your location")
        return f"{base} near {self.label}" if self.label else base


def coerce(latitude, longitude) -> tuple[float, float] | None:
    """A pair of client-supplied values as real coordinates, or None. Never raises."""
    try:
        parsed_latitude, parsed_longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (MIN_LATITUDE <= parsed_latitude <= MAX_LATITUDE and MIN_LONGITUDE <= parsed_longitude <= MAX_LONGITUDE):
        return None
    # (0, 0) is in the Atlantic and is what a half-initialised client sends. Treating it as a
    # real fix would rank every pharmacy in Beirut as ~3000 km away, in a plausible-looking order.
    if parsed_latitude == 0 and parsed_longitude == 0:
        return None
    return parsed_latitude, parsed_longitude


def resolve_origin(*, user=None, latitude=None, longitude=None) -> Origin | None:
    """
    The best position available for this caller, or None if there is genuinely none.

    Imports are local because this module is imported by `apps.common`, which the apps it
    reads from import in turn.
    """
    from apps.common.geo import nearest_area

    supplied = coerce(latitude, longitude)
    if supplied is not None:
        return Origin(supplied[0], supplied[1], "request", nearest_area(*supplied))

    if user is None or not getattr(user, "is_authenticated", False):
        return None

    saved = getattr(user, "shopper_location", None)
    if saved is not None:
        return Origin(*saved.position, "saved", saved.label or nearest_area(*saved.position))

    return _from_default_address(user)


def _from_default_address(user) -> Origin | None:
    from apps.orders.models import DeliveryAddress

    address = DeliveryAddress.objects.filter(user=user).order_by("-is_default", "label").first()
    if address is None:
        return None
    position = coerce(address.latitude, address.longitude)
    if position is None:
        return None
    return Origin(position[0], position[1], "address", address.area or address.city)
