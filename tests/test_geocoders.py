"""Tests for geocoder instances, their ACL model, and per-list attachments.

Covers the ``places-geocoder`` resource type (actions/roles/resources_sql), the
admin CRUD + attachment routes, and the two access gates: attaching needs
``geocoder-use`` + ``places-manage``; querying re-checks ``geocoder-use``.
OpenCage HTTP is mocked via the ``_make_client`` seam (see test_geocode.py).
"""

from __future__ import annotations

import json

import httpx
import pytest
from datasette.app import Datasette

from datasette_places.permissions import (
    PLACES_GEOCODER_ACTIONS,
    PLACES_GEOCODER_RESOURCE_TYPE,
    PlacesGeocoderResource,
)

ADMIN = "admin"


async def _make_ds(*, with_key: bool = True) -> Datasette:
    plugins = {"opencage_api_key": "test-key"} if with_key else {}
    config = {
        "permissions": {
            "datasette-places-list": True,
            "datasette-places-create": True,
            # Only `admin` may manage the geocoder catalog.
            "datasette-places-geocoder-admin": {"id": ADMIN},
        }
    }
    if plugins:
        config["plugins"] = {"datasette-places": plugins}
    ds = Datasette(memory=True, config=config)
    await ds.invoke_startup()
    return ds


def _cookie(ds, actor_id):
    return {"ds_actor": ds.sign({"a": {"id": actor_id}}, "actor")}


async def _post(ds, path, body, actor):
    return await ds.client.post(
        path,
        content=json.dumps(body),
        headers={"content-type": "application/json"},
        cookies=_cookie(ds, actor),
    )


async def _create_geocoder(
    ds,
    *,
    gid="opencage-global",
    provider_type="opencage",
    label="OpenCage",
    config=None,
    public=False,
    actor=ADMIN,
):
    return await _post(
        ds,
        "/-/places/api/geocoders",
        {
            "id": gid,
            "provider_type": provider_type,
            "label": label,
            "config": config or {},
            "public": public,
        },
        actor,
    )


async def _create_list(ds, actor="alice", name="L"):
    r = await _post(ds, "/-/places/api/lists", {"name": name}, actor)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _grant_use(ds, geocoder_id, actor_id, role="User"):
    from datasette_acl.grants import grant, Principal

    return grant(
        ds,
        PLACES_GEOCODER_RESOURCE_TYPE,
        str(geocoder_id),
        principal=Principal.actor(actor_id),
        role=role,
        by_actor=ADMIN,
    )


def _install_mock(monkeypatch):
    def handler(req):
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "formatted": "1 Main St",
                        "geometry": {"lat": 1.0, "lng": 2.0},
                        "confidence": 9,
                        "components": {},
                    }
                ],
                "status": {"code": 200},
            },
        )

    monkeypatch.setattr(
        "datasette_places.geocoders.opencage._make_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_geocoder_actions_registered():
    ds = await _make_ds()
    for action in PLACES_GEOCODER_ACTIONS:
        assert action in ds.actions
        assert ds.actions[action].resource_class is PlacesGeocoderResource
    assert "datasette-places-geocoder-admin" in ds.actions


@pytest.mark.asyncio
async def test_geocoder_roles_registered():
    from datasette_acl.roles import roles_for

    ds = await _make_ds()
    roles = {r.name: r for r in roles_for(ds, PLACES_GEOCODER_RESOURCE_TYPE)}
    assert set(roles) == {"User", "Manager"}
    assert roles["User"].actions == ["geocoder-use"]
    assert roles["Manager"].actions == ["geocoder-use", "geocoder-manage"]
    assert roles["Manager"].manage is True
    assert roles["User"].manage is False


@pytest.mark.asyncio
async def test_resources_sql_lists_instances():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="a", label="A")
    await _create_geocoder(ds, gid="b", label="B")
    sql = await PlacesGeocoderResource.resources_sql(ds)
    rows = (await ds.get_internal_database().execute(sql)).rows
    parents = {row["parent"] for row in rows}
    assert {"a", "b"} <= parents


# ---------------------------------------------------------------------------
# Admin CRUD + gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requires_admin():
    ds = await _make_ds()
    r = await _create_geocoder(ds, actor="not-admin")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_seeds_manager_grant_for_creator():
    ds = await _make_ds()
    r = await _create_geocoder(ds, gid="g1")
    assert r.status_code == 201, r.text
    # Creator (admin) is a Manager → can use + manage.
    res = PlacesGeocoderResource("g1")
    assert await ds.allowed(action="geocoder-use", resource=res, actor={"id": ADMIN})
    assert await ds.allowed(action="geocoder-manage", resource=res, actor={"id": ADMIN})


@pytest.mark.asyncio
async def test_create_rejects_bad_slug_and_duplicate():
    ds = await _make_ds()
    bad = await _create_geocoder(ds, gid="Bad Slug!")
    assert bad.status_code == 400
    ok = await _create_geocoder(ds, gid="dup")
    assert ok.status_code == 201
    again = await _create_geocoder(ds, gid="dup")
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_public_geocoder_usable_by_anyone():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", public=True)
    res = PlacesGeocoderResource("pub")
    assert await ds.allowed(action="geocoder-use", resource=res, actor={"id": "random"})


@pytest.mark.asyncio
async def test_private_geocoder_not_usable_by_stranger():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="priv")
    res = PlacesGeocoderResource("priv")
    assert not await ds.allowed(
        action="geocoder-use", resource=res, actor={"id": "stranger"}
    )


@pytest.mark.asyncio
async def test_delete_geocoder():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="tmp")
    r = await _post(ds, "/-/places/api/geocoders/tmp/delete", {}, ADMIN)
    assert r.status_code == 200
    r = await _post(ds, "/-/places/api/geocoders/tmp/delete", {}, ADMIN)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Listing usable instances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_geocoders_returns_only_usable():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", label="Pub", public=True)
    await _create_geocoder(ds, gid="priv", label="Priv")
    await _grant_use(ds, "priv", "bob")

    # bob sees pub (everyone) + priv (granted)
    r = await ds.client.get("/-/places/api/geocoders", cookies=_cookie(ds, "bob"))
    ids = {g["id"] for g in r.json()}
    assert ids == {"pub", "priv"}

    # carol (no grant) sees only the public one
    r = await ds.client.get("/-/places/api/geocoders", cookies=_cookie(ds, "carol"))
    ids = {g["id"] for g in r.json()}
    assert ids == {"pub"}


@pytest.mark.asyncio
async def test_list_geocoders_never_leaks_config():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", public=True, config={"api_key_ref": "secret"})
    r = await ds.client.get("/-/places/api/geocoders", cookies=_cookie(ds, "x"))
    assert "config" not in r.json()[0]
    assert "config_json" not in r.json()[0]


# ---------------------------------------------------------------------------
# Attachment gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_requires_list_manage_and_geocoder_use():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="priv")
    list_id = await _create_list(ds, actor="alice")  # alice = Manager of the list

    # alice manages the list but lacks geocoder-use on priv → 403.
    r = await _post(
        ds, f"/-/places/api/lists/{list_id}/geocoders", {"geocoder_id": "priv"}, "alice"
    )
    assert r.status_code == 403

    # Grant alice use of priv → attach succeeds.
    await _grant_use(ds, "priv", "alice")
    r = await _post(
        ds, f"/-/places/api/lists/{list_id}/geocoders", {"geocoder_id": "priv"}, "alice"
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_non_manager_cannot_attach():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", public=True)
    list_id = await _create_list(ds, actor="alice")

    # bob can use pub but does not manage alice's list → 403.
    r = await _post(
        ds, f"/-/places/api/lists/{list_id}/geocoders", {"geocoder_id": "pub"}, "bob"
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_attach_list_geocoders_and_default():
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", label="Pub", public=True)
    list_id = await _create_list(ds, actor="alice")
    await _post(
        ds, f"/-/places/api/lists/{list_id}/geocoders", {"geocoder_id": "pub"}, "alice"
    )
    # Set as default.
    r = await _post(
        ds,
        f"/-/places/api/lists/{list_id}/geocoders/pub/update",
        {"is_default": True},
        "alice",
    )
    assert r.status_code == 200

    r = await ds.client.get(
        f"/-/places/api/lists/{list_id}/geocoders", cookies=_cookie(ds, "alice")
    )
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["geocoder_id"] == "pub"
    assert rows[0]["is_default"] is True
    assert rows[0]["canUse"] is True


# ---------------------------------------------------------------------------
# Query-time gate via /api/geocode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_geocode_via_instance_enforces_use(monkeypatch):
    _install_mock(monkeypatch)
    ds = await _make_ds()
    await _create_geocoder(ds, gid="priv")
    list_id = await _create_list(ds, actor="alice")
    await _grant_use(ds, "priv", "alice")
    await _post(
        ds, f"/-/places/api/lists/{list_id}/geocoders", {"geocoder_id": "priv"}, "alice"
    )

    # alice (has use + view) can geocode through the attached instance.
    r = await ds.client.get(
        f"/-/places/api/geocode?q=main&geocoder=priv&list={list_id}",
        cookies=_cookie(ds, "alice"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["latitude"] == 1.0

    # Give bob view of the list but NOT use of priv → blocked at query time.
    from datasette_acl.grants import grant, Principal
    from datasette_places.permissions import PLACES_LIST_RESOURCE_TYPE

    await grant(
        ds,
        PLACES_LIST_RESOURCE_TYPE,
        str(list_id),
        principal=Principal.actor("bob"),
        role="Viewer",
        by_actor="alice",
    )
    r = await ds.client.get(
        f"/-/places/api/geocode?q=main&geocoder=priv&list={list_id}",
        cookies=_cookie(ds, "bob"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_geocode_instance_must_be_attached(monkeypatch):
    _install_mock(monkeypatch)
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", public=True)
    list_id = await _create_list(ds, actor="alice")
    # Not attached to the list → 400 even though alice can use it.
    r = await ds.client.get(
        f"/-/places/api/geocode?q=main&geocoder=pub&list={list_id}",
        cookies=_cookie(ds, "alice"),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_geocode_uses_list_default(monkeypatch):
    _install_mock(monkeypatch)
    ds = await _make_ds()
    await _create_geocoder(ds, gid="pub", public=True)
    list_id = await _create_list(ds, actor="alice")
    await _post(
        ds, f"/-/places/api/lists/{list_id}/geocoders", {"geocoder_id": "pub"}, "alice"
    )
    await _post(
        ds,
        f"/-/places/api/lists/{list_id}/geocoders/pub/update",
        {"is_default": True},
        "alice",
    )
    # No ?geocoder= → falls back to the list default (pub).
    r = await ds.client.get(
        f"/-/places/api/geocode?q=main&list={list_id}",
        cookies=_cookie(ds, "alice"),
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_config_seed_creates_instances_and_grants():
    """Geocoders declared in plugin config are upserted on startup with grants."""
    ds = Datasette(
        memory=True,
        config={
            "permissions": {
                "datasette-places-list": True,
                "datasette-places-create": True,
            },
            "plugins": {
                "datasette-places": {
                    "opencage_api_key": "k",
                    "geocoders": [
                        {
                            "id": "ocg",
                            "provider_type": "opencage",
                            "label": "OpenCage",
                            "public": True,
                        },
                        {
                            "id": "pluto-la",
                            "provider_type": "pluto",
                            "label": "PLUTO LA",
                            "config": {"database": "pluto_la"},
                            "grant_use": {"actors": ["alice"]},
                        },
                    ],
                }
            },
        },
    )
    await ds.invoke_startup()

    # Public one usable by anyone; private one only by the granted actor.
    assert await ds.allowed(
        action="geocoder-use", resource=PlacesGeocoderResource("ocg"), actor={"id": "z"}
    )
    assert await ds.allowed(
        action="geocoder-use",
        resource=PlacesGeocoderResource("pluto-la"),
        actor={"id": "alice"},
    )
    assert not await ds.allowed(
        action="geocoder-use",
        resource=PlacesGeocoderResource("pluto-la"),
        actor={"id": "stranger"},
    )

    # Idempotent: a second startup must not raise or duplicate.
    await ds.invoke_startup()
    from datasette_places.db import PlacesDB

    rows = await PlacesDB(ds.get_internal_database()).list_geocoders()
    assert {r.id for r in rows} == {"ocg", "pluto-la"}
