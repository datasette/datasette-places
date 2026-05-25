"""OpenCage geocoding proxy.

Proxies requests through the backend to handle API key management
and avoid exposing the key to the frontend.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("datasette_places.geocoding")

OPENCAGE_API_URL = "https://api.opencagedata.com/geocode/v1/json"


class GeocodingError(Exception):
    """An upstream geocoding request failed.

    ``message`` is human-readable and safe to show in the UI; ``status`` is
    the HTTP status the API route should return to the client.
    """

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


async def _opencage_request(query: str, api_key: str, limit: int) -> list[dict]:
    """Call OpenCage and return normalized results.

    Raises ``GeocodingError`` with a user-facing message (and logs the
    underlying cause) for any network, timeout, or upstream API failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                OPENCAGE_API_URL,
                params={
                    "q": query,
                    "key": api_key,
                    "limit": limit,
                    "no_annotations": 1,
                },
                timeout=10,
            )
    except httpx.TimeoutException as e:
        logger.warning("OpenCage request timed out for %r: %s", query, e)
        raise GeocodingError(
            "The geocoding service timed out. Please try again.", status=504
        ) from e
    except httpx.HTTPError as e:
        logger.warning("OpenCage request failed for %r: %s", query, e)
        raise GeocodingError(
            "Could not reach the geocoding service.", status=502
        ) from e

    # OpenCage returns JSON for both success and error responses, with a
    # ``status`` object describing the error. Surface that message in logs.
    try:
        data = resp.json()
    except ValueError as e:
        logger.error(
            "OpenCage returned non-JSON response (HTTP %s) for %r",
            resp.status_code,
            query,
        )
        raise GeocodingError(
            "The geocoding service returned an unexpected response.", status=502
        ) from e

    if resp.status_code != 200:
        upstream_message = (data.get("status") or {}).get("message", "")
        logger.warning(
            "OpenCage error for %r: HTTP %s — %s",
            query,
            resp.status_code,
            upstream_message or "(no message)",
        )
        raise GeocodingError(_client_message(resp.status_code, upstream_message))

    return [
        {
            "display_name": r.get("formatted", ""),
            "latitude": r["geometry"]["lat"],
            "longitude": r["geometry"]["lng"],
            "components": r.get("components", {}),
        }
        for r in data.get("results", [])
    ]


def _client_message(status_code: int, upstream_message: str) -> str:
    """Map an OpenCage HTTP status to a clear, user-facing message."""
    if status_code in (401, 403):
        return "The geocoding API key is invalid or not authorized."
    if status_code == 402:
        return "The geocoding quota has been exceeded. Try again later."
    if status_code == 429:
        return "Too many geocoding requests. Please wait a moment and retry."
    if upstream_message:
        return f"Geocoding service error: {upstream_message}"
    return f"Geocoding service error (HTTP {status_code})."


async def geocode_search(query: str, api_key: str) -> list[dict]:
    """Forward geocode: text query → list of results."""
    return await _opencage_request(query, api_key, limit=5)


async def reverse_geocode(lat: float, lon: float, api_key: str) -> dict | None:
    """Reverse geocode: lat/lon → address."""
    results = await _opencage_request(f"{lat},{lon}", api_key, limit=1)
    return results[0] if results else None
