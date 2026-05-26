"""Database operations for datasette-places.

All operations run on Datasette's internal database via execute_write_fn
for transaction safety.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlaceList:
    id: int
    name: str
    created_by: Optional[str]
    created_at: str
    updated_at: str
    visibility: str
    state: str
    description: Optional[str] = None


@dataclass
class Place:
    id: int
    list_id: int
    name: str
    address: Optional[str]
    latitude: float
    longitude: float
    notes: Optional[str]
    color: Optional[str]
    metadata_json: Optional[str]
    created_by: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class Share:
    list_id: int
    actor_id: str
    role: str
    granted_by: Optional[str]
    granted_at: str


def _row_to_list(row) -> PlaceList:
    # `description` (row[7]) was added in migration m002; guard against rows
    # selected before the column exists.
    return PlaceList(
        id=row[0],
        name=row[1],
        created_by=row[2],
        created_at=row[3],
        updated_at=row[4],
        visibility=row[5],
        state=row[6],
        description=row[7] if len(row) > 7 else None,
    )


def _row_to_place(row) -> Place:
    return Place(
        id=row[0],
        list_id=row[1],
        name=row[2],
        address=row[3],
        latitude=row[4],
        longitude=row[5],
        notes=row[6],
        color=row[7],
        metadata_json=row[8],
        created_by=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


def _row_to_share(row) -> Share:
    return Share(
        list_id=row[0],
        actor_id=row[1],
        role=row[2],
        granted_by=row[3],
        granted_at=row[4],
    )


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
            cursor = conn.execute(
                "INSERT INTO _datasette_places_list (name, created_by) VALUES (?, ?) RETURNING *",
                [name, created_by],
            )
            return _row_to_list(cursor.fetchone())

        return await self.database.execute_write_fn(write)

    async def select_list_by_id(self, list_id: int) -> Optional[PlaceList]:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM _datasette_places_list WHERE id = ?", [list_id]
            ).fetchone()
            return _row_to_list(row) if row else None

        return await self.database.execute_write_fn(read)

    async def list_lists_by_ids_and_state(
        self, *, list_ids: list[int], state: str
    ) -> list[PlaceList]:
        ids_json = json.dumps(list_ids)

        def read(conn):
            rows = conn.execute(
                """
                SELECT l.* FROM _datasette_places_list l
                JOIN json_each(?) je ON je.value = l.id
                WHERE l.state = ?
                ORDER BY l.updated_at DESC
                """,
                [ids_json, state],
            ).fetchall()
            return [_row_to_list(r) for r in rows]

        return await self.database.execute_write_fn(read)

    async def update_list_name(self, *, list_id: int, name: str) -> Optional[PlaceList]:
        def write(conn):
            row = conn.execute(
                """
                UPDATE _datasette_places_list
                SET name = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id = ?
                RETURNING *
                """,
                [name, list_id],
            ).fetchone()
            return _row_to_list(row) if row else None

        return await self.database.execute_write_fn(write)

    async def update_list_description(
        self, *, list_id: int, description: Optional[str]
    ) -> Optional[PlaceList]:
        def write(conn):
            row = conn.execute(
                """
                UPDATE _datasette_places_list
                SET description = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id = ?
                RETURNING *
                """,
                [description, list_id],
            ).fetchone()
            return _row_to_list(row) if row else None

        return await self.database.execute_write_fn(write)

    async def trash_list(self, *, list_id: int) -> None:
        def write(conn):
            conn.execute(
                """
                UPDATE _datasette_places_list
                SET state = 'trashed',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id = ?
                """,
                [list_id],
            )

        await self.database.execute_write_fn(write)

    async def restore_list(self, *, list_id: int) -> None:
        def write(conn):
            conn.execute(
                """
                UPDATE _datasette_places_list
                SET state = 'active',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id = ?
                """,
                [list_id],
            )

        await self.database.execute_write_fn(write)

    async def place_count_for_list(self, *, list_id: int) -> int:
        def read(conn):
            row = conn.execute(
                "SELECT COUNT(*) FROM _datasette_places_place WHERE list_id = ?",
                [list_id],
            ).fetchone()
            return row[0]

        return await self.database.execute_write_fn(read)

    async def place_counts_by_list_ids(self, list_ids: list[int]) -> dict[int, int]:
        ids_json = json.dumps(list_ids)

        def read(conn):
            rows = conn.execute(
                """
                SELECT list_id, COUNT(*) as cnt
                FROM _datasette_places_place
                WHERE list_id IN (SELECT value FROM json_each(?))
                GROUP BY list_id
                """,
                [ids_json],
            ).fetchall()
            return {row[0]: row[1] for row in rows}

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
            cursor = conn.execute(
                """
                INSERT INTO _datasette_places_place
                    (list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                [
                    list_id,
                    name,
                    address,
                    latitude,
                    longitude,
                    notes,
                    color,
                    metadata_json,
                    created_by,
                ],
            )
            # Also bump the parent list's updated_at
            conn.execute(
                "UPDATE _datasette_places_list SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                [list_id],
            )
            return _row_to_place(cursor.fetchone())

        return await self.database.execute_write_fn(write)

    async def select_places_for_list(self, *, list_id: int) -> list[Place]:
        def read(conn):
            rows = conn.execute(
                "SELECT * FROM _datasette_places_place WHERE list_id = ? ORDER BY created_at ASC",
                [list_id],
            ).fetchall()
            return [_row_to_place(r) for r in rows]

        return await self.database.execute_write_fn(read)

    async def select_place_by_id(self, *, place_id: int) -> Optional[Place]:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM _datasette_places_place WHERE id = ?", [place_id]
            ).fetchone()
            return _row_to_place(row) if row else None

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
            # Fetch current place to get list_id for bumping
            current = conn.execute(
                "SELECT * FROM _datasette_places_place WHERE id = ?", [place_id]
            ).fetchone()
            if current is None:
                return None
            cur = _row_to_place(current)
            row = conn.execute(
                """
                UPDATE _datasette_places_place
                SET name = ?,
                    address = ?,
                    latitude = ?,
                    longitude = ?,
                    notes = ?,
                    color = ?,
                    metadata_json = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id = ?
                RETURNING *
                """,
                [
                    name if name is not None else cur.name,
                    address if address is not None else cur.address,
                    latitude if latitude is not None else cur.latitude,
                    longitude if longitude is not None else cur.longitude,
                    notes if notes is not None else cur.notes,
                    color if color is not None else cur.color,
                    metadata_json if metadata_json is not None else cur.metadata_json,
                    place_id,
                ],
            ).fetchone()
            conn.execute(
                "UPDATE _datasette_places_list SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                [cur.list_id],
            )
            return _row_to_place(row) if row else None

        return await self.database.execute_write_fn(write)

    async def delete_place(self, *, place_id: int) -> bool:
        def write(conn):
            current = conn.execute(
                "SELECT list_id FROM _datasette_places_place WHERE id = ?", [place_id]
            ).fetchone()
            if current is None:
                return False
            conn.execute("DELETE FROM _datasette_places_place WHERE id = ?", [place_id])
            conn.execute(
                "UPDATE _datasette_places_list SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                [current[0]],
            )
            return True

        return await self.database.execute_write_fn(write)

    # ------------------------------------------------------------------
    # Shares
    # ------------------------------------------------------------------

    async def select_shares(self, *, list_id: int) -> list[Share]:
        def read(conn):
            rows = conn.execute(
                "SELECT * FROM _datasette_places_share WHERE list_id = ? ORDER BY granted_at ASC",
                [list_id],
            ).fetchall()
            return [_row_to_share(r) for r in rows]

        return await self.database.execute_write_fn(read)

    async def replace_shares(
        self,
        *,
        list_id: int,
        visibility: str,
        shares: list[tuple[str, str]],
        granted_by: Optional[str],
    ) -> None:
        def write(conn):
            conn.execute(
                "UPDATE _datasette_places_list SET visibility = ? WHERE id = ?",
                [visibility, list_id],
            )
            conn.execute(
                "DELETE FROM _datasette_places_share WHERE list_id = ?", [list_id]
            )
            for actor_id, role in shares:
                conn.execute(
                    "INSERT INTO _datasette_places_share (list_id, actor_id, role, granted_by) VALUES (?, ?, ?, ?)",
                    [list_id, actor_id, role, granted_by],
                )

        await self.database.execute_write_fn(write)
