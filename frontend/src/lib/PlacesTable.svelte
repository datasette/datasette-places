<script lang="ts">
  import type { Field, MetaValue } from "./fields";
  import { sortedFields } from "./fields";
  import FieldValue from "./FieldValue.svelte";
  import FieldInput from "./FieldInput.svelte";

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
    canEdit = false,
    selectedId = null,
    onSelectPlace,
    onPlaceUpdated,
  }: {
    places: Place[];
    fields: Field[];
    listId: number;
    canEdit: boolean;
    selectedId: number | null;
    onSelectPlace: (id: number) => void;
    onPlaceUpdated: (place: Place) => void;
  } = $props();

  let cols = $derived(sortedFields(fields));

  // --- sorting (client-side) ---
  let sortKey = $state<string>("name");
  let sortDir = $state<1 | -1>(1);

  function cellValue(p: Place, key: string): MetaValue {
    if (key === "name") return p.name;
    return p.metadata?.[key];
  }

  function setSort(key: string) {
    if (sortKey === key) sortDir = sortDir === 1 ? -1 : 1;
    else {
      sortKey = key;
      sortDir = 1;
    }
  }

  let sortedPlaces = $derived(
    [...places].sort((a, b) => {
      const av = cellValue(a, sortKey);
      const bv = cellValue(b, sortKey);
      const aEmpty = av === null || av === undefined || av === "";
      const bEmpty = bv === null || bv === undefined || bv === "";
      if (aEmpty && bEmpty) return 0;
      if (aEmpty) return 1; // empties sink to the bottom regardless of dir
      if (bEmpty) return -1;
      if (typeof av === "number" && typeof bv === "number")
        return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    })
  );

  // --- inline editing ---
  let editing = $state<{ placeId: number; key: string } | null>(null);
  let editValue = $state<MetaValue>(undefined);
  let editError = $state<string | null>(null);
  let saving = $state(false);

  function startEdit(p: Place, field: Field) {
    if (!canEdit) return;
    editing = { placeId: p.id, key: field.key };
    editValue = p.metadata?.[field.key];
    editError = null;
  }

  function isEditing(p: Place, field: Field): boolean {
    return editing?.placeId === p.id && editing?.key === field.key;
  }

  function fieldFor(key: string): Field | undefined {
    return cols.find((f) => f.key === key);
  }

  function clearable(field: Field, value: MetaValue): boolean {
    if (field.type === "boolean") return false;
    return (
      value === null ||
      value === undefined ||
      value === "" ||
      (Array.isArray(value) && value.length === 0)
    );
  }

  async function commitEdit() {
    if (!editing || saving) return;
    const field = fieldFor(editing.key);
    if (!field) {
      editing = null;
      return;
    }
    saving = true;
    editError = null;
    const body: { key: string; value?: MetaValue } = { key: editing.key };
    if (!clearable(field, editValue)) body.value = editValue;
    try {
      const resp = await fetch(
        `/-/places/api/lists/${listId}/places/${editing.placeId}/metadata`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        editError = data.errors?.[editing.key] || data.error || "Invalid value";
        saving = false;
        return;
      }
      onPlaceUpdated(data);
      editing = null;
    } catch {
      editError = "Failed to save";
    }
    saving = false;
  }

  function cancelEdit() {
    editing = null;
    editError = null;
  }
</script>

<div class="table-wrap">
  {#if places.length === 0}
    <p class="empty">No places yet.</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th class="sortable" onclick={() => setSort("name")}>
            Name
            {#if sortKey === "name"}<span class="arrow">{sortDir === 1 ? "▲" : "▼"}</span>{/if}
          </th>
          {#each cols as f (f.id)}
            <th class="sortable" onclick={() => setSort(f.key)}>
              {f.label}
              {#if sortKey === f.key}<span class="arrow">{sortDir === 1 ? "▲" : "▼"}</span>{/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each sortedPlaces as p (p.id)}
          <tr class:selected={p.id === selectedId}>
            <th
              class="name-cell"
              scope="row"
              onclick={() => onSelectPlace(p.id)}
              title={p.address ?? ""}
            >
              <span class="dot" style={`background:${p.color || "#3b82f6"}`}></span>
              {p.name}
            </th>
            {#each cols as f (f.id)}
              <td
                class:editable={canEdit}
                class:editing={isEditing(p, f)}
              >
                {#if isEditing(p, f)}
                  <!-- svelte-ignore a11y_no_static_element_interactions -->
                  <div class="cell-edit" onkeydown={(e) => { if (e.key === "Escape") cancelEdit(); }}>
                    <FieldInput field={f} bind:value={editValue} onenter={commitEdit} />
                    <div class="cell-edit-actions">
                      <button type="button" class="ce-save" disabled={saving} onclick={commitEdit}>✓</button>
                      <button type="button" class="ce-cancel" onclick={cancelEdit}>×</button>
                    </div>
                    {#if editError}<div class="cell-error">{editError}</div>{/if}
                  </div>
                {:else}
                  <!-- svelte-ignore a11y_click_events_have_key_events -->
                  <!-- svelte-ignore a11y_no_static_element_interactions -->
                  <div class="cell-view" onclick={() => startEdit(p, f)}>
                    <FieldValue field={f} value={p.metadata?.[f.key]} />
                  </div>
                {/if}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .table-wrap {
    width: 100%;
    height: 100%;
    overflow: auto;
    background: #fff;
  }
  .empty {
    padding: 30px;
    text-align: center;
    color: #888;
  }
  table {
    border-collapse: collapse;
    font-size: 0.88em;
    min-width: 100%;
    /* Override datasette-paper's `.ProseMirror table { table-layout: fixed }`
       when this table is shown inside a block embed — without this, columns get
       equal fixed widths and long names overflow into the next column. */
    table-layout: auto !important;
  }
  thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: #f4f6f8;
    text-align: left;
    padding: 8px 12px;
    border-bottom: 2px solid #dde2e7;
    white-space: nowrap;
    font-weight: 600;
  }
  th.sortable {
    cursor: pointer;
    user-select: none;
  }
  th.sortable:hover {
    background: #e9edf1;
  }
  .arrow {
    font-size: 0.75em;
    color: #0b5cad;
    margin-left: 2px;
  }
  tbody tr {
    border-bottom: 1px solid #eee;
  }
  tbody tr:hover {
    background: #f8f9fa;
  }
  tbody tr.selected {
    background: #e8f0fe;
  }
  td,
  .name-cell {
    padding: 6px 12px;
    vertical-align: top;
  }
  .name-cell {
    font-weight: 600;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
    position: sticky;
    left: 0;
    background: inherit;
  }
  tbody tr:hover .name-cell {
    background: #f8f9fa;
  }
  tbody tr.selected .name-cell {
    background: #e8f0fe;
  }
  .dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
  }
  td.editable .cell-view {
    cursor: pointer;
    min-height: 18px;
  }
  td.editable .cell-view:hover {
    outline: 1px dashed #b9d4ef;
    outline-offset: 2px;
    border-radius: 2px;
  }
  td.editing {
    background: #fffdf2;
  }
  .cell-edit {
    display: flex;
    align-items: flex-start;
    gap: 4px;
    min-width: 150px;
  }
  .cell-edit-actions {
    display: flex;
    gap: 2px;
    flex-shrink: 0;
  }
  .cell-edit-actions button {
    border: 1px solid #ccc;
    background: #fff;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.85em;
    line-height: 1.3;
    padding: 1px 5px;
  }
  .ce-save {
    color: #0a7a26;
  }
  .ce-cancel {
    color: #999;
  }
  .cell-error {
    color: #8a1a1a;
    font-size: 0.85em;
    margin-top: 2px;
    flex-basis: 100%;
  }
</style>
