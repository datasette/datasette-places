"""datasette-paper integration: a `paper_resource_provider` so a Places map
can be referenced/embedded inside a paper document.

Claims ``/-/places/list/{id}`` URLs. ``resolve`` returns the list's name (+ a
globe icon hint) for the inline pill; ``render`` returns the same identity —
the actual map is drawn client-side by the ``<datasette-places-map>`` web
component (see ``frontend/src/pages/paper-embed/main.ts``), which paper loads
via the ``frontend_assets`` declared here and which fetches its own place data
from the Places API. Permission is ours: an actor without ``places-view`` gets
``denied`` with no name leaked.

The hook is a no-op unless datasette-paper is installed (it owns the
``paper_resource_provider`` spec); when absent, nothing calls this.
"""

from __future__ import annotations

import re

from datasette import hookimpl
from datasette_vite import vite_css_urls, vite_js_urls

from .permissions import PlacesListResource
from .util import places_db

# Vite entry that defines the web component + registers the paper renderer.
_PAPER_EMBED_ENTRY = "src/pages/paper-embed/main.ts"

_LIST_RE = re.compile(r"^/-/places/list/(\d+)/?$")


class PlacesResourceProvider:
    """Resolves/renders ``/-/places/list/{id}`` refs for datasette-paper."""

    def claims(self, ref):
        return bool(_LIST_RE.match(ref or ""))

    def _list_id(self, ref):
        match = _LIST_RE.match(ref or "")
        return int(match.group(1)) if match else None

    async def resolve(self, datasette, actor, ref):
        list_id = self._list_id(ref)
        if list_id is None:
            return {"status": "not_found"}
        # Permission first so a denied actor never learns the list exists.
        allowed = await datasette.allowed(
            action="places-view",
            resource=PlacesListResource(list_id),
            actor=actor,
        )
        if not allowed:
            return {"status": "denied"}
        row = await places_db(datasette).select_list_by_id(list_id)
        if row is None or row.state != "active":
            return {"status": "not_found"}
        return {
            "status": "ok",
            "kind": "place-list",
            "label": row.name,
            "icon": "globe",
            "href": datasette.urls.path(f"/-/places/list/{list_id}"),
        }

    async def render(self, datasette, actor, ref, mode, limit):
        # Identity only — the web component fetches place data itself.
        return await self.resolve(datasette, actor, ref)

    def frontend_assets(self, datasette):
        return {
            "js": vite_js_urls(
                datasette=datasette,
                entrypoint=_PAPER_EMBED_ENTRY,
                plugin_package="datasette_places",
            ),
            "css": vite_css_urls(
                datasette=datasette,
                entrypoint=_PAPER_EMBED_ENTRY,
                plugin_package="datasette_places",
            ),
        }


@hookimpl
def paper_resource_provider(datasette):
    return PlacesResourceProvider()
