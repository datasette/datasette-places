import re
from collections import defaultdict

from datasette import hookimpl, Response
from datasette.permissions import Action
from datasette_vite import vite_entry

# datasette-acl is a hard dependency: the per-list permission model resolves
# through acl grants and friendly roles, so its role factory is always
# importable.
from datasette_acl.roles import standard_roles

# datasette-acl-share is a hard dependency: the list page hosts its
# <datasette-acl-share-dialog>, so its asset helper is always importable.
from datasette_acl_share import datasette_share_assets as _share_assets

from .router import router
from .permissions import (  # noqa: F401
    ACTION_CREATE,
    ACTION_EDIT,
    ACTION_LIST,
    ACTION_MANAGE,
    ACTION_VIEW,
    PlacesListResource,
    PLACES_LIST_RESOURCE_TYPE,
)
from . import routes  # noqa: F401 — triggers decorator registration


# The list page is the only places page that hosts <datasette-acl-share-dialog>, so
# the share bundle is included there (opt-in) rather than site-wide. Matches
# ``/-/places/list/<id>`` exactly — not the index or any API route.
_LIST_PAGE_RE = re.compile(r"^/-/places/list/\d+$")


def _is_list_page(request) -> bool:
    return bool(request and _LIST_PAGE_RE.match(request.path or ""))


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
    """Include the <datasette-acl-share-dialog> JS bundle on the list page only."""
    if not _is_list_page(request):
        return []
    return _share_assets(datasette)["js"]


@hookimpl
def extra_css_urls(datasette, request):
    """Include the <datasette-acl-share-dialog> CSS on the list page only."""
    if not _is_list_page(request):
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
            name=ACTION_LIST,
            description="Can list place lists (see the index page)",
        ),
        Action(
            name=ACTION_CREATE,
            description="Can create new place lists",
            also_requires=ACTION_LIST,
        ),
        # --- acl-backed resource actions ------------------------------------
        # These resolve against datasette-acl grants on PlacesListResource.
        # Every per-list permission check goes through these; places no longer
        # ships owner/shared/visibility SQL.
        Action(
            name=ACTION_VIEW,
            description="View a place list",
            resource_class=PlacesListResource,
        ),
        Action(
            name=ACTION_EDIT,
            description="Edit a place list",
            resource_class=PlacesListResource,
            also_requires=ACTION_VIEW,
        ),
        Action(
            name=ACTION_MANAGE,
            description="Manage sharing for a place list",
            resource_class=PlacesListResource,
            also_requires=ACTION_VIEW,
        ),
    ]


@hookimpl
def datasette_acl_roles(datasette):
    """Friendly Viewer / Editor / Manager roles for the ``places-list`` type.

    Consumed by datasette-acl's role registry (see ``build_roles_registry`` /
    ``roles_for``). Built straight from acl's ``standard_roles`` factory — the
    canonical cumulative Viewer / Editor / Manager triple (Manager carries
    ``manage=True``, so ``places-manage`` authorizes re-sharing).
    """
    return standard_roles(
        PLACES_LIST_RESOURCE_TYPE,
        view=ACTION_VIEW,
        edit=ACTION_EDIT,
        manage=ACTION_MANAGE,
        descriptions={
            "Viewer": "Can view the list",
            "Editor": "Can view and edit the list",
            "Manager": "Can view, edit, and manage sharing",
        },
    )


@hookimpl
def menu_links(datasette, actor, request=None):
    async def inner():
        if await datasette.allowed(action=ACTION_LIST, actor=actor):
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
    from .migrations import ensure_migrations

    internal = datasette.get_internal_database()
    await ensure_migrations(internal)


# Bootstrap `bi-geo-alt-fill` location marker — used as the sidebar icon.
PLACES_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
    'fill="currentColor" class="bi bi-geo-alt-fill" viewBox="0 0 16 16">'
    '<path d="M8 16s6-5.686 6-10A6 6 0 0 0 2 6c0 4.314 6 10 6 10m0-7a3 3 0 '
    '1 1 0-6 3 3 0 0 1 0 6"/></svg>'
)


# Optional integration with `datasette-sidebar` — if the package is installed,
# register a Places entry. The try/except keeps the plugin import-clean when
# datasette-sidebar isn't present.
try:
    from datasette_sidebar.hookspecs import SidebarApp  # type: ignore[import-not-found]

    @hookimpl
    def datasette_sidebar_apps(datasette):
        return [
            SidebarApp(
                label="Places",
                description="Saved lists of places on a map",
                href=lambda _db: "/-/places/",
                icon=PLACES_ICON_SVG,
                color="#276890",
            )
        ]
except ImportError:
    pass
