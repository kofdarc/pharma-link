from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088

# Straight-line distance understates real driving. Beirut's street grid, one-way
# systems and traffic make ~1.4x a reasonable planning multiplier, and it keeps the
# whole planner dependency-free (no routing API, no API key, works offline in the POC).
ROAD_FACTOR = 1.4

# Average door-to-door speed for a scooter in dense Beirut traffic.
AVERAGE_SPEED_KMH = 18.0

# Fixed time cost of a stop: parking, finding the counter, handover, signature.
PICKUP_SERVICE_MINUTES = 6.0
DROPOFF_SERVICE_MINUTES = 4.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (float(lat1), float(lon1), float(lat2), float(lon2)))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    inner = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, inner)))


def road_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * ROAD_FACTOR


def travel_minutes(distance_km: float) -> float:
    return (distance_km / AVERAGE_SPEED_KMH) * 60.0


# Approximate centres of the Beirut areas the platform serves.
#
# Sourcing ranks pharmacies by distance, so an address with no coordinates cannot
# be planned against - but asking a patient to type a latitude is not a question
# anyone can answer. The area they already named is enough to rank pharmacies a
# few kilometres apart, which is the only decision these coordinates feed.
#
# This is a fallback, never an override: an address that carries real
# coordinates (from a map pin, or a future geocoding service) keeps them.
AREA_CENTRES: dict[str, tuple[float, float]] = {
    "hamra": (33.8971, 35.4805),
    "achrafieh": (33.8886, 35.5175),
    "ashrafieh": (33.8886, 35.5175),
    "gemmayze": (33.8959, 35.5142),
    "gemmayzeh": (33.8959, 35.5142),
    "mar mikhael": (33.8977, 35.5215),
    "verdun": (33.8790, 35.4835),
    "ras beirut": (33.8990, 35.4760),
    "manara": (33.8998, 35.4718),
    "clemenceau": (33.8930, 35.4830),
    "downtown": (33.8959, 35.5045),
    "beirut central district": (33.8959, 35.5045),
    "badaro": (33.8746, 35.5155),
    "mathaf": (33.8790, 35.5155),
    "sodeco": (33.8830, 35.5130),
    "sin el fil": (33.8720, 35.5480),
    "furn el chebbak": (33.8660, 35.5330),
    "jnah": (33.8672, 35.4870),
    "ramlet el baida": (33.8720, 35.4790),
    "mazraa": (33.8790, 35.5010),
    "tarik el jdideh": (33.8700, 35.4960),
    "bourj hammoud": (33.8930, 35.5390),
    "dekwaneh": (33.8710, 35.5610),
    "hazmieh": (33.8480, 35.5410),
    "baabda": (33.8340, 35.5440),
}

# Where an unrecognised Beirut address is assumed to be: the city centre. Being
# a few kilometres out changes which pharmacy ranks first, not whether the order
# can be filled, and it beats refusing to plan the basket at all.
BEIRUT_CENTRE = (33.8938, 35.5018)


def area_coordinates(area: str, city: str = "") -> tuple[float, float]:
    """Best-effort coordinates for a named area. Never raises - see AREA_CENTRES."""
    for candidate in (area, city):
        found = AREA_CENTRES.get((candidate or "").strip().lower())
        if found:
            return found
    return BEIRUT_CENTRE
