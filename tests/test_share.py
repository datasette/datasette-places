import json
import pytest


async def _create_list(ds, name="Shared List"):
    resp = await ds.client.post(
        "/-/places/api/lists",
        content=json.dumps({"name": name}),
        headers={"content-type": "application/json"},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_get_share_state(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.get(f"/-/places/api/lists/{list_id}/share")
    assert resp.status_code == 200
    data = resp.json()
    assert data["visibility"] == "private"
    assert data["owner"] == "test-user"
    assert data["shares"] == []
    assert data["canManage"] is True


@pytest.mark.asyncio
async def test_set_share_state(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/share",
        content=json.dumps({
            "visibility": "link-view",
            "shares": [
                {"actorID": "bob", "role": "editor"},
                {"actorID": "carol", "role": "viewer"},
            ],
        }),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["visibility"] == "link-view"
    assert len(data["shares"]) == 2
    assert data["shares"][0]["actorID"] == "bob"
    assert data["shares"][0]["role"] == "editor"


@pytest.mark.asyncio
async def test_share_validation_bad_visibility(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/share",
        content=json.dumps({"visibility": "public", "shares": []}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_share_validation_duplicate_actor(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/share",
        content=json.dumps({
            "visibility": "private",
            "shares": [
                {"actorID": "bob", "role": "editor"},
                {"actorID": "bob", "role": "viewer"},
            ],
        }),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    assert "duplicate" in resp.json()["error"]


@pytest.mark.asyncio
async def test_share_validation_owner_in_shares(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/share",
        content=json.dumps({
            "visibility": "private",
            "shares": [{"actorID": "test-user", "role": "editor"}],
        }),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    assert "owner" in resp.json()["error"]
