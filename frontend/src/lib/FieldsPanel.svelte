<script lang="ts">
  import type { Field, FieldType, FieldOption, FieldConfig } from "./fields";
  import {
    FIELD_TYPES,
    RESERVED_KEYS,
    KEY_RE,
    sortedFields,
    keyFromLabel,
  } from "./fields";

  let {
    listId,
    fields,
    onChanged,
  }: {
    listId: number;
    fields: Field[];
    // Refetch list detail (or fields) after a successful mutation.
    onChanged: () => Promise<void> | void;
  } = $props();

  let open = $state(false);
  let busy = $state(false);
  let formError = $state<string | null>(null);

  // Draft for the add/edit form. id === null means "new field".
  type Draft = {
    id: number | null;
    key: string;
    label: string;
    type: FieldType;
    required: boolean;
    unique: boolean;
    config: FieldConfig;
    keyTouched: boolean;
  };

  function blankDraft(): Draft {
    return {
      id: null,
      key: "",
      label: "",
      type: "text",
      required: false,
      unique: false,
      config: {},
      keyTouched: false,
    };
  }

  let draft = $state<Draft>(blankDraft());
  let ordered = $derived(sortedFields(fields));

  // Track unsaved edits so closing the modal (backdrop / ×) can warn before
  // discarding them. `formSnapshot` is the draft's serialized state as of the
  // last reset/edit; `dirty` is true once the user has changed anything.
  function draftSig(d: Draft): string {
    return JSON.stringify({
      id: d.id,
      key: d.key,
      label: d.label,
      type: d.type,
      required: d.required,
      unique: d.unique,
      config: d.config,
    });
  }
  let formSnapshot = $state(draftSig(blankDraft()));
  let dirty = $derived(draftSig(draft) !== formSnapshot);

  function resetForm() {
    draft = blankDraft();
    formError = null;
    formSnapshot = draftSig(draft);
  }

  function editField(f: Field) {
    draft = {
      id: f.id,
      key: f.key,
      label: f.label,
      type: f.type,
      required: f.required,
      unique: f.unique,
      config: JSON.parse(JSON.stringify(f.config ?? {})),
      keyTouched: true,
    };
    formError = null;
    formSnapshot = draftSig(draft);
  }

  // Close the modal, warning first if there are unsaved draft edits.
  function tryClose() {
    if (dirty && !window.confirm("Discard your unsaved field changes?")) return;
    open = false;
    resetForm();
  }

  function onLabelInput(v: string) {
    draft.label = v;
    if (draft.id === null && !draft.keyTouched) {
      draft.key = keyFromLabel(v);
    }
  }

  // --- select options builder ---
  function options(): FieldOption[] {
    if (!draft.config.options) draft.config.options = [];
    return draft.config.options;
  }
  function addOption() {
    options().push({ value: "", label: "" });
  }
  function removeOption(i: number) {
    options().splice(i, 1);
  }

  function validateDraft(): string | null {
    if (!draft.label.trim()) return "Label is required.";
    if (draft.id === null) {
      if (!KEY_RE.test(draft.key))
        return "Key must be lowercase, start with a letter, and use only letters, digits, or underscores.";
      if (RESERVED_KEYS.has(draft.key)) return `Key “${draft.key}” is reserved.`;
      if (fields.some((f) => f.key === draft.key))
        return `A field with key “${draft.key}” already exists.`;
    }
    if (draft.type === "select") {
      const opts = (draft.config.options ?? []).filter((o) => o.value.trim());
      if (opts.length === 0)
        return "A select field needs at least one option value.";
    }
    return null;
  }

  // Strip config keys that don't apply to the chosen type before saving.
  function cleanConfig(): FieldConfig {
    const c = draft.config;
    switch (draft.type) {
      case "text":
        return { maxlength: c.maxlength, multiline: c.multiline };
      case "number":
        return { min: c.min, max: c.max, step: c.step, unit: c.unit };
      case "url":
        return { icon: c.icon };
      case "rating":
        return { max: c.max };
      case "select":
        return {
          options: (c.options ?? [])
            .filter((o) => o.value.trim())
            .map((o) => ({
              value: o.value.trim(),
              label: o.label.trim() || o.value.trim(),
              ...(o.color ? { color: o.color } : {}),
            })),
          multiple: c.multiple,
        };
      case "icon":
        return { set: c.set || "bootstrap" };
      default:
        return {};
    }
  }

  async function save() {
    const err = validateDraft();
    if (err) {
      formError = err;
      return;
    }
    busy = true;
    formError = null;
    const body = {
      key: draft.key,
      label: draft.label.trim(),
      type: draft.type,
      required: draft.required,
      unique: draft.unique,
      config: cleanConfig(),
    };
    const url =
      draft.id === null
        ? `/-/places/api/lists/${listId}/fields`
        : `/-/places/api/lists/${listId}/fields/${draft.id}/update`;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        formError = data.error || "Failed to save field.";
        busy = false;
        return;
      }
      await onChanged();
      resetForm();
    } catch {
      formError = "Failed to save field.";
    }
    busy = false;
  }

  async function remove(f: Field) {
    if (
      !window.confirm(
        `Delete the “${f.label}” field? This removes its column from the table view. Stored values stay in each place's metadata but are no longer shown.`
      )
    )
      return;
    busy = true;
    try {
      await fetch(`/-/places/api/lists/${listId}/fields/${f.id}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (draft.id === f.id) resetForm();
      await onChanged();
    } catch {
      formError = "Failed to delete field.";
    }
    busy = false;
  }

  // Reorder by swapping position with the neighbor, then persisting both.
  async function move(f: Field, dir: -1 | 1) {
    const list = ordered;
    const idx = list.findIndex((x) => x.id === f.id);
    const other = list[idx + dir];
    if (!other) return;
    busy = true;
    try {
      await Promise.all([
        fetch(`/-/places/api/lists/${listId}/fields/${f.id}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position: other.position }),
        }),
        fetch(`/-/places/api/lists/${listId}/fields/${other.id}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position: f.position }),
        }),
      ]);
      await onChanged();
    } catch {
      formError = "Failed to reorder fields.";
    }
    busy = false;
  }

  function typeLabel(t: FieldType): string {
    return FIELD_TYPES.find((x) => x.value === t)?.label ?? t;
  }
</script>

<button type="button" class="fields-trigger" onclick={() => (open = true)}>
  Fields
</button>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fields-backdrop" onclick={tryClose}>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="fields-modal" role="dialog" tabindex="-1" aria-label="List fields" onclick={(e) => e.stopPropagation()}>
      <div class="fm-head">
        <h2>Fields</h2>
        <button type="button" class="fm-close" onclick={tryClose} aria-label="Close">×</button>
      </div>
      <p class="fm-sub">
        Custom attributes every place in this list can fill in. They appear in the
        place editor and as columns in the table view.
      </p>

      {#if ordered.length > 0}
        <ul class="fm-list">
          {#each ordered as f, i (f.id)}
            <li class:active={draft.id === f.id}>
              <div class="fm-item-main">
                <span class="fm-label">{f.label}</span>
                <code class="fm-key">{f.key}</code>
                <span class="fm-type">{typeLabel(f.type)}</span>
                {#if f.required}<span class="fm-badge">required</span>{/if}
                {#if f.unique}<span class="fm-badge">unique</span>{/if}
              </div>
              <div class="fm-item-actions">
                <button type="button" disabled={busy || i === 0} title="Move up" onclick={() => move(f, -1)}>↑</button>
                <button
                  type="button"
                  disabled={busy || i === ordered.length - 1}
                  title="Move down"
                  onclick={() => move(f, 1)}>↓</button
                >
                <button type="button" onclick={() => editField(f)}>Edit</button>
                <button type="button" class="danger" disabled={busy} onclick={() => remove(f)}>Delete</button>
              </div>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="fm-empty">No fields yet. Add one below.</p>
      {/if}

      <form
        class="fm-form"
        onsubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h3>{draft.id === null ? "Add field" : `Edit “${draft.label}”`}</h3>
        <div class="fm-row">
          <label class="fm-field">
            Label
            <input
              type="text"
              value={draft.label}
              oninput={(e) => onLabelInput(e.currentTarget.value)}
              placeholder="Rating"
            />
          </label>
          <label class="fm-field">
            Key
            <input
              type="text"
              bind:value={draft.key}
              oninput={() => (draft.keyTouched = true)}
              disabled={draft.id !== null}
              placeholder="rating"
            />
          </label>
          <label class="fm-field">
            Type
            <select bind:value={draft.type}>
              {#each FIELD_TYPES as t}
                <option value={t.value}>{t.label}</option>
              {/each}
            </select>
          </label>
        </div>

        <!-- Per-type config editor. -->
        {#if draft.type === "select"}
          <div class="fm-config">
            <div class="fm-config-head">Options</div>
            {#each options() as opt, i (i)}
              <div class="fm-opt-row">
                <input type="text" placeholder="value" bind:value={opt.value} />
                <input type="text" placeholder="label" bind:value={opt.label} />
                <input type="color" value={opt.color ?? "#cccccc"} oninput={(e) => (opt.color = e.currentTarget.value)} title="Chip color" />
                <button type="button" class="fm-opt-del" title="Remove option" onclick={() => removeOption(i)}>×</button>
              </div>
            {/each}
            <button type="button" class="fm-add-opt" onclick={addOption}>+ Add option</button>
            <label class="fm-inline">
              <input type="checkbox" bind:checked={draft.config.multiple} /> Allow multiple
            </label>
          </div>
        {:else if draft.type === "rating"}
          <div class="fm-config">
            <label class="fm-field fm-narrow">
              Max stars
              <input
                type="number"
                min="1"
                max="10"
                value={draft.config.max ?? 5}
                oninput={(e) => (draft.config.max = e.currentTarget.valueAsNumber || 5)}
              />
            </label>
          </div>
        {:else if draft.type === "number"}
          <div class="fm-config fm-config-grid">
            <label class="fm-field fm-narrow">Min<input type="number" value={draft.config.min ?? ""} oninput={(e) => (draft.config.min = e.currentTarget.value === "" ? undefined : e.currentTarget.valueAsNumber)} /></label>
            <label class="fm-field fm-narrow">Max<input type="number" value={draft.config.max ?? ""} oninput={(e) => (draft.config.max = e.currentTarget.value === "" ? undefined : e.currentTarget.valueAsNumber)} /></label>
            <label class="fm-field fm-narrow">Step<input type="number" value={draft.config.step ?? ""} oninput={(e) => (draft.config.step = e.currentTarget.value === "" ? undefined : e.currentTarget.valueAsNumber)} /></label>
            <label class="fm-field fm-narrow">Unit<input type="text" bind:value={draft.config.unit} placeholder="km" /></label>
          </div>
        {:else if draft.type === "text"}
          <div class="fm-config fm-config-grid">
            <label class="fm-field fm-narrow">Max length<input type="number" value={draft.config.maxlength ?? ""} oninput={(e) => (draft.config.maxlength = e.currentTarget.value === "" ? undefined : e.currentTarget.valueAsNumber)} /></label>
            <label class="fm-inline"><input type="checkbox" bind:checked={draft.config.multiline} /> Multi-line</label>
          </div>
        {:else if draft.type === "url"}
          <div class="fm-config">
            <label class="fm-field">Link label / icon<input type="text" bind:value={draft.config.icon} placeholder="Instagram" /></label>
          </div>
        {:else if draft.type === "icon"}
          <div class="fm-config">
            <label class="fm-field fm-narrow">Icon set<input type="text" bind:value={draft.config.set} placeholder="bootstrap" /></label>
          </div>
        {/if}

        <div class="fm-toggles">
          <label class="fm-inline"><input type="checkbox" bind:checked={draft.required} /> Required</label>
          <label class="fm-inline"><input type="checkbox" bind:checked={draft.unique} /> Unique</label>
        </div>

        {#if formError}
          <div class="fm-error">{formError}</div>
        {/if}

        <div class="fm-actions">
          <button type="submit" class="fm-save" disabled={busy}>
            {draft.id === null ? "Add field" : "Save changes"}
          </button>
          {#if draft.id !== null}
            <button type="button" class="fm-cancel" onclick={resetForm}>Cancel</button>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .fields-trigger {
    font: inherit;
    font-size: 0.85em;
    padding: 4px 10px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
  }
  .fields-trigger:hover {
    background: #f0f0f0;
  }
  .fields-backdrop {
    position: fixed;
    inset: 0;
    z-index: 2000;
    background: rgba(0, 0, 0, 0.35);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 16px;
    overflow-y: auto;
  }
  .fields-modal {
    background: #fff;
    border-radius: 8px;
    width: 560px;
    max-width: 100%;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3);
    padding: 18px 20px 20px;
  }
  .fm-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .fm-head h2 {
    margin: 0;
    font-size: 1.25em;
  }
  .fm-close {
    border: none;
    background: none;
    font-size: 1.6em;
    line-height: 1;
    cursor: pointer;
    color: #888;
  }
  .fm-close:hover {
    color: #333;
  }
  .fm-sub {
    margin: 4px 0 14px;
    font-size: 0.85em;
    color: #666;
    line-height: 1.4;
  }
  .fm-list {
    list-style: none;
    margin: 0 0 16px;
    padding: 0;
    border: 1px solid #eee;
    border-radius: 6px;
  }
  .fm-list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 10px;
    flex-wrap: wrap;
  }
  .fm-list li + li {
    border-top: 1px solid #eee;
  }
  .fm-list li.active {
    background: #eef4fb;
  }
  .fm-item-main {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .fm-label {
    font-weight: 600;
    font-size: 0.92em;
  }
  .fm-key {
    font-size: 0.8em;
    color: #777;
    background: #f4f4f4;
    padding: 0 5px;
    border-radius: 3px;
  }
  .fm-type {
    font-size: 0.78em;
    color: #888;
  }
  .fm-badge {
    font-size: 0.68em;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #0b5cad;
    border: 1px solid #b9d4ef;
    border-radius: 8px;
    padding: 0 6px;
  }
  .fm-item-actions {
    display: flex;
    gap: 4px;
  }
  .fm-item-actions button {
    font: inherit;
    font-size: 0.78em;
    padding: 2px 7px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    cursor: pointer;
  }
  .fm-item-actions button:hover:not(:disabled) {
    background: #f0f0f0;
  }
  .fm-item-actions button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .fm-item-actions .danger {
    color: #8a1a1a;
    border-color: #daa;
  }
  .fm-empty {
    color: #888;
    font-size: 0.9em;
    margin: 0 0 16px;
  }
  .fm-form {
    border-top: 1px solid #eee;
    padding-top: 14px;
  }
  .fm-form h3 {
    margin: 0 0 10px;
    font-size: 1.02em;
  }
  .fm-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .fm-field {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 0.8em;
    color: #555;
    flex: 1;
    min-width: 130px;
  }
  .fm-narrow {
    flex: 0 0 auto;
    min-width: 90px;
  }
  .fm-field input,
  .fm-field select {
    font: inherit;
    font-size: 0.95em;
    padding: 4px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
  }
  .fm-field input:disabled {
    background: #f4f4f4;
    color: #888;
  }
  .fm-config {
    margin-top: 12px;
    padding: 10px;
    background: #f8f9fb;
    border-radius: 6px;
  }
  .fm-config-grid {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: flex-end;
  }
  .fm-config-head {
    font-size: 0.8em;
    color: #555;
    margin-bottom: 6px;
  }
  .fm-opt-row {
    display: flex;
    gap: 6px;
    margin-bottom: 5px;
    align-items: center;
  }
  .fm-opt-row input[type="text"] {
    font: inherit;
    font-size: 0.88em;
    padding: 3px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
    flex: 1;
    min-width: 0;
  }
  .fm-opt-row input[type="color"] {
    width: 28px;
    height: 26px;
    padding: 0;
    border: 1px solid #ccc;
    border-radius: 3px;
  }
  .fm-opt-del {
    border: none;
    background: none;
    cursor: pointer;
    color: #999;
    font-size: 1.1em;
  }
  .fm-add-opt {
    font: inherit;
    font-size: 0.8em;
    border: none;
    background: none;
    color: #0b5cad;
    cursor: pointer;
    padding: 0;
    margin-top: 2px;
  }
  .fm-add-opt:hover {
    text-decoration: underline;
  }
  .fm-inline {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.85em;
    color: #444;
  }
  .fm-toggles {
    display: flex;
    gap: 16px;
    margin-top: 12px;
  }
  .fm-error {
    margin-top: 12px;
    background: #ffd6d6;
    color: #5a0000;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 0.85em;
  }
  .fm-actions {
    margin-top: 14px;
    display: flex;
    gap: 8px;
  }
  .fm-save {
    font: inherit;
    font-size: 0.88em;
    font-weight: 600;
    padding: 6px 14px;
    border: 1px solid #0b5cad;
    border-radius: 5px;
    background: #0b5cad;
    color: #fff;
    cursor: pointer;
  }
  .fm-save:hover:not(:disabled) {
    background: #094a8d;
  }
  .fm-save:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .fm-cancel {
    font: inherit;
    font-size: 0.88em;
    padding: 6px 14px;
    border: 1px solid #ccc;
    border-radius: 5px;
    background: #fff;
    cursor: pointer;
  }
  .fm-cancel:hover {
    background: #f0f0f0;
  }
</style>
