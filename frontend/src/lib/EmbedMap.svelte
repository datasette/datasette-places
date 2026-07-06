<script lang="ts">
  import type { Field, MetaValue } from "./fields";
  import MapView from "./MapView.svelte";
  import PlacesTable from "./PlacesTable.svelte";

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

  let {
    places,
    fields,
    listId,
  }: {
    places: Place[];
    fields: Field[];
    listId: number;
  } = $props();

  let view = $state<"map" | "table">("map");
  const noop = () => {};

  // Pins for the map (read-only): the table reads the full place objects.
  let pins = $derived(
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
</script>

<div class="embed">
  <div class="embed-toolbar" role="group" aria-label="View mode">
    <button type="button" class:active={view === "map"} onclick={() => (view = "map")}>
      Map
    </button>
    <button
      type="button"
      class:active={view === "table"}
      onclick={() => (view = "table")}
    >
      Table
    </button>
  </div>
  <div class="embed-body">
    {#if view === "table"}
      <PlacesTable
        {places}
        {fields}
        {listId}
        canEdit={false}
        selectedId={null}
        onSelectPlace={noop}
        onPlaceUpdated={noop}
      />
    {:else}
      <MapView
        places={pins}
        {fields}
        selectedId={null}
        previewPin={null}
        canEdit={false}
        onSelectPlace={noop}
        onMapClick={noop}
        onMovePlace={noop}
      />
    {/if}
  </div>
</div>

<style>
  .embed {
    width: 100%;
    display: flex;
    flex-direction: column;
  }
  .embed-toolbar {
    display: inline-flex;
    align-self: flex-start;
    margin: 0 0 6px;
    border: 1px solid #ccc;
    border-radius: 6px;
    overflow: hidden;
  }
  .embed-toolbar button {
    font: inherit;
    font-size: 0.82em;
    font-weight: 600;
    padding: 4px 14px;
    border: none;
    background: #fff;
    color: #555;
    cursor: pointer;
  }
  .embed-toolbar button + button {
    border-left: 1px solid #ccc;
  }
  .embed-toolbar button.active {
    background: #0b5cad;
    color: #fff;
  }
  .embed-body {
    position: relative;
    height: 420px;
    border: 1px solid #e2e2e2;
    border-radius: 6px;
    overflow: hidden;
  }
</style>
