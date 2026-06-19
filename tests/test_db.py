"""Tests for PlacesDB (datasette_places/db.py).

PlacesDB is the async orchestration layer over the generated query helpers:
it serializes work through ``execute_write_fn`` closures and owns the
multi-statement behaviour the generated single-statement helpers don't —
partial-update merging in ``update_place`` and the parent-list ``updated_at``
bump chained after place inserts/updates/deletes.

These run against a real (in-memory) Datasette internal database with
migrations applied via ``invoke_startup``.
"""

from __future__ import annotations

import pytest
from datasette.app import Datasette

from datasette_places.db import Place, PlaceList, PlacesDB


async def _db() -> PlacesDB:
    ds = Datasette(memory=True)
    await ds.invoke_startup()
    return PlacesDB(ds.get_internal_database())


async def _set_old_updated_at(db: PlacesDB, list_id: int) -> None:
    """Force a list's updated_at into the past so a later bump is observable."""
    await db.database.execute_write(
        "UPDATE _datasette_places_list SET updated_at = '2000-01-01T00:00:00.000Z' WHERE id = ?",
        [list_id],
    )


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_select_list():
    db = await _db()
    pl = await db.insert_list(name="Trip", created_by="alice")
    assert isinstance(pl, PlaceList)
    assert pl.name == "Trip" and pl.created_by == "alice" and pl.state == "active"

    assert await db.select_list_by_id(pl.id) == pl
    assert await db.select_list_by_id(9999) is None


@pytest.mark.asyncio
async def test_insert_list_anonymous_owner():
    db = await _db()
    pl = await db.insert_list(name="Orphan")
    assert pl.created_by is None


@pytest.mark.asyncio
async def test_update_list_name_and_description():
    db = await _db()
    pl = await db.insert_list(name="Old", created_by="alice")

    renamed = await db.update_list_name(list_id=pl.id, name="New")
    assert renamed.name == "New"

    described = await db.update_list_description(list_id=pl.id, description="desc")
    assert described.description == "desc"
    cleared = await db.update_list_description(list_id=pl.id, description=None)
    assert cleared.description is None

    assert await db.update_list_name(list_id=9999, name="x") is None
    assert await db.update_list_description(list_id=9999, description="x") is None


@pytest.mark.asyncio
async def test_list_lists_by_ids_and_state():
    db = await _db()
    a = await db.insert_list(name="A", created_by="alice")
    b = await db.insert_list(name="B", created_by="alice")
    c = await db.insert_list(name="C", created_by="alice")
    await db.trash_list(list_id=b.id)

    ids = [a.id, b.id, c.id]
    active = await db.list_lists_by_ids_and_state(list_ids=ids, state="active")
    assert {pl.id for pl in active} == {a.id, c.id}

    trashed = await db.list_lists_by_ids_and_state(list_ids=ids, state="trashed")
    assert {pl.id for pl in trashed} == {b.id}

    assert await db.list_lists_by_ids_and_state(list_ids=[], state="active") == []


@pytest.mark.asyncio
async def test_trash_and_restore_list():
    db = await _db()
    pl = await db.insert_list(name="A", created_by="alice")
    await db.trash_list(list_id=pl.id)
    assert (await db.select_list_by_id(pl.id)).state == "trashed"
    await db.restore_list(list_id=pl.id)
    assert (await db.select_list_by_id(pl.id)).state == "active"


# ---------------------------------------------------------------------------
# Places + counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_counts():
    db = await _db()
    a = await db.insert_list(name="A", created_by="alice")
    b = await db.insert_list(name="B", created_by="alice")
    for i in range(2):
        await db.insert_place(list_id=a.id, name=f"p{i}", latitude=1.0, longitude=2.0)

    assert await db.place_count_for_list(list_id=a.id) == 2
    assert await db.place_count_for_list(list_id=b.id) == 0

    counts = await db.place_counts_by_list_ids([a.id, b.id])
    # Only lists with places appear (GROUP BY); db.py returns a dict.
    assert counts == {a.id: 2}


@pytest.mark.asyncio
async def test_insert_place_returns_place_and_bumps_list():
    db = await _db()
    pl = await db.insert_list(name="L", created_by="alice")
    await _set_old_updated_at(db, pl.id)

    place = await db.insert_place(
        list_id=pl.id, name="Cafe", latitude=40.5, longitude=-73.9
    )
    assert isinstance(place, Place)
    assert place.list_id == pl.id and place.name == "Cafe"
    # Optional fields default to None when omitted.
    assert place.address is None and place.notes is None

    bumped = await db.select_list_by_id(pl.id)
    assert bumped.updated_at > "2000-01-01T00:00:00.000Z"


@pytest.mark.asyncio
async def test_select_places_for_list_ordered():
    db = await _db()
    pl = await db.insert_list(name="L", created_by="alice")
    ids = [
        (
            await db.insert_place(
                list_id=pl.id, name=f"p{i}", latitude=0.0, longitude=0.0
            )
        ).id
        for i in range(3)
    ]
    rows = await db.select_places_for_list(list_id=pl.id)
    assert [r.id for r in rows] == ids


@pytest.mark.asyncio
async def test_update_place_partial_merge_keeps_other_fields():
    db = await _db()
    pl = await db.insert_list(name="L", created_by="alice")
    place = await db.insert_place(
        list_id=pl.id,
        name="X",
        latitude=1.0,
        longitude=2.0,
        address="addr",
        notes="orig",
        color="#fff",
    )
    # Update only the name; everything else must be preserved.
    updated = await db.update_place(place_id=place.id, name="Y")
    assert updated.name == "Y"
    assert updated.address == "addr"
    assert updated.notes == "orig"
    assert updated.color == "#fff"
    assert (updated.latitude, updated.longitude) == (1.0, 2.0)


@pytest.mark.asyncio
async def test_update_place_bumps_list():
    db = await _db()
    pl = await db.insert_list(name="L", created_by="alice")
    place = await db.insert_place(list_id=pl.id, name="X", latitude=1.0, longitude=2.0)
    await _set_old_updated_at(db, pl.id)

    await db.update_place(place_id=place.id, name="Y")
    assert (await db.select_list_by_id(pl.id)).updated_at > "2000-01-01T00:00:00.000Z"


@pytest.mark.asyncio
async def test_update_place_missing_returns_none():
    db = await _db()
    assert await db.update_place(place_id=9999, name="Y") is None


@pytest.mark.asyncio
async def test_delete_place_removes_and_bumps_list():
    db = await _db()
    pl = await db.insert_list(name="L", created_by="alice")
    place = await db.insert_place(list_id=pl.id, name="X", latitude=1.0, longitude=2.0)
    await _set_old_updated_at(db, pl.id)

    assert await db.delete_place(place_id=place.id) is True
    assert await db.select_place_by_id(place_id=place.id) is None
    assert (await db.select_list_by_id(pl.id)).updated_at > "2000-01-01T00:00:00.000Z"


@pytest.mark.asyncio
async def test_delete_place_missing_returns_false():
    db = await _db()
    assert await db.delete_place(place_id=9999) is False
