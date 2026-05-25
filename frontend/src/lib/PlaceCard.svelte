<script lang="ts">
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
    place,
    isSelected = false,
    canEdit = false,
    onSelect,
    onDelete,
    onUpdate,
  }: {
    place: Place;
    isSelected: boolean;
    canEdit: boolean;
    onSelect: () => void;
    onDelete: () => void;
    onUpdate: (updates: Partial<Place>) => void;
  } = $props();

  let editing = $state(false);
  let editName = $state("");
  let editNotes = $state("");
  let editColor = $state("");

  function startEdit() {
    editName = place.name;
    editNotes = place.notes || "";
    editColor = place.color || "#3b82f6";
    editing = true;
  }

  function saveEdit() {
    const updates: Record<string, unknown> = {};
    if (editName.trim() && editName !== place.name) updates.name = editName.trim();
    if (editNotes !== (place.notes || "")) updates.notes = editNotes;
    if (editColor !== (place.color || "#3b82f6")) updates.color = editColor;
    if (Object.keys(updates).length > 0) {
      onUpdate(updates as Partial<Place>);
    }
    editing = false;
  }

  function cancelEdit() {
    editing = false;
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") cancelEdit();
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveEdit(); }
  }
</script>

<div
  class="place-card"
  class:selected={isSelected}
  role="button"
  tabindex="0"
  onclick={onSelect}
  onkeydown={(e) => { if (e.key === "Enter") onSelect(); }}
>
  <div class="header">
    <span
      class="color-dot"
      style="background: {place.color || '#3b82f6'}"
    ></span>
    {#if editing}
      <input
        type="text"
        class="edit-name"
        bind:value={editName}
        onkeydown={onKeydown}
        onclick={(e) => e.stopPropagation()}
      />
    {:else}
      <span class="name">{place.name}</span>
    {/if}
  </div>

  {#if place.address}
    <div class="address">{place.address}</div>
  {/if}

  {#if editing}
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="edit-form" onclick={(e) => e.stopPropagation()}>
      <label>
        Color:
        <input type="color" bind:value={editColor} />
      </label>
      <textarea
        bind:value={editNotes}
        placeholder="Notes..."
        rows="2"
        onkeydown={onKeydown}
      ></textarea>
      <div class="edit-actions">
        <button type="button" class="btn-save" onclick={saveEdit}>Save</button>
        <button type="button" class="btn-cancel" onclick={cancelEdit}>Cancel</button>
      </div>
    </div>
  {:else}
    {#if place.notes}
      <div class="notes">{place.notes}</div>
    {/if}
    {#if canEdit}
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div class="actions" onclick={(e) => e.stopPropagation()}>
        <button type="button" onclick={startEdit}>Edit</button>
        <button type="button" class="danger" onclick={onDelete}>Delete</button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .place-card {
    padding: 10px 12px;
    border-bottom: 1px solid #eee;
    cursor: pointer;
    transition: background 0.1s;
  }
  .place-card:hover { background: #f8f9fa; }
  .place-card.selected { background: #e8f0fe; border-left: 3px solid #0b5cad; }
  .header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .color-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .name { font-weight: 600; font-size: 0.95em; }
  .address { font-size: 0.85em; color: #666; margin-top: 2px; padding-left: 20px; }
  .notes { font-size: 0.85em; color: #555; margin-top: 4px; padding-left: 20px; white-space: pre-wrap; }
  .actions {
    margin-top: 6px;
    padding-left: 20px;
    display: flex;
    gap: 6px;
  }
  .actions button {
    border: 1px solid #ccc;
    background: #fff;
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.8em;
  }
  .actions button:hover { background: #f0f0f0; }
  .actions button.danger { color: #8a1a1a; border-color: #daa; }
  .actions button.danger:hover { background: #fbecec; }
  .edit-form {
    margin-top: 8px;
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .edit-name {
    flex: 1;
    font: inherit;
    font-weight: 600;
    padding: 2px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
  }
  .edit-form textarea {
    font: inherit;
    font-size: 0.9em;
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    resize: vertical;
  }
  .edit-form label {
    font-size: 0.85em;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .edit-form input[type="color"] {
    width: 28px;
    height: 24px;
    padding: 0;
    border: 1px solid #ccc;
    border-radius: 3px;
    cursor: pointer;
  }
  .edit-actions {
    display: flex;
    gap: 6px;
  }
  .btn-save, .btn-cancel {
    padding: 3px 10px;
    border: 1px solid #ccc;
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
    font-size: 0.85em;
    background: #fff;
  }
  .btn-save { background: #0b5cad; color: #fff; border-color: #0b5cad; }
  .btn-save:hover { background: #094a8d; }
  .btn-cancel:hover { background: #f0f0f0; }
</style>
