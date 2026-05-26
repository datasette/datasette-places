"""Tests for places sharing after the datasette-share migration (phase-06/03).

Sharing now lives in datasette-acl: the embedded ``<datasette-share-dialog>``
custom element grants / updates / revokes acl grants directly against the acl
JSON API, and places no longer ships its own ``GET/POST /share`` routes, share
table, or ShareDialog. These tests cover that the legacy routes are gone, the
share bundle is included on the list page (and only there), the capability
probe answers, and an end-to-end grant/list/revoke round-trip persists in acl
exactly as the dialog would drive it.
"""

from __future__ import annotations

import json

import pytest
from datasette.app import Datasette

from datasette_places.permissions import (
    PLACES_LIST_RESOURCE_TYPE,
    PlacesListResource,
)


async def _make_ds():
    ds = Datasette(
        memory=True,
        config={
            "permissions": {
                "datasette-places-list": True,
                "datasette-places-create": True,
            }
        },
    )
    await ds.invoke_startup()
    return ds


def _cookie(ds, actor_id):
    return {"ds_actor": ds.sign({"a": {"id": actor_id}}, "actor")}


async def _create_list(ds, actor_id="alice", name="L"):
    r = await ds.client.post(
        "/-/places/api/lists",
        content=json.dumps({"name": name}),
        headers={"content-type": "application/json"},
        cookies=_cookie(ds, actor_id),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Legacy bespoke share routes are gone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_share_routes_removed():
    ds = await _make_ds()
    list_id = await _create_list(ds)

    r = await ds.client.get(
        f"/-/places/api/lists/{list_id}/share", cookies=_cookie(ds, "alice")
    )
    assert r.status_code == 404
    r = await ds.client.post(
        f"/-/places/api/lists/{list_id}/share",
        content="{}",
        headers={"content-type": "application/json"},
        cookies=_cookie(ds, "alice"),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Share bundle is included on the list page only (opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_bundle_on_list_page_only():
    from datasette_places import extra_js_urls

    ds = await _make_ds()

    class _Req:
        def __init__(self, path):
            self.path = path

    list_js = extra_js_urls(ds, _Req("/-/places/list/1"))
    assert list_js, "share bundle JS not included on the list page"

    # Not included on the index or API routes.
    assert extra_js_urls(ds, _Req("/-/places/")) == []
    assert extra_js_urls(ds, _Req("/-/places/api/lists")) == []


@pytest.mark.asyncio
async def test_capability_probe():
    ds = await _make_ds()
    r = await ds.client.get("/-/share/capabilities")
    assert r.status_code == 200
    caps = r.json()
    # groups + public are intrinsic to acl; people/agents depend on optional
    # plugins not installed here.
    assert caps["groups"] is True
    assert caps["public"] is True


# ---------------------------------------------------------------------------
# Owner round-trip through the acl JSON API (what the dialog drives)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_read_grants_via_acl_api():
    """The dialog opens by GETting the per-resource grants; the owner (Manager
    seeded on create) is authorized and sees their own grant."""
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")

    r = await ds.client.get(
        f"/-/acl/api/resource/{PLACES_LIST_RESOURCE_TYPE}/{list_id}",
        cookies=_cookie(ds, "alice"),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["can_manage"] is True
    actor_grants = {
        g["id"] for g in data["grants"] if g["principal"] == "actor"
    }
    assert "alice" in actor_grants


@pytest.mark.asyncio
async def test_grant_update_revoke_round_trip():
    """Grant bob Viewer, upgrade to Editor, then revoke — exactly the dialog's
    incremental writes — and confirm via datasette.allowed each step."""
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    res = PlacesListResource(list_id)
    base = f"/-/acl/api/resource/{PLACES_LIST_RESOURCE_TYPE}/{list_id}"
    alice = _cookie(ds, "alice")

    # Grant Viewer.
    r = await ds.client.post(
        f"{base}/grant",
        content=json.dumps({"actor_id": "bob", "role": "Viewer"}),
        headers={"content-type": "application/json"},
        cookies=alice,
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert await ds.allowed(action="places-view", resource=res, actor={"id": "bob"})
    assert not await ds.allowed(
        action="places-edit", resource=res, actor={"id": "bob"}
    )

    # Update to Editor.
    r = await ds.client.post(
        f"{base}/update",
        content=json.dumps({"actor_id": "bob", "role": "Editor"}),
        headers={"content-type": "application/json"},
        cookies=alice,
    )
    assert r.status_code == 200, r.text
    assert await ds.allowed(action="places-edit", resource=res, actor={"id": "bob"})

    # Revoke.
    r = await ds.client.post(
        f"{base}/revoke",
        content=json.dumps({"actor_id": "bob"}),
        headers={"content-type": "application/json"},
        cookies=alice,
    )
    assert r.status_code == 200, r.text
    assert not await ds.allowed(
        action="places-view", resource=res, actor={"id": "bob"}
    )


@pytest.mark.asyncio
async def test_non_manager_cannot_grant():
    """A stranger (no grant) cannot drive the acl mutation endpoints."""
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")

    r = await ds.client.post(
        f"/-/acl/api/resource/{PLACES_LIST_RESOURCE_TYPE}/{list_id}/grant",
        content=json.dumps({"actor_id": "carol", "role": "Viewer"}),
        headers={"content-type": "application/json"},
        cookies=_cookie(ds, "mallory"),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# General access (wildcard) grants via the API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_general_access_signed_in_grant():
    """A general-access Viewer grant for _signed_in opens view to any signed-in
    actor but not anonymous — the dialog's 'General access' section."""
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    res = PlacesListResource(list_id)

    r = await ds.client.post(
        f"/-/acl/api/resource/{PLACES_LIST_RESOURCE_TYPE}/{list_id}/grant",
        content=json.dumps({"actor_id": "_signed_in", "role": "Viewer"}),
        headers={"content-type": "application/json"},
        cookies=_cookie(ds, "alice"),
    )
    assert r.status_code == 200, r.text

    assert await ds.allowed(action="places-view", resource=res, actor={"id": "zed"})
    assert not await ds.allowed(action="places-view", resource=res, actor=None)
