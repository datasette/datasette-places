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

from .sql import queries_generated as _queries
from .sql.queries_generated import Place, PlaceList  # re-exported for callers

__all__ = ["PlacesDB", "Place", "PlaceList"]


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
