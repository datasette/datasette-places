<script lang="ts">
  type GeoResult = {
    display_name: string;
    latitude: number;
    longitude: number;
    components: Record<string, string>;
  };

  let {
    onSelect,
  }: {
    onSelect: (result: GeoResult) => void;
  } = $props();

  let query = $state("");
  let results = $state<GeoResult[]>([]);
  let loading = $state(false);
  let showResults = $state(false);
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  async function search() {
    const q = query.trim();
    if (!q) {
      results = [];
      showResults = false;
      return;
    }
    loading = true;
    try {
      const resp = await fetch(
        `/-/places/api/geocode?q=${encodeURIComponent(q)}`,
        { headers: { "Content-Type": "application/json" } }
      );
      if (!resp.ok) throw new Error("Search failed");
      const data = await resp.json();
      results = data.results || [];
      showResults = results.length > 0;
    } catch {
      results = [];
      showResults = false;
    }
    loading = false;
  }

  function onInput() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => void search(), 350);
  }

  function selectResult(r: GeoResult) {
    showResults = false;
    query = r.display_name;
    onSelect(r);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      showResults = false;
    }
  }

  function onBlur() {
    // Delay to allow click on result
    setTimeout(() => { showResults = false; }, 200);
  }
</script>

<div class="search-wrapper">
  <div class="search-input-row">
    <input
      type="text"
      bind:value={query}
      oninput={onInput}
      onkeydown={onKeydown}
      onfocus={() => { if (results.length > 0) showResults = true; }}
      onblur={onBlur}
      placeholder="Search for an address or place..."
    />
    {#if loading}
      <span class="spinner">...</span>
    {/if}
  </div>

  {#if showResults}
    <ul class="results">
      {#each results as r, i}
        <li>
          <button
            type="button"
            onclick={() => selectResult(r)}
          >
            {r.display_name}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .search-wrapper {
    position: relative;
    width: 100%;
  }
  .search-input-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font: inherit;
    font-size: 0.95em;
  }
  input:focus {
    outline: none;
    border-color: #0b5cad;
    box-shadow: 0 0 0 2px rgba(11, 92, 173, 0.15);
  }
  .spinner {
    color: #888;
    font-size: 0.85em;
  }
  .results {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 100;
    list-style: none;
    margin: 2px 0 0;
    padding: 0;
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 4px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    max-height: 260px;
    overflow-y: auto;
  }
  .results li + li {
    border-top: 1px solid #eee;
  }
  .results button {
    display: block;
    width: 100%;
    text-align: left;
    padding: 8px 12px;
    border: none;
    background: transparent;
    cursor: pointer;
    font: inherit;
    font-size: 0.9em;
    line-height: 1.4;
    color: #333;
  }
  .results button:hover {
    background: #f0f4f8;
  }
</style>
