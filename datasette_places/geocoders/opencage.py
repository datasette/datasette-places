"""OpenCage geocoding provider.

Wraps the hosted OpenCage geocoding API. The HTTP/error handling lives in
``_opencage_request`` (returning raw OpenCage result dicts); :class:`OpenCageProvider`
maps those into :class:`Candidate` objects, and the module-level
``geocode_search`` / ``reverse_geocode`` functions provide the legacy normalized
dict shape (re-exported from ``datasette_places.geocoding`` for back-compat).
"""

from __future__ import annotations

import logging

import httpx

from .base import Candidate, GeocodeProvider, GeocodingError

logger = logging.getLogger("datasette_places.geocoding")

DEFAULT_OPENCAGE_API_URL = "https://api.opencagedata.com/geocode/v1/json"


def _make_client() -> httpx.AsyncClient:
    """Construct the HTTP client. A seam so tests can inject a mock transport
    without monkeypatching ``httpx.AsyncClient`` globally (which would also
    capture Datasette's own test client)."""
    return httpx.AsyncClient()


async def _opencage_request(
    query: str, api_key: str, limit: int, base_url: str = DEFAULT_OPENCAGE_API_URL
) -> list[dict]:
    """Call OpenCage and return the raw ``results`` list.

    ``base_url`` is the OpenCage geocoding endpoint, configurable to support
    self-hosted or alternate (e.g. staging) deployments.

    Raises ``GeocodingError`` with a user-facing message (and logs the
    underlying cause) for any network, timeout, or upstream API failure.
    """
    try:
        async with _make_client() as client:
            resp = await client.get(
                base_url,
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

    return data.get("results", [])


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


def _confidence_to_score(confidence) -> float | None:
    """OpenCage ``confidence`` is 1..10 (10 best) → normalized 0..1."""
    if confidence is None:
        return None
    try:
        return max(0.0, min(1.0, float(confidence) / 10.0))
    except (TypeError, ValueError):
        return None


def _normalize(result: dict) -> dict:
    """Raw OpenCage result → the legacy normalized dict."""
    return {
        "display_name": result.get("formatted", ""),
        "latitude": result["geometry"]["lat"],
        "longitude": result["geometry"]["lng"],
        "components": result.get("components", {}),
    }


def _to_candidate(result: dict) -> Candidate:
    """Raw OpenCage result → :class:`Candidate` (keeping label + confidence)."""
    return Candidate(
        latitude=result["geometry"]["lat"],
        longitude=result["geometry"]["lng"],
        label=result.get("formatted", ""),
        score=_confidence_to_score(result.get("confidence")),
        components=result.get("components", {}),
    )


class OpenCageProvider(GeocodeProvider):
    """Geocode against the hosted OpenCage API."""

    type = "opencage"
    supports_reverse = True

    def __init__(self, api_key: str, base_url: str = DEFAULT_OPENCAGE_API_URL):
        self.api_key = api_key
        self.base_url = base_url or DEFAULT_OPENCAGE_API_URL

    async def geocode(self, query: str, *, limit: int = 5) -> list[Candidate]:
        results = await _opencage_request(
            query, self.api_key, limit=limit, base_url=self.base_url
        )
        return [_to_candidate(r) for r in results]

    async def reverse(self, lat: float, lon: float) -> list[Candidate]:
        results = await _opencage_request(
            f"{lat},{lon}", self.api_key, limit=1, base_url=self.base_url
        )
        return [_to_candidate(r) for r in results]

    @classmethod
    def from_instance(cls, datasette, config: dict) -> "OpenCageProvider | None":
        """Build from a geocoder instance's ``config_json``.

        ``config`` may carry ``api_key`` (inline) or ``api_key_ref`` (the name of
        a ``plugins.datasette-places.*`` config key holding the key); ``base_url``
        is optional. Falls back to the top-level ``opencage_api_key`` /
        ``opencage_base_url`` plugin config so a bare ``{}`` instance works with
        an existing single-key deployment. Returns ``None`` when no key resolves.
        """
        plugin_config = datasette.plugin_config("datasette-places") or {}
        api_key = config.get("api_key")
        ref = config.get("api_key_ref")
        if not api_key and ref:
            api_key = plugin_config.get(ref)
        if not api_key:
            api_key = plugin_config.get("opencage_api_key")
        if not api_key:
            return None
        base_url = (
            config.get("base_url")
            or plugin_config.get("opencage_base_url")
            or DEFAULT_OPENCAGE_API_URL
        )
        return cls(api_key, base_url)


# ---------------------------------------------------------------------------
# Legacy function API (back-compat; re-exported from datasette_places.geocoding)
# ---------------------------------------------------------------------------


async def geocode_search(
    query: str, api_key: str, base_url: str = DEFAULT_OPENCAGE_API_URL
) -> list[dict]:
    """Forward geocode: text query → list of normalized result dicts."""
    results = await _opencage_request(query, api_key, limit=5, base_url=base_url)
    return [_normalize(r) for r in results]


async def reverse_geocode(
    lat: float, lon: float, api_key: str, base_url: str = DEFAULT_OPENCAGE_API_URL
) -> dict | None:
    """Reverse geocode: lat/lon → a single normalized result dict, or None."""
    results = await _opencage_request(
        f"{lat},{lon}", api_key, limit=1, base_url=base_url
    )
    return _normalize(results[0]) if results else None
