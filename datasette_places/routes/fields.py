"""Route handlers for per-list metadata field definitions.

Field definitions are list configuration, so writes gate on ``places-manage``
(like sharing) and reads on ``places-view``. Every mutation rebuilds the list's
dynamic artifacts (expanded view + unique indexes) inside ``PlacesDB`` so they
stay in sync with the defs.
"""

import json

from datasette import Response

from ..fields import FieldError, validate_key, validate_type
from ..router import router
from ..permissions import ensure_places_manage, ensure_places_view
from ..util import read_json_body, places_db


def field_payload(f) -> dict:
    try:
        config = json.loads(f.config_json) if f.config_json else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    return {
        "id": f.id,
        "list_id": f.list_id,
        "key": f.key,
        "label": f.label,
        "type": f.type,
        "position": f.position,
        "required": bool(f.required),
        "unique": bool(f.is_unique),
        "config": config,
    }


@router.GET(r"^/-/places/api/lists/(?P<list_id>\d+)/fields$")
async def api_list_fields(datasette, request, list_id: int):
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    rows = await db.select_fields_for_list(list_id=list_id)
    return Response.json(
        {"list_id": list_id, "fields": [field_payload(r) for r in rows]}
    )


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/fields$")
async def api_add_field(datasette, request, list_id: int):
    await ensure_places_manage(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)

    body = await read_json_body(request)
    key = (body.get("key") or "").strip()
    label = (body.get("label") or "").strip()
    type_ = body.get("type")
    if not label:
        return Response.json({"error": "label is required"}, status=400)
    try:
        validate_key(key)
        validate_type(type_)
    except FieldError as exc:
        return Response.json({"error": str(exc)}, status=400)

    config = body.get("config")
    try:
        field = await db.insert_list_field(
            list_id=list_id,
            key=key,
            label=label,
            type=type_,
            required=bool(body.get("required")),
            is_unique=bool(body.get("unique")),
            config_json=json.dumps(config) if config is not None else "{}",
        )
    except Exception as exc:  # UNIQUE(list_id,key) collision, etc.
        if "UNIQUE" in str(exc):
            return Response.json(
                {"error": f"a field with key '{key}' already exists"}, status=400
            )
        raise
    return Response.json(field_payload(field), status=201)


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/fields/(?P<field_id>\d+)/update$")
async def api_update_field(datasette, request, list_id: int, field_id: int):
    await ensure_places_manage(datasette, request, list_id)
    db = places_db(datasette)
    existing = await db.select_list_field_by_id(field_id=field_id)
    if existing is None or existing.list_id != list_id:
        return Response.json({"error": "Field not found"}, status=404)

    body = await read_json_body(request)
    # Key is immutable post-create (it backs the view column + stored values).
    label = (body.get("label") or existing.label).strip() or existing.label
    type_ = body.get("type", existing.type)
    try:
        validate_type(type_)
    except FieldError as exc:
        return Response.json({"error": str(exc)}, status=400)
    position = body.get("position", existing.position)
    required = body.get("required")
    is_unique = body.get("unique")
    config = body.get("config")

    field = await db.update_list_field(
        field_id=field_id,
        label=label,
        type=type_,
        position=int(position),
        required=bool(existing.required if required is None else required),
        is_unique=bool(existing.is_unique if is_unique is None else is_unique),
        config_json=(
            json.dumps(config) if config is not None else existing.config_json
        ),
    )
    if field is None:
        return Response.json({"error": "Field not found"}, status=404)
    return Response.json(field_payload(field))


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/fields/(?P<field_id>\d+)/delete$")
async def api_delete_field(datasette, request, list_id: int, field_id: int):
    await ensure_places_manage(datasette, request, list_id)
    db = places_db(datasette)
    existing = await db.select_list_field_by_id(field_id=field_id)
    if existing is None or existing.list_id != list_id:
        return Response.json({"error": "Field not found"}, status=404)
    await db.delete_list_field(field_id=field_id)
    return Response.json({"ok": True})
