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
def m002_geocoders(db: Database):
    # Geocoder *instances*: a named, configured, ACL'd deployment of a provider
    # type (``opencage``, ``pluto``, …). ``id`` is a stable slug used as the
    # datasette-acl ``places-geocoder`` resource parent. ``config_json`` holds
    # NON-SECRET provider config (e.g. an ``api_key_ref`` naming a plugin-config
    # key, or a pluto ``database`` name) — secrets stay in plugin config and are
    # resolved by reference at call time. ``enabled`` is a global kill-switch,
    # independent of the per-list toggle below.
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS _datasette_places_geocoder (
            id            TEXT PRIMARY KEY NOT NULL,
            provider_type TEXT NOT NULL,
            label         TEXT NOT NULL,
            config_json   TEXT NOT NULL DEFAULT '{}',
            enabled       INTEGER NOT NULL DEFAULT 1,
            created_by    TEXT,
            created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );

        -- Per-list attachments: which geocoders are enabled on a list, ordered,
        -- with one optional default for the search box + map-click reverse.
        -- Attaching is gated by places-manage(list) + geocoder-use(geocoder);
        -- querying re-checks geocoder-use (see routes/geocode.py).
        CREATE TABLE IF NOT EXISTS _datasette_places_list_geocoder (
            list_id     INTEGER NOT NULL REFERENCES _datasette_places_list(id) ON DELETE CASCADE,
            geocoder_id TEXT NOT NULL REFERENCES _datasette_places_geocoder(id) ON DELETE CASCADE,
            enabled     INTEGER NOT NULL DEFAULT 1,
            is_default  INTEGER NOT NULL DEFAULT 0,
            position    INTEGER NOT NULL DEFAULT 0,
            added_by    TEXT,
            added_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            PRIMARY KEY (list_id, geocoder_id)
        );
        CREATE INDEX IF NOT EXISTS idx_places_list_geocoder_list
            ON _datasette_places_list_geocoder(list_id);
        """
    )
