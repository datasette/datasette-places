"""Permission model for datasette-places.

Per-list access is answered by **datasette-acl**: the ``places-view`` /
``places-edit`` / ``places-manage`` actions resolve against acl grants on the
:class:`PlacesListResource` resource (type ``places-list``). places ships no
owner/shared/visibility permission SQL — owner semantics come from a Manager
grant seeded for ``created_by`` on create (see
:func:`seed_owner_manager_grant`); shares and general access are acl grants
written through the share UI.

places has no ``locked`` read-only flag, so it keeps **no** bespoke permission
SQL at all — every per-list check goes through acl.

Two global actions remain config-driven (handled by Datasette's standard
config-permissions plugin from the ``permissions:`` block):

    - ``datasette-places-list``    — see the index page + list endpoint
    - ``datasette-places-create``  — POST /-/places/api/lists
"""

from __future__ import annotations

from datasette.permissions import Resource

# datasette-acl is a hard dependency: the permission model resolves every
# per-list check through acl grants, so its roles + grant helpers are always
# importable.
from datasette_acl.grants import grant as _acl_grant, Principal as _Principal


# Resource type name for the acl-backed model.
PLACES_LIST_RESOURCE_TYPE = "places-list"

# Resource-scoped actions, resolved by datasette-acl against grants on
# PlacesListResource. Referenced by name throughout the plugin via these
# constants rather than bare string literals.
ACTION_VIEW = "places-view"
ACTION_EDIT = "places-edit"
ACTION_MANAGE = "places-manage"

PLACES_LIST_ACTIONS = (ACTION_VIEW, ACTION_EDIT, ACTION_MANAGE)

# Global, config-driven actions (resolved by Datasette's config-permissions
# plugin, not acl).
ACTION_LIST = "datasette-places-list"
ACTION_CREATE = "datasette-places-create"
# Admin of geocoder *instances* (create/edit/delete the named geocoders
# themselves). Config-driven and global, like list/create above. Sharing an
# instance with users/groups is a per-instance acl grant, not this.
ACTION_GEOCODER_ADMIN = "datasette-places-geocoder-admin"


# --- Geocoder instances: acl-backed resource type ---------------------------
# A geocoder instance is ACL'd the same way a list is: a parent-only acl
# resource (parent = the geocoder slug) with use/manage actions resolved by
# datasette-acl. "Anyone can add OpenCage" == geocoder-use granted to everyone;
# "only A/B/C can add the LA geocoder" == geocoder-use granted to A/B/C.
PLACES_GEOCODER_RESOURCE_TYPE = "places-geocoder"

ACTION_GEOCODER_USE = "geocoder-use"
ACTION_GEOCODER_MANAGE = "geocoder-manage"

PLACES_GEOCODER_ACTIONS = (ACTION_GEOCODER_USE, ACTION_GEOCODER_MANAGE)


class PlacesListResource(Resource):
    """A single place list, acl-backed (resource type ``places-list``).

    Parent-only resource: the list id is the ``parent`` and ``child`` is
    ``None``. This is the model the ``places-view`` / ``places-edit`` /
    ``places-manage`` actions resolve against via datasette-acl's
    ``permission_resources_sql`` and grant helpers. The single positional
    argument is the list id, matching acl's ``build_resource`` convention for
    parent-only types (``rc(parent)``).
    """

    name = PLACES_LIST_RESOURCE_TYPE
    parent_class = None

    def __init__(self, list_id):
        super().__init__(parent=str(list_id), child=None)

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        return (
            "SELECT CAST(id AS TEXT) AS parent, NULL AS child "
            "FROM _datasette_places_list"
        )


class PlacesGeocoderResource(Resource):
    """A single geocoder instance, acl-backed (resource type ``places-geocoder``).

    Parent-only: the geocoder slug is the ``parent``, ``child`` is ``None``. The
    ``geocoder-use`` / ``geocoder-manage`` actions resolve against acl grants on
    this resource, mirroring :class:`PlacesListResource`.
    """

    name = PLACES_GEOCODER_RESOURCE_TYPE
    parent_class = None

    def __init__(self, geocoder_id):
        super().__init__(parent=str(geocoder_id), child=None)

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        return "SELECT id AS parent, NULL AS child FROM _datasette_places_geocoder"


async def seed_geocoder_manager_grant(datasette, geocoder_id, created_by) -> None:
    """Grant the geocoder creator the Manager role on the new instance.

    Mirrors :func:`seed_owner_manager_grant` for lists. No-op for anonymous
    creates (``created_by`` falsy).
    """
    if not created_by:
        return
    await _acl_grant(
        datasette,
        PLACES_GEOCODER_RESOURCE_TYPE,
        str(geocoder_id),
        principal=_Principal.actor(str(created_by)),
        role="Manager",
        by_actor=str(created_by),
    )


async def grant_geocoder_use_everyone(datasette, geocoder_id, by_actor=None) -> None:
    """Make a geocoder public: grant ``geocoder-use`` to the everyone audience."""
    await _acl_grant(
        datasette,
        PLACES_GEOCODER_RESOURCE_TYPE,
        str(geocoder_id),
        principal=_Principal.everyone(),
        actions=[ACTION_GEOCODER_USE],
        by_actor=by_actor,
    )


async def grant_geocoder_use_actor(
    datasette, geocoder_id, actor_id, *, by_actor=None
) -> None:
    """Grant a single actor the User role (``geocoder-use``) on a geocoder."""
    await _acl_grant(
        datasette,
        PLACES_GEOCODER_RESOURCE_TYPE,
        str(geocoder_id),
        principal=_Principal.actor(str(actor_id)),
        role="User",
        by_actor=by_actor or "config-seed",
    )


async def can_geocoder_use(datasette, actor, geocoder_id) -> bool:
    """True when ``actor`` may use (and attach) the geocoder."""
    return await datasette.allowed(
        action=ACTION_GEOCODER_USE,
        resource=PlacesGeocoderResource(geocoder_id),
        actor=actor,
    )


async def can_geocoder_manage(datasette, actor, geocoder_id) -> bool:
    """True when ``actor`` may manage sharing for the geocoder."""
    return await datasette.allowed(
        action=ACTION_GEOCODER_MANAGE,
        resource=PlacesGeocoderResource(geocoder_id),
        actor=actor,
    )


async def seed_owner_manager_grant(datasette, list_id, created_by) -> None:
    """Grant the list creator the Manager role on the new list.

    Replaces the old ``created_by``-based owner SQL: ownership is now an acl
    Manager grant on the ``places-list`` resource. No-op for anonymous creates
    (``created_by`` falsy — anonymous actors never own).
    """
    if not created_by:
        return
    await _acl_grant(
        datasette,
        PLACES_LIST_RESOURCE_TYPE,
        str(list_id),
        principal=_Principal.actor(str(created_by)),
        role="Manager",
        by_actor=str(created_by),
    )


# ---------------------------------------------------------------------------
# Per-action helpers used by route handlers
# ---------------------------------------------------------------------------


async def ensure_places_list(datasette, request) -> None:
    await datasette.ensure_permission(action=ACTION_LIST, actor=request.actor)


async def ensure_places_create(datasette, request) -> None:
    await datasette.ensure_permission(action=ACTION_CREATE, actor=request.actor)


async def ensure_places_view(datasette, request, list_id) -> None:
    await datasette.ensure_permission(
        action=ACTION_VIEW,
        resource=PlacesListResource(list_id),
        actor=request.actor,
    )


async def ensure_places_edit(datasette, request, list_id) -> None:
    await datasette.ensure_permission(
        action=ACTION_EDIT,
        resource=PlacesListResource(list_id),
        actor=request.actor,
    )


async def can_places_edit(datasette, actor, list_id) -> bool:
    """Like ensure_places_edit but returns True/False without raising."""
    return await datasette.allowed(
        action=ACTION_EDIT,
        resource=PlacesListResource(list_id),
        actor=actor,
    )


async def can_places_manage(datasette, actor, list_id) -> bool:
    """True when ``actor`` may manage sharing for ``list_id``.

    Manage is the acl Manager-only capability (the owner gets it via the
    seeded Manager grant). Used in place of the old inline ``created_by``
    -equality owner check.
    """
    return await datasette.allowed(
        action=ACTION_MANAGE,
        resource=PlacesListResource(list_id),
        actor=actor,
    )
