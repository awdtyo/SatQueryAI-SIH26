"""Geocoding via Nominatim (OpenStreetMap) — free, no API key.

Converts place name -> {lat, lon} with graceful not-found handling.
"""

from __future__ import annotations

import logging
import re

import requests
from fastapi import HTTPException

from backend import config

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "SatQueryAI/1.0 (SIH 2026; contact: satquery-ai@example.com)",
    "Accept-Language": "en",
}


def parse_coordinates(raw: str) -> dict | None:
    """Try to parse 'lat,lon' or 'lat lon' from a raw string.

    Returns {lat, lon} or None if not parseable.
    """
    if not raw or not isinstance(raw, str):
        return None
    # Accept "lat, lon" "lat,lon" "lat lon"
    raw = raw.strip()
    # Regex for two floats separated by comma or space
    m = re.match(r"^\s*([+-]?\d+(?:\.\d+)?)\s*[, ]\s*([+-]?\d+(?:\.\d+)?)\s*$", raw)
    if not m:
        return None
    try:
        lat = float(m.group(1))
        lon = float(m.group(2))
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"lat": lat, "lon": lon}


def geocode_place(place: str, limit: int = 1) -> dict:
    """Geocode a place name via Nominatim.

    Returns dict {lat, lon, display_name, boundingbox}.
    Raises HTTPException 422 if not found, 502 if upstream fails.
    """
    place = (place or "").strip()
    if not place:
        raise HTTPException(status_code=422, detail="location_query is empty")

    # Fast path: if the query is already lat,lon coordinates
    coords = parse_coordinates(place)
    if coords:
        return {
            "lat": coords["lat"],
            "lon": coords["lon"],
            "display_name": f"{coords['lat']}, {coords['lon']}",
            "boundingbox": None,
        }

    endpoint = config.SATQUERY_NOMINATIM_ENDPOINT
    params = {
        "q": place,
        "format": "json",
        "limit": limit,
        "addressdetails": 0,
    }
    try:
        r = requests.get(endpoint, params=params, headers=_HEADERS, timeout=10)
    except requests.RequestException as e:
        logger.warning("Nominatim request failed for %r: %s", place, e)
        raise HTTPException(status_code=502, detail=f"Geocoding service temporarily unavailable: {e}") from e

    if r.status_code != 200:
        logger.warning("Nominatim non-200 for %r: %s %s", place, r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail=f"Geocoding service error (HTTP {r.status_code})")

    try:
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Geocoding returned invalid response: {e}") from e

    if not data:
        raise HTTPException(
            status_code=422,
            detail=f"Location not found: '{place}'. Try a more specific place name or paste lat,lon (e.g. '12.97, 77.59').",
        )

    first = data[0]
    try:
        lat = float(first["lat"])
        lon = float(first["lon"])
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Geocoding returned invalid coordinates for '{place}'") from e

    return {
        "lat": lat,
        "lon": lon,
        "display_name": first.get("display_name", place),
        "boundingbox": first.get("boundingbox"),
    }
