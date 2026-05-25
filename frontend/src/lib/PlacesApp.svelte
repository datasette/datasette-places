<script lang="ts">
  import { onMount } from "svelte";
  import MapView from "./MapView.svelte";
  import AddressSearch from "./AddressSearch.svelte";
  import PlacesList from "./PlacesList.svelte";
  import ShareDialog from "./ShareDialog.svelte";

  type Place = {
    id: number;
    list_id: number;
    name: string;
    address: string | null;
    latitude: number;
    longitude: number;
    notes: string | null;
    color: string | null;
    metadata: Record<string, string> | null;
    created_by: string | null;
    created_at: string;
    updated_at: string;
  };

  type GeoResult = {
    display_name: string;
    latitude: number;
    longitude: number;
    components: Record<string, string>;
  };

  type ListDetail = {
    id: number;
    name: string;
    created_by: string | null;
    visibility: string;
    state: string;
    place_count: number;
    updated_at: string;
    permissions: {
      canView: boolean;
      canEdit: boolean;
      canManage: boolean;
      isOwner: boolean;
    };
  };

  let { listId }: { listId: number } = $props();

  let listDetail = $state<ListDetail | null>(null);
  let places = $state<Place[]>([]);
  let selectedId = $state<number | null>(null);
  let previewPin = $state<{ latitude: number; longitude: number; name: string } | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let saving = $state(false);
  let editingName = $state(false);
  let editNameValue = $state("");
  let shareOpen = $state(false);
  let mapView: MapView;

  let canEdit = $derived(listDetail?.permissions?.canEdit ?? false);

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
  }

  async function savePreviewAsPlace() {
    if (!previewPin || saving) return;
    saving = true;
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}/places`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: previewPin.name,
          address: previewPin.name,
          latitude: previewPin.latitude,
          longitude: previewPin.longitude,
        }),
      });
      if (!resp.ok) throw new Error("Failed to save");
      const place = await resp.json();
      places = [...places, place];
      previewPin = null;
      selectedId = place.id;
    } catch {
      error = "Failed to save place";
    }
    saving = false;
  }

  function cancelPreview() {
    previewPin = null;
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

  async function onUpdatePlace(id: number, updates: Partial<Place>) {
    try {
      const resp = await fetch(
        `/-/places/api/lists/${listId}/places/${id}/update`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        }
      );
      if (!resp.ok) throw new Error("Failed to update");
      const updated = await resp.json();
      places = places.map((p) => (p.id === id ? updated : p));
    } catch {
      error = "Failed to update place";
    }
  }

  function onMapClick(lat: number, lon: number) {
    // If we have edit permissions, set a preview pin at click location
    if (canEdit) {
      previewPin = {
        latitude: lat,
        longitude: lon,
        name: `${lat.toFixed(5)}, ${lon.toFixed(5)}`,
      };
    }
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
    }))
  );

  onMount(() => {
    void loadData();
  });
</script>

<div class="places-app">
  {#if loading}
    <div class="loading-screen">Loading...</div>
  {:else if error && !listDetail}
    <div class="error-screen">{error}</div>
  {:else if listDetail}
    <header class="app-header">
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
        {#if listDetail.permissions.isOwner}
          <button
            type="button"
            class="share-btn"
            onclick={() => { shareOpen = true; }}
          >
            Share
          </button>
        {/if}
      </div>
      {#if error}
        <div class="error-inline">{error}</div>
      {/if}
    </header>

    <div class="app-body">
      <aside class="sidebar">
        {#if canEdit}
          <div class="search-section">
            <AddressSearch onSelect={onSearchSelect} />
            {#if previewPin}
              <div class="preview-actions">
                <span class="preview-label" title={previewPin.name}>
                  {previewPin.name.length > 40
                    ? previewPin.name.slice(0, 40) + "..."
                    : previewPin.name}
                </span>
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
            {/if}
          </div>
        {/if}
        <PlacesList
          {places}
          {selectedId}
          {canEdit}
          onSelectPlace={onSelectPlace}
          onDeletePlace={onDeletePlace}
          onUpdatePlace={onUpdatePlace}
        />
      </aside>

      <main class="map-area">
        <MapView
          bind:this={mapView}
          places={mapPlaces}
          {selectedId}
          {previewPin}
          onSelectPlace={onSelectPlace}
          onMapClick={onMapClick}
        />
      </main>
    </div>
    <ShareDialog
      {listId}
      open={shareOpen}
      onClose={() => { shareOpen = false; }}
    />
  {/if}
</div>

<style>
  .places-app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  .loading-screen, .error-screen {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
    font-size: 1.1em;
    color: #666;
  }
  .error-screen { color: #8a1a1a; }

  .app-header {
    padding: 10px 16px;
    border-bottom: 1px solid #ddd;
    background: #fff;
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
  .share-btn {
    font: inherit;
    font-size: 0.85em;
    padding: 4px 14px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
  }
  .share-btn:hover { background: #f0f4f8; }
  .error-inline {
    background: #ffd6d6;
    color: #5a0000;
    padding: 4px 8px;
    border-radius: 3px;
    margin-top: 6px;
    font-size: 0.9em;
  }

  .app-body {
    display: flex;
    flex: 1;
    overflow: hidden;
  }
  .sidebar {
    width: 360px;
    min-width: 280px;
    border-right: 1px solid #ddd;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: #fff;
  }
  .search-section {
    padding: 12px;
    border-bottom: 1px solid #eee;
  }
  .preview-actions {
    margin-top: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .preview-label {
    font-size: 0.85em;
    color: #555;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
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

  .map-area {
    flex: 1;
    position: relative;
  }

  @media (max-width: 768px) {
    .app-body { flex-direction: column-reverse; }
    .sidebar {
      width: 100%;
      max-height: 40vh;
      border-right: none;
      border-top: 1px solid #ddd;
    }
  }
</style>
