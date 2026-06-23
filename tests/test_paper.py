"""Tests for the datasette-paper resource provider (datasette_places.paper).

The provider claims `/-/places/list/{id}` refs and resolves them to a label
for paper's inline pill / block embed, gated on `places-view`.
"""

import pytest
from datasette.app import Datasette

from datasette_places.paper import PlacesResourceProvider


def test_claims_only_list_urls():
    p = PlacesResourceProvider()
    assert p.claims("/-/places/list/5")
    assert p.claims("/-/places/list/5/")
    assert not p.claims("/-/places/")
    assert not p.claims("/-/places/list/abc")
    assert not p.claims("/data/vendors")
    assert not p.claims("")


async def _create_list(ds, name="City Council Map"):
    resp = await ds.client.post("/-/places/api/lists", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_resolve_ok_for_viewer(ds):
    list_id = await _create_list(ds)
    p = PlacesResourceProvider()
    # The creator (DEFAULT_ACTOR_ID) holds a Manager grant → places-view.
    out = await p.resolve(ds, {"id": "test-user"}, f"/-/places/list/{list_id}")
    assert out == {
        "status": "ok",
        "kind": "place-list",
        "label": "City Council Map",
        "icon": "globe",
        "href": f"/-/places/list/{list_id}",
    }


@pytest.mark.asyncio
async def test_resolve_denied_for_stranger_leaks_nothing(ds):
    list_id = await _create_list(ds)
    p = PlacesResourceProvider()
    out = await p.resolve(ds, {"id": "stranger"}, f"/-/places/list/{list_id}")
    assert out == {"status": "denied"}
    assert "label" not in out


@pytest.mark.asyncio
async def test_resolve_trashed_is_not_found(ds):
    list_id = await _create_list(ds)
    trash = await ds.client.post(f"/-/places/api/lists/{list_id}/trash")
    assert trash.status_code == 200, trash.text
    p = PlacesResourceProvider()
    # Creator still has the grant, so permission passes; the list is gone.
    out = await p.resolve(ds, {"id": "test-user"}, f"/-/places/list/{list_id}")
    assert out == {"status": "not_found"}


@pytest.mark.asyncio
async def test_render_returns_identity(ds):
    list_id = await _create_list(ds)
    p = PlacesResourceProvider()
    out = await p.render(
        ds, {"id": "test-user"}, f"/-/places/list/{list_id}", "map", 25
    )
    assert out["kind"] == "place-list"
    assert out["label"] == "City Council Map"


def test_frontend_assets_shape():
    p = PlacesResourceProvider()
    assets = p.frontend_assets(Datasette(memory=True))
    assert set(assets) == {"js", "css"}
    assert isinstance(assets["js"], list)
    assert isinstance(assets["css"], list)


def test_picker_shape():
    spec = PlacesResourceProvider().picker()
    assert spec == {
        "id": "places",
        "label": "Places map",
        "icon": "globe",
        "mode": "block",
    }


@pytest.mark.asyncio
async def test_search_lists_viewable_maps(ds):
    await _create_list(ds, "City Council Map")
    await _create_list(ds, "Hiking Trails")
    p = PlacesResourceProvider()
    results = await p.search(ds, {"id": "test-user"}, "", 20)
    labels = {r["label"] for r in results}
    assert {"City Council Map", "Hiking Trails"} <= labels
    # Shape: ref claimable by the provider + a place-count detail line.
    by_label = {r["label"]: r for r in results}
    council = by_label["City Council Map"]
    assert p.claims(council["ref"])
    assert council["kind"] == "place-list"
    assert "place" in council["detail"]


@pytest.mark.asyncio
async def test_search_filters_by_query(ds):
    await _create_list(ds, "City Council Map")
    await _create_list(ds, "Hiking Trails")
    p = PlacesResourceProvider()
    results = await p.search(ds, {"id": "test-user"}, "hiking", 20)
    assert [r["label"] for r in results] == ["Hiking Trails"]


@pytest.mark.asyncio
async def test_search_stranger_sees_nothing(ds):
    await _create_list(ds, "City Council Map")
    p = PlacesResourceProvider()
    # A stranger has no places-view grants → empty (no leak).
    assert await p.search(ds, {"id": "stranger"}, "", 20) == []
