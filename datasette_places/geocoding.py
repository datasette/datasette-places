"""OpenCage geocoding proxy.

Proxies requests through the backend to handle API key management
and avoid exposing the key to the frontend.
"""

from __future__ import annotations

import httpx

OPENCAGE_API_URL = "https://api.opencagedata.com/geocode/v1/json"


async def geocode_search(query: str, api_key: str) -> list[dict]:
    """Forward geocode: text query → list of results."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            OPENCAGE_API_URL,
            params={
                "q": query,
                "key": api_key,
                "limit": 5,
                "no_annotations": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        {
            "display_name": r.get("formatted", ""),
            "latitude": r["geometry"]["lat"],
            "longitude": r["geometry"]["lng"],
            "components": r.get("components", {}),
        }
        for r in data.get("results", [])
    ]


async def reverse_geocode(lat: float, lon: float, api_key: str) -> dict | None:
    """Reverse geocode: lat/lon → address."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            OPENCAGE_API_URL,
            params={
                "q": f"{lat},{lon}",
                "key": api_key,
                "limit": 1,
                "no_annotations": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    if not results:
        return None
    r = results[0]
    return {
        "display_name": r.get("formatted", ""),
        "latitude": r["geometry"]["lat"],
        "longitude": r["geometry"]["lng"],
        "components": r.get("components", {}),
    }
