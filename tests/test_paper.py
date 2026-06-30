"""Tests for the datasette-paper embed provider (datasette_places.paper).

Under the current paper API the backend is a thin *descriptor* only: it
declares the provider's `kind`, the ref namespace it owns, the `/`-menu source,
and where its JS/CSS bundle lives. Resolve/render/search all moved client-side
(see frontend/src/pages/paper-embed/main.ts) and are not exercised here.
"""

from datasette.app import Datasette

from datasette_places.paper import (
    PlacesEmbedProvider,
    paper_embed_provider,
)


def test_descriptor_fields():
    p = PlacesEmbedProvider()
    # `kind` must match the bundle's default-exported provider kind.
    assert p.kind == "place-list"
    assert p.label == "Places map"
    # Stored refs (/-/places/list/{id}) all live under this namespace, so paper
    # can lazy-load the bundle for a doc's embeds before running matchRef.
    assert p.ref_prefixes == ["/-/places/"]


def test_sources_mirror_the_bundle_picker():
    # The `/`-menu source paper shows before the bundle loads; must mirror the
    # bundle's picker() in main.ts.
    assert PlacesEmbedProvider().sources == [
        {"id": "places", "label": "Places map", "icon": "globe", "mode": "block"},
    ]


def test_frontend_assets_shape():
    assets = PlacesEmbedProvider().frontend_assets(Datasette(memory=True))
    assert set(assets) == {"js", "css"}
    assert isinstance(assets["js"], list)
    assert isinstance(assets["css"], list)


def test_hook_returns_provider():
    provider = paper_embed_provider(datasette=Datasette(memory=True))
    assert isinstance(provider, PlacesEmbedProvider)
