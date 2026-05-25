from sqlite_utils import Database
from sqlite_migrate import Migrations

migrations = Migrations("datasette-places")


async def ensure_migrations(database) -> None:
    """Apply pending datasette-places migrations to *database* (idempotent)."""

    def _apply(connection):
        migrations.apply(Database(connection))

    await database.execute_write_fn(_apply)


@migrations()
def m001_initial(db: Database):
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS _datasette_places_list (
            id         INTEGER PRIMARY KEY NOT NULL,
            name       TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private','link-view','link-edit')),
            state      TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','trashed'))
        );
        CREATE INDEX IF NOT EXISTS idx_places_list_owner
            ON _datasette_places_list(created_by);
        CREATE INDEX IF NOT EXISTS idx_places_list_state
            ON _datasette_places_list(state);

        CREATE TABLE IF NOT EXISTS _datasette_places_place (
            id            INTEGER PRIMARY KEY NOT NULL,
            list_id       INTEGER NOT NULL REFERENCES _datasette_places_list(id) ON DELETE CASCADE,
            name          TEXT NOT NULL,
            address       TEXT,
            latitude      REAL NOT NULL,
            longitude     REAL NOT NULL,
            notes         TEXT,
            color         TEXT DEFAULT '#3b82f6',
            metadata_json TEXT,
            created_by    TEXT,
            created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_places_place_list
            ON _datasette_places_place(list_id);

        CREATE TABLE IF NOT EXISTS _datasette_places_share (
            list_id    INTEGER NOT NULL REFERENCES _datasette_places_list(id) ON DELETE CASCADE,
            actor_id   TEXT NOT NULL,
            role       TEXT NOT NULL CHECK (role IN ('viewer','editor')),
            granted_by TEXT,
            granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            PRIMARY KEY (list_id, actor_id)
        );
        CREATE INDEX IF NOT EXISTS idx_places_share_actor
            ON _datasette_places_share(actor_id);
        """
    )
