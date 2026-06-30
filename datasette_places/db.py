"""Database operations for datasette-places.

All operations run on Datasette's internal database via execute_write_fn
for transaction safety.

The SQL itself lives in ``sql/queries.sql`` and is compiled into
``sql/queries_generated.py`` by ``just codegen-queries``. PlacesDB is orchestration
only — multi-statement operations (a place insert/update/delete bumping the
parent list's ``updated_at``) chain the generated helpers inside a single
``execute_write_fn`` closure so the transaction stays atomic.
"""

from __future__ import annotations

import json
from typing import Optional

from sqlite_quote import quote_identifier, quote_string

from . import fields as _fields
from .sql import queries_generated as _queries
from .sql.queries_generated import (  # re-exported for callers
    ListField,
    Place,
    PlaceList,
)

__all__ = ["PlacesDB", "Place", "PlaceList", "ListField"]


class PlacesDB:
    """Thin async wrapper around Datasette's internal Database."""

    def __init__(self, database) -> None:
        self.database = database

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    async def insert_list(
        self, *, name: str, created_by: Optional[str] = None
    ) -> PlaceList:
        def write(conn):
            return _queries.insert_list(conn, name=name, created_by=created_by)

        pl = await self.database.execute_write_fn(write)
        assert pl is not None
        return pl

    async def select_list_by_id(self, list_id: int) -> Optional[PlaceList]:
        def read(conn):
            return _queries.select_list_by_id(conn, list_id=list_id)

        return await self.database.execute_write_fn(read)

    async def list_lists_by_ids_and_state(
        self, *, list_ids: list[int], state: str
    ) -> list[PlaceList]:
        ids_json = json.dumps(list_ids)

        def read(conn):
            return _queries.list_lists_by_ids_and_state(
                conn, ids_json=ids_json, state=state
            )

        return await self.database.execute_write_fn(read)

    async def update_list_name(self, *, list_id: int, name: str) -> Optional[PlaceList]:
        def write(conn):
            return _queries.update_list_name(conn, name=name, list_id=list_id)

        return await self.database.execute_write_fn(write)

    async def update_list_description(
        self, *, list_id: int, description: Optional[str]
    ) -> Optional[PlaceList]:
        def write(conn):
            return _queries.update_list_description(
                conn, description=description, list_id=list_id
            )

        return await self.database.execute_write_fn(write)

    async def trash_list(self, *, list_id: int) -> None:
        def write(conn):
            _queries.trash_list(conn, list_id=list_id)

        await self.database.execute_write_fn(write)

    async def restore_list(self, *, list_id: int) -> None:
        def write(conn):
            _queries.restore_list(conn, list_id=list_id)

        await self.database.execute_write_fn(write)

    async def place_count_for_list(self, *, list_id: int) -> int:
        def read(conn):
            return _queries.place_count_for_list(conn, list_id=list_id)

        return await self.database.execute_write_fn(read)

    async def place_counts_by_list_ids(self, list_ids: list[int]) -> dict[int, int]:
        ids_json = json.dumps(list_ids)

        def read(conn):
            rows = _queries.place_counts_by_list_ids(conn, ids_json=ids_json)
            return {row.list_id: row.cnt for row in rows}

        return await self.database.execute_write_fn(read)

    # ------------------------------------------------------------------
    # Places
    # ------------------------------------------------------------------

    async def insert_place(
        self,
        *,
        list_id: int,
        name: str,
        latitude: float,
        longitude: float,
        address: Optional[str] = None,
        notes: Optional[str] = None,
        color: Optional[str] = None,
        metadata_json: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Place:
        def write(conn):
            place = _queries.insert_place(
                conn,
                list_id=list_id,
                name=name,
                address=address,
                latitude=latitude,
                longitude=longitude,
                notes=notes,
                color=color,
                metadata_json=metadata_json,
                created_by=created_by,
            )
            # Also bump the parent list's updated_at.
            _queries.bump_list_updated_at(conn, list_id=list_id)
            return place

        place = await self.database.execute_write_fn(write)
        assert place is not None
        return place

    async def select_places_for_list(self, *, list_id: int) -> list[Place]:
        def read(conn):
            return _queries.select_places_for_list(conn, list_id=list_id)

        return await self.database.execute_write_fn(read)

    async def select_place_by_id(self, *, place_id: int) -> Optional[Place]:
        def read(conn):
            return _queries.select_place_by_id(conn, place_id=place_id)

        return await self.database.execute_write_fn(read)

    async def update_place(
        self,
        *,
        place_id: int,
        name: Optional[str] = None,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        notes: Optional[str] = None,
        color: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ) -> Optional[Place]:
        def write(conn):
            # Fetch current place so absent fields keep their existing values
            # (partial update), and to get list_id for the parent bump.
            cur = _queries.select_place_by_id(conn, place_id=place_id)
            if cur is None:
                return None
            place = _queries.update_place(
                conn,
                name=name if name is not None else cur.name,
                address=address if address is not None else cur.address,
                latitude=latitude if latitude is not None else cur.latitude,
                longitude=longitude if longitude is not None else cur.longitude,
                notes=notes if notes is not None else cur.notes,
                color=color if color is not None else cur.color,
                metadata_json=metadata_json
                if metadata_json is not None
                else cur.metadata_json,
                place_id=place_id,
            )
            _queries.bump_list_updated_at(conn, list_id=cur.list_id)
            return place

        return await self.database.execute_write_fn(write)

    async def delete_place(self, *, place_id: int) -> bool:
        def write(conn):
            list_id = _queries.select_place_list_id(conn, place_id=place_id)
            if list_id is None:
                return False
            _queries.delete_place(conn, place_id=place_id)
            _queries.bump_list_updated_at(conn, list_id=list_id)
            return True

        return await self.database.execute_write_fn(write)

    # ------------------------------------------------------------------
    # List fields (per-list metadata schema)
    #
    # Every mutation rebuilds the list's dynamic artifacts (expanded view +
    # unique indexes) in the SAME closure so they never drift from the defs.
    # ------------------------------------------------------------------

    async def select_fields_for_list(self, *, list_id: int) -> list[ListField]:
        def read(conn):
            return _queries.select_fields_for_list(conn, list_id=list_id)

        return await self.database.execute_write_fn(read)

    async def select_list_field_by_id(self, *, field_id: int) -> Optional[ListField]:
        def read(conn):
            return _queries.select_list_field_by_id(conn, field_id=field_id)

        return await self.database.execute_write_fn(read)

    async def insert_list_field(
        self,
        *,
        list_id: int,
        key: str,
        label: str,
        type: str,
        required: bool = False,
        is_unique: bool = False,
        config_json: str = "{}",
    ) -> ListField:
        _fields.validate_key(key)
        _fields.validate_type(type)

        def write(conn):
            max_pos = _queries.max_field_position_for_list(conn, list_id=list_id)
            position = (max_pos if max_pos is not None else -1) + 1
            field = _queries.insert_list_field(
                conn,
                list_id=list_id,
                key=key,
                label=label,
                type=type,
                position=position,
                required=1 if required else 0,
                is_unique=1 if is_unique else 0,
                config_json=config_json,
            )
            _rebuild_list_artifacts(conn, list_id)
            return field

        field = await self.database.execute_write_fn(write)
        assert field is not None
        return field

    async def update_list_field(
        self,
        *,
        field_id: int,
        label: str,
        type: str,
        position: int,
        required: bool,
        is_unique: bool,
        config_json: str,
    ) -> Optional[ListField]:
        _fields.validate_type(type)

        def write(conn):
            field = _queries.update_list_field(
                conn,
                field_id=field_id,
                label=label,
                type=type,
                position=position,
                required=1 if required else 0,
                is_unique=1 if is_unique else 0,
                config_json=config_json,
            )
            if field is not None:
                _rebuild_list_artifacts(conn, field.list_id)
            return field

        return await self.database.execute_write_fn(write)

    async def delete_list_field(self, *, field_id: int) -> Optional[int]:
        """Delete a field; returns its list_id (for the caller), or None."""

        def write(conn):
            field = _queries.select_list_field_by_id(conn, field_id=field_id)
            if field is None:
                return None
            _queries.delete_list_field(conn, field_id=field_id)
            _rebuild_list_artifacts(conn, field.list_id)
            return field.list_id

        return await self.database.execute_write_fn(write)

    async def rebuild_list_artifacts(self, *, list_id: int) -> None:
        def write(conn):
            _rebuild_list_artifacts(conn, list_id)

        await self.database.execute_write_fn(write)

    async def drop_list_artifacts(self, *, list_id: int) -> None:
        def write(conn):
            _drop_list_artifacts(conn, list_id)

        await self.database.execute_write_fn(write)

    # ------------------------------------------------------------------
    # Per-key place metadata writes (json_set / json_remove)
    # ------------------------------------------------------------------

    async def set_place_metadata_key(
        self, *, place_id: int, key: str, value_json: str
    ) -> Optional[Place]:
        _fields.validate_key(key)

        def write(conn):
            place = _queries.set_place_metadata_key(
                conn, place_id=place_id, key=key, value_json=value_json
            )
            if place is not None:
                _queries.bump_list_updated_at(conn, list_id=place.list_id)
            return place

        return await self.database.execute_write_fn(write)

    async def clear_place_metadata_key(
        self, *, place_id: int, key: str
    ) -> Optional[Place]:
        _fields.validate_key(key)

        def write(conn):
            place = _queries.remove_place_metadata_key(conn, place_id=place_id, key=key)
            if place is not None:
                _queries.bump_list_updated_at(conn, list_id=place.list_id)
            return place

        return await self.database.execute_write_fn(write)


# ----------------------------------------------------------------------
# Dynamic per-list DDL (expanded view + uniqueness indexes)
#
# DDL identifiers and string literals cannot be passed as bound parameters, so
# this SQL is assembled by interpolation. Two layers of defense:
#   1. every field key is re-validated against the whitelist (``validate_key``)
#      before it is used, and ``list_id`` is coerced to ``int``;
#   2. every interpolated identifier goes through ``sqlite_quote.quote_identifier``
#      (SQLite ``%w``) and every interpolated literal through
#      ``sqlite_quote.quote_string`` (``%Q``), so even a hypothetical bad value
#      that slipped past (1) cannot break out of its token.
# Run inside a PlacesDB closure so they share the surrounding write transaction.
# ----------------------------------------------------------------------


def _view_name(list_id: int) -> str:
    return f"_datasette_places_list_{int(list_id)}_expanded"


def _json_path(key: str) -> str:
    """Quoted SQL literal for a field's JSON path, e.g. ``'$.rating'``."""
    return quote_string(f"$.{key}")


def _drop_list_artifacts(conn, list_id: int) -> None:
    list_id = int(list_id)
    conn.execute(f"DROP VIEW IF EXISTS {quote_identifier(_view_name(list_id))}")
    prefix = f"_dsp_uniq_{list_id}_"
    stale = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE ? || '%'",
        (prefix,),
    ).fetchall()
    for (name,) in stale:
        conn.execute(f"DROP INDEX IF EXISTS {quote_identifier(name)}")


def _rebuild_list_artifacts(conn, list_id: int) -> None:
    list_id = int(list_id)
    field_rows = _queries.select_fields_for_list(conn, list_id=list_id)

    # Re-validate every key before interpolation (defense in depth, layer 1).
    for f in field_rows:
        _fields.validate_key(f.key)

    _drop_list_artifacts(conn, list_id)

    select_cols = list(_fields.BASE_VIEW_COLUMNS)
    extracted = [
        f"json_extract(metadata_json, {_json_path(f.key)}) AS {quote_identifier(f.key)}"
        for f in field_rows
    ]
    cols_sql = ",\n       ".join(select_cols + extracted)
    conn.execute(
        f"CREATE VIEW {quote_identifier(_view_name(list_id))} AS\n"
        f"SELECT {cols_sql}\n"
        f"FROM _datasette_places_place WHERE list_id = {list_id}"
    )

    for f in field_rows:
        if not f.is_unique:
            continue
        idx = quote_identifier(f"_dsp_uniq_{list_id}_{f.key}")
        path = f"json_extract(metadata_json, {_json_path(f.key)})"
        conn.execute(
            f"CREATE UNIQUE INDEX {idx} "
            f"ON _datasette_places_place(list_id, {path}) "
            f"WHERE list_id = {list_id} AND {path} IS NOT NULL"
        )
