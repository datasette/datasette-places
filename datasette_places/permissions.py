"""Permission model for datasette-places.

Four actions:
    - ``datasette-places-list``    (global)          — see the index page
    - ``datasette-places-create``  (global)          — create new lists
    - ``datasette-places-view``    (PlacesResource)  — view a specific list
    - ``datasette-places-edit``    (PlacesResource)  — edit a specific list

Per-list actions resolved via permission_resources_sql with three rule
sets: owner, shared, visibility.
"""

from __future__ import annotations

from datasette import hookimpl
from datasette.permissions import PermissionSQL, Resource


class PlacesResource(Resource):
    """A single place list. Single-level: list_id in parent, child=None."""

    name = "places"
    parent_class = None

    def __init__(self, list_id):
        super().__init__(parent=str(list_id), child=None)

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        return (
            "SELECT CAST(id AS TEXT) AS parent, NULL AS child "
            "FROM _datasette_places_list"
        )


@hookimpl
async def permission_resources_sql(datasette, actor, action):
    if action not in ("datasette-places-view", "datasette-places-edit"):
        return None

    actor_id = actor.get("id") if actor else None
    is_edit = action == "datasette-places-edit"
    role_filter = "AND s.role = 'editor'" if is_edit else ""

    rules = [
        # Owner rule
        PermissionSQL(
            sql=(
                "SELECT CAST(id AS TEXT) AS parent, NULL AS child, "
                "1 AS allow, 'owner' AS reason "
                "FROM _datasette_places_list "
                "WHERE :_places_aid IS NOT NULL AND created_by = :_places_aid"
            ),
            params={"_places_aid": actor_id},
        ),
        # Explicit per-actor shares
        PermissionSQL(
            sql=(
                "SELECT CAST(s.list_id AS TEXT) AS parent, NULL AS child, "
                "1 AS allow, 'shared' AS reason "
                "FROM _datasette_places_share s "
                "WHERE :_places_aid IS NOT NULL AND s.actor_id = :_places_aid "
                f"{role_filter}"
            ),
            params={"_places_aid": actor_id},
        ),
    ]

    # Visibility-based grants
    if await datasette.allowed(action="datasette-places-list", actor=actor):
        if action == "datasette-places-view":
            visibilities = "('link-view','link-edit')"
        else:
            visibilities = "('link-edit')"
        rules.append(
            PermissionSQL(
                sql=(
                    "SELECT CAST(id AS TEXT) AS parent, NULL AS child, "
                    "1 AS allow, 'visibility' AS reason "
                    f"FROM _datasette_places_list WHERE visibility IN {visibilities}"
                ),
            )
        )

    return rules


# ---------------------------------------------------------------------------
# Per-action helpers
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
        action="datasette-places-view",
        resource=PlacesResource(list_id),
        actor=request.actor,
    )


async def ensure_places_edit(datasette, request, list_id) -> None:
    await datasette.ensure_permission(
        action="datasette-places-edit",
        resource=PlacesResource(list_id),
        actor=request.actor,
    )
