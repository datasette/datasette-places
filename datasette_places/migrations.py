import logging

from sqlite_utils import Database
from sqlite_migrate import Migrations

# NOTE: keep module-level imports limited to what the ``@migrations()`` step
# functions below need. The async share→acl backfill is the only code that
# needs the permission constants + acl grant helper, so those imports are
# deferred into ``migrate_shares_to_acl`` (see ``_acl_helpers``) — mirroring
# datasette-paper, where the codegen pipeline loads this module without package
# context.

logger = logging.getLogger("datasette_places.migrations")


def _acl_helpers():
    """Lazily resolve the permission constants + acl grant API.

    Imported on demand (not at module load). Returns
    ``(PLACES_LIST_RESOURCE_TYPE, grant, build_roles_registry)``; the two acl
    callables are ``None`` when acl isn't installed (the backfill then no-ops).
    """
    from .permissions import PLACES_LIST_RESOURCE_TYPE

    try:  # acl is a soft dependency — the backfill no-ops when it is absent.
        from datasette_acl.grants import grant as acl_grant
    except ImportError:  # pragma: no cover
        acl_grant = None
    try:
        from datasette_acl.roles import build_roles_registry
    except ImportError:  # pragma: no cover
        build_roles_registry = None
    return PLACES_LIST_RESOURCE_TYPE, acl_grant, build_roles_registry


migrations = Migrations("datasette-places")

# Marker table recording that the one-time visibility/share → acl-grant data
# migration has completed. Distinct from the sqlite-migrate schema migrations:
# those create/alter tables, this backfills acl grants and must not run before
# acl's startup has built the roles registry.
_ACL_MIGRATION_TABLE = "_datasette_places_acl_migration"
_ACL_MIGRATION_KEY = "shares_to_acl_grants"

# Default general-access principal for ``link-*`` visibility. ``_signed_in``
# means "anyone signed in"; deployments wanting truly public (incl. anonymous)
# lists can set the ``share-general-principal`` plugin setting to ``*``.
DEFAULT_GENERAL_PRINCIPAL = "_signed_in"

# Old per-list visibility enum → general-access principal role for the wildcard
# grant. ``private`` grants nothing extra (owner + explicit shares only). Per
# DECISIONS.md, upgrade default is CLOSED: we migrate *explicit* link-*
# visibility faithfully but never auto-open private lists.
_VISIBILITY_ROLE = {
    "link-view": "Viewer",
    "link-edit": "Editor",
}

# Old per-actor share role → new acl role.
_SHARE_ROLE = {
    "viewer": "Viewer",
    "editor": "Editor",
}


async def ensure_migrations(database) -> None:
    """Apply pending datasette-places migrations to *database* (idempotent)."""

    def _apply(connection):
        migrations.apply(Database(connection))

    await database.execute_write_fn(_apply)


def _general_principal(datasette) -> str:
    """Resolve the wildcard principal for ``link-*`` visibility.

    Configurable via the ``share-general-principal`` plugin setting
    (``datasette-places`` block); defaults to ``_signed_in``. Only ``*`` and
    ``_signed_in`` are honoured — anything else falls back to the default.
    """
    config = datasette.plugin_config("datasette-places") or {}
    principal = config.get("share-general-principal", DEFAULT_GENERAL_PRINCIPAL)
    if principal not in ("*", "_signed_in"):
        logger.warning(
            "datasette-places: ignoring invalid share-general-principal %r; using %r",
            principal,
            DEFAULT_GENERAL_PRINCIPAL,
        )
        return DEFAULT_GENERAL_PRINCIPAL
    return principal


async def _acl_migration_done(db) -> bool:
    """True if the shares→grants migration marker has been recorded."""
    rows = (
        await db.execute(
            f"SELECT 1 FROM {_ACL_MIGRATION_TABLE} WHERE key = ?",
            [_ACL_MIGRATION_KEY],
        )
    ).rows
    return bool(rows)


async def _legacy_share_schema_present(db) -> bool:
    """True if the pre-acl share storage still exists to be migrated.

    Both the ``_datasette_places_share`` table and the
    ``_datasette_places_list.visibility`` column are dropped by a later
    migration after their data is backfilled into acl. This guards the one-time
    backfill so it no-ops (rather than raising) once that schema is gone.
    """
    table = (
        await db.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = '_datasette_places_share'"
        )
    ).rows
    if not table:
        return False
    cols = (await db.execute("PRAGMA table_info(_datasette_places_list)")).rows
    return any(row["name"] == "visibility" for row in cols)


async def _mark_acl_migration_done(db) -> None:
    await db.execute_write(
        f"INSERT OR IGNORE INTO {_ACL_MIGRATION_TABLE} (key, migrated_at) "
        "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        [_ACL_MIGRATION_KEY],
    )


async def _ensure_places_roles_registry(
    datasette, resource_type, build_roles_registry
) -> bool:
    """Make sure acl's roles registry knows the ``places-list`` roles.

    The data migration runs from places' ``startup`` hook and calls acl's
    ``grant(role=...)`` helper, which resolves role names against
    ``datasette._acl_roles_registry``. That registry is populated by *acl's* own
    startup hook, and the relative ordering of two plugins' startup hooks is not
    guaranteed. Rather than depend on ordering, (re)build the registry here if
    our roles aren't present yet — cheap and idempotent.

    Returns False when acl isn't installed (registry helper unavailable), so the
    caller can skip the migration entirely.
    """
    if build_roles_registry is None:
        return False
    registry = getattr(datasette, "_acl_roles_registry", None)
    if not registry or resource_type not in registry:
        datasette._acl_roles_registry = await build_roles_registry(datasette)
    return resource_type in (getattr(datasette, "_acl_roles_registry", None) or {})


async def migrate_shares_to_acl(datasette, *, force: bool = False) -> dict:
    """One-time backfill of legacy share/visibility data into acl grants.

    Converts every existing list's ``created_by`` + ``visibility`` and every
    ``_datasette_places_share`` row into acl grants on the ``places-list``
    resource, using acl's ``grant`` helper (no raw writes into acl's schema):

        owner (created_by)      -> Manager grant for that actor
        share row 'viewer'      -> Viewer grant for that actor
        share row 'editor'      -> Editor grant for that actor
        visibility 'private'    -> nothing
        visibility 'link-view'  -> Viewer grant for the general principal
        visibility 'link-edit'  -> Editor grant for the general principal

    Idempotent on two levels: a marker row in ``_datasette_places_acl_migration``
    short-circuits repeat runs, and acl's ``grant`` only inserts actions a
    principal doesn't already hold (so even a forced re-run produces no duplicate
    grants or audit rows). ``force=True`` bypasses the marker for tests / a
    deliberate re-run. No-ops (returning zero counts) when acl is not installed.
    Returns a small stats dict for logging / assertions.
    """
    stats = {"owners": 0, "shares": 0, "visibility": 0, "skipped": False}

    resource_type, acl_grant, build_roles_registry = _acl_helpers()

    if acl_grant is None or not await _ensure_places_roles_registry(
        datasette, resource_type, build_roles_registry
    ):
        # acl absent — nothing to migrate into. Still record the marker so we
        # don't re-scan on every startup; if acl is later installed the share
        # UI / create path seed grants going forward.
        stats["skipped"] = True
        return stats

    db = datasette.get_internal_database()
    await db.execute_write(
        f"CREATE TABLE IF NOT EXISTS {_ACL_MIGRATION_TABLE} ("
        "key TEXT PRIMARY KEY, migrated_at TEXT NOT NULL)"
    )

    if not force and await _acl_migration_done(db):
        stats["skipped"] = True
        return stats

    # The legacy ``visibility`` column + ``_datasette_places_share`` table are
    # dropped by a later migration once their data has been backfilled. On any
    # DB that held legacy data the backfill ran (and set its marker) on an
    # earlier boot, so reaching here without that column/table means there is
    # nothing to migrate (fresh install, or a forced re-run after the drop).
    if not await _legacy_share_schema_present(db):
        stats["skipped"] = True
        await _mark_acl_migration_done(db)
        return stats

    general_principal = _general_principal(datasette)

    # Owner + visibility live on the list row.
    lists = (
        await db.execute(
            "SELECT id, created_by, visibility FROM _datasette_places_list"
        )
    ).rows
    for row in lists:
        list_id = str(row["id"])
        created_by = row["created_by"]
        visibility = row["visibility"]

        # Owner → Manager (skip anonymous-created lists: NULL/empty created_by).
        if created_by:
            await acl_grant(
                datasette,
                resource_type,
                list_id,
                actor_id=str(created_by),
                role="Manager",
                by_actor=str(created_by),
            )
            stats["owners"] += 1

        # Visibility → general-access (wildcard) grant.
        vis_role = _VISIBILITY_ROLE.get(visibility)
        if vis_role is not None:
            await acl_grant(
                datasette,
                resource_type,
                list_id,
                actor_id=general_principal,
                role=vis_role,
                by_actor=None,
            )
            stats["visibility"] += 1

    # Explicit per-actor share rows.
    shares = (
        await db.execute(
            "SELECT list_id, actor_id, role, granted_by FROM _datasette_places_share"
        )
    ).rows
    for row in shares:
        share_role = _SHARE_ROLE.get(row["role"])
        if share_role is None:  # pragma: no cover - CHECK constraint guards this
            logger.warning(
                "datasette-places: skipping share with unknown role %r (list %s)",
                row["role"],
                row["list_id"],
            )
            continue
        await acl_grant(
            datasette,
            resource_type,
            str(row["list_id"]),
            actor_id=str(row["actor_id"]),
            role=share_role,
            by_actor=str(row["granted_by"]) if row["granted_by"] else None,
        )
        stats["shares"] += 1

    await _mark_acl_migration_done(db)
    logger.info(
        "datasette-places: migrated shares to acl grants "
        "(owners=%(owners)s shares=%(shares)s visibility=%(visibility)s)",
        stats,
    )
    return stats


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


@migrations()
def m002_list_description(db: Database):
    # A free-text description shown under the list title.
    db.execute("ALTER TABLE _datasette_places_list ADD COLUMN description TEXT")


@migrations()
def m003_drop_legacy_share_model(db: Database):
    # Sharing is now owned by datasette-acl (resource type ``places-list``).
    # The owner/visibility/share data was backfilled into acl grants by the
    # one-time ``migrate_shares_to_acl`` startup routine (see above); this step
    # retires the legacy storage that fed it:
    #
    #   * ``_datasette_places_share``           — explicit per-actor grants
    #   * ``_datasette_places_list.visibility`` — the link-* general-access enum
    #
    # IMPORTANT: this runs in ``ensure_migrations`` BEFORE the startup data
    # migration's read. On any DB that already holds legacy data the backfill
    # ran on a prior boot (its marker is set), so dropping here loses nothing;
    # on a fresh DB there was never any legacy data. ``migrate_shares_to_acl``
    # tolerates the missing column/table (it treats "no legacy schema" as
    # "nothing to migrate").
    #
    # SQLite only learned ``ALTER TABLE ... DROP COLUMN`` in 3.35; sqlite-migrate
    # may run against older engines, so drop ``visibility`` via the portable
    # 12-step table rebuild rather than DROP COLUMN. The rebuilt table keeps the
    # exact column set + constraints + indexes minus ``visibility``.
    db.executescript(
        """
        DROP TABLE IF EXISTS _datasette_places_share;

        CREATE TABLE _datasette_places_list_new (
            id          INTEGER PRIMARY KEY NOT NULL,
            name        TEXT NOT NULL,
            created_by  TEXT,
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            state       TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','trashed')),
            description TEXT
        );

        INSERT INTO _datasette_places_list_new (
            id, name, created_by, created_at, updated_at, state, description
        )
        SELECT
            id, name, created_by, created_at, updated_at, state, description
        FROM _datasette_places_list;

        DROP TABLE _datasette_places_list;
        ALTER TABLE _datasette_places_list_new RENAME TO _datasette_places_list;

        CREATE INDEX IF NOT EXISTS idx_places_list_owner
            ON _datasette_places_list(created_by);
        CREATE INDEX IF NOT EXISTS idx_places_list_state
            ON _datasette_places_list(state);
        """
    )
