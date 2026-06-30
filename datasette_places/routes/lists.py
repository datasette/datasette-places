"""Route handlers for place list CRUD and HTML pages."""

from datasette import Forbidden, Response

from ..router import router
from ..permissions import (
    ACTION_EDIT,
    ACTION_MANAGE,
    ACTION_VIEW,
    PlacesListResource,
    can_places_manage,
    ensure_places_create,
    ensure_places_edit,
    ensure_places_list,
    ensure_places_view,
    seed_owner_manager_grant,
)
from ..util import read_json_body, actor_id, places_db


@router.GET(r"^/-/places/api/lists$")
async def api_list_lists(datasette, request):
    await ensure_places_list(datasette, request)
    state = (request.args.get("state") or "active").lower()
    if state not in ("active", "trashed"):
        return Response.json(
            {"error": "state must be one of: active, trashed"}, status=400
        )

    page = await datasette.allowed_resources(
        action=ACTION_VIEW, actor=request.actor, limit=1000
    )
    list_ids = [int(r.parent) for r in page.resources]
    db = places_db(datasette)
    rows = await db.list_lists_by_ids_and_state(list_ids=list_ids, state=state)
    counts = await db.place_counts_by_list_ids([r.id for r in rows])
    me = actor_id(request)
    return Response.json(
        [
            {
                "id": r.id,
                "name": r.name,
                "place_count": counts.get(r.id, 0),
                "created_by": r.created_by,
                "updated_at": r.updated_at,
                "state": r.state,
                "is_owner": r.created_by is not None and r.created_by == me,
            }
            for r in rows
        ]
    )


@router.POST(r"^/-/places/api/lists$")
async def api_create_list(datasette, request):
    await ensure_places_create(datasette, request)
    db = places_db(datasette)
    body = await read_json_body(request)
    name = (body.get("name") or "").strip() or "Untitled"
    pl = await db.insert_list(name=name, created_by=actor_id(request))
    # Ownership is now an acl Manager grant on the new list rather than a
    # created_by-based SQL rule.
    await seed_owner_manager_grant(datasette, pl.id, pl.created_by)
    return Response.json(
        {
            "id": pl.id,
            "name": pl.name,
            "created_by": pl.created_by,
            "created_at": pl.created_at,
        },
        status=201,
    )


@router.GET(r"^/-/places/api/lists/(?P<list_id>\d+)$")
async def api_get_list(datasette, request, list_id: int):
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    count = await db.place_count_for_list(list_id=list_id)
    me = actor_id(request)
    is_owner = pl.created_by is not None and pl.created_by == me
    can_edit = await datasette.allowed(
        action=ACTION_EDIT,
        resource=PlacesListResource(list_id),
        actor=request.actor,
    )
    can_manage = await can_places_manage(datasette, request.actor, list_id)
    return Response.json(
        {
            "id": pl.id,
            "name": pl.name,
            "description": pl.description,
            "created_by": pl.created_by,
            "state": pl.state,
            "place_count": count,
            "updated_at": pl.updated_at,
            "permissions": {
                "canView": True,
                "canEdit": can_edit,
                "canManage": can_manage,
                "isOwner": is_owner,
            },
        }
    )


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/rename$")
async def api_rename_list(datasette, request, list_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    body = await read_json_body(request)
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return Response.json({"error": "name is required"}, status=400)
    pl = await db.update_list_name(list_id=list_id, name=new_name)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    return Response.json({"id": pl.id, "name": pl.name, "updated_at": pl.updated_at})


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/describe$")
async def api_describe_list(datasette, request, list_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    body = await read_json_body(request)
    # An empty string clears the description; missing key is treated the same.
    raw = body.get("description")
    description = raw.strip() if isinstance(raw, str) and raw.strip() else None
    pl = await db.update_list_description(list_id=list_id, description=description)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    return Response.json(
        {"id": pl.id, "description": pl.description, "updated_at": pl.updated_at}
    )


async def _ensure_owner(datasette, request, list_id: int):
    """View-permission check then escalate to manage (owner-only) capability.

    Trash / restore are now gated by the acl ``places-manage`` capability (the
    owner gets it via the seeded Manager grant) rather than a created_by-equality
    check.
    """
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return None
    if not await can_places_manage(datasette, request.actor, list_id):
        raise Forbidden(ACTION_MANAGE)
    return pl


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/trash$")
async def api_trash_list(datasette, request, list_id: int):
    pl = await _ensure_owner(datasette, request, list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    db = places_db(datasette)
    await db.trash_list(list_id=list_id)
    return Response.json({"ok": True})


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/restore$")
async def api_restore_list(datasette, request, list_id: int):
    pl = await _ensure_owner(datasette, request, list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    db = places_db(datasette)
    await db.restore_list(list_id=list_id)
    return Response.json({"ok": True})


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@router.GET(r"^/-/places/?$")
async def places_index_page(datasette, request):
    await ensure_places_list(datasette, request)
    return Response.html(
        await datasette.render_template(
            "places_base.html",
            {
                "page_title": "Places",
                "entrypoint": "src/pages/index/main.ts",
                "page_data": {},
            },
            request=request,
        )
    )


@router.GET(r"^/-/places/list/(?P<list_id>\d+)$")
async def places_list_page(datasette, request, list_id: int):
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.html("List not found", status=404)
    return Response.html(
        await datasette.render_template(
            "places_base.html",
            {
                "page_title": pl.name or f"Places {list_id}",
                "entrypoint": "src/pages/list/main.ts",
                # actor is surfaced so the embedded <datasette-acl-share-dialog> can
                # mark the current user's row "(you)".
                "page_data": {
                    "list_id": list_id,
                    "actor": request.actor,
                },
            },
            request=request,
        )
    )
