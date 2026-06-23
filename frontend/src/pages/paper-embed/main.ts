/**
 * datasette-paper embed integration.
 *
 * Defines a `<datasette-places-map list-id="N">` web component that renders a
 * read-only Leaflet map (the existing `MapView`) for a saved place list,
 * fetching its own data from the Places API. Then registers a renderer with
 * paper's JS API (`window.datasettePaperEmbeds`) for the `place-list` kind, so
 * paper's block embed delegates rendering of a places ref to us.
 *
 * paper loads this bundle into its editor page via the provider's
 * `frontend_assets` (see datasette_places/paper.py). It is otherwise inert.
 */
import { mount, unmount } from "svelte";
import MapView from "../../lib/MapView.svelte";
import "leaflet/dist/leaflet.css";

// --- Paper's embed registry contract (kept minimal + in sync with paper) ----
interface PaperEmbedContext {
  ref: string;
  payload: Record<string, unknown>;
  mode: string;
}
interface PaperEmbedRenderer {
  kind: string;
  matchUrl?(url: URL): string | null;
  mount(host: HTMLElement, ctx: PaperEmbedContext): void | (() => void);
}
interface PaperEmbedRegistry {
  register(renderer: PaperEmbedRenderer): void;
  get(kind: string): PaperEmbedRenderer | undefined;
  match(url: URL): string | null;
  all(): PaperEmbedRenderer[];
}
declare global {
  interface Window {
    datasettePaperEmbeds?: PaperEmbedRegistry;
  }
}

/** Get (or lazily create) the shared registry — paper and this bundle load in
 *  arbitrary order, so whichever runs first creates it with this same shape. */
function embedRegistry(): PaperEmbedRegistry {
  if (!window.datasettePaperEmbeds) {
    const byKind: Record<string, PaperEmbedRenderer> = {};
    window.datasettePaperEmbeds = {
      register: (r) => {
        byKind[r.kind] = r;
      },
      get: (k) => byKind[k],
      match: (url) => {
        for (const r of Object.values(byKind)) {
          if (r.matchUrl) {
            const ref = r.matchUrl(url);
            if (ref) return ref;
          }
        }
        return null;
      },
      all: () => Object.values(byKind),
    };
  }
  return window.datasettePaperEmbeds;
}

const LIST_RE = /^\/-\/places\/list\/(\d+)\/?$/;

function listIdFromRef(ref: string): number | null {
  const m = LIST_RE.exec(ref);
  return m ? Number(m[1]) : null;
}

type PlacePin = {
  id: number;
  name: string;
  address: string | null;
  latitude: number;
  longitude: number;
  color: string;
  shape: string;
};

/** Fetch + map the list's places into MapView pins (read-only). */
async function fetchPins(listId: number): Promise<PlacePin[]> {
  const resp = await fetch(`/-/places/api/lists/${listId}/places`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) throw new Error(`places ${resp.status}`);
  const data = (await resp.json()) as {
    places?: Array<{
      id: number;
      name: string;
      address: string | null;
      latitude: number;
      longitude: number;
      color: string | null;
      metadata?: { shape?: string } | null;
    }>;
  };
  return (data.places ?? []).map((p) => ({
    id: p.id,
    name: p.name,
    address: p.address ?? null,
    latitude: p.latitude,
    longitude: p.longitude,
    color: p.color || "#3b82f6",
    shape: p.metadata?.shape || "pin",
  }));
}

/** `<datasette-places-map list-id="N">` — read-only map for one place list. */
class DatasettePlacesMap extends HTMLElement {
  private app: ReturnType<typeof mount> | null = null;

  connectedCallback(): void {
    this.style.display = "block";
    this.style.width = "100%";
    const listId = Number(this.getAttribute("list-id"));
    if (!Number.isFinite(listId)) {
      this.textContent = "Invalid map reference";
      return;
    }
    void this.renderMap(listId);
  }

  private async renderMap(listId: number): Promise<void> {
    let places: PlacePin[];
    try {
      places = await fetchPins(listId);
    } catch {
      this.textContent = "Could not load this map";
      return;
    }
    if (!this.isConnected) return; // unmounted while fetching
    this.app = mount(MapView, {
      target: this,
      props: { places, selectedId: null, previewPin: null, canEdit: false },
    });
  }

  disconnectedCallback(): void {
    if (this.app) {
      void unmount(this.app);
      this.app = null;
    }
  }
}

if (!customElements.get("datasette-places-map")) {
  customElements.define("datasette-places-map", DatasettePlacesMap);
}

embedRegistry().register({
  kind: "place-list",
  matchUrl(url) {
    const m = LIST_RE.exec(url.pathname);
    return m ? `/-/places/list/${m[1]}` : null;
  },
  mount(host, ctx) {
    const listId = listIdFromRef(ctx.ref);
    const el = document.createElement("datasette-places-map");
    if (listId != null) el.setAttribute("list-id", String(listId));
    host.appendChild(el);
    return () => el.remove();
  },
});
