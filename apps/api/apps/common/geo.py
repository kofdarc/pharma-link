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
