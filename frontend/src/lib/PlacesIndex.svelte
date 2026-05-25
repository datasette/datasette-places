<script lang="ts">
  import { onMount } from "svelte";

  type ListRow = {
    id: number;
    name: string;
    place_count: number;
    created_by: string | null;
    updated_at: string;
    visibility: string;
    state: string;
    is_owner: boolean;
  };

  let lists = $state<ListRow[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let newName = $state("");
  let creating = $state(false);
  let tab = $state<"active" | "trashed">("active");
  let trashedLists = $state<ListRow[] | null>(null);
  let nowTick = $state(Date.now());

  async function loadLists() {
    loading = true;
    error = null;
    try {
      const resp = await fetch("/-/places/api/lists?state=active", {
        headers: { "Content-Type": "application/json" },
      });
      if (!resp.ok) throw new Error("Failed to load");
      lists = await resp.json();
    } catch {
      error = "Failed to load place lists";
    }
    loading = false;
  }

  async function loadTrashed() {
    try {
      const resp = await fetch("/-/places/api/lists?state=trashed", {
        headers: { "Content-Type": "application/json" },
      });
      if (!resp.ok) throw new Error("Failed to load");
      trashedLists = await resp.json();
    } catch {
      trashedLists = [];
    }
  }

  function selectTab(t: "active" | "trashed") {
    tab = t;
    if (t === "trashed" && trashedLists === null) void loadTrashed();
  }

  async function create(e: Event) {
    e.preventDefault();
    if (!newName.trim() || creating) return;
    creating = true;
    error = null;
    try {
      const resp = await fetch("/-/places/api/lists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      });
      if (!resp.ok) throw new Error("Failed to create");
      const data = await resp.json();
      window.location.href = `/-/places/list/${data.id}`;
    } catch {
      error = "Failed to create list";
      creating = false;
    }
  }

  async function trashList(row: ListRow) {
    if (!window.confirm(`Move "${row.name}" to trash?`)) return;
    try {
      await fetch(`/-/places/api/lists/${row.id}/trash`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      await loadLists();
      trashedLists = null;
    } catch {
      error = "Failed to trash list";
    }
  }

  async function restoreList(row: ListRow) {
    try {
      await fetch(`/-/places/api/lists/${row.id}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      await loadLists();
      await loadTrashed();
    } catch {
      error = "Failed to restore list";
    }
  }

  function relativeTime(iso: string): string {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return iso;
    const diff = nowTick - t;
    if (diff < 45_000) return "just now";
    const mins = Math.round(diff / 60_000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(diff / 3_600_000);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(diff / 86_400_000);
    return `${days}d ago`;
  }

  onMount(() => {
    void loadLists();
    const timer = setInterval(() => { nowTick = Date.now(); }, 60_000);
    return () => clearInterval(timer);
  });

  let visibleRows = $derived(tab === "active" ? lists : (trashedLists ?? []));
</script>

<div class="places-index">
  <h1>Places</h1>

  {#if error}
    <div class="error">{error}</div>
  {/if}

  <form onsubmit={create}>
    <input
      type="text"
      bind:value={newName}
      placeholder="New list name"
      disabled={creating}
      required
    />
    <button type="submit" disabled={creating || !newName.trim()}>
      {creating ? "Creating..." : "New list"}
    </button>
  </form>

  <div class="tabs" role="tablist">
    <button
      type="button"
      role="tab"
      aria-selected={tab === "active"}
      class:active={tab === "active"}
      onclick={() => selectTab("active")}
    >
      Active ({lists.length})
    </button>
    <button
      type="button"
      role="tab"
      aria-selected={tab === "trashed"}
      class:active={tab === "trashed"}
      onclick={() => selectTab("trashed")}
    >
      Trash {trashedLists ? `(${trashedLists.length})` : ""}
    </button>
  </div>

  {#if loading && tab === "active"}
    <p>Loading...</p>
  {:else if visibleRows.length === 0}
    {#if tab === "active"}
      <p class="empty">No place lists yet. Create one above.</p>
    {:else}
      <p class="empty">Trash is empty.</p>
    {/if}
  {:else}
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Places</th>
          <th>Updated</th>
          <th class="actions-col"></th>
        </tr>
      </thead>
      <tbody>
        {#each visibleRows as row (row.id)}
          <tr>
            <td>
              <a href="/-/places/list/{row.id}">{row.name}</a>
              {#if row.visibility !== "private"}
                <span class="badge">{row.visibility}</span>
              {/if}
            </td>
            <td>{row.place_count}</td>
            <td title={row.updated_at}>{relativeTime(row.updated_at)}</td>
            <td class="actions">
              {#if row.is_owner}
                {#if tab === "active"}
                  <button
                    type="button"
                    class="action-btn danger"
                    onclick={() => void trashList(row)}
                    title="Move to trash"
                  >Trash</button>
                {:else}
                  <button
                    type="button"
                    class="action-btn"
                    onclick={() => void restoreList(row)}
                    title="Restore from trash"
                  >Restore</button>
                {/if}
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .places-index {
    max-width: 880px;
    margin: 0 auto;
    padding: 0 16px;
  }
  .error {
    background: #ffd6d6;
    color: #5a0000;
    padding: 6px 10px;
    border-radius: 4px;
    margin-bottom: 1em;
  }
  .empty {
    color: #666;
    font-style: italic;
  }
  form {
    margin: 1em 0;
    display: flex;
    gap: 0.5em;
    align-items: center;
  }
  input[type="text"] {
    width: 280px;
    max-width: 100%;
    padding: 6px 10px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font: inherit;
  }
  button[type="submit"] {
    padding: 6px 16px;
    background: #0b5cad;
    color: #fff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font: inherit;
  }
  button[type="submit"]:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid #ddd;
    margin-top: 1em;
  }
  .tabs button {
    border: none;
    background: transparent;
    padding: 8px 14px;
    cursor: pointer;
    font: inherit;
    color: #555;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .tabs button.active {
    color: #1a1a1a;
    border-bottom-color: #0b5cad;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin-top: 1em;
  }
  th, td {
    border-bottom: 1px solid #eee;
    padding: 8px;
    text-align: left;
  }
  .actions-col { width: 1%; }
  td.actions { text-align: right; white-space: nowrap; }
  .action-btn {
    border: 1px solid #ccc;
    background: #fff;
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
    font-size: 0.85em;
  }
  .action-btn:hover { background: #f5f5f5; }
  .action-btn.danger { color: #8a1a1a; border-color: #daa; }
  .action-btn.danger:hover { background: #fbecec; }
  .badge {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 7px;
    font-size: 11px;
    border-radius: 9px;
    background: #eef2f7;
    color: #4a5568;
    border: 1px solid #d0d7e0;
  }
</style>
