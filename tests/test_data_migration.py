"""Tests for the one-time legacy share/visibility → acl-grant data migration
(phase-06/02).

A real upgrade has *pre-existing* lists whose access lived in
``_datasette_places_list.created_by`` / ``.visibility`` and
``_datasette_places_share`` rows, with no acl grants yet.
``migrate_shares_to_acl`` backfills those into acl grants via acl's ``grant``
helper.

NOTE (phase-06/03): the legacy ``visibility`` column + ``_datasette_places_share``
table are dropped by a schema migration once the backfill has run, so a fresh
test DB no longer carries them. To exercise the backfill in isolation, these
tests reconstruct the pre-drop legacy schema (``_recreate_legacy_schema``) and
clear the backfill marker before seeding — reproducing the on-disk state of a
deployment mid-upgrade (legacy rows present, no grants yet).

These tests seed that legacy state directly (raw inserts, *not* the create API,
which would already seed an owner grant), run the migration, then assert both
the resulting grants and the effective ``datasette.allowed`` outcomes, plus
idempotency.
"""

from __future__ import annotations

import pytest
from datasette.app import Datasette

from datasette_acl.grants import list_grants
from datasette_places.migrations import (
    DEFAULT_GENERAL_PRINCIPAL,
    migrate_shares_to_acl,
)
from datasette_places.permissions import (
    PLACES_LIST_RESOURCE_TYPE,
    PlacesListResource,
)


async def _make_ds(config=None):
    base = {
        "permissions": {
            "datasette-places-list": True,
            "datasette-places-create": True,
        }
    }
    if config:
        base.update(config)
    ds = Datasette(memory=True, config=base)
    await ds.invoke_startup()
    return ds


async def _recreate_legacy_schema(ds):
    """Reconstruct the pre-drop legacy share schema for backfill tests.

    A later schema migration drops ``_datasette_places_list.visibility`` and the
    ``_datasette_places_share`` table. The backfill (``migrate_shares_to_acl``)
    reads them, so to test it in isolation we re-add the column + table (mirror
    of the original m001 shape) and clear the backfill marker, putting the DB in
    the state a real deployment had on the upgrade boot where the backfill ran.
    Idempotent: safe to call once per seeded list.
    """
    db = ds.get_internal_database()
    cols = (await db.execute("PRAGMA table_info(_datasette_places_list)")).rows
    if not any(row["name"] == "visibility" for row in cols):
        await db.execute_write(
            "ALTER TABLE _datasette_places_list ADD COLUMN visibility TEXT "
            "NOT NULL DEFAULT 'private' "
            "CHECK (visibility IN ('private','link-view','link-edit'))"
        )
    await db.execute_write(
        "CREATE TABLE IF NOT EXISTS _datasette_places_share ("
        "list_id INTEGER NOT NULL, actor_id TEXT NOT NULL, "
        "role TEXT NOT NULL CHECK (role IN ('viewer','editor')), "
        "granted_by TEXT, "
        "granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), "
        "PRIMARY KEY (list_id, actor_id))"
    )
    # Clear the marker that startup's backfill recorded on the empty DB, so the
    # tests' own (forced) backfill runs against the legacy rows they seed.
    from datasette_places.migrations import _ACL_MIGRATION_TABLE

    await db.execute_write(f"DELETE FROM {_ACL_MIGRATION_TABLE}")


async def _seed_list(ds, *, list_id, created_by, visibility="private", name="L"):
    """Insert a legacy list row directly (bypassing the grant-seeding create path)."""
    await _recreate_legacy_schema(ds)
    db = ds.get_internal_database()
    await db.execute_write(
        "INSERT INTO _datasette_places_list (id, name, created_by, visibility) "
        "VALUES (?, ?, ?, ?)",
        [list_id, name, created_by, visibility],
    )


async def _seed_share(ds, *, list_id, actor_id, role, granted_by="alice"):
    db = ds.get_internal_database()
    await db.execute_write(
        "INSERT INTO _datasette_places_share (list_id, actor_id, role, granted_by) "
        "VALUES (?, ?, ?, ?)",
        [list_id, actor_id, role, granted_by],
    )


async def _grant_map(ds, list_id):
    """Return {actor_id: set(actions)} for actor grants on a list."""
    grants = await list_grants(ds, PLACES_LIST_RESOURCE_TYPE, str(list_id))
    return {
        g["actor_id"]: set(g["actions"]) for g in grants if g["principal"] == "actor"
    }


# ---------------------------------------------------------------------------
# Owner → Manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_migrated_to_manager():
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice", visibility="private")

    stats = await migrate_shares_to_acl(ds, force=True)
    assert stats["owners"] == 1
    assert stats["visibility"] == 0
    assert stats["shares"] == 0

    grants = await _grant_map(ds, 1)
    assert grants["alice"] == {"places-view", "places-edit", "places-manage"}

    res = PlacesListResource(1)
    for action in ("places-view", "places-edit", "places-manage"):
        assert await ds.allowed(action=action, resource=res, actor={"id": "alice"})
    # A stranger sees nothing on a private list.
    assert not await ds.allowed(
        action="places-view", resource=res, actor={"id": "bob"}
    )


@pytest.mark.asyncio
async def test_anonymous_owner_skipped():
    """created_by NULL (anonymous create) yields no owner grant."""
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by=None, visibility="private")

    stats = await migrate_shares_to_acl(ds, force=True)
    assert stats["owners"] == 0

    grants = await _grant_map(ds, 1)
    assert grants == {}


# ---------------------------------------------------------------------------
# Share rows → Viewer / Editor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_rows_migrated_to_viewer_and_editor():
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice")
    await _seed_share(ds, list_id=1, actor_id="bob", role="viewer")
    await _seed_share(ds, list_id=1, actor_id="carol", role="editor")

    stats = await migrate_shares_to_acl(ds, force=True)
    assert stats["owners"] == 1
    assert stats["shares"] == 2

    grants = await _grant_map(ds, 1)
    assert grants["bob"] == {"places-view"}
    assert grants["carol"] == {"places-view", "places-edit"}

    res = PlacesListResource(1)
    # viewer can view, not edit
    assert await ds.allowed(action="places-view", resource=res, actor={"id": "bob"})
    assert not await ds.allowed(
        action="places-edit", resource=res, actor={"id": "bob"}
    )
    # editor can view + edit, not manage
    assert await ds.allowed(action="places-edit", resource=res, actor={"id": "carol"})
    assert not await ds.allowed(
        action="places-manage", resource=res, actor={"id": "carol"}
    )


# ---------------------------------------------------------------------------
# Visibility → general-access principal grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visibility_link_view_grants_signed_in_viewer():
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice", visibility="link-view")

    stats = await migrate_shares_to_acl(ds, force=True)
    assert stats["visibility"] == 1

    grants = await _grant_map(ds, 1)
    assert grants[DEFAULT_GENERAL_PRINCIPAL] == {"places-view"}

    res = PlacesListResource(1)
    # Any signed-in actor can view, but not edit.
    assert await ds.allowed(action="places-view", resource=res, actor={"id": "zed"})
    assert not await ds.allowed(action="places-edit", resource=res, actor={"id": "zed"})
    # Anonymous (no id) does NOT match _signed_in.
    assert not await ds.allowed(action="places-view", resource=res, actor=None)


@pytest.mark.asyncio
async def test_visibility_link_edit_grants_signed_in_editor():
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice", visibility="link-edit")

    stats = await migrate_shares_to_acl(ds, force=True)
    assert stats["visibility"] == 1

    grants = await _grant_map(ds, 1)
    assert grants[DEFAULT_GENERAL_PRINCIPAL] == {"places-view", "places-edit"}

    res = PlacesListResource(1)
    assert await ds.allowed(action="places-edit", resource=res, actor={"id": "zed"})
    assert not await ds.allowed(
        action="places-manage", resource=res, actor={"id": "zed"}
    )


@pytest.mark.asyncio
async def test_private_visibility_grants_nothing_extra():
    """DECISIONS.md: upgrade default CLOSED — private lists stay owner-only."""
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice", visibility="private")

    await migrate_shares_to_acl(ds, force=True)

    grants = await _grant_map(ds, 1)
    # Only the owner, no _signed_in / * principal.
    assert set(grants) == {"alice"}
    assert "_signed_in" not in grants
    assert "*" not in grants


# ---------------------------------------------------------------------------
# Configurable general principal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_general_principal_configurable_to_wildcard():
    ds = await _make_ds(
        config={"plugins": {"datasette-places": {"share-general-principal": "*"}}}
    )
    await _seed_list(ds, list_id=1, created_by="alice", visibility="link-view")

    await migrate_shares_to_acl(ds, force=True)

    grants = await _grant_map(ds, 1)
    assert "*" in grants
    assert grants["*"] == {"places-view"}

    res = PlacesListResource(1)
    # '*' includes anonymous callers.
    assert await ds.allowed(action="places-view", resource=res, actor=None)


@pytest.mark.asyncio
async def test_invalid_general_principal_falls_back_to_default():
    ds = await _make_ds(
        config={
            "plugins": {"datasette-places": {"share-general-principal": "nonsense"}}
        }
    )
    await _seed_list(ds, list_id=1, created_by="alice", visibility="link-view")

    await migrate_shares_to_acl(ds, force=True)

    grants = await _grant_map(ds, 1)
    assert DEFAULT_GENERAL_PRINCIPAL in grants
    assert "nonsense" not in grants


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marker_skips_repeat_run():
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice", visibility="link-view")
    await _seed_share(ds, list_id=1, actor_id="bob", role="editor")

    first = await migrate_shares_to_acl(ds, force=True)
    assert first["skipped"] is False
    assert first["owners"] == 1

    # Without force, the marker recorded by the first run short-circuits.
    second = await migrate_shares_to_acl(ds)
    assert second["skipped"] is True
    assert second["owners"] == 0


@pytest.mark.asyncio
async def test_forced_rerun_no_duplicate_grants_or_audit():
    """A forced second run must not duplicate grants or audit rows."""
    ds = await _make_ds()
    await _seed_list(ds, list_id=1, created_by="alice", visibility="link-edit")
    await _seed_share(ds, list_id=1, actor_id="bob", role="viewer")
    await _seed_share(ds, list_id=1, actor_id="carol", role="editor")

    await migrate_shares_to_acl(ds, force=True)

    db = ds.get_internal_database()
    acl_count_1 = (await db.execute("SELECT count(*) FROM acl")).single_value()
    audit_count_1 = (await db.execute("SELECT count(*) FROM acl_audit")).single_value()
    grants_1 = await _grant_map(ds, 1)

    # Run again, forcing past the marker.
    await migrate_shares_to_acl(ds, force=True)

    acl_count_2 = (await db.execute("SELECT count(*) FROM acl")).single_value()
    audit_count_2 = (await db.execute("SELECT count(*) FROM acl_audit")).single_value()
    grants_2 = await _grant_map(ds, 1)

    assert acl_count_2 == acl_count_1
    assert audit_count_2 == audit_count_1
    assert grants_2 == grants_1


# ---------------------------------------------------------------------------
# End-to-end multi-list spot check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_corpus_migrates_correctly():
    ds = await _make_ds()
    # list 1: private, owner alice, bob editor share
    await _seed_list(ds, list_id=1, created_by="alice", visibility="private")
    await _seed_share(ds, list_id=1, actor_id="bob", role="editor")
    # list 2: link-view, owner carol
    await _seed_list(ds, list_id=2, created_by="carol", visibility="link-view")
    # list 3: link-edit, anonymous owner
    await _seed_list(ds, list_id=3, created_by=None, visibility="link-edit")

    stats = await migrate_shares_to_acl(ds, force=True)
    assert stats["owners"] == 2  # alice, carol (not anon list 3)
    assert stats["shares"] == 1  # bob
    assert stats["visibility"] == 2  # list 2 + list 3

    # list 1: alice manages, bob edits, stranger denied
    r1 = PlacesListResource(1)
    assert await ds.allowed(action="places-manage", resource=r1, actor={"id": "alice"})
    assert await ds.allowed(action="places-edit", resource=r1, actor={"id": "bob"})
    assert not await ds.allowed(
        action="places-view", resource=r1, actor={"id": "stranger"}
    )

    # list 2: carol manages, any signed-in views (not edits)
    r2 = PlacesListResource(2)
    assert await ds.allowed(action="places-manage", resource=r2, actor={"id": "carol"})
    assert await ds.allowed(
        action="places-view", resource=r2, actor={"id": "stranger"}
    )
    assert not await ds.allowed(
        action="places-edit", resource=r2, actor={"id": "stranger"}
    )

    # list 3: no owner, any signed-in edits
    r3 = PlacesListResource(3)
    assert await ds.allowed(action="places-edit", resource=r3, actor={"id": "stranger"})
    assert len(await _grant_map(ds, 3)) == 1  # only the _signed_in principal


# ---------------------------------------------------------------------------
# Startup wiring + empty-DB behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_marks_migration_on_empty_db():
    """startup() runs the migration once; with no lists it just records the marker."""
    ds = await _make_ds()
    db = ds.get_internal_database()
    from datasette_places.migrations import (
        _ACL_MIGRATION_KEY,
        _ACL_MIGRATION_TABLE,
    )

    rows = (
        await db.execute(
            f"SELECT key FROM {_ACL_MIGRATION_TABLE} WHERE key = ?",
            [_ACL_MIGRATION_KEY],
        )
    ).rows
    assert rows, "migration marker not recorded at startup"

    # A subsequent unforced run is a no-op.
    stats = await migrate_shares_to_acl(ds)
    assert stats["skipped"] is True
