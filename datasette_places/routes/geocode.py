"""Geocoding proxy routes using OpenCage."""

import logging

from datasette import Response

from ..router import router
from ..permissions import ensure_places_list
from ..geocoding import GeocodingError, geocode_search, reverse_geocode

logger = logging.getLogger("datasette_places.geocode")


def _get_api_key(datasette) -> str | None:
    """Read the OpenCage API key from plugin config."""
    config = datasette.plugin_config("datasette-places") or {}
    return config.get("opencage_api_key")


def _no_key_response():
    logger.error(
        "Geocoding requested but no OpenCage API key is configured. Set "
        "plugins.datasette-places.opencage_api_key in your Datasette config."
    )
    return Response.json(
        {"error": "Geocoding is not configured on this server."}, status=503
    )


@router.GET(r"^/-/places/api/geocode$")
async def api_geocode(datasette, request):
    await ensure_places_list(datasette, request)
    api_key = _get_api_key(datasette)
    if not api_key:
        return _no_key_response()
    query = request.args.get("q", "").strip()
    if not query:
        return Response.json({"error": "Search query is required."}, status=400)
    try:
        results = await geocode_search(query, api_key)
    except GeocodingError as e:
        return Response.json({"error": str(e)}, status=e.status)
    except Exception:
        logger.exception("Unexpected error geocoding %r", query)
        return Response.json(
            {"error": "Unexpected error while searching. Please try again."},
            status=502,
        )
    return Response.json({"results": results})


@router.GET(r"^/-/places/api/reverse$")
async def api_reverse_geocode(datasette, request):
    await ensure_places_list(datasette, request)
    api_key = _get_api_key(datasette)
    if not api_key:
        return _no_key_response()
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except (TypeError, ValueError):
        return Response.json(
            {"error": "lat and lon parameters are required and must be numbers."},
            status=400,
        )
    try:
        result = await reverse_geocode(lat, lon, api_key)
    except GeocodingError as e:
        return Response.json({"error": str(e)}, status=e.status)
    except Exception:
        logger.exception("Unexpected error reverse geocoding %s,%s", lat, lon)
        return Response.json(
            {"error": "Unexpected error while looking up that location."},
            status=502,
        )
    if result is None:
        return Response.json(
            {"error": "No address found for that location."}, status=404
        )
    return Response.json(result)
