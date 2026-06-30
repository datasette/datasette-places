<script lang="ts">
  import { onMount } from "svelte";
  import MapView from "./MapView.svelte";
  import AddressSearch from "./AddressSearch.svelte";
  import PlacesList from "./PlacesList.svelte";
  import FieldsPanel from "./FieldsPanel.svelte";
  import PlacesTable from "./PlacesTable.svelte";
  import type { Field, MetaValue } from "./fields";
  // The <datasette-acl-share-dialog> custom element is registered by the
  // datasette-acl-share JS bundle, which places' extra_js_urls hook includes on
  // the list page — no component import needed here.

  // acl resource identity for a place list: type "places-list", a parent-only
  // resource whose parent is the list id (child omitted).
  const SHARE_RESOURCE_TYPE = "places-list";

  type Place = {
    id: number;
    list_id: number;
    name: string;
    address: string | null;
    latitude: number;
    longitude: number;
    notes: string | null;
    color: string | null;
    metadata: Record<string, MetaValue> | null;
    created_by: string | null;
    created_at: string;
    updated_at: string;
  };

  type UpdateResult = { ok: boolean; errors?: Record<string, string> };

  type GeoResult = {
    display_name: string;
    latitude: number;
    longitude: number;
    components: Record<string, string>;
  };

  type ListDetail = {
    id: number;
    name: string;
    description: string | null;
    created_by: string | null;
    state: string;
    place_count: number;
    updated_at: string;
    permissions: {
      canView: boolean;
      canEdit: boolean;
      canManage: boolean;
      isOwner: boolean;
    };
    fields: Field[];
  };

  let {
    listId,
    actor = null,
  }: {
    listId: number;
    actor?: { id: string } | null;
  } = $props();

  let listDetail = $state<ListDetail | null>(null);
  let places = $state<Place[]>([]);
  let selectedId = $state<number | null>(null);
  let previewPin = $state<{ latitude: number; longitude: number; name: string } | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let saving = $state(false);
  let editingName = $state(false);
  let editNameValue = $state("");
  let editingDesc = $state(false);
  let editDescValue = $state("");
  let geocodingClick = $state(false);
  // Editable title for a place being added (defaults from the address).
  let previewName = $state("");
  // A geocoded street address for the preview, if we have one. Clicking the map
  // drops a pin from coordinates alone (no geocoding required); this stays null
  // unless reverse geocoding succeeds, so we never save a coordinate string as
  // the place's "address".
  let previewAddress = $state<string | null>(null);
  // Map "add" mode, surfaced in the floating panel (the in-map toolbar button
  // can sit behind other chrome like the datasette debug bar).
  let addMode = $state(false);
  // Map vs spreadsheet (Table) view of the same places.
  let viewMode = $state<"map" | "table">("map");

  let fields = $derived(listDetail?.fields ?? []);

  /** First, most-specific part of a comma-separated address — a sane title default. */
  function shortLabel(label: string): string {
    return label.split(",")[0].trim() || label;
  }

  let canEdit = $derived(listDetail?.permissions?.canEdit ?? false);
  // Share is gated on the acl manage capability (the owner gets it via the
  // seeded Manager grant) rather than ownership of the row.
  let canManage = $derived(listDetail?.permissions?.canManage ?? false);
  // actor-json the dialog reads to mark the current user's row "(you)".
  let actorJson = $derived(actor ? JSON.stringify(actor) : "");

  function relativeTime(iso: string): string {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return iso;
    const diff = Date.now() - t;
    if (diff < 60_000) return "just now";
    const mins = Math.round(diff / 60_000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(diff / 3_600_000);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(diff / 86_400_000)}d ago`;
  }

  async function loadData() {
    loading = true;
    error = null;
    try {
      const [listResp, placesResp] = await Promise.all([
        fetch(`/-/places/api/lists/${listId}`, {
          headers: { "Content-Type": "application/json" },
        }),
        fetch(`/-/places/api/lists/${listId}/places`, {
          headers: { "Content-Type": "application/json" },
        }),
      ]);
      if (!listResp.ok || !placesResp.ok) throw new Error("Failed to load");
      listDetail = await listResp.json();
      const data = await placesResp.json();
      places = data.places;
    } catch {
      error = "Failed to load list data";
    }
    loading = false;
  }

  function onSearchSelect(result: GeoResult) {
    previewPin = {
      latitude: result.latitude,
      longitude: result.longitude,
      name: result.display_name,
    };
    previewName = shortLabel(result.display_name);
    previewAddress = result.display_name;
  }

  async function savePreviewAsPlace() {
    if (!previewPin || saving) return;
    saving = true;
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}/places`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: previewName.trim() || previewPin.name,
          // Only a real (geocoded/searched) address — never the coordinate
          // label we fall back to when geocoding is unavailable.
          address: previewAddress,
          latitude: previewPin.latitude,
          longitude: previewPin.longitude,
        }),
      });
      if (!resp.ok) throw new Error("Failed to save");
      const place = await resp.json();
      places = [...places, place];
      previewPin = null;
      previewName = "";
      previewAddress = null;
      selectedId = place.id;
    } catch {
      error = "Failed to save place";
    }
    saving = false;
  }

  function cancelPreview() {
    previewPin = null;
    previewName = "";
    previewAddress = null;
  }

  function onSelectPlace(id: number) {
    selectedId = selectedId === id ? null : id;
  }

  async function onDeletePlace(id: number) {
    if (!window.confirm("Delete this place?")) return;
    try {
      await fetch(`/-/places/api/lists/${listId}/places/${id}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      places = places.filter((p) => p.id !== id);
      if (selectedId === id) selectedId = null;
    } catch {
      error = "Failed to delete place";
    }
  }

  async function onUpdatePlace(
    id: number,
    updates: Partial<Place>
  ): Promise<UpdateResult> {
    try {
      const resp = await fetch(
        `/-/places/api/lists/${listId}/places/${id}/update`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        }
      );
      if (resp.status === 400) {
        // Per-field validation failures: {errors:{<key>:msg}}.
        const data = await resp.json().catch(() => ({}));
        return { ok: false, errors: data.errors };
      }
      if (!resp.ok) throw new Error("Failed to update");
      const updated = await resp.json();
      places = places.map((p) => (p.id === id ? updated : p));
      return { ok: true };
    } catch {
      error = "Failed to update place";
      return { ok: false };
    }
  }

  // Replace a place in local state (used by the table's per-key inline edits,
  // which call the metadata endpoint directly and return the updated place).
  function onPlaceUpdated(updated: Place) {
    places = places.map((p) => (p.id === updated.id ? updated : p));
  }

  // Re-fetch just the list detail after a field-def change so `fields` reflects
  // the new schema without disturbing the loaded places / selection.
  async function reloadFields() {
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}`, {
        headers: { "Content-Type": "application/json" },
      });
      if (resp.ok) listDetail = await resp.json();
    } catch {
      error = "Failed to reload fields";
    }
  }

  async function onMapClick(lat: number, lon: number) {
    if (!canEdit) return;
    // Drop the pin immediately with coordinates, then try to resolve a real
    // address via reverse geocoding and upgrade the label when it arrives.
    const coordLabel = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    previewPin = { latitude: lat, longitude: lon, name: coordLabel };
    previewName = coordLabel;
    // No address yet — reverse geocoding below is best-effort and may be
    // unavailable (e.g. no OpenCage key configured for this demo).
    previewAddress = null;
    geocodingClick = true;
    try {
      const resp = await fetch(
        `/-/places/api/reverse?lat=${lat}&lon=${lon}`,
        { headers: { "Content-Type": "application/json" } }
      );
      if (resp.ok) {
        const data = await resp.json();
        // Only apply if the user hasn't moved/cancelled the pin meanwhile.
        if (
          previewPin &&
          previewPin.latitude === lat &&
          previewPin.longitude === lon &&
          data.display_name
        ) {
          previewPin = { ...previewPin, name: data.display_name };
          previewAddress = data.display_name;
          // Upgrade the title default too, unless the user already edited it.
          if (previewName === coordLabel) previewName = shortLabel(data.display_name);
        }
      }
      // A non-200 (e.g. geocoding not configured) is swallowed: the pin stays
      // dropped at the clicked coordinates with no address.
    } catch {
      // Keep the coordinate label on failure — non-fatal.
    }
    geocodingClick = false;
  }

  async function onMovePlace(id: number, lat: number, lon: number) {
    await onUpdatePlace(id, {
      latitude: lat,
      longitude: lon,
    } as Partial<Place>);
  }

  async function saveListDescription() {
    const value = editDescValue.trim();
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}/describe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: value }),
      });
      if (!resp.ok) throw new Error("Failed to save description");
      const data = await resp.json();
      if (listDetail) listDetail = { ...listDetail, description: data.description };
    } catch {
      error = "Failed to save description";
    }
    editingDesc = false;
  }

  function startEditDesc() {
    if (!canEdit) return;
    editDescValue = listDetail?.description ?? "";
    editingDesc = true;
  }

  function startEditName() {
    if (!listDetail || !canEdit) return;
    editNameValue = listDetail.name;
    editingName = true;
  }

  async function saveListName() {
    if (!editNameValue.trim()) return;
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editNameValue.trim() }),
      });
      if (!resp.ok) throw new Error("Failed to rename");
      const data = await resp.json();
      if (listDetail) listDetail = { ...listDetail, name: data.name };
    } catch {
      error = "Failed to rename list";
    }
    editingName = false;
  }

  let mapPlaces = $derived(
    places.map((p) => ({
      id: p.id,
      name: p.name,
      address: p.address,
      latitude: p.latitude,
      longitude: p.longitude,
      color: p.color || "#3b82f6",
      shape: String(p.metadata?.shape || "pin"),
      metadata: p.metadata,
    }))
  );

  onMount(() => {
    void loadData();
    // Let the map run fullscreen beneath datasette's nav (see app.css).
    document.body.classList.add("places-fullscreen");
    return () => document.body.classList.remove("places-fullscreen");
  });
</script>

<div class="places-app">
  {#if loading}
    <div class="loading-screen">Loading...</div>
  {:else if error && !listDetail}
    <div class="error-screen">{error}</div>
  {:else if listDetail}
    <div class="stage" class:split={viewMode === "table"}>
    {#if viewMode === "table"}
      <section class="table-pane">
        <PlacesTable
          {places}
          {fields}
          {listId}
          {canEdit}
          {selectedId}
          onSelectPlace={onSelectPlace}
          onPlaceUpdated={onPlaceUpdated}
        />
      </section>
    {/if}
    <section class="map-pane">
      {#if canEdit}
        <div class="map-search-overlay">
          <AddressSearch onSelect={onSearchSelect} />
          {#if previewPin}
            <div class="preview-card">
              <input
                type="text"
                class="preview-name"
                bind:value={previewName}
                placeholder="Place name"
                aria-label="Place name"
                onkeydown={(e) => {
                  if (e.key === "Enter") void savePreviewAsPlace();
                  if (e.key === "Escape") cancelPreview();
                }}
              />
              <div class="preview-label" title={previewPin.name}>
                {previewPin.name.length > 48
                  ? previewPin.name.slice(0, 48) + "..."
                  : previewPin.name}
                {#if geocodingClick}<em class="lookup">finding address…</em>{/if}
              </div>
              <div class="preview-buttons">
                <button
                  type="button"
                  class="btn-save"
                  disabled={saving}
                  onclick={savePreviewAsPlace}
                >
                  {saving ? "Saving..." : "Save place"}
                </button>
                <button type="button" class="btn-cancel" onclick={cancelPreview}>
                  Cancel
                </button>
              </div>
            </div>
          {/if}
        </div>
      {/if}
      <MapView
        places={mapPlaces}
        {fields}
        {selectedId}
        {previewPin}
        {canEdit}
        bind:addMode
        onSelectPlace={onSelectPlace}
        onMapClick={onMapClick}
        onMovePlace={onMovePlace}
      />
    </section>
    </div>

    <aside class="floating-panel">
      <div class="panel-header">
        <a href="/-/places/" class="back-link">&larr; All Lists</a>
        <div class="title-row">
          {#if editingName}
            <input
              type="text"
              class="title-input"
              bind:value={editNameValue}
              onkeydown={(e) => {
                if (e.key === "Enter") void saveListName();
                if (e.key === "Escape") editingName = false;
              }}
              onblur={() => void saveListName()}
            />
          {:else}
            {#if canEdit}
              <h1><button type="button" class="title-btn" onclick={startEditName}>{listDetail.name}</button></h1>
            {:else}
              <h1>{listDetail.name}</h1>
            {/if}
          {/if}
          {#if canManage}
            <FieldsPanel {listId} {fields} onChanged={reloadFields} />
            <!-- The <datasette-acl-share-dialog> custom element (registered by the
                 datasette-acl-share bundle) is self-contained: it renders its OWN
                 trigger button + dialog and talks to the acl JSON API directly. We
                 render it inline as the Share button (trigger-label="Share") rather
                 than wrapping it in a second modal. places is parent-only: parent =
                 list id, no child. -->
            <datasette-acl-share-dialog
              class="share-dialog"
              resource-type={SHARE_RESOURCE_TYPE}
              parent={String(listId)}
              resource-label={listDetail.name ?? ""}
              actor-json={actorJson}
              trigger-label="Share"
              features="people,groups,agents,public"
            ></datasette-acl-share-dialog>
          {/if}
        </div>

        {#if editingDesc}
          <textarea
            class="desc-input"
            bind:value={editDescValue}
            rows="2"
            placeholder="Add a description for this map..."
            onkeydown={(e) => {
              if (e.key === "Escape") editingDesc = false;
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void saveListDescription();
            }}
            onblur={() => void saveListDescription()}
          ></textarea>
        {:else if listDetail.description}
          {#if canEdit}
            <button type="button" class="desc-btn" onclick={startEditDesc} title="Edit description">
              {listDetail.description}
            </button>
          {:else}
            <p class="desc">{listDetail.description}</p>
          {/if}
        {:else if canEdit}
          <button type="button" class="desc-add" onclick={startEditDesc}>
            + Add description
          </button>
        {/if}

        <div class="meta-row">
          <div class="meta-line">
            {places.length}
            {places.length === 1 ? "place" : "places"}
            · edited {relativeTime(listDetail.updated_at)}
          </div>
          <button
            type="button"
            class="view-toggle-btn"
            class:active={viewMode === "table"}
            aria-pressed={viewMode === "table"}
            title={viewMode === "table" ? "Hide the table" : "Show a table of all places"}
            onclick={() => (viewMode = viewMode === "table" ? "map" : "table")}
          >
            ▤ Table
          </button>
        </div>

        {#if canEdit}
          <button
            type="button"
            class="add-place-btn"
            class:active={addMode}
            onclick={() => (addMode = !addMode)}
          >
            {addMode ? "Click the map to drop a pin — done" : "+ Add a place"}
          </button>
        {/if}

        {#if error}
          <div class="error-inline">{error}</div>
        {/if}
      </div>

      {#if viewMode === "map"}
        <PlacesList
          {places}
          {fields}
          {selectedId}
          {canEdit}
          onSelectPlace={onSelectPlace}
          onDeletePlace={onDeletePlace}
          onUpdatePlace={onUpdatePlace}
        />
      {/if}
    </aside>
  {/if}
</div>

<style>
  .places-app {
    position: relative;
    height: 100%;
    overflow: hidden;
  }
  .loading-screen, .error-screen {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-size: 1.1em;
    color: #666;
  }
  .error-screen { color: #8a1a1a; }

  /* Floating list panel layered over the fullscreen map. */
  .floating-panel {
    position: absolute;
    top: 14px;
    left: 14px;
    z-index: 700;
    width: 340px;
    max-width: calc(100% - 28px);
    max-height: calc(100% - 28px);
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 14px rgba(0, 0, 0, 0.28);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .panel-header {
    padding: 10px 16px;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
  }
  .back-link {
    font-size: 0.85em;
    color: #0b5cad;
    text-decoration: none;
  }
  .back-link:hover { text-decoration: underline; }
  .title-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 2px;
  }
  h1 {
    margin: 0;
    font-size: 1.3em;
    line-height: 1.3;
  }
  .title-btn {
    all: unset;
    font: inherit;
    cursor: pointer;
  }
  .title-btn:hover { color: #0b5cad; }
  .title-input {
    font: inherit;
    font-size: 1.3em;
    font-weight: 700;
    padding: 0 4px;
    border: 1px solid #0b5cad;
    border-radius: 3px;
    outline: none;
  }
  /* The <datasette-acl-share-dialog> custom element ships its own trigger +
     dialog styles (light DOM, datasette-acl-share-* prefixed). We only nudge
     the inline trigger to sit nicely next to the title. */
  .share-dialog {
    display: inline-flex;
    align-items: center;
  }
  .error-inline {
    background: #ffd6d6;
    color: #5a0000;
    padding: 4px 8px;
    border-radius: 3px;
    margin-top: 6px;
    font-size: 0.9em;
  }
  .desc, .desc-btn {
    margin: 4px 0 0;
    font-size: 0.88em;
    color: #555;
    line-height: 1.4;
    white-space: pre-wrap;
  }
  .desc-btn {
    display: block;
    text-align: left;
    width: 100%;
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: #555;
    cursor: pointer;
  }
  .desc-btn:hover { color: #0b5cad; }
  .desc-add {
    margin-top: 4px;
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    font-size: 0.82em;
    color: #0b5cad;
    cursor: pointer;
  }
  .desc-add:hover { text-decoration: underline; }
  .desc-input {
    display: block;
    width: 100%;
    margin-top: 4px;
    font: inherit;
    font-size: 0.88em;
    padding: 4px 6px;
    border: 1px solid #0b5cad;
    border-radius: 3px;
    resize: vertical;
  }
  .meta-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-top: 6px;
  }
  .meta-line {
    font-size: 0.78em;
    color: #888;
  }

  .add-place-btn {
    margin-top: 10px;
    width: 100%;
    padding: 7px 10px;
    background: #0b5cad;
    color: #fff;
    border: 1px solid #0b5cad;
    border-radius: 6px;
    font: inherit;
    font-size: 0.85em;
    font-weight: 600;
    cursor: pointer;
  }
  .add-place-btn:hover {
    background: #0a4f95;
  }
  .add-place-btn.active {
    background: #fff;
    color: #0b5cad;
  }

  .floating-panel :global(.places-list) {
    min-height: 0;
  }
  .map-search-overlay {
    position: absolute;
    top: 10px;
    /* Centered in the map area to the right of the floating panel. */
    left: calc(50% + 175px);
    transform: translateX(-50%);
    z-index: 600;
    width: min(380px, calc(100% - 110px));
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .map-search-overlay :global(.search-input-row) {
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
    border-radius: 4px;
  }
  .preview-card {
    padding: 8px;
    border: 1px solid #d6d6d6;
    border-radius: 5px;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.22);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .preview-name {
    font: inherit;
    font-weight: 600;
    font-size: 0.95em;
    padding: 5px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    outline: none;
  }
  .preview-name:focus {
    border-color: #0b5cad;
    box-shadow: 0 0 0 2px rgba(11, 92, 173, 0.15);
  }
  .preview-label {
    font-size: 0.8em;
    color: #777;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .preview-buttons {
    display: flex;
    gap: 6px;
  }
  .lookup { color: #999; font-size: 0.9em; }
  .btn-save, .btn-cancel {
    padding: 4px 12px;
    border: 1px solid #ccc;
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
    font-size: 0.85em;
    background: #fff;
  }
  .btn-save {
    background: #0b5cad;
    color: #fff;
    border-color: #0b5cad;
  }
  .btn-save:hover { background: #094a8d; }
  .btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-cancel:hover { background: #f0f0f0; }

  /* The stage stacks its panes vertically. Map-only → the map fills it; in
     "split" (table) view the table sits on top and the map stays below. */
  .stage {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
  }
  .map-pane {
    position: relative;
    flex: 1 1 0;
    min-height: 0;
  }
  /* In split view the table clears the floating panel on the left and scrolls
     within its own pane. It fits its content but never takes more than ~62% of
     the height, so a short list doesn't leave a gap and the map keeps the rest. */
  .table-pane {
    position: relative;
    flex: 0 1 auto;
    max-height: 62%;
    overflow: auto;
    background: #fff;
    padding-left: 368px;
    border-bottom: 1px solid #ddd;
  }

  /* Small, secondary toggle that matches the Fields/Share panel buttons rather
     than a big primary call-to-action. Active = subtly tinted, not filled. */
  .view-toggle-btn {
    flex-shrink: 0;
    font: inherit;
    font-size: 0.82em;
    padding: 4px 10px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    color: #444;
    cursor: pointer;
    white-space: nowrap;
  }
  .view-toggle-btn:hover {
    background: #f0f0f0;
  }
  .view-toggle-btn.active {
    background: #eef3fb;
    border-color: #9cc0ec;
    color: #0b5cad;
  }

  @media (max-width: 768px) {
    /* List becomes a bottom sheet; map stays fullscreen behind it. */
    .floating-panel {
      top: auto;
      bottom: 0;
      left: 0;
      width: 100%;
      max-width: 100%;
      max-height: 45vh;
      border-radius: 12px 12px 0 0;
    }
    /* Re-center the search across the full width, clear of the controls. */
    .map-search-overlay {
      left: 50%;
      width: calc(100% - 88px);
      top: 8px;
    }
    /* Panel is a bottom sheet now, so the table pane uses the full width; the
       map pane keeps the lower portion behind the sheet. */
    .table-pane {
      padding-left: 0;
    }
  }
</style>
