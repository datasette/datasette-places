"""Permission model for datasette-places.

Per-list access is answered by **datasette-acl**: the ``places-view`` /
``places-edit`` / ``places-manage`` actions resolve against acl grants on the
:class:`PlacesListResource` resource (type ``places-list``). places no longer
ships owner/shared/visibility permission SQL — owner semantics come from a
Manager grant seeded for ``created_by`` on create (see
:func:`seed_owner_manager_grant`); shares and general access are acl grants
written through the share UI / data migration.

Unlike datasette-paper, places has no ``locked`` read-only flag, so it keeps
**no** bespoke permission SQL at all — every per-list check goes through acl.

Two global actions remain config-driven (handled by Datasette's standard
config-permissions plugin from the ``permissions:`` block):

    - ``datasette-places-list``    — see the index page + list endpoint
    - ``datasette-places-create``  — POST /-/places/api/lists
"""

from __future__ import annotations

from datasette.permissions import Resource

try:  # acl is a soft dependency — the roles hook + grant seeding no-op when absent.
    from datasette_acl.roles import AclRole
except ImportError:  # pragma: no cover
    AclRole = None

try:
    from datasette_acl.grants import grant as _acl_grant
except ImportError:  # pragma: no cover
    _acl_grant = None


# Resource type name for the acl-backed model.
PLACES_LIST_RESOURCE_TYPE = "places-list"

# Resource-scoped actions, resolved by datasette-acl against grants on
# PlacesListResource.
PLACES_LIST_ACTIONS = (
    "places-view",
    "places-edit",
    "places-manage",
)


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


async def seed_owner_manager_grant(datasette, list_id, created_by) -> None:
    """Grant the list creator the Manager role on the new list.

    Replaces the old ``created_by``-based owner SQL: ownership is now an acl
    Manager grant on the ``places-list`` resource. No-op for anonymous creates
    (``created_by`` falsy — anonymous actors never own) and when acl isn't
    installed.
    """
    if not created_by or _acl_grant is None:
        return
    await _acl_grant(
        datasette,
        PLACES_LIST_RESOURCE_TYPE,
        str(list_id),
        actor_id=str(created_by),
        role="Manager",
        by_actor=str(created_by),
    )


# ---------------------------------------------------------------------------
# Per-action helpers used by route handlers
# ---------------------------------------------------------------------------


async def ensure_places_list(datasette, request) -> None:
    await datasette.ensure_permission(
        action="datasette-places-list", actor=request.actor
    )


async def ensure_places_create(datasette, request) -> None:
    await datasette.ensure_permission(
        action="datasette-places-create", actor=request.actor
    )


async def ensure_places_view(datasette, request, list_id) -> None:
    await datasette.ensure_permission(
        action="places-view",
        resource=PlacesListResource(list_id),
        actor=request.actor,
    )


async def ensure_places_edit(datasette, request, list_id) -> None:
    await datasette.ensure_permission(
        action="places-edit",
        resource=PlacesListResource(list_id),
        actor=request.actor,
    )


async def can_places_edit(datasette, actor, list_id) -> bool:
    """Like ensure_places_edit but returns True/False without raising."""
    return await datasette.allowed(
        action="places-edit",
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
        action="places-manage",
        resource=PlacesListResource(list_id),
        actor=actor,
    )
