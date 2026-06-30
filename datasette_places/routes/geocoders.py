"""Routes for geocoder instances and per-list attachments.

Two resource families:

* **Instances** — the named geocoder catalog. Listing returns the instances the
  actor may *use* (acl ``geocoder-use``); create/edit/delete require the global
  ``datasette-places-geocoder-admin`` action. Sharing an instance with other
  users/groups is done through the existing datasette-acl share UI/API, not here.
* **Attachments** — which instances are enabled on a given list. Reading needs
  ``places-view`` on the list; mutating needs ``places-manage`` on the list, and
  attaching additionally needs ``geocoder-use`` on the instance.
"""

import json

from datasette import Forbidden, Response

from ..router import router
from ..permissions import (
    ACTION_GEOCODER_ADMIN,
    ACTION_GEOCODER_USE,
    can_geocoder_manage,
    can_geocoder_use,
    ensure_places_view,
    grant_geocoder_use_everyone,
    seed_geocoder_manager_grant,
)
from ..permissions import can_places_manage
from ..util import read_json_body, actor_id, places_db

# Slug charset for new instance ids: keeps them URL/acl-parent safe.
_SLUG_OK = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def _is_valid_slug(value: str) -> bool:
    return bool(value) and all(c in _SLUG_OK for c in value)


def _geocoder_payload(g, *, can_manage=False, can_admin=False) -> dict:
    """Public JSON for a geocoder instance — never leaks secrets.

    ``config_json`` is intentionally omitted; only non-sensitive display fields
    are exposed. (Even the non-secret config can name secret refs, so it stays
    server-side.)
    """
    return {
        "id": g.id,
        "provider_type": g.provider_type,
        "label": g.label,
        "enabled": bool(g.enabled),
        "canManage": can_manage,
        "canAdmin": can_admin,
    }


# ---------------------------------------------------------------------------
# Instances (the catalog)
# ---------------------------------------------------------------------------


@router.GET(r"^/-/places/api/geocoders$")
async def api_list_geocoders(datasette, request):
    """Geocoder instances the actor may use, annotated with manage/admin flags."""
    page = await datasette.allowed_resources(
        action=ACTION_GEOCODER_USE, actor=request.actor, limit=1000
    )
    usable_ids = [r.parent for r in page.resources]
    db = places_db(datasette)
    rows = await db.list_geocoders_by_ids(usable_ids)
    can_admin = await datasette.allowed(
        action=ACTION_GEOCODER_ADMIN, actor=request.actor
    )
    out = []
    for g in rows:
        can_manage = await can_geocoder_manage(datasette, request.actor, g.id)
        out.append(_geocoder_payload(g, can_manage=can_manage, can_admin=can_admin))
    return Response.json(out)


@router.POST(r"^/-/places/api/geocoders$")
async def api_create_geocoder(datasette, request):
    await datasette.ensure_permission(action=ACTION_GEOCODER_ADMIN, actor=request.actor)
    db = places_db(datasette)
    body = await read_json_body(request)

    gid = (body.get("id") or "").strip().lower()
    if not _is_valid_slug(gid):
        return Response.json(
            {"error": "id must be a slug: lowercase letters, digits, - and _ only."},
            status=400,
        )
    provider_type = (body.get("provider_type") or "").strip()
    if not provider_type:
        return Response.json({"error": "provider_type is required."}, status=400)
    label = (body.get("label") or "").strip() or gid
    config = body.get("config") or {}
    if not isinstance(config, dict):
        return Response.json({"error": "config must be an object."}, status=400)

    if await db.select_geocoder_by_id(gid) is not None:
        return Response.json(
            {"error": f"A geocoder with id {gid!r} already exists."}, status=409
        )

    me = actor_id(request)
    g = await db.insert_geocoder(
        id=gid,
        provider_type=provider_type,
        label=label,
        config_json=json.dumps(config),
        enabled=bool(body.get("enabled", True)),
        created_by=me,
    )
    # Creator gets Manager (so they can re-share); optionally publish to everyone.
    await seed_geocoder_manager_grant(datasette, g.id, me)
    if body.get("public"):
        await grant_geocoder_use_everyone(datasette, g.id, by_actor=me)
    return Response.json(
        _geocoder_payload(g, can_manage=True, can_admin=True), status=201
    )


@router.POST(r"^/-/places/api/geocoders/(?P<geocoder_id>[a-z0-9_-]+)/update$")
async def api_update_geocoder(datasette, request, geocoder_id: str):
    await datasette.ensure_permission(action=ACTION_GEOCODER_ADMIN, actor=request.actor)
    db = places_db(datasette)
    g = await db.select_geocoder_by_id(geocoder_id)
    if g is None:
        return Response.json({"error": "Geocoder not found"}, status=404)
    body = await read_json_body(request)
    label = (body.get("label") or g.label).strip() or g.label
    if "config" in body:
        config = body.get("config") or {}
        if not isinstance(config, dict):
            return Response.json({"error": "config must be an object."}, status=400)
        config_json = json.dumps(config)
    else:
        config_json = g.config_json
    enabled = bool(body.get("enabled", bool(g.enabled)))
    updated = await db.update_geocoder(
        geocoder_id=geocoder_id, label=label, config_json=config_json, enabled=enabled
    )
    return Response.json(_geocoder_payload(updated, can_manage=True, can_admin=True))


@router.POST(r"^/-/places/api/geocoders/(?P<geocoder_id>[a-z0-9_-]+)/delete$")
async def api_delete_geocoder(datasette, request, geocoder_id: str):
    await datasette.ensure_permission(action=ACTION_GEOCODER_ADMIN, actor=request.actor)
    db = places_db(datasette)
    if await db.select_geocoder_by_id(geocoder_id) is None:
        return Response.json({"error": "Geocoder not found"}, status=404)
    # Attachments cascade via the FK; acl grants on the resource are orphaned but
    # harmless (a re-created id would inherit them — acceptable for now).
    await db.delete_geocoder(geocoder_id=geocoder_id)
    return Response.json({"ok": True})


# ---------------------------------------------------------------------------
# Per-list attachments
# ---------------------------------------------------------------------------


def _attachment_payload(row, *, can_use: bool) -> dict:
    return {
        "geocoder_id": row.geocoder_id,
        "label": row.label,
        "provider_type": row.provider_type,
        "enabled": bool(row.enabled),
        "is_default": bool(row.is_default),
        "position": row.position,
        "geocoder_enabled": bool(row.geocoder_enabled),
        "canUse": can_use,
    }


@router.GET(r"^/-/places/api/lists/(?P<list_id>\d+)/geocoders$")
async def api_list_list_geocoders(datasette, request, list_id: int):
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    rows = await db.list_geocoders_for_list(list_id=list_id)
    out = []
    for row in rows:
        can_use = await can_geocoder_use(datasette, request.actor, row.geocoder_id)
        out.append(_attachment_payload(row, can_use=can_use))
    return Response.json(out)


async def _ensure_list_manage(datasette, request, list_id: int):
    """places-view then escalate to places-manage; raises Forbidden otherwise.

    Returns the list row, or ``None`` if the list does not exist.
    """
    await ensure_places_view(datasette, request, list_id)
    db = places_db(datasette)
    pl = await db.select_list_by_id(list_id)
    if pl is None:
        return None
    if not await can_places_manage(datasette, request.actor, list_id):
        raise Forbidden("places-manage")
    return pl


@router.POST(r"^/-/places/api/lists/(?P<list_id>\d+)/geocoders$")
async def api_attach_geocoder(datasette, request, list_id: int):
    pl = await _ensure_list_manage(datasette, request, list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    db = places_db(datasette)
    body = await read_json_body(request)
    geocoder_id = (body.get("geocoder_id") or "").strip()
    if not geocoder_id:
        return Response.json({"error": "geocoder_id is required."}, status=400)
    g = await db.select_geocoder_by_id(geocoder_id)
    if g is None:
        return Response.json({"error": "Geocoder not found"}, status=404)
    # Attaching requires use rights on the geocoder (the ACL gate that makes a
    # private geocoder attachable only by authorized users).
    if not await can_geocoder_use(datasette, request.actor, geocoder_id):
        raise Forbidden(ACTION_GEOCODER_USE)
    row = await db.attach_geocoder_to_list(
        list_id=list_id, geocoder_id=geocoder_id, added_by=actor_id(request)
    )
    return Response.json(
        {
            "geocoder_id": row.geocoder_id,
            "enabled": bool(row.enabled),
            "is_default": bool(row.is_default),
            "position": row.position,
        },
        status=201,
    )


@router.POST(
    r"^/-/places/api/lists/(?P<list_id>\d+)/geocoders/(?P<geocoder_id>[a-z0-9_-]+)/update$"
)
async def api_update_list_geocoder(datasette, request, list_id: int, geocoder_id: str):
    pl = await _ensure_list_manage(datasette, request, list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    db = places_db(datasette)
    if await db.select_list_geocoder(list_id=list_id, geocoder_id=geocoder_id) is None:
        return Response.json(
            {"error": "Geocoder is not attached to this list"}, status=404
        )
    body = await read_json_body(request)
    if "enabled" in body:
        await db.set_list_geocoder_enabled(
            list_id=list_id, geocoder_id=geocoder_id, enabled=bool(body["enabled"])
        )
    if body.get("is_default"):
        await db.set_list_geocoder_default(list_id=list_id, geocoder_id=geocoder_id)
    return Response.json({"ok": True})


@router.POST(
    r"^/-/places/api/lists/(?P<list_id>\d+)/geocoders/(?P<geocoder_id>[a-z0-9_-]+)/detach$"
)
async def api_detach_geocoder(datasette, request, list_id: int, geocoder_id: str):
    pl = await _ensure_list_manage(datasette, request, list_id)
    if pl is None:
        return Response.json({"error": "List not found"}, status=404)
    db = places_db(datasette)
    await db.detach_geocoder_from_list(list_id=list_id, geocoder_id=geocoder_id)
    return Response.json({"ok": True})
