"""Tests for the codegen-generated query helpers (sql/queries_generated.py).

These exercise the generated functions directly against a raw
``sqlite3.Connection`` — the layer below PlacesDB — to pin down the contract
the generator produces: dataclass shapes, ``$name::type`` parameter binding,
nullability, the json_each IN-clause, RETURNING/:value/void result handling.

The schema comes from migrations.py (the single source of truth), applied to an
in-memory database, so these stay in lock-step with `just codegen-queries`,
which validates the same queries against the same schema.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlite_utils import Database

from datasette_places.migrations import migrations
from datasette_places.sql import queries_generated as q


@pytest.fixture
def conn() -> sqlite3.Connection:
    db = Database(memory=True)
    migrations.apply(db)
    return db.conn


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def test_insert_list_returns_placelist_shape(conn):
    pl = q.insert_list(conn, name="Trip", created_by="alice")
    assert isinstance(pl, q.PlaceList)
    assert (pl.id, pl.name, pl.created_by, pl.state, pl.description) == (
        1,
        "Trip",
        "alice",
        "active",
        None,
    )
    # Timestamps are populated by column defaults.
    assert pl.created_at and pl.updated_at


def test_insert_list_nullable_created_by(conn):
    pl = q.insert_list(conn, name="Orphan", created_by=None)
    assert pl is not None
    assert pl.created_by is None


def test_select_list_by_id_hit_and_miss(conn):
    created = q.insert_list(conn, name="A", created_by="alice")
    fetched = q.select_list_by_id(conn, list_id=created.id)
    assert fetched == created
    assert q.select_list_by_id(conn, list_id=9999) is None


def test_list_lists_by_ids_and_state_filters(conn):
    import json

    a = q.insert_list(conn, name="A", created_by="alice")
    b = q.insert_list(conn, name="B", created_by="alice")
    c = q.insert_list(conn, name="C", created_by="alice")
    q.trash_list(conn, list_id=b.id)

    ids = json.dumps([a.id, b.id, c.id])
    active = q.list_lists_by_ids_and_state(conn, ids_json=ids, state="active")
    assert {pl.id for pl in active} == {a.id, c.id}
    assert all(isinstance(pl, q.PlaceList) for pl in active)

    trashed = q.list_lists_by_ids_and_state(conn, ids_json=ids, state="trashed")
    assert {pl.id for pl in trashed} == {b.id}

    # Empty id list collapses to no rows.
    assert q.list_lists_by_ids_and_state(conn, ids_json="[]", state="active") == []


def test_update_list_name_and_description(conn):
    pl = q.insert_list(conn, name="Old", created_by="alice")
    renamed = q.update_list_name(conn, name="New", list_id=pl.id)
    assert renamed.name == "New"

    described = q.update_list_description(conn, description="hi", list_id=pl.id)
    assert described.description == "hi"
    # Nullable description round-trips None.
    cleared = q.update_list_description(conn, description=None, list_id=pl.id)
    assert cleared.description is None

    assert q.update_list_name(conn, name="x", list_id=9999) is None


def test_trash_and_restore_are_void_and_mutate_state(conn):
    pl = q.insert_list(conn, name="A", created_by="alice")
    assert q.trash_list(conn, list_id=pl.id) is None
    assert q.select_list_by_id(conn, list_id=pl.id).state == "trashed"
    assert q.restore_list(conn, list_id=pl.id) is None
    assert q.select_list_by_id(conn, list_id=pl.id).state == "active"


def test_bump_list_updated_at(conn):
    pl = q.insert_list(conn, name="A", created_by="alice")
    conn.execute(
        "UPDATE _datasette_places_list SET updated_at = '2000-01-01T00:00:00.000Z' WHERE id = ?",
        [pl.id],
    )
    q.bump_list_updated_at(conn, list_id=pl.id)
    bumped = q.select_list_by_id(conn, list_id=pl.id)
    assert bumped.updated_at > "2000-01-01T00:00:00.000Z"


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------


def _list(conn) -> int:
    return q.insert_list(conn, name="L", created_by="alice").id


def test_place_counts(conn):
    import json

    lid = _list(conn)
    other = _list(conn)
    assert q.place_count_for_list(conn, list_id=lid) == 0

    for i in range(3):
        q.insert_place(
            conn,
            list_id=lid,
            name=f"p{i}",
            address=None,
            latitude=1.0,
            longitude=2.0,
            notes=None,
            color=None,
            metadata_json=None,
            created_by="alice",
        )
    assert q.place_count_for_list(conn, list_id=lid) == 3

    counts = q.place_counts_by_list_ids(conn, ids_json=json.dumps([lid, other]))
    by_id = {row.list_id: row.cnt for row in counts}
    # GROUP BY only yields rows for lists that have places.
    assert by_id == {lid: 3}
    assert all(isinstance(row, q.PlaceCount) for row in counts)


def test_insert_place_shape_and_nullability(conn):
    lid = _list(conn)
    p = q.insert_place(
        conn,
        list_id=lid,
        name="Cafe",
        address=None,
        latitude=40.5,
        longitude=-73.9,
        notes=None,
        color=None,
        metadata_json=None,
        created_by=None,
    )
    assert isinstance(p, q.Place)
    assert (p.list_id, p.name, p.latitude, p.longitude) == (lid, "Cafe", 40.5, -73.9)
    assert p.address is None and p.notes is None and p.color is None
    assert p.created_by is None


def test_select_places_for_list_orders_by_created_at(conn):
    lid = _list(conn)
    ids = []
    for i in range(3):
        ids.append(
            q.insert_place(
                conn,
                list_id=lid,
                name=f"p{i}",
                address=None,
                latitude=float(i),
                longitude=0.0,
                notes=None,
                color=None,
                metadata_json=None,
                created_by="alice",
            ).id
        )
    rows = q.select_places_for_list(conn, list_id=lid)
    assert [r.id for r in rows] == ids  # insertion order == created_at ASC


def test_select_place_by_id_and_list_id(conn):
    lid = _list(conn)
    p = q.insert_place(
        conn,
        list_id=lid,
        name="X",
        address="addr",
        latitude=1.0,
        longitude=2.0,
        notes="n",
        color="#fff",
        metadata_json='{"k":1}',
        created_by="alice",
    )
    assert q.select_place_by_id(conn, place_id=p.id) == p
    assert q.select_place_list_id(conn, place_id=p.id) == lid
    assert q.select_place_by_id(conn, place_id=9999) is None
    assert q.select_place_list_id(conn, place_id=9999) is None


def test_update_place_and_delete(conn):
    lid = _list(conn)
    p = q.insert_place(
        conn,
        list_id=lid,
        name="X",
        address=None,
        latitude=1.0,
        longitude=2.0,
        notes=None,
        color=None,
        metadata_json=None,
        created_by="alice",
    )
    updated = q.update_place(
        conn,
        name="Y",
        address="new",
        latitude=3.0,
        longitude=4.0,
        notes="note",
        color="#000",
        metadata_json=None,
        place_id=p.id,
    )
    assert (updated.name, updated.address, updated.latitude) == ("Y", "new", 3.0)

    assert q.delete_place(conn, place_id=p.id) is None
    assert q.select_place_by_id(conn, place_id=p.id) is None


def test_reexported_dataclasses_are_identical(conn):
    from datasette_places.db import Place, PlaceList

    assert Place is q.Place
    assert PlaceList is q.PlaceList
