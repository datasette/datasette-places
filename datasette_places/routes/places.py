"""Route handlers for place CRUD within a list."""

import json

from datasette import Response

from ..router import router
from ..fields import FieldError, validate_key, validate_metadata
from ..permissions import ensure_places_edit, ensure_places_view
from ..util import read_json_body, actor_id, places_db


class _UniqueViolation(Exception):
    """A unique-field expression index rejected the write."""


def _is_unique_error(exc: Exception) -> bool:
    return "UNIQUE" in str(exc) and "_dsp_uniq_" in str(exc)


def _place_payload(p) -> dict:
    metadata = None
    if p.metadata_json:
        try:
            metadata = json.loads(p.metadata_json)
        except (json.JSONDecodeError, TypeError):
            metadata = None
    return {
        "id": p.id,
        "list_id": p.list_id,
        "name": p.name,
        "address": p.address,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "notes": p.notes,
        "color": p.color,
        "metadata": metadata,
        "created_by": p.created_by,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@router.GET(r"^/-/places/api/lists/(?P<list_id>\d+)/places$")
async def api_list_places(datasette, request, list_id: int):
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    rows = await db.select_places_for_list(list_id=list_id)
    return Response.json(
        {
            "list_id": list_id,
            "places": [_place_payload(r) for r in rows],
        }
    )


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/places$")
async def api_add_place(datasette, request, list_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)

    body = await read_json_body(request)
    name = (body.get("name") or "").strip()
    if not name:
        return Response.json({"error": "name is required"}, status=400)
    lat = body.get("latitude")
    lon = body.get("longitude")
    if lat is None or lon is None:
        return Response.json(
            {"error": "latitude and longitude are required"}, status=400
        )
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return Response.json(
            {"error": "latitude and longitude must be numbers"}, status=400
        )

    metadata = body.get("metadata")
    if metadata is not None:
        field_rows = await db.select_fields_for_list(list_id=list_id)
        clean, errors = validate_metadata(metadata, field_rows)
        if errors:
            return Response.json({"errors": errors}, status=400)
        metadata = clean
    metadata_json = json.dumps(metadata) if metadata is not None else None

    try:
        place = await db.insert_place(
            list_id=list_id,
            name=name,
            latitude=lat,
            longitude=lon,
            address=body.get("address"),
            notes=body.get("notes"),
            color=body.get("color"),
            metadata_json=metadata_json,
            created_by=actor_id(request),
        )
    except Exception as exc:
        if _is_unique_error(exc):
            return Response.json(
                {"error": "a unique field value is already taken"}, status=400
            )
        raise
    return Response.json(_place_payload(place), status=201)


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/places/(?P<place_id>\d+)/update$")
async def api_update_place(datasette, request, list_id: int, place_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    existing = await db.select_place_by_id(place_id=place_id)
    if existing is None or existing.list_id != list_id:
        return Response.json({"error": "Place not found"}, status=404)

    body = await read_json_body(request)
    metadata = body.get("metadata")
    if metadata is not None:
        field_rows = await db.select_fields_for_list(list_id=list_id)
        clean, errors = validate_metadata(metadata, field_rows)
        if errors:
            return Response.json({"errors": errors}, status=400)
        metadata = clean
    metadata_json = json.dumps(metadata) if metadata is not None else None

    lat = body.get("latitude")
    lon = body.get("longitude")
    if lat is not None:
        try:
            lat = float(lat)
        except (TypeError, ValueError):
            return Response.json({"error": "latitude must be a number"}, status=400)
    if lon is not None:
        try:
            lon = float(lon)
        except (TypeError, ValueError):
            return Response.json({"error": "longitude must be a number"}, status=400)

    try:
        place = await db.update_place(
            place_id=place_id,
            name=body.get("name"),
            address=body.get("address"),
            latitude=lat,
            longitude=lon,
            notes=body.get("notes"),
            color=body.get("color"),
            metadata_json=metadata_json,
        )
    except Exception as exc:
        if _is_unique_error(exc):
            return Response.json(
                {"error": "a unique field value is already taken"}, status=400
            )
        raise
    if place is None:
        return Response.json({"error": "Place not found"}, status=404)
    return Response.json(_place_payload(place))


@router.POST(
    r"^/-/places/api/lists/(?P<list_id>\d+)/places/(?P<place_id>\d+)/metadata$"
)
async def api_set_place_metadata(datasette, request, list_id: int, place_id: int):
    """Set or clear a single metadata key via json_set/json_remove.

    Body: ``{"key": "rating", "value": 4}`` to set, or ``{"key": "rating"}``
    (value omitted/null) to clear. The value is validated against the field def
    for ``key`` before writing.
    """
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    existing = await db.select_place_by_id(place_id=place_id)
    if existing is None or existing.list_id != list_id:
        return Response.json({"error": "Place not found"}, status=404)

    body = await read_json_body(request)
    key = body.get("key")
    try:
        validate_key(key)
    except FieldError as exc:
        return Response.json({"error": str(exc)}, status=400)

    if "value" not in body or body.get("value") is None:
        place = await db.clear_place_metadata_key(place_id=place_id, key=key)
        return Response.json(_place_payload(place))

    value = body.get("value")
    # Validate against the declared field (single-key slice of validate_metadata).
    field_rows = await db.select_fields_for_list(list_id=list_id)
    field = next((f for f in field_rows if f.key == key), None)
    if field is None:
        return Response.json(
            {"errors": {key: "unknown field for this list"}}, status=400
        )
    _, errors = validate_metadata({key: value}, [field])
    if errors:
        return Response.json({"errors": errors}, status=400)

    try:
        place = await db.set_place_metadata_key(
            place_id=place_id, key=key, value_json=json.dumps(value)
        )
    except Exception as exc:
        if "UNIQUE" in str(exc):
            return Response.json(
                {"errors": {key: "must be unique within this list"}}, status=400
            )
        raise
    return Response.json(_place_payload(place))


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/places/(?P<place_id>\d+)/delete$")
async def api_delete_place(datasette, request, list_id: int, place_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    existing = await db.select_place_by_id(place_id=place_id)
    if existing is None or existing.list_id != list_id:
        return Response.json({"error": "Place not found"}, status=404)
    await db.delete_place(place_id=place_id)
    return Response.json({"ok": True})
