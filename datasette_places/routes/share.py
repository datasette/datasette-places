"""Route handlers for share management."""

from datasette import Forbidden, Response

from ..router import router
from ..permissions import ensure_places_edit
from ..util import read_json_body, actor_id, places_db


VALID_VISIBILITIES = ("private", "link-view", "link-edit")
VALID_ROLES = ("viewer", "editor")


@router.GET(r"^/-/places/api/lists/(?P<list_id>\d+)/share$")
async def get_share(datasette, request, list_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    shares = await db.select_shares(list_id=list_id)
    me = actor_id(request)
    can_manage = pl.created_by is not None and pl.created_by == me
    return Response.json(
        {
            "visibility": pl.visibility,
            "owner": pl.created_by,
            "shares": [
                {
                    "actorID": s.actor_id,
                    "role": s.role,
                    "grantedAt": s.granted_at,
                }
                for s in shares
            ],
            "canManage": can_manage,
        }
    )


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/share$")
async def post_share(datasette, request, list_id: int):
    await ensure_places_edit(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)

    me = actor_id(request)
    if pl.created_by is None or pl.created_by != me:
        raise Forbidden("datasette-places-manage")

    body = await read_json_body(request)
    visibility = body.get("visibility")
    if visibility not in VALID_VISIBILITIES:
        return Response.json(
            {"error": f"visibility must be one of: {', '.join(VALID_VISIBILITIES)}"},
            status=400,
        )

    raw_shares = body.get("shares", [])
    if not isinstance(raw_shares, list):
        return Response.json({"error": "shares must be a list"}, status=400)

    seen: set[str] = set()
    parsed: list[tuple[str, str]] = []
    for entry in raw_shares:
        if not isinstance(entry, dict):
            return Response.json(
                {"error": "each share must be an object"}, status=400
            )
        actor_value = entry.get("actorID")
        role = entry.get("role")
        if not isinstance(actor_value, str) or not actor_value.strip():
            return Response.json(
                {"error": "actorID must be a non-empty string"}, status=400
            )
        if role not in VALID_ROLES:
            return Response.json(
                {"error": f"role must be one of: {', '.join(VALID_ROLES)}"},
                status=400,
            )
        actor_value = actor_value.strip()
        if actor_value == pl.created_by:
            return Response.json(
                {"error": "owner cannot appear in shares"}, status=400
            )
        if actor_value in seen:
            return Response.json(
                {"error": f"duplicate actor in shares: {actor_value}"}, status=400
            )
        seen.add(actor_value)
        parsed.append((actor_value, role))

    await db.replace_shares(
        list_id=list_id,
        visibility=visibility,
        shares=parsed,
        granted_by=me,
    )

    refreshed = await db.select_list_by_id(list_id)
    shares_after = await db.select_shares(list_id=list_id)
    return Response.json(
        {
            "visibility": refreshed.visibility,
            "owner": refreshed.created_by,
            "shares": [
                {
                    "actorID": s.actor_id,
                    "role": s.role,
                    "grantedAt": s.granted_at,
                }
                for s in shares_after
            ],
            "canManage": True,
        }
    )
