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
-- Geocoder instances
--
-- Every Geocoder-returning query selects the same column set so the generated
-- ``Geocoder`` dataclass has one shape:
--   id, provider_type, label, config_json, enabled, created_by, created_at, updated_at
-- ============================================================================

-- name: insertGeocoder :row -> Geocoder
INSERT INTO _datasette_places_geocoder (id, provider_type, label, config_json, enabled, created_by)
VALUES ($id::text, $provider_type::text, $label::text, $config_json::text, $enabled::integer, $created_by::text::)
RETURNING id, provider_type, label, config_json, enabled, created_by, created_at, updated_at;

-- name: selectGeocoderById :row -> Geocoder
SELECT id, provider_type, label, config_json, enabled, created_by, created_at, updated_at
FROM _datasette_places_geocoder
WHERE id = $id::text;

-- name: listGeocoders :rows -> Geocoder
SELECT id, provider_type, label, config_json, enabled, created_by, created_at, updated_at
FROM _datasette_places_geocoder
ORDER BY label COLLATE NOCASE ASC;

-- name: listGeocodersByIds :rows -> Geocoder
SELECT g.id, g.provider_type, g.label, g.config_json, g.enabled, g.created_by, g.created_at, g.updated_at
FROM _datasette_places_geocoder g
JOIN json_each($ids_json::text) je ON je.value = g.id
ORDER BY g.label COLLATE NOCASE ASC;

-- name: updateGeocoder :row -> Geocoder
UPDATE _datasette_places_geocoder
SET label = $label::text,
    config_json = $config_json::text,
    enabled = $enabled::integer,
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE id = $id::text
RETURNING id, provider_type, label, config_json, enabled, created_by, created_at, updated_at;

-- name: deleteGeocoder
DELETE FROM _datasette_places_geocoder WHERE id = $id::text;

-- ============================================================================
-- Per-list geocoder attachments
--
-- Every ListGeocoder-returning query selects the same column set:
--   list_id, geocoder_id, enabled, is_default, position, added_by, added_at
-- listGeocodersForList joins the instance columns for display (ListGeocoderRow).
-- ============================================================================

-- name: attachGeocoderToList :row -> ListGeocoder
INSERT INTO _datasette_places_list_geocoder (list_id, geocoder_id, enabled, is_default, position, added_by)
VALUES ($list_id::integer, $geocoder_id::text, 1, 0,
        (SELECT COALESCE(MAX(position), -1) + 1 FROM _datasette_places_list_geocoder WHERE list_id = $list_id::integer),
        $added_by::text::)
ON CONFLICT (list_id, geocoder_id) DO UPDATE SET enabled = 1
RETURNING list_id, geocoder_id, enabled, is_default, position, added_by, added_at;

-- name: selectListGeocoder :row -> ListGeocoder
SELECT list_id, geocoder_id, enabled, is_default, position, added_by, added_at
FROM _datasette_places_list_geocoder
WHERE list_id = $list_id::integer AND geocoder_id = $geocoder_id::text;

-- listGeocodersForList joins instance columns so the API can render the
-- attachment without a second lookup.
-- name: listGeocodersForList :rows -> ListGeocoderRow
SELECT lg.list_id, lg.geocoder_id, lg.enabled, lg.is_default, lg.position,
       g.provider_type, g.label, g.config_json, g.enabled AS geocoder_enabled
FROM _datasette_places_list_geocoder lg
JOIN _datasette_places_geocoder g ON g.id = lg.geocoder_id
WHERE lg.list_id = $list_id::integer
ORDER BY lg.position ASC, g.label COLLATE NOCASE ASC;

-- name: defaultGeocoderForList :value
SELECT geocoder_id
FROM _datasette_places_list_geocoder
WHERE list_id = $list_id::integer AND is_default = 1 AND enabled = 1
LIMIT 1;

-- name: setListGeocoderEnabled
UPDATE _datasette_places_list_geocoder
SET enabled = $enabled::integer
WHERE list_id = $list_id::integer AND geocoder_id = $geocoder_id::text;

-- Clear every default flag for a list (called before setting a new default so
-- at most one row is is_default=1).
-- name: clearListGeocoderDefault
UPDATE _datasette_places_list_geocoder
SET is_default = 0
WHERE list_id = $list_id::integer;

-- name: setListGeocoderDefault
UPDATE _datasette_places_list_geocoder
SET is_default = 1
WHERE list_id = $list_id::integer AND geocoder_id = $geocoder_id::text;

-- name: detachGeocoderFromList
DELETE FROM _datasette_places_list_geocoder
WHERE list_id = $list_id::integer AND geocoder_id = $geocoder_id::text;
