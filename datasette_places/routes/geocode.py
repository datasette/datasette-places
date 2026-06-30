"""Geocoding proxy routes.

Forward (``/api/geocode``) and reverse (``/api/reverse``) lookups are proxied
through the backend so API keys never reach the browser. The provider is
resolved per request:

* ``?geocoder=<id>`` selects a specific geocoder instance;
* otherwise the list's default (``?list=<id>``) is used;
* otherwise the legacy config-driven OpenCage provider.

When a specific instance is used the request is gated: the actor must hold
``geocoder-use`` on it, and — when a list is named — the instance must be
attached and enabled on that list and the actor must have ``places-view``.
"""

import logging

from datasette import Forbidden, Response

from ..router import router
from ..permissions import (
    can_geocoder_use,
    ensure_places_list,
    ensure_places_view,
)
from ..geocoders import GeocodingError, default_provider, resolve_provider
from ..util import places_db

logger = logging.getLogger("datasette_places.geocode")


class _ProviderError(Exception):
    """Carries a ready-made Response for the route to return."""

    def __init__(self, response: Response):
        self.response = response


def _no_provider_response():
    logger.error(
        "Geocoding requested but no geocoder is configured. Set "
        "plugins.datasette-places.opencage_api_key or create a geocoder instance."
    )
    return Response.json(
        {"error": "Geocoding is not configured on this server."}, status=503
    )


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _resolve_provider(datasette, request):
    """Resolve the provider for this request, enforcing the access gates.

    Raises :class:`_ProviderError` (wrapping a Response) on any gate failure or
    unavailable provider; returns a live provider otherwise.
    """
    geocoder_id = (request.args.get("geocoder") or "").strip() or None
    list_id = _int_or_none(request.args.get("list"))

    # Baseline gate: a list context tightens to places-view on that list;
    # otherwise the global "can use places" check (legacy behavior).
    if list_id is not None:
        await ensure_places_view(datasette, request, list_id)
    else:
        await ensure_places_list(datasette, request)

    db = places_db(datasette)

    # Fall back to the list's default geocoder when none is named explicitly.
    if geocoder_id is None and list_id is not None:
        geocoder_id = await db.default_geocoder_for_list(list_id=list_id)

    # No instance in play → legacy config-driven default provider.
    if geocoder_id is None:
        provider = default_provider(datasette)
        if provider is None:
            raise _ProviderError(_no_provider_response())
        return provider

    geocoder = await db.select_geocoder_by_id(geocoder_id)
    if geocoder is None or not geocoder.enabled:
        raise _ProviderError(
            Response.json({"error": "That geocoder is unavailable."}, status=404)
        )

    # When scoped to a list, the instance must be attached and enabled there.
    if list_id is not None:
        attachment = await db.select_list_geocoder(
            list_id=list_id, geocoder_id=geocoder_id
        )
        if attachment is None or not attachment.enabled:
            raise _ProviderError(
                Response.json(
                    {"error": "That geocoder is not enabled for this list."},
                    status=400,
                )
            )

    # Query-time access gate (defense-in-depth: a revoked user is blocked even
    # if the instance is still attached).
    if not await can_geocoder_use(datasette, request.actor, geocoder_id):
        raise Forbidden("geocoder-use")

    provider = await resolve_provider(datasette, geocoder)
    if provider is None:
        raise _ProviderError(
            Response.json({"error": "That geocoder is unavailable."}, status=503)
        )
    return provider


@router.GET(r"^/-/places/api/geocode$")
async def api_geocode(datasette, request):
    try:
        provider = await _resolve_provider(datasette, request)
    except _ProviderError as e:
        return e.response
    query = request.args.get("q", "").strip()
    if not query:
        return Response.json({"error": "Search query is required."}, status=400)
    try:
        candidates = await provider.geocode(query)
    except GeocodingError as e:
        return Response.json({"error": str(e)}, status=e.status)
    except Exception:
        logger.exception("Unexpected error geocoding %r", query)
        return Response.json(
            {"error": "Unexpected error while searching. Please try again."},
            status=502,
        )
    return Response.json({"results": [c.to_result() for c in candidates]})


@router.GET(r"^/-/places/api/reverse$")
async def api_reverse_geocode(datasette, request):
    try:
        provider = await _resolve_provider(datasette, request)
    except _ProviderError as e:
        return e.response
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except (TypeError, ValueError):
        return Response.json(
            {"error": "lat and lon parameters are required and must be numbers."},
            status=400,
        )
    try:
        candidates = await provider.reverse(lat, lon)
    except GeocodingError as e:
        return Response.json({"error": str(e)}, status=e.status)
    except Exception:
        logger.exception("Unexpected error reverse geocoding %s,%s", lat, lon)
        return Response.json(
            {"error": "Unexpected error while looking up that location."},
            status=502,
        )
    if not candidates:
        return Response.json(
            {"error": "No address found for that location."}, status=404
        )
    return Response.json(candidates[0].to_result())
