import json
import pytest


async def _create_list(ds, name="Test List"):
    resp = await ds.client.post(
        "/-/places/api/lists",
        content=json.dumps({"name": name}),
        headers={"content-type": "application/json"},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_add_place(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps(
            {
                "name": "Blue Bottle Coffee",
                "address": "123 Main St, SF",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "notes": "Great pour-over",
                "color": "#ef4444",
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Blue Bottle Coffee"
    assert data["latitude"] == 37.7749
    assert data["longitude"] == -122.4194
    assert data["color"] == "#ef4444"


@pytest.mark.asyncio
async def test_list_places(ds):
    list_id = await _create_list(ds)

    for name, lat, lon in [("A", 1.0, 2.0), ("B", 3.0, 4.0)]:
        await ds.client.post(
            f"/-/places/api/lists/{list_id}/places",
            content=json.dumps({"name": name, "latitude": lat, "longitude": lon}),
            headers={"content-type": "application/json"},
        )

    resp = await ds.client.get(f"/-/places/api/lists/{list_id}/places")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["places"]) == 2
    assert data["places"][0]["name"] == "A"
    assert data["places"][1]["name"] == "B"


@pytest.mark.asyncio
async def test_update_place(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps({"name": "Original", "latitude": 1.0, "longitude": 2.0}),
        headers={"content-type": "application/json"},
    )
    place_id = resp.json()["id"]

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places/{place_id}/update",
        content=json.dumps({"name": "Updated", "notes": "New note"}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated"
    assert data["notes"] == "New note"
    assert data["latitude"] == 1.0  # unchanged


@pytest.mark.asyncio
async def test_delete_place(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps({"name": "Gone", "latitude": 1.0, "longitude": 2.0}),
        headers={"content-type": "application/json"},
    )
    place_id = resp.json()["id"]

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places/{place_id}/delete",
        content="{}",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = await ds.client.get(f"/-/places/api/lists/{list_id}/places")
    assert len(resp.json()["places"]) == 0


@pytest.mark.asyncio
async def test_place_count_in_list(ds):
    list_id = await _create_list(ds)

    await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps({"name": "P1", "latitude": 1.0, "longitude": 2.0}),
        headers={"content-type": "application/json"},
    )

    resp = await ds.client.get("/-/places/api/lists")
    assert resp.json()[0]["place_count"] == 1


@pytest.mark.asyncio
async def test_add_place_with_metadata(ds):
    list_id = await _create_list(ds)

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps(
            {
                "name": "Tagged",
                "latitude": 1.0,
                "longitude": 2.0,
                "metadata": {"rating": "5", "wifi": "yes"},
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["metadata"] == {"rating": "5", "wifi": "yes"}


@pytest.mark.asyncio
async def test_add_place_validation(ds):
    list_id = await _create_list(ds)

    # Missing name
    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps({"latitude": 1.0, "longitude": 2.0}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400

    # Missing lat/lon
    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps({"name": "X"}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
