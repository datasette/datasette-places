<script lang="ts">
  type Visibility = "private" | "link-view" | "link-edit";
  type Role = "viewer" | "editor";
  type ShareEntry = { actorID: string; role: Role; grantedAt?: string };
  type ShareState = {
    visibility: Visibility;
    owner: string | null;
    shares: ShareEntry[];
    canManage: boolean;
  };

  let {
    listId,
    open = false,
    onClose,
  }: {
    listId: number;
    open: boolean;
    onClose: () => void;
  } = $props();

  let state = $state<ShareState | null>(null);
  let loading = $state(false);
  let saving = $state(false);
  let error = $state<string | null>(null);

  // Draft state for editing
  let draftVisibility = $state<Visibility>("private");
  let draftShares = $state<ShareEntry[]>([]);
  let newActorId = $state("");
  let newRole = $state<Role>("viewer");

  async function load() {
    loading = true;
    error = null;
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}/share`, {
        headers: { "Content-Type": "application/json" },
      });
      if (!resp.ok) throw new Error("Failed to load");
      state = await resp.json();
      draftVisibility = state!.visibility;
      draftShares = state!.shares.map((s) => ({ ...s }));
    } catch {
      error = "Failed to load share settings";
    }
    loading = false;
  }

  function addShare() {
    const id = newActorId.trim();
    if (!id) return;
    if (state && id === state.owner) {
      error = "Cannot add the owner as a share";
      return;
    }
    if (draftShares.some((s) => s.actorID === id)) {
      error = "Actor already in list";
      return;
    }
    error = null;
    draftShares = [...draftShares, { actorID: id, role: newRole }];
    newActorId = "";
  }

  function removeShare(actorID: string) {
    draftShares = draftShares.filter((s) => s.actorID !== actorID);
  }

  function changeRole(actorID: string, role: Role) {
    draftShares = draftShares.map((s) =>
      s.actorID === actorID ? { ...s, role } : s
    );
  }

  let isDirty = $derived(() => {
    if (!state) return false;
    if (draftVisibility !== state.visibility) return true;
    if (draftShares.length !== state.shares.length) return true;
    const orig = state.shares.map((s) => `${s.actorID}:${s.role}`).sort().join(",");
    const draft = draftShares.map((s) => `${s.actorID}:${s.role}`).sort().join(",");
    return orig !== draft;
  });

  async function save() {
    if (saving) return;
    saving = true;
    error = null;
    try {
      const resp = await fetch(`/-/places/api/lists/${listId}/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          visibility: draftVisibility,
          shares: draftShares.map((s) => ({
            actorID: s.actorID,
            role: s.role,
          })),
        }),
      });
      if (!resp.ok) {
        const data = await resp.json();
        throw new Error(data.error || "Failed to save");
      }
      state = await resp.json();
      draftVisibility = state!.visibility;
      draftShares = state!.shares.map((s) => ({ ...s }));
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save";
    }
    saving = false;
  }

  function handleBackdrop(e: MouseEvent) {
    if ((e.target as Element)?.classList.contains("backdrop")) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") onClose();
  }

  $effect(() => {
    if (open && !state && !loading) void load();
  });
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="backdrop" onclick={handleBackdrop}>
    <div class="dialog" role="dialog" aria-modal="true" onkeydown={handleKeydown}>
      <header>
        <h2>Share settings</h2>
        <button type="button" class="close-btn" onclick={onClose}>&times;</button>
      </header>

      {#if loading}
        <p class="loading">Loading...</p>
      {:else if state}
        {#if error}
          <div class="error">{error}</div>
        {/if}

        <section>
          <h3>General access</h3>
          <label>
            <input
              type="radio"
              bind:group={draftVisibility}
              value="private"
              disabled={!state.canManage}
            />
            Restricted (only shared people)
          </label>
          <label>
            <input
              type="radio"
              bind:group={draftVisibility}
              value="link-view"
              disabled={!state.canManage}
            />
            Anyone with access can view
          </label>
          <label>
            <input
              type="radio"
              bind:group={draftVisibility}
              value="link-edit"
              disabled={!state.canManage}
            />
            Anyone with access can edit
          </label>
        </section>

        <section>
          <h3>People with access</h3>
          {#if state.owner}
            <div class="share-row">
              <span class="actor">{state.owner}</span>
              <span class="role-tag">Owner</span>
            </div>
          {/if}

          {#each draftShares as share}
            <div class="share-row">
              <span class="actor">{share.actorID}</span>
              {#if state.canManage}
                <select
                  value={share.role}
                  onchange={(e) => changeRole(share.actorID, (e.target as HTMLSelectElement).value as Role)}
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                <button
                  type="button"
                  class="remove-btn"
                  onclick={() => removeShare(share.actorID)}
                >&times;</button>
              {:else}
                <span class="role-tag">{share.role}</span>
              {/if}
            </div>
          {/each}

          {#if state.canManage}
            <div class="add-share">
              <input
                type="text"
                bind:value={newActorId}
                placeholder="Actor ID"
                onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); addShare(); } }}
              />
              <select bind:value={newRole}>
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button type="button" onclick={addShare} disabled={!newActorId.trim()}>Add</button>
            </div>
          {/if}
        </section>

        {#if state.canManage}
          <footer>
            <button
              type="button"
              class="btn-save"
              disabled={!isDirty() || saving}
              onclick={save}
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </footer>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .dialog {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    width: 440px;
    max-width: 95vw;
    max-height: 80vh;
    overflow-y: auto;
    padding: 20px;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  h2 { margin: 0; font-size: 1.1em; }
  h3 { margin: 12px 0 8px; font-size: 0.95em; color: #444; }
  .close-btn {
    border: none;
    background: transparent;
    font-size: 1.4em;
    cursor: pointer;
    color: #888;
    padding: 0 4px;
  }
  .close-btn:hover { color: #333; }
  .loading { color: #888; text-align: center; padding: 20px; }
  .error {
    background: #ffd6d6;
    color: #5a0000;
    padding: 6px 10px;
    border-radius: 4px;
    margin-bottom: 12px;
    font-size: 0.9em;
  }
  section { margin-bottom: 16px; }
  label {
    display: block;
    padding: 4px 0;
    font-size: 0.9em;
    cursor: pointer;
  }
  label input[type="radio"] { margin-right: 6px; }
  .share-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid #f0f0f0;
  }
  .actor {
    flex: 1;
    font-family: monospace;
    font-size: 0.9em;
  }
  .role-tag {
    font-size: 0.8em;
    padding: 2px 8px;
    background: #eef2f7;
    border-radius: 9px;
    color: #4a5568;
  }
  .share-row select {
    font: inherit;
    font-size: 0.85em;
    padding: 2px 4px;
    border: 1px solid #ccc;
    border-radius: 3px;
  }
  .remove-btn {
    border: none;
    background: transparent;
    color: #8a1a1a;
    font-size: 1.1em;
    cursor: pointer;
    padding: 0 4px;
  }
  .remove-btn:hover { color: #c00; }
  .add-share {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
  }
  .add-share input {
    flex: 1;
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    font: inherit;
    font-size: 0.9em;
  }
  .add-share select {
    font: inherit;
    font-size: 0.85em;
    padding: 4px;
    border: 1px solid #ccc;
    border-radius: 3px;
  }
  .add-share button {
    padding: 4px 12px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    cursor: pointer;
    font: inherit;
    font-size: 0.85em;
  }
  .add-share button:disabled { opacity: 0.5; cursor: not-allowed; }
  .add-share button:hover:not(:disabled) { background: #f0f0f0; }
  footer {
    margin-top: 16px;
    display: flex;
    justify-content: flex-end;
  }
  .btn-save {
    padding: 6px 20px;
    background: #0b5cad;
    color: #fff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font: inherit;
  }
  .btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-save:hover:not(:disabled) { background: #094a8d; }
</style>
