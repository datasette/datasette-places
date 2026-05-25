"""Geocoding proxy routes using OpenCage."""

from datasette import Response

from ..router import router
from ..permissions import ensure_places_list
from ..geocoding import geocode_search, reverse_geocode


def _get_api_key(datasette) -> str | None:
    """Read the OpenCage API key from plugin config."""
    config = datasette.plugin_config("datasette-places") or {}
    return config.get("opencage_api_key")


@router.GET(r"^/-/places/api/geocode$")
async def api_geocode(datasette, request):
    await ensure_places_list(datasette, request)
    api_key = _get_api_key(datasette)
    if not api_key:
        return Response.json(
            {"error": "OpenCage API key not configured"}, status=500
        )
    query = request.args.get("q", "").strip()
    if not query:
        return Response.json({"error": "q parameter is required"}, status=400)
    try:
        results = await geocode_search(query, api_key)
    except Exception as e:
        return Response.json({"error": str(e)}, status=502)
    return Response.json({"results": results})


@router.GET(r"^/-/places/api/reverse$")
async def api_reverse_geocode(datasette, request):
    await ensure_places_list(datasette, request)
    api_key = _get_api_key(datasette)
    if not api_key:
        return Response.json(
            {"error": "OpenCage API key not configured"}, status=500
        )
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except (TypeError, ValueError):
        return Response.json(
            {"error": "lat and lon parameters are required and must be numbers"},
            status=400,
        )
    try:
        result = await reverse_geocode(lat, lon, api_key)
    except Exception as e:
        return Response.json({"error": str(e)}, status=502)
    if result is None:
        return Response.json({"error": "No results found"}, status=404)
    return Response.json(result)
