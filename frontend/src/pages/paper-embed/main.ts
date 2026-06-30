/**
 * datasette-paper embed integration.
 *
 * Defines a `<datasette-places-map list-id="N">` web component that renders a
 * read-only Leaflet map (the existing `MapView`) for a saved place list,
 * fetching its own data from the Places API. Then `export default`s a paper
 * embed provider for the `place-list` kind: paper `import()`s this bundle on
 * demand and registers the provider for us (see the provider descriptor in
 * datasette_places/paper.py and docs/EMBED_PROVIDERS.md in datasette-paper).
 *
 * Everything is client-side: resolve/search fetch the Places API with the
 * viewer's `ds_actor` cookie, so per-viewer leak discipline is ours — a denied
 * list yields `denied`/`not_found` with no name or data leaked.
 */
import { mount, unmount } from "svelte";
import MapView from "../../lib/MapView.svelte";
import "leaflet/dist/leaflet.css";

const LIST_RE = /^\/-\/places\/list\/(\d+)\/?$/;

function listIdFromRef(ref: string): number | null {
  const m = LIST_RE.exec(ref);
  return m ? Number(m[1]) : null;
}

// bootstrap-icons/globe — inline pill + block-card header icon. Static markup
// only (paper renders it as raw HTML, unsanitized — never interpolate data).
const GLOBE_ICON =
  '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8m7.5-6.923c-.67.204-1.335.82-1.887 1.855A8 8 0 0 0 5.145 4H7.5zM4.09 4a9.3 9.3 0 0 1 .64-1.539 7 7 0 0 1 .597-.933A7.03 7.03 0 0 0 2.255 4zm-.582 3.5c.03-.877.138-1.718.312-2.5H1.674a7 7 0 0 0-.656 2.5zM4.847 5a12.5 12.5 0 0 0-.338 2.5H7.5V5zM8.5 5v2.5h2.99a12.5 12.5 0 0 0-.337-2.5zM4.51 8.5a12.5 12.5 0 0 0 .337 2.5H7.5V8.5zm3.99 0V11h2.653c.187-.765.306-1.608.338-2.5zM5.145 12q.208.58.468 1.068c.552 1.035 1.218 1.65 1.887 1.855V12zm.182 2.472a7 7 0 0 1-.597-.933A9.3 9.3 0 0 1 4.09 12H2.255a7 7 0 0 0 3.072 2.472M3.82 11a13.7 13.7 0 0 1-.312-2.5h-2.49c.062.89.291 1.733.656 2.5zm6.853 3.472A7 7 0 0 0 13.745 12H11.91a9.3 9.3 0 0 1-.64 1.539 7 7 0 0 1-.597.933M8.5 12v2.923c.67-.204 1.335-.82 1.887-1.855q.26-.487.468-1.068zm3.68-1h2.146c.365-.767.594-1.61.656-2.5h-2.49a13.7 13.7 0 0 1-.312 2.5m2.802-3.5a7 7 0 0 0-.656-2.5H12.18c.174.782.282 1.623.312 2.5zM11.27 2.461q.337.708.582 1.539h1.835a7 7 0 0 0-3.072-2.472q.327.482.655 1.348zM10.855 4a8 8 0 0 0-.468-1.068C9.835 1.897 9.17 1.282 8.5 1.077V4z"/></svg>';

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

// --- Paper embed provider (paper import()s this bundle + registers it) -------

type ResolveResult =
  | { status: "ok"; kind: string; label: string; href: string; icon?: string }
  | { status: "denied" }
  | { status: "not_found" }
  | null;

interface PaperEmbedContext {
  ref: string;
  mode: string;
}

interface PickerSource {
  id: string;
  label: string;
  icon?: string;
  mode?: string;
}

interface SearchHit {
  ref: string;
  label: string;
  kind?: string;
  detail?: string;
}

const provider = {
  kind: "place-list",

  /** Claim a stored ref (checked before paper's native .json resolution). */
  matchRef(ref: string): boolean {
    return LIST_RE.test(ref);
  },

  /** Claim a pasted same-origin URL → the ref to store. */
  matchUrl(url: URL): string | null {
    const m = LIST_RE.exec(url.pathname);
    return m ? `/-/places/list/${m[1]}` : null;
  },

  /** Inline-pill identity. Fetch with the viewer's cookie; leak discipline:
   *  a denied/missing list never yields a label. */
  async resolve(ref: string): Promise<ResolveResult> {
    const listId = listIdFromRef(ref);
    if (listId == null) return { status: "not_found" };
    let res: Response;
    try {
      res = await fetch(`/-/places/api/lists/${listId}`, {
        headers: { Accept: "application/json" },
      });
    } catch {
      return { status: "not_found" };
    }
    if (res.status === 403) return { status: "denied" }; // never a label here
    if (!res.ok) return { status: "not_found" };
    const j = (await res.json()) as { name?: string };
    return {
      status: "ok",
      kind: "place-list",
      label: j.name || `List ${listId}`,
      href: ref,
      icon: GLOBE_ICON,
    };
  },

  /** Block card body. Paper owns the header; we fill `host` with the map. */
  mount(host: HTMLElement, ctx: PaperEmbedContext): () => void {
    const listId = listIdFromRef(ctx.ref);
    const el = document.createElement("datasette-places-map");
    if (listId != null) el.setAttribute("list-id", String(listId));
    host.appendChild(el);
    return () => el.remove();
  },

  /** Browsable `/`-menu source — mirrored by `sources` in paper.py so it shows
   *  before this bundle loads. */
  picker(): PickerSource {
    return { id: "places", label: "Places map", icon: "globe", mode: "block" };
  },

  /** Viewer-filtered place lists matching `q`, for the picker dialog. The API
   *  only returns lists the viewer may see, so no leak. */
  async search(q: string, limit: number): Promise<SearchHit[]> {
    let res: Response;
    try {
      res = await fetch(`/-/places/api/lists`, {
        headers: { Accept: "application/json" },
      });
    } catch {
      return [];
    }
    if (!res.ok) return [];
    const rows = (await res.json()) as Array<{
      id: number;
      name: string | null;
      place_count?: number;
    }>;
    const qLow = (q || "").toLowerCase();
    const matched = rows
      .filter((r) => !qLow || (r.name || "").toLowerCase().includes(qLow))
      .sort((a, b) => {
        const an = (a.name || "").toLowerCase();
        const bn = (b.name || "").toLowerCase();
        const aStarts = an.startsWith(qLow) ? 0 : 1;
        const bStarts = bn.startsWith(qLow) ? 0 : 1;
        return aStarts - bStarts || an.localeCompare(bn);
      })
      .slice(0, limit);
    return matched.map((r) => {
      const count = r.place_count ?? 0;
      return {
        ref: `/-/places/list/${r.id}`,
        kind: "place-list",
        label: r.name || `List ${r.id}`,
        detail: `${count} place${count === 1 ? "" : "s"}`,
      };
    });
  },
};

export default provider;
