<script lang="ts">
  import type { Field, MetaValue } from "./fields";
  import { ratingMax, ratingStates, starSvg } from "./fields";

  let {
    field,
    value = $bindable(),
    onenter,
  }: {
    field: Field;
    value: MetaValue;
    onenter?: () => void;
  } = $props();

  let max = $derived(ratingMax(field));
  let stars = $derived(ratingStates(Number(value) || 0, max));
  let hasRating = $derived(Number(value) > 0);
  let options = $derived(field.config?.options ?? []);

  // Click the left half of a star for x.5, the right half for a whole star;
  // clicking the current value again clears it.
  function setRating(v: number) {
    value = Number(value) === v ? undefined : v;
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "Enter" && onenter) {
      e.preventDefault();
      onenter();
    }
  }
</script>

{#if field.type === "rating"}
  <span class="fi-stars" role="group" aria-label={field.label}>
    {#each stars as st, i}
      <span class={`fi-star ${st}`}>
        <button
          type="button"
          class="fi-half left"
          title={`${i + 0.5} / ${max}`}
          aria-label={`${i + 0.5} of ${max}`}
          onclick={() => setRating(i + 0.5)}
        ></button>
        <button
          type="button"
          class="fi-half right"
          title={`${i + 1} / ${max}`}
          aria-label={`${i + 1} of ${max}`}
          onclick={() => setRating(i + 1)}
        ></button>
        {@html starSvg(st)}
      </span>
    {/each}
    {#if hasRating}
      <button type="button" class="fi-clear" title="Clear" onclick={() => (value = undefined)}>×</button>
    {/if}
  </span>
{:else if field.type === "select"}
  <select bind:value onkeydown={onKey}>
    <option value="">{field.required ? "Select…" : "—"}</option>
    {#each options as o}
      <option value={o.value}>{o.label}</option>
    {/each}
  </select>
{:else if field.type === "color"}
  <input type="color" value={(value as string) || "#3b82f6"} oninput={(e) => (value = e.currentTarget.value)} />
{:else if field.type === "icon"}
  <span class="fi-icon">
    <input
      type="text"
      placeholder="e.g. star-fill"
      value={(value as string) ?? ""}
      oninput={(e) => (value = e.currentTarget.value)}
      onkeydown={onKey}
    />
    {#if value}<i class={`bi bi-${value}`}></i>{/if}
  </span>
{:else if field.type === "url"}
  <input
    type="url"
    placeholder="https://…"
    value={(value as string) ?? ""}
    oninput={(e) => (value = e.currentTarget.value)}
    onkeydown={onKey}
  />
{:else if field.type === "number"}
  <input
    type="number"
    min={field.config?.min}
    max={field.config?.max}
    step={field.config?.step ?? "any"}
    value={value ?? ""}
    oninput={(e) => (value = e.currentTarget.value === "" ? undefined : e.currentTarget.valueAsNumber)}
    onkeydown={onKey}
  />
{:else if field.type === "date"}
  <input
    type="date"
    value={(value as string) ?? ""}
    oninput={(e) => (value = e.currentTarget.value || undefined)}
    onkeydown={onKey}
  />
{:else if field.type === "boolean"}
  <input type="checkbox" checked={value === true} onchange={(e) => (value = e.currentTarget.checked)} />
{:else if field.config?.multiline}
  <textarea
    rows="3"
    maxlength={field.config?.maxlength}
    value={(value as string) ?? ""}
    oninput={(e) => (value = e.currentTarget.value)}
  ></textarea>
{:else}
  <input
    type="text"
    maxlength={field.config?.maxlength}
    value={(value as string) ?? ""}
    oninput={(e) => (value = e.currentTarget.value)}
    onkeydown={onKey}
  />
{/if}

<style>
  input[type="text"],
  input[type="url"],
  input[type="number"],
  input[type="date"],
  select,
  textarea {
    font: inherit;
    font-size: 0.9em;
    padding: 3px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
    width: 100%;
    box-sizing: border-box;
    background: #fff;
  }
  textarea {
    resize: vertical;
  }
  input[type="color"] {
    width: 30px;
    height: 26px;
    padding: 0;
    border: 1px solid #ccc;
    border-radius: 3px;
    cursor: pointer;
  }
  .fi-icon {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .fi-icon i {
    font-size: 1.1em;
  }
  .fi-stars {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  /* Each star is a 1.2em box with the glyph behind two half-width click zones. */
  .fi-star {
    position: relative;
    display: inline-block;
    width: 1.2em;
    height: 1.2em;
    font-size: 1.2em;
    line-height: 1;
    color: #ccc;
  }
  .fi-star.full,
  .fi-star.half {
    color: #f5a623;
  }
  .fi-star :global(svg) {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .fi-half {
    position: absolute;
    top: 0;
    height: 100%;
    width: 50%;
    border: none;
    background: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    z-index: 1;
  }
  .fi-half.left {
    left: 0;
  }
  .fi-half.right {
    right: 0;
  }
  .fi-clear {
    border: none;
    background: none;
    cursor: pointer;
    color: #999;
    font-size: 1em;
    margin-left: 4px;
  }
</style>
