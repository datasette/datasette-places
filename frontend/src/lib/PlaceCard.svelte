<script lang="ts">
  import type { Field, MetaValue } from "./fields";
  import { sortedFields } from "./fields";
  import FieldValue from "./FieldValue.svelte";
  import FieldInput from "./FieldInput.svelte";

  type Place = {
    id: number;
    name: string;
    address: string | null;
    latitude: number;
    longitude: number;
    notes: string | null;
    color: string | null;
    metadata: Record<string, MetaValue> | null;
  };

  type UpdateResult = { ok: boolean; errors?: Record<string, string> };

  const SHAPES = ["pin", "circle", "square", "star", "flag"] as const;
  const SHAPE_GLYPH: Record<string, string> = {
    pin: "📍",
    circle: "⬤",
    square: "⬛",
    star: "★",
    flag: "⚑",
  };

  let {
    place,
    fields = [],
    isSelected = false,
    canEdit = false,
    onSelect,
    onDelete,
    onUpdate,
  }: {
    place: Place;
    fields?: Field[];
    isSelected: boolean;
    canEdit: boolean;
    onSelect: () => void;
    onDelete: () => void;
    onUpdate: (updates: Partial<Place>) => Promise<UpdateResult> | void;
  } = $props();

  let editing = $state(false);
  let editName = $state("");
  let editNotes = $state("");
  let editColor = $state("");
  let editShape = $state("pin");
  // Per-field values being edited, keyed by field key.
  let editMeta = $state<Record<string, MetaValue>>({});
  let fieldErrors = $state<Record<string, string>>({});
  let saving = $state(false);
  let cardEl: HTMLDivElement | undefined = $state();

  let orderedFields = $derived(sortedFields(fields));
  // Declared fields that have a value to show in the read view.
  let displayFields = $derived(
    orderedFields.filter((f) => {
      const v = place.metadata?.[f.key];
      return !(
        v === null ||
        v === undefined ||
        v === "" ||
        (Array.isArray(v) && v.length === 0)
      );
    })
  );

  let shape = $derived(String(place.metadata?.shape || "pin"));
  let directionsUrl = $derived(
    `https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`
  );

  function startEdit() {
    editName = place.name;
    editNotes = place.notes || "";
    editColor = place.color || "#3b82f6";
    editShape = String(place.metadata?.shape || "pin");
    editMeta = {};
    for (const f of orderedFields) editMeta[f.key] = place.metadata?.[f.key];
    fieldErrors = {};
    editing = true;
  }

  function isEmpty(v: MetaValue): boolean {
    return (
      v === null ||
      v === undefined ||
      v === "" ||
      (Array.isArray(v) && v.length === 0)
    );
  }

  // Merge edited field values onto the existing metadata, always preserving the
  // reserved `shape` marker key + any undeclared keys the UI doesn't manage.
  function buildMetadata(): Record<string, MetaValue> {
    const meta: Record<string, MetaValue> = {
      ...(place.metadata || {}),
      shape: editShape,
    };
    for (const f of orderedFields) {
      const v = editMeta[f.key];
      if (isEmpty(v)) delete meta[f.key];
      else meta[f.key] = v;
    }
    return meta;
  }

  async function saveEdit() {
    const updates: Record<string, unknown> = {};
    if (editName.trim() && editName !== place.name) updates.name = editName.trim();
    if (editNotes !== (place.notes || "")) updates.notes = editNotes;
    if (editColor !== (place.color || "#3b82f6")) updates.color = editColor;
    const newMeta = buildMetadata();
    // Normalize the baseline's implicit shape default so an unchanged edit
    // doesn't write a redundant {shape:"pin"}.
    const baseline: Record<string, MetaValue> = { ...(place.metadata || {}) };
    if (baseline.shape === undefined) baseline.shape = "pin";
    if (JSON.stringify(newMeta) !== JSON.stringify(baseline)) {
      updates.metadata = newMeta;
    }
    if (Object.keys(updates).length === 0) {
      editing = false;
      return;
    }
    saving = true;
    fieldErrors = {};
    const result = await onUpdate(updates as Partial<Place>);
    saving = false;
    if (result && !result.ok) {
      if (result.errors && Object.keys(result.errors).length > 0) {
        fieldErrors = result.errors;
        return; // keep the form open so the user can fix the values
      }
    }
    editing = false;
  }

  function cancelEdit() {
    editing = false;
    fieldErrors = {};
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") cancelEdit();
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      saveEdit();
    }
  }

  // Scroll the card into view when it becomes selected (e.g. via map click).
  $effect(() => {
    if (isSelected && cardEl) {
      cardEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  });
</script>

<div
  class="place-card"
  class:selected={isSelected}
  bind:this={cardEl}
  role="button"
  tabindex="0"
  onclick={onSelect}
  onkeydown={(e) => {
    if (e.key === "Enter") onSelect();
  }}
>
  <div class="header">
    <span class="color-dot" style="background: {place.color || '#3b82f6'}">
      <span class="shape-glyph">{SHAPE_GLYPH[shape] ?? ""}</span>
    </span>
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
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="edit-form" role="presentation" onclick={(e) => e.stopPropagation()}>
      <label>
        Color:
        <input type="color" bind:value={editColor} />
      </label>
      <div class="shape-picker" role="group" aria-label="Marker shape">
        {#each SHAPES as s}
          <button
            type="button"
            class="shape-opt"
            class:active={editShape === s}
            title={s}
            onclick={() => (editShape = s)}
          >
            {SHAPE_GLYPH[s]}
          </button>
        {/each}
      </div>
      <textarea
        bind:value={editNotes}
        placeholder="Description..."
        rows="3"
        onkeydown={onKeydown}
      ></textarea>
      {#each orderedFields as f (f.id)}
        <div class="attr-field">
          <label for={`f-${place.id}-${f.key}`}>
            {f.label}{#if f.required}<span class="req">*</span>{/if}
          </label>
          <FieldInput field={f} bind:value={editMeta[f.key]} />
          {#if fieldErrors[f.key]}
            <div class="field-error">{fieldErrors[f.key]}</div>
          {/if}
        </div>
      {/each}
      <div class="edit-actions">
        <button type="button" class="btn-save" disabled={saving} onclick={saveEdit}>
          {saving ? "Saving..." : "Save"}
        </button>
        <button type="button" class="btn-cancel" onclick={cancelEdit}>Cancel</button>
      </div>
    </div>
  {:else}
    {#if place.notes}
      <div class="notes">{place.notes}</div>
    {/if}
    {#if displayFields.length > 0}
      <dl class="attrs">
        {#each displayFields as f (f.id)}
          <div class="attr-row">
            <dt>{f.label}</dt>
            <dd><FieldValue field={f} value={place.metadata?.[f.key]} /></dd>
          </div>
        {/each}
      </dl>
    {/if}
    {#if isSelected}
      <div class="detail">
        <span class="coords" title="Latitude, longitude"
          >{place.latitude.toFixed(5)}, {place.longitude.toFixed(5)}</span
        >
        <a
          class="dir-link"
          href={directionsUrl}
          target="_blank"
          rel="noopener"
          onclick={(e) => e.stopPropagation()}>Directions ↗</a
        >
      </div>
    {/if}
    {#if canEdit}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="actions" role="presentation" onclick={(e) => e.stopPropagation()}>
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
  .place-card:hover {
    background: #f8f9fa;
  }
  .place-card.selected {
    background: #e8f0fe;
    border-left: 3px solid #0b5cad;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .color-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .shape-glyph {
    font-size: 9px;
    line-height: 1;
    filter: drop-shadow(0 0 1px rgba(0, 0, 0, 0.4));
  }
  .name {
    font-weight: 600;
    font-size: 0.95em;
  }
  .address {
    font-size: 0.85em;
    color: #666;
    margin-top: 2px;
    padding-left: 24px;
  }
  .notes {
    font-size: 0.85em;
    color: #555;
    margin-top: 4px;
    padding-left: 24px;
    white-space: pre-wrap;
  }
  .detail {
    margin-top: 6px;
    padding-left: 24px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.8em;
  }
  .coords {
    color: #777;
    font-variant-numeric: tabular-nums;
  }
  .dir-link {
    color: #0b5cad;
    text-decoration: none;
  }
  .dir-link:hover {
    text-decoration: underline;
  }
  .actions {
    margin-top: 6px;
    padding-left: 24px;
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
  .actions button:hover {
    background: #f0f0f0;
  }
  .actions button.danger {
    color: #8a1a1a;
    border-color: #daa;
  }
  .actions button.danger:hover {
    background: #fbecec;
  }
  .edit-form {
    margin-top: 8px;
    padding-left: 24px;
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
  .shape-picker {
    display: flex;
    gap: 4px;
  }
  .shape-opt {
    width: 28px;
    height: 26px;
    border: 1px solid #ccc;
    background: #fff;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.9em;
    line-height: 1;
  }
  .shape-opt:hover {
    background: #f0f0f0;
  }
  .shape-opt.active {
    border-color: #0b5cad;
    box-shadow: 0 0 0 1px #0b5cad inset;
  }
  .attr-field {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .attr-field > label {
    font-size: 0.78em;
    color: #666;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .attr-field .req {
    color: #c0392b;
  }
  .field-error {
    color: #8a1a1a;
    font-size: 0.78em;
  }
  .attrs {
    margin: 6px 0 0;
    padding-left: 24px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 10px;
    font-size: 0.82em;
  }
  .attr-row {
    display: contents;
  }
  .attrs dt {
    color: #888;
  }
  .attrs dd {
    margin: 0;
    color: #333;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .edit-actions {
    display: flex;
    gap: 6px;
  }
  .btn-save,
  .btn-cancel {
    padding: 3px 10px;
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
  .btn-save:hover {
    background: #094a8d;
  }
  .btn-cancel:hover {
    background: #f0f0f0;
  }
</style>
