"""Tests for the acl-backed places-list resource model (phase-06/01).

Covers the resource/actions/roles and that every per-list permission check now
resolves through datasette-acl grants on ``PlacesListResource`` via
``datasette.allowed(action="places-edit", resource=PlacesListResource(list_id),
...)``. Grants are written via acl's ``grant`` helper; the creator gets a
Manager grant seeded on create.
"""

import json
import pytest
from datasette.app import Datasette

from datasette_places.permissions import (
    PLACES_LIST_ACTIONS,
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


def _actor_cookie(ds, actor_id):
    return ds.sign({"a": {"id": actor_id}}, "actor")


async def _create_list(ds, actor_id="alice", name="L"):
    cookies = {"ds_actor": _actor_cookie(ds, actor_id)}
    r = await ds.client.post(
        "/-/places/api/lists",
        content=json.dumps({"name": name}),
        headers={"content-type": "application/json"},
        cookies=cookies,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _grant(ds, list_id, actor_id, role):
    from datasette_acl.grants import grant, Principal

    await grant(
        ds,
        PLACES_LIST_RESOURCE_TYPE,
        str(list_id),
        principal=Principal.actor(actor_id),
        role=role,
        by_actor="alice",
    )


async def _revoke(ds, list_id, actor_id):
    from datasette_acl.grants import revoke, Principal

    await revoke(
        ds,
        PLACES_LIST_RESOURCE_TYPE,
        str(list_id),
        principal=Principal.actor(actor_id),
        by_actor="alice",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_actions_registered():
    ds = await _make_ds()
    for action in PLACES_LIST_ACTIONS:
        assert action in ds.actions, f"{action} not registered"
        assert ds.actions[action].resource_class is PlacesListResource

    # Legacy resource-scoped string actions are gone — acl resolves them now.
    for legacy in ("datasette-places-view", "datasette-places-edit"):
        assert legacy not in ds.actions


@pytest.mark.asyncio
async def test_roles_registered():
    from datasette_acl.roles import roles_for

    ds = await _make_ds()
    # acl resolves roles on demand from the datasette_acl_roles hook (no
    # startup-populated registry attribute any more).
    roles = roles_for(ds, PLACES_LIST_RESOURCE_TYPE)
    assert roles, "places-list roles not registered with acl"
    by_name = {r.name: r for r in roles}
    assert set(by_name) == {"Viewer", "Editor", "Manager"}
    assert by_name["Viewer"].actions == ["places-view"]
    assert by_name["Editor"].actions == ["places-view", "places-edit"]
    assert by_name["Manager"].actions == [
        "places-view",
        "places-edit",
        "places-manage",
    ]
    assert (
        by_name["Viewer"].rank,
        by_name["Editor"].rank,
        by_name["Manager"].rank,
    ) == (1, 2, 3)
    assert by_name["Manager"].manage is True
    assert by_name["Viewer"].manage is False
    assert by_name["Editor"].manage is False


# ---------------------------------------------------------------------------
# resources_sql + construction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resources_sql_lists_lists():
    ds = await _make_ds()
    list_a = await _create_list(ds, name="A")
    list_b = await _create_list(ds, name="B")

    sql = await PlacesListResource.resources_sql(ds)
    rows = (await ds.get_internal_database().execute(sql)).rows
    pairs = {(row["parent"], row["child"]) for row in rows}
    assert (str(list_a), None) in pairs
    assert (str(list_b), None) in pairs


@pytest.mark.asyncio
async def test_resource_construction_parent_only():
    res = PlacesListResource(7)
    assert res.parent == "7"
    assert res.child is None


@pytest.mark.asyncio
async def test_build_resource_roundtrips_via_acl():
    from datasette_acl.utils import build_resource

    ds = await _make_ds()
    res = build_resource(ds, PLACES_LIST_RESOURCE_TYPE, "9")
    assert isinstance(res, PlacesListResource)
    assert res.parent == "9"
    assert res.child is None


# ---------------------------------------------------------------------------
# Creator gets Manager on create (no lockout)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_view_edit_manage_own_list():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")

    res = PlacesListResource(list_id)
    for action in ("places-view", "places-edit", "places-manage"):
        assert await ds.allowed(action=action, resource=res, actor={"id": "alice"}), (
            action
        )


@pytest.mark.asyncio
async def test_anonymous_create_seeds_no_grant():
    """Anonymous create (no actor) → no owner grant, owner-only stays closed."""
    from datasette_places.db import PlacesDB

    ds = await _make_ds()
    db = PlacesDB(ds.get_internal_database())
    pl = await db.insert_list(name="Orphan", created_by=None)

    res = PlacesListResource(pl.id)
    assert not await ds.allowed(action="places-view", resource=res, actor=None)
    assert not await ds.allowed(
        action="places-view", resource=res, actor={"id": "anyone"}
    )


# ---------------------------------------------------------------------------
# Grants resolve via datasette.allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stranger_denied_on_private_list():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")

    res = PlacesListResource(list_id)
    assert not await ds.allowed(action="places-view", resource=res, actor={"id": "bob"})
    assert not await ds.allowed(action="places-edit", resource=res, actor={"id": "bob"})


@pytest.mark.asyncio
async def test_viewer_grant_allows_view_not_edit():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    await _grant(ds, list_id, "carol", "Viewer")

    res = PlacesListResource(list_id)
    assert await ds.allowed(action="places-view", resource=res, actor={"id": "carol"})
    assert not await ds.allowed(
        action="places-edit", resource=res, actor={"id": "carol"}
    )


@pytest.mark.asyncio
async def test_editor_grant_allows_view_and_edit_not_manage():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    await _grant(ds, list_id, "bob", "Editor")

    res = PlacesListResource(list_id)
    assert await ds.allowed(action="places-view", resource=res, actor={"id": "bob"})
    assert await ds.allowed(action="places-edit", resource=res, actor={"id": "bob"})
    assert not await ds.allowed(
        action="places-manage", resource=res, actor={"id": "bob"}
    )


@pytest.mark.asyncio
async def test_manager_grant_allows_all_three():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    await _grant(ds, list_id, "dave", "Manager")

    res = PlacesListResource(list_id)
    for action in ("places-view", "places-edit", "places-manage"):
        assert await ds.allowed(action=action, resource=res, actor={"id": "dave"}), (
            action
        )


@pytest.mark.asyncio
async def test_revoke_denies_again():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    await _grant(ds, list_id, "bob", "Editor")

    res = PlacesListResource(list_id)
    assert await ds.allowed(action="places-edit", resource=res, actor={"id": "bob"})

    await _revoke(ds, list_id, "bob")
    assert not await ds.allowed(action="places-view", resource=res, actor={"id": "bob"})
    assert not await ds.allowed(action="places-edit", resource=res, actor={"id": "bob"})


@pytest.mark.asyncio
async def test_grant_scoped_to_specific_list():
    ds = await _make_ds()
    list_a = await _create_list(ds, name="A")
    list_b = await _create_list(ds, name="B")
    await _grant(ds, list_a, "bob", "Editor")

    assert await ds.allowed(
        action="places-edit", resource=PlacesListResource(list_a), actor={"id": "bob"}
    )
    assert not await ds.allowed(
        action="places-edit", resource=PlacesListResource(list_b), actor={"id": "bob"}
    )


# ---------------------------------------------------------------------------
# Route-level: editor grant unblocks the edit endpoints; trash is manager-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_editor_can_hit_edit_route_viewer_cannot():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    await _grant(ds, list_id, "bob", "Editor")
    await _grant(ds, list_id, "carol", "Viewer")

    # Editor bob can rename.
    r = await ds.client.post(
        f"/-/places/api/lists/{list_id}/rename",
        content=json.dumps({"name": "Renamed"}),
        headers={"content-type": "application/json"},
        cookies={"ds_actor": _actor_cookie(ds, "bob")},
    )
    assert r.status_code == 200

    # Viewer carol cannot rename (edit also-requires view, which she has, but
    # not edit).
    r = await ds.client.post(
        f"/-/places/api/lists/{list_id}/rename",
        content=json.dumps({"name": "Nope"}),
        headers={"content-type": "application/json"},
        cookies={"ds_actor": _actor_cookie(ds, "carol")},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_trash_is_manager_only():
    ds = await _make_ds()
    list_id = await _create_list(ds, actor_id="alice")
    await _grant(ds, list_id, "bob", "Editor")

    # Editor cannot trash (manage-only).
    r = await ds.client.post(
        f"/-/places/api/lists/{list_id}/trash",
        content="{}",
        headers={"content-type": "application/json"},
        cookies={"ds_actor": _actor_cookie(ds, "bob")},
    )
    assert r.status_code == 403

    # Owner (Manager) can trash.
    r = await ds.client.post(
        f"/-/places/api/lists/{list_id}/trash",
        content="{}",
        headers={"content-type": "application/json"},
        cookies={"ds_actor": _actor_cookie(ds, "alice")},
    )
    assert r.status_code == 200
