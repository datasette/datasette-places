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
  let errorMsg = $state<string | null>(null);
  let searched = $state(false);
  let wrapperEl: HTMLDivElement;

  async function search() {
    const q = query.trim();
    errorMsg = null;
    if (!q) {
      results = [];
      showResults = false;
      searched = false;
      return;
    }
    loading = true;
    searched = true;
    try {
      const resp = await fetch(
        `/-/places/api/geocode?q=${encodeURIComponent(q)}`,
        { headers: { "Content-Type": "application/json" } }
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.error || `Search failed (HTTP ${resp.status}).`);
      }
      results = data.results || [];
      showResults = true;
    } catch (e) {
      results = [];
      showResults = false;
      errorMsg =
        e instanceof Error ? e.message : "Something went wrong searching.";
    }
    loading = false;
  }

  function onSubmit(e: SubmitEvent) {
    e.preventDefault();
    void search();
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

  function onBlur(e: FocusEvent) {
    // Keep results open while focus stays inside the widget (e.g. moving to
    // the Search button or clicking a result); otherwise hide shortly after.
    const next = e.relatedTarget as Node | null;
    if (next && wrapperEl?.contains(next)) return;
    setTimeout(() => {
      showResults = false;
    }, 200);
  }
</script>

<div class="search-wrapper" bind:this={wrapperEl}>
  <form class="search-input-row" onsubmit={onSubmit}>
    <input
      type="text"
      bind:value={query}
      onkeydown={onKeydown}
      onfocus={() => {
        if (results.length > 0) showResults = true;
      }}
      onblur={onBlur}
      placeholder="Search for an address or place..."
    />
    <button
      type="submit"
      class="search-btn"
      disabled={loading || !query.trim()}
    >
      {loading ? "..." : "Search"}
    </button>
  </form>

  {#if errorMsg}
    <div class="search-error">{errorMsg}</div>
  {/if}

  {#if showResults}
    {#if results.length > 0}
      <ul class="results">
        {#each results as r}
          <li>
            <button type="button" onclick={() => selectResult(r)}>
              {r.display_name}
            </button>
          </li>
        {/each}
      </ul>
    {:else if searched && !loading}
      <div class="no-results">No matches found for that search.</div>
    {/if}
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
    margin: 0;
  }
  input {
    flex: 1;
    min-width: 0;
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
  .search-btn {
    flex-shrink: 0;
    padding: 8px 14px;
    border: 1px solid #0b5cad;
    border-radius: 4px;
    background: #0b5cad;
    color: #fff;
    font: inherit;
    font-size: 0.9em;
    cursor: pointer;
  }
  .search-btn:hover:not(:disabled) {
    background: #094a8d;
  }
  .search-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .search-error {
    margin-top: 6px;
    padding: 6px 10px;
    background: #ffd6d6;
    color: #5a0000;
    border-radius: 4px;
    font-size: 0.85em;
  }
  .no-results {
    margin-top: 6px;
    padding: 6px 10px;
    color: #777;
    font-size: 0.85em;
    font-style: italic;
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
