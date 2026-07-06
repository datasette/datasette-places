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
    # Per-list access lives entirely in datasette-acl grants on the
    # ``places-list`` resource (see datasette_places.permissions); the schema
    # carries no owner/shared/visibility columns. ``created_by`` is retained
    # only to seed the creator's Manager grant on create.
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS _datasette_places_list (
            id          INTEGER PRIMARY KEY NOT NULL,
            name        TEXT NOT NULL,
            created_by  TEXT,
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            state       TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','trashed')),
            description TEXT
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
        """
    )


@migrations()
def m002_list_fields(db: Database):
    # User-defined per-list metadata fields (the "schema" for a list's places).
    # Each row declares one custom attribute every place in the list may fill in.
    # ``key`` is BOTH the JSON path segment in ``_datasette_places_place.metadata_json``
    # AND the column name in the per-list expanded view, so it is whitelisted to
    # ``^[a-z][a-z0-9_]{0,62}$`` and may not collide with reserved keys (shape,
    # color, name, …) — enforced in datasette_places.fields, not the schema.
    # ``type`` selects an editor/renderer/validator (text|number|url|rating|
    # select|color|icon|boolean|date). ``config_json`` holds type-specific config
    # (e.g. select ``options``, rating ``max``). ``required``/``is_unique`` are
    # validation flags; uniqueness is additionally enforced by a dynamic
    # expression index built in db.rebuild_list_artifacts.
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS _datasette_places_list_field (
            id          INTEGER PRIMARY KEY NOT NULL,
            list_id     INTEGER NOT NULL REFERENCES _datasette_places_list(id) ON DELETE CASCADE,
            key         TEXT NOT NULL,
            label       TEXT NOT NULL,
            type        TEXT NOT NULL,
            position    INTEGER NOT NULL DEFAULT 0,
            required    INTEGER NOT NULL DEFAULT 0,
            is_unique   INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE (list_id, key)
        );
        CREATE INDEX IF NOT EXISTS idx_places_list_field_list
            ON _datasette_places_list_field(list_id);
        """
    )
