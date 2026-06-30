<script lang="ts">
  import type { Field, MetaValue } from "./fields";
  import { ratingMax, ratingStates, starSvg, selectOption, formatDate } from "./fields";

  let {
    field,
    value,
  }: {
    field: Field;
    value: MetaValue;
  } = $props();

  let empty = $derived(
    value === null ||
      value === undefined ||
      value === "" ||
      (Array.isArray(value) && value.length === 0)
  );

  let max = $derived(ratingMax(field));
  let stars = $derived(ratingStates(Number(value) || 0, max));
  let opt = $derived(selectOption(field, value));
</script>

{#if empty}
  <span class="fv-empty">—</span>
{:else if field.type === "rating"}
  <span class="fv-stars" title={`${value} / ${max}`}>
    {#each stars as st}<span class={`fv-star ${st}`}>{@html starSvg(st)}</span>{/each}
  </span>
{:else if field.type === "select"}
  {#if field.config?.multiple && Array.isArray(value)}
    <span class="fv-chips">
      {#each value as v}
        {@const o = (field.config?.options ?? []).find((x) => x.value === v)}
        <span class="fv-chip" style={o?.color ? `background:${o.color};color:#fff` : ""}>
          {o?.label ?? v}
        </span>
      {/each}
    </span>
  {:else}
    <span class="fv-chip" style={opt?.color ? `background:${opt.color};color:#fff` : ""}>
      {opt?.label ?? value}
    </span>
  {/if}
{:else if field.type === "url"}
  <a class="fv-link" href={String(value)} target="_blank" rel="noopener" onclick={(e) => e.stopPropagation()}>
    {field.config?.icon ? `${field.config.icon} ↗` : "Link ↗"}
  </a>
{:else if field.type === "color"}
  <span class="fv-color"><span class="fv-swatch" style={`background:${value}`}></span>{value}</span>
{:else if field.type === "icon"}
  <span class="fv-icon"><i class={`bi bi-${value}`}></i> {value}</span>
{:else if field.type === "boolean"}
  <span class="fv-bool">{value ? "✓" : "—"}</span>
{:else if field.type === "date"}
  <span>{formatDate(String(value))}</span>
{:else if field.type === "number"}
  <span>{value}{field.config?.unit ? ` ${field.config.unit}` : ""}</span>
{:else}
  <span class="fv-text">{value}</span>
{/if}

<style>
  .fv-empty {
    color: #bbb;
  }
  .fv-stars {
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
  }
  .fv-star :global(svg) {
    display: block;
  }
  .fv-star.full,
  .fv-star.half {
    color: #f5a623;
  }
  .fv-star.empty {
    color: #ccc;
  }
  .fv-chip {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    background: #eef1f4;
    color: #333;
    font-size: 0.85em;
    line-height: 1.5;
  }
  .fv-chips {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 3px;
  }
  .fv-link {
    color: #0b5cad;
    text-decoration: none;
  }
  .fv-link:hover {
    text-decoration: underline;
  }
  .fv-color {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-variant-numeric: tabular-nums;
  }
  .fv-swatch {
    width: 13px;
    height: 13px;
    border-radius: 3px;
    border: 1px solid rgba(0, 0, 0, 0.2);
    display: inline-block;
  }
  .fv-icon i {
    font-size: 1.05em;
  }
  .fv-text {
    white-space: pre-wrap;
  }
</style>
