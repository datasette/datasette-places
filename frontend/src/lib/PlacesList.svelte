<script lang="ts">
  import PlaceCard from "./PlaceCard.svelte";

  type Place = {
    id: number;
    name: string;
    address: string | null;
    latitude: number;
    longitude: number;
    notes: string | null;
    color: string | null;
    metadata: Record<string, string> | null;
  };

  let {
    places,
    selectedId = null,
    canEdit = false,
    onSelectPlace,
    onDeletePlace,
    onUpdatePlace,
  }: {
    places: Place[];
    selectedId: number | null;
    canEdit: boolean;
    onSelectPlace: (id: number) => void;
    onDeletePlace: (id: number) => void;
    onUpdatePlace: (id: number, updates: Partial<Place>) => void;
  } = $props();
</script>

<div class="places-list">
  {#if places.length === 0}
    <p class="empty">No places saved yet. Search for an address above to add one.</p>
  {:else}
    {#each places as place (place.id)}
      <PlaceCard
        {place}
        isSelected={place.id === selectedId}
        {canEdit}
        onSelect={() => onSelectPlace(place.id)}
        onDelete={() => onDeletePlace(place.id)}
        onUpdate={(updates) => onUpdatePlace(place.id, updates)}
      />
    {/each}
  {/if}
</div>

<style>
  .places-list {
    overflow-y: auto;
    flex: 1;
  }
  .empty {
    padding: 16px;
    color: #888;
    font-size: 0.9em;
    text-align: center;
  }
</style>
