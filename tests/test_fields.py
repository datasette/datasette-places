"""Tests for user-defined per-list metadata fields."""

import json

import pytest


async def _create_list(ds, name="Restaurants"):
    resp = await ds.client.post(
        "/-/places/api/lists",
        content=json.dumps({"name": name}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _add_field(ds, list_id, **body):
    return await ds.client.post(
        f"/-/places/api/lists/{list_id}/fields",
        content=json.dumps(body),
        headers={"content-type": "application/json"},
    )


async def _add_place(ds, list_id, **body):
    body.setdefault("latitude", 1.0)
    body.setdefault("longitude", 2.0)
    return await ds.client.post(
        f"/-/places/api/lists/{list_id}/places",
        content=json.dumps(body),
        headers={"content-type": "application/json"},
    )


def _cookie(ds, actor_id):
    return {"ds_actor": ds.sign({"a": {"id": actor_id}}, "actor")}


# --- Field CRUD + validation -------------------------------------------------


@pytest.mark.asyncio
async def test_field_writes_require_manage(ds):
    # owner (default actor) creates the list + a field
    list_id = await _create_list(ds)
    # a different actor with no grant cannot create a field
    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/fields",
        content=json.dumps({"key": "x", "label": "X", "type": "text"}),
        headers={"content-type": "application/json"},
        cookies=_cookie(ds, "intruder"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_field_and_list_detail(ds):
    list_id = await _create_list(ds)
    resp = await _add_field(
        ds, list_id, key="rating", label="Rating", type="rating", config={"max": 5}
    )
    assert resp.status_code == 201
    f = resp.json()
    assert f["key"] == "rating"
    assert f["type"] == "rating"
    assert f["config"] == {"max": 5}
    assert f["position"] == 0

    # second field gets the next position
    resp2 = await _add_field(ds, list_id, key="insta", label="Instagram", type="url")
    assert resp2.json()["position"] == 1

    detail = await ds.client.get(f"/-/places/api/lists/{list_id}")
    keys = [f["key"] for f in detail.json()["fields"]]
    assert keys == ["rating", "insta"]


@pytest.mark.asyncio
async def test_reserved_and_bad_keys_rejected(ds):
    list_id = await _create_list(ds)
    for bad in ("shape", "color", "name", "latitude"):
        resp = await _add_field(ds, list_id, key=bad, label="X", type="text")
        assert resp.status_code == 400, bad
        assert "reserved" in resp.json()["error"]
    for bad in ("Rating", "1abc", "has space", "a" * 64):
        resp = await _add_field(ds, list_id, key=bad, label="X", type="text")
        assert resp.status_code == 400, bad


@pytest.mark.asyncio
async def test_unknown_type_and_duplicate_key_rejected(ds):
    list_id = await _create_list(ds)
    resp = await _add_field(ds, list_id, key="x", label="X", type="bogus")
    assert resp.status_code == 400
    assert "unknown field type" in resp.json()["error"]

    assert (
        await _add_field(ds, list_id, key="dup", label="A", type="text")
    ).status_code == 201
    resp = await _add_field(ds, list_id, key="dup", label="B", type="text")
    assert resp.status_code == 400
    assert "already exists" in resp.json()["error"]


@pytest.mark.asyncio
async def test_delete_field(ds):
    list_id = await _create_list(ds)
    fid = (await _add_field(ds, list_id, key="temp", label="Temp", type="text")).json()[
        "id"
    ]
    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/fields/{fid}/delete",
        content="{}",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    detail = await ds.client.get(f"/-/places/api/lists/{list_id}")
    assert detail.json()["fields"] == []


# --- The expanded view -------------------------------------------------------


async def _view_columns(ds, list_id):
    internal = ds.get_internal_database()
    rows = await internal.execute(
        f'SELECT * FROM "_datasette_places_list_{list_id}_expanded" LIMIT 0'
    )
    return list(rows.columns)


@pytest.mark.asyncio
async def test_view_tracks_fields_and_extracts_values(ds):
    list_id = await _create_list(ds)
    await _add_field(ds, list_id, key="rating", label="Rating", type="rating")
    await _add_field(ds, list_id, key="cuisine", label="Cuisine", type="text")
    cols = await _view_columns(ds, list_id)
    assert "rating" in cols and "cuisine" in cols
    assert "name" in cols  # base column

    await _add_place(
        ds, list_id, name="Thai Place", metadata={"rating": 4, "cuisine": "thai"}
    )
    internal = ds.get_internal_database()
    row = (
        await internal.execute(
            f'SELECT rating, cuisine FROM "_datasette_places_list_{list_id}_expanded"'
        )
    ).first()
    assert row["rating"] == 4
    assert row["cuisine"] == "thai"


@pytest.mark.asyncio
async def test_unique_field_enforced_by_index(ds):
    list_id = await _create_list(ds)
    await _add_field(ds, list_id, key="code", label="Code", type="text", unique=True)

    assert (
        await _add_place(ds, list_id, name="A", metadata={"code": "x1"})
    ).status_code == 201
    # duplicate value rejected (mapped from IntegrityError to 400)
    dup = await _add_place(ds, list_id, name="B", metadata={"code": "x1"})
    assert dup.status_code == 400
    # two places with no value for the unique field are fine (NULLs don't collide)
    assert (await _add_place(ds, list_id, name="C")).status_code == 201
    assert (await _add_place(ds, list_id, name="D")).status_code == 201


@pytest.mark.asyncio
async def test_toggle_unique_off_drops_index(ds):
    list_id = await _create_list(ds)
    fid = (
        await _add_field(
            ds, list_id, key="code", label="Code", type="text", unique=True
        )
    ).json()["id"]
    internal = ds.get_internal_database()

    def _idx_count(rows):
        return rows.first()["c"]

    rows = await internal.execute(
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='index' AND name LIKE ?",
        [f"_dsp_uniq_{list_id}_%"],
    )
    assert _idx_count(rows) == 1

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/fields/{fid}/update",
        content=json.dumps({"unique": False}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    rows = await internal.execute(
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='index' AND name LIKE ?",
        [f"_dsp_uniq_{list_id}_%"],
    )
    assert _idx_count(rows) == 0


# --- Value validation on places ----------------------------------------------


@pytest.mark.asyncio
async def test_metadata_validation_errors(ds):
    list_id = await _create_list(ds)
    await _add_field(
        ds, list_id, key="rating", label="Rating", type="rating", config={"max": 5}
    )
    await _add_field(
        ds,
        list_id,
        key="cuisine",
        label="Cuisine",
        type="select",
        config={"options": [{"value": "thai"}, {"value": "sushi"}]},
    )
    await _add_field(ds, list_id, key="site", label="Site", type="url")

    # rating out of range
    resp = await _add_place(ds, list_id, name="A", metadata={"rating": 9})
    assert resp.status_code == 400
    assert "rating" in resp.json()["errors"]

    # select not in options
    resp = await _add_place(ds, list_id, name="B", metadata={"cuisine": "pizza"})
    assert resp.status_code == 400
    assert "cuisine" in resp.json()["errors"]

    # bad url
    resp = await _add_place(ds, list_id, name="C", metadata={"site": "not a url"})
    assert resp.status_code == 400

    # all valid
    resp = await _add_place(
        ds,
        list_id,
        name="D",
        metadata={"rating": 5, "cuisine": "thai", "site": "https://x.test"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_required_field(ds):
    list_id = await _create_list(ds)
    await _add_field(
        ds, list_id, key="rating", label="Rating", type="rating", required=True
    )
    resp = await _add_place(ds, list_id, name="A", metadata={})
    assert resp.status_code == 400
    assert "required" in resp.json()["errors"]["rating"]


# --- Per-key metadata endpoint (json_set / json_remove) ----------------------


@pytest.mark.asyncio
async def test_per_key_metadata_set_preserves_shape(ds):
    list_id = await _create_list(ds)
    await _add_field(ds, list_id, key="rating", label="Rating", type="rating")
    place = (await _add_place(ds, list_id, name="A", metadata={"shape": "star"})).json()
    pid = place["id"]

    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places/{pid}/metadata",
        content=json.dumps({"key": "rating", "value": 3}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    md = resp.json()["metadata"]
    assert md["rating"] == 3
    assert md["shape"] == "star"  # reserved key preserved by json_set

    # clear it
    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places/{pid}/metadata",
        content=json.dumps({"key": "rating"}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    md = resp.json()["metadata"]
    assert "rating" not in md
    assert md["shape"] == "star"


@pytest.mark.asyncio
async def test_per_key_metadata_validates(ds):
    list_id = await _create_list(ds)
    await _add_field(
        ds, list_id, key="rating", label="Rating", type="rating", config={"max": 5}
    )
    pid = (await _add_place(ds, list_id, name="A")).json()["id"]
    resp = await ds.client.post(
        f"/-/places/api/lists/{list_id}/places/{pid}/metadata",
        content=json.dumps({"key": "rating", "value": 99}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    assert "rating" in resp.json()["errors"]
