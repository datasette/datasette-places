import re
from collections import defaultdict

from datasette import hookimpl, Response
from datasette.permissions import Action
from datasette_vite import vite_entry

from .router import router
from .permissions import (  # noqa: F401
    AclRole,
    PlacesListResource,
    PLACES_LIST_RESOURCE_TYPE,
)
from . import routes  # noqa: F401 — triggers decorator registration


# The list page is the only places page that hosts <datasette-share-dialog>, so
# the share bundle is included there (opt-in) rather than site-wide. Matches
# ``/-/places/list/<id>`` exactly — not the index or any API route.
_LIST_PAGE_RE = re.compile(r"^/-/places/list/\d+$")


def _is_list_page(request) -> bool:
    return bool(request and _LIST_PAGE_RE.match(request.path or ""))


# datasette-share is an optional sibling plugin (local editable dev dep). When
# it isn't installed the asset helper is unavailable, so the list page simply
# renders without the share dialog rather than erroring.
try:
    from datasette_share import datasette_share_assets as _share_assets
except ImportError:  # pragma: no cover
    _share_assets = None


def _method_dispatch_routes(raw_routes):
    """Combine routes with the same path pattern into method-dispatching views."""
    by_path = defaultdict(dict)
    order = []

    for entry in router._routes:
        path = entry.path
        method = entry.method.upper()
        if path not in by_path:
            order.append(path)
        by_path[path][method] = entry.fn

    result = []
    for path in order:
        method_map = by_path[path]
        if len(method_map) == 1:
            result.append((path, next(iter(method_map.values()))))
        else:

            def _make_dispatcher(m):
                async def dispatcher(
                    request,
                    datasette=None,
                    scope=None,
                    receive=None,
                    send=None,
                ):
                    method = request.method.upper()
                    handler = m.get(method)
                    if handler is None:
                        allowed = ", ".join(sorted(m.keys()))
                        return Response(
                            f"Method {method} not allowed",
                            status=405,
                            headers={"Allow": allowed},
                        )
                    return await handler(
                        request,
                        datasette=datasette,
                        scope=scope,
                        receive=receive,
                        send=send,
                    )

                return dispatcher

            result.append((path, _make_dispatcher(dict(method_map))))

    return result


@hookimpl
def extra_template_vars(datasette):
    return {
        "datasette_places_vite_entry": vite_entry(
            datasette=datasette,
            plugin_package="datasette_places",
        ),
    }


@hookimpl
def extra_js_urls(datasette, request):
    """Include the <datasette-share-dialog> JS bundle on the list page only."""
    if _share_assets is None or not _is_list_page(request):
        return []
    return _share_assets(datasette)["js"]


@hookimpl
def extra_css_urls(datasette, request):
    """Include the <datasette-share-dialog> CSS on the list page only."""
    if _share_assets is None or not _is_list_page(request):
        return []
    return _share_assets(datasette)["css"]


@hookimpl
def register_routes():
    return _method_dispatch_routes(router._routes)


@hookimpl
def register_actions(datasette):
    return [
        # --- Global actions (unchanged) -------------------------------------
        Action(
            name="datasette-places-list",
            description="Can list place lists (see the index page)",
        ),
        Action(
            name="datasette-places-create",
            description="Can create new place lists",
            also_requires="datasette-places-list",
        ),
        # --- acl-backed resource actions ------------------------------------
        # These resolve against datasette-acl grants on PlacesListResource.
        # Every per-list permission check goes through these; places no longer
        # ships owner/shared/visibility SQL.
        Action(
            name="places-view",
            description="View a place list",
            resource_class=PlacesListResource,
        ),
        Action(
            name="places-edit",
            description="Edit a place list",
            resource_class=PlacesListResource,
            also_requires="places-view",
        ),
        Action(
            name="places-manage",
            description="Manage sharing for a place list",
            resource_class=PlacesListResource,
            also_requires="places-view",
        ),
    ]


@hookimpl
def datasette_acl_roles(datasette):
    """Friendly Viewer / Editor / Manager roles for the ``places-list`` type.

    Consumed by datasette-acl's role registry (see ``build_roles_registry``).
    No-op when acl is not installed (``AclRole is None``).
    """
    if AclRole is None:
        return []
    return [
        AclRole(
            resource_type=PLACES_LIST_RESOURCE_TYPE,
            name="Viewer",
            actions=["places-view"],
            rank=1,
            description="Can view the list",
        ),
        AclRole(
            resource_type=PLACES_LIST_RESOURCE_TYPE,
            name="Editor",
            actions=["places-view", "places-edit"],
            rank=2,
            description="Can view and edit the list",
        ),
        AclRole(
            resource_type=PLACES_LIST_RESOURCE_TYPE,
            name="Manager",
            actions=["places-view", "places-edit", "places-manage"],
            rank=3,
            manage=True,
            description="Can view, edit, and manage sharing",
        ),
    ]


@hookimpl
def menu_links(datasette, actor, request=None):
    async def inner():
        if await datasette.allowed(action="datasette-places-list", actor=actor):
            return [
                {
                    "href": datasette.urls.path("/-/places/"),
                    "label": "Places",
                }
            ]
        return []

    return inner


@hookimpl
async def startup(datasette):
    from .migrations import ensure_migrations, migrate_shares_to_acl

    internal = datasette.get_internal_database()
    await ensure_migrations(internal)
    # One-time backfill of legacy visibility/share rows into acl grants. Runs
    # after the schema migrations (it reads _datasette_places_list /
    # _datasette_places_share) and is guarded by its own marker so it's a no-op
    # on every startup after the first. Safe when acl isn't installed.
    await migrate_shares_to_acl(datasette)
