-- schema: ../../schema.db

-- Named queries for datasette-places.
--
-- Edit here, then run `just codegen-queries` to regenerate
-- `queries.sql.json` (the IR) and `queries_generated.py` (typed Python helpers).
-- `just check-queries-fresh` is the CI gate.
--
-- solite codegen syntax (subset):
--     -- name: foo                     -- :rows by default → list[Row]
--     -- name: foo :rows -> PlaceList  -- list[PlaceList] using a named class
--     -- name: foo :row  -> PlaceList  -- PlaceList | None
--     -- name: foo :value              -- scalar | None
--     -- name: foo                     -- None for INSERT/UPDATE/DELETE
--
-- Parameter sigils:
--     $foo::text                       -- non-null text → str
--     $foo::text::                     -- nullable text → str | None
--     $foo::integer                    -- int (non-null)
--     $foo::real                       -- float (non-null)
--
-- Schema is resolved from migrations.py (see `just codegen-queries`), so every
-- result type + nullability below is validated against the real columns.
-- Multi-statement orchestration (RETURNING the row, then bumping the parent
-- list's updated_at) lives in db.py — codegen emits one helper per query block.

-- ============================================================================
-- Lists
--
-- Every PlaceList-returning query selects the same column set so the generated
-- ``PlaceList`` dataclass has one shape:
--   id, name, created_by, created_at, updated_at, state, description
-- ============================================================================

-- name: insertList :row -> PlaceList
INSERT INTO _datasette_places_list (name, created_by)
VALUES ($name::text, $created_by::text::)
RETURNING id, name, created_by, created_at, updated_at, state, description;

-- name: selectListById :row -> PlaceList
SELECT id, name, created_by, created_at, updated_at, state, description
FROM _datasette_places_list
WHERE id = $list_id::integer;

-- Variable-length IN clause: the caller passes a JSON array of integer list
-- ids (db.py uses ``json.dumps(...)``); ``json_each`` unpacks it. An empty
-- list collapses to no rows naturally.
-- name: listListsByIdsAndState :rows -> PlaceList
SELECT l.id, l.name, l.created_by, l.created_at, l.updated_at, l.state, l.description
FROM _datasette_places_list l
JOIN json_each($ids_json::text) je ON je.value = l.id
WHERE l.state = $state::text
ORDER BY l.updated_at DESC;

-- name: updateListName :row -> PlaceList
UPDATE _datasette_places_list
SET name = $name::text,
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $list_id::integer
RETURNING id, name, created_by, created_at, updated_at, state, description;

-- name: updateListDescription :row -> PlaceList
UPDATE _datasette_places_list
SET description = $description::text::,
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $list_id::integer
RETURNING id, name, created_by, created_at, updated_at, state, description;

-- name: trashList
UPDATE _datasette_places_list
SET state = 'trashed',
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $list_id::integer;

-- name: restoreList
UPDATE _datasette_places_list
SET state = 'active',
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $list_id::integer;

-- Bump a list's updated_at. Chained in db.py after place inserts/updates/deletes
-- so the parent list sorts to the top of the index.
-- name: bumpListUpdatedAt
UPDATE _datasette_places_list
SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $list_id::integer;

-- name: placeCountForList :value
SELECT COUNT(*) FROM _datasette_places_place WHERE list_id = $list_id::integer;

-- Per-list place counts for a set of list ids. db.py turns the rows into a
-- ``{list_id: cnt}`` dict.
-- name: placeCountsByListIds :rows -> PlaceCount
SELECT list_id, COUNT(*) AS cnt
FROM _datasette_places_place
WHERE list_id IN (SELECT CAST(value AS INTEGER) FROM json_each($ids_json::text))
GROUP BY list_id;

-- ============================================================================
-- Places
--
-- Every Place-returning query selects the same column set so the generated
-- ``Place`` dataclass has one shape:
--   id, list_id, name, address, latitude, longitude, notes, color,
--   metadata_json, created_by, created_at, updated_at
-- ============================================================================

-- name: insertPlace :row -> Place
INSERT INTO _datasette_places_place
    (list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by)
VALUES
    ($list_id::integer, $name::text, $address::text::, $latitude::real, $longitude::real,
     $notes::text::, $color::text::, $metadata_json::text::, $created_by::text::)
RETURNING id, list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by, created_at, updated_at;

-- name: selectPlacesForList :rows -> Place
SELECT id, list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by, created_at, updated_at
FROM _datasette_places_place
WHERE list_id = $list_id::integer
ORDER BY created_at ASC;

-- name: selectPlaceById :row -> Place
SELECT id, list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by, created_at, updated_at
FROM _datasette_places_place
WHERE id = $place_id::integer;

-- Just the parent list id for a place — used by db.py's delete orchestration to
-- bump the list's updated_at after the row is gone.
-- name: selectPlaceListId :value
SELECT list_id FROM _datasette_places_place WHERE id = $place_id::integer;

-- db.py merges partial updates against the current row before calling this, so
-- every field is supplied (nullable ones may be NULL).
-- name: updatePlace :row -> Place
UPDATE _datasette_places_place
SET name = $name::text,
    address = $address::text::,
    latitude = $latitude::real,
    longitude = $longitude::real,
    notes = $notes::text::,
    color = $color::text::,
    metadata_json = $metadata_json::text::,
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $place_id::integer
RETURNING id, list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by, created_at, updated_at;

-- name: deletePlace
DELETE FROM _datasette_places_place WHERE id = $place_id::integer;

-- ============================================================================
-- List fields (user-defined per-list metadata schema)
--
-- Every ListField-returning query selects the same column set so the generated
-- ``ListField`` dataclass has one shape:
--   id, list_id, key, label, type, position, required, is_unique, config_json,
--   created_at, updated_at
-- ``key`` is whitelisted (^[a-z][a-z0-9_]{0,62}$) and reserved-checked in
-- datasette_places.fields before it ever reaches these queries or the dynamic
-- view DDL in db.py.
-- ============================================================================

-- name: insertListField :row -> ListField
INSERT INTO _datasette_places_list_field
    (list_id, key, label, type, position, required, is_unique, config_json)
VALUES
    ($list_id::integer, $key::text, $label::text, $type::text, $position::integer,
     $required::integer, $is_unique::integer, $config_json::text)
RETURNING id, list_id, key, label, type, position, required, is_unique, config_json, created_at, updated_at;

-- name: selectFieldsForList :rows -> ListField
SELECT id, list_id, key, label, type, position, required, is_unique, config_json, created_at, updated_at
FROM _datasette_places_list_field
WHERE list_id = $list_id::integer
ORDER BY position ASC, id ASC;

-- name: selectListFieldById :row -> ListField
SELECT id, list_id, key, label, type, position, required, is_unique, config_json, created_at, updated_at
FROM _datasette_places_list_field
WHERE id = $field_id::integer;

-- name: maxFieldPositionForList :value
SELECT COALESCE(MAX(position), -1) FROM _datasette_places_list_field
WHERE list_id = $list_id::integer;

-- name: updateListField :row -> ListField
UPDATE _datasette_places_list_field
SET label = $label::text,
    type = $type::text,
    position = $position::integer,
    required = $required::integer,
    is_unique = $is_unique::integer,
    config_json = $config_json::text,
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $field_id::integer
RETURNING id, list_id, key, label, type, position, required, is_unique, config_json, created_at, updated_at;

-- name: deleteListField
DELETE FROM _datasette_places_list_field WHERE id = $field_id::integer;

-- ============================================================================
-- Per-key place metadata writes (json_set / json_remove)
--
-- Targeted single-attribute edits that avoid a read-modify-write of the whole
-- metadata bag. ``$key`` is whitelisted before it reaches here; ``$value_json``
-- is a JSON-encoded scalar so types round-trip. Reserved keys like ``shape``
-- are preserved (json_set only touches the named path).
-- ============================================================================

-- name: setPlaceMetadataKey :row -> Place
UPDATE _datasette_places_place
SET metadata_json = json_set(COALESCE(metadata_json, '{}'), '$.' || $key::text, json($value_json::text)),
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $place_id::integer
RETURNING id, list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by, created_at, updated_at;

-- name: removePlaceMetadataKey :row -> Place
UPDATE _datasette_places_place
SET metadata_json = json_remove(COALESCE(metadata_json, '{}'), '$.' || $key::text),
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $place_id::integer
RETURNING id, list_id, name, address, latitude, longitude, notes, color, metadata_json, created_by, created_at, updated_at;
