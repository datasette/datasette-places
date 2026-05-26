<script lang="ts">
  import { onMount } from "svelte";
  import L from "leaflet";

  type PlacePin = {
    id: number;
    name: string;
    address: string | null;
    latitude: number;
    longitude: number;
    color: string;
    shape: string;
  };

  let {
    places = [],
    selectedId = null,
    previewPin = null,
    canEdit = false,
    onSelectPlace,
    onMapClick,
    onMovePlace,
  }: {
    places: PlacePin[];
    selectedId: number | null;
    previewPin: { latitude: number; longitude: number; name: string } | null;
    canEdit?: boolean;
    onSelectPlace?: (id: number) => void;
    onMapClick?: (lat: number, lon: number) => void;
    onMovePlace?: (id: number, lat: number, lon: number) => void;
  } = $props();

  let mapEl: HTMLDivElement;
  let map: L.Map | undefined;
  let markersLayer: L.LayerGroup | undefined;
  let previewMarker: L.Marker | undefined;
  let markersById = new Map<number, L.Marker>();
  let addMode = $state(false);

  // --- Marker icon rendering -------------------------------------------------

  /** Build a DivIcon for a given shape + colour, larger/glowing when selected. */
  function createIcon(color: string, shape: string, isSelected: boolean): L.DivIcon {
    const scale = isSelected ? 1.3 : 1;
    const w = Math.round(26 * scale);
    const stroke = "#ffffff";
    const strokeW = isSelected ? 3 : 2;
    const cls = `place-marker${isSelected ? " selected" : ""}`;

    let html: string;
    let iconSize: [number, number];
    let iconAnchor: [number, number];

    if (shape === "pin") {
      const h = Math.round(w * 1.35);
      html = `<svg width="${w}" height="${h}" viewBox="0 0 24 32" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 0C6 0 1 4.7 1 10.7 1 18.6 12 32 12 32s11-13.4 11-21.3C23 4.7 18 0 12 0z"
          fill="${color}" stroke="${stroke}" stroke-width="${strokeW}"/>
        <circle cx="12" cy="11" r="4.2" fill="#fff" fill-opacity="0.92"/>
      </svg>`;
      iconSize = [w, h];
      iconAnchor = [w / 2, h];
    } else if (shape === "square") {
      html = `<svg width="${w}" height="${w}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="2" width="20" height="20" rx="4" fill="${color}" stroke="${stroke}" stroke-width="${strokeW}"/>
      </svg>`;
      iconSize = [w, w];
      iconAnchor = [w / 2, w / 2];
    } else if (shape === "star") {
      html = `<svg width="${w}" height="${w}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 1.5l3 6.5 7 .8-5.2 4.8 1.4 7L12 18.9 5.8 22.6l1.4-7L2 10.8l7-.8z"
          fill="${color}" stroke="${stroke}" stroke-width="${strokeW}" stroke-linejoin="round"/>
      </svg>`;
      iconSize = [w, w];
      iconAnchor = [w / 2, w / 2];
    } else if (shape === "flag") {
      const h = Math.round(w * 1.15);
      html = `<svg width="${w}" height="${h}" viewBox="0 0 24 28" xmlns="http://www.w3.org/2000/svg">
        <line x1="4" y1="2" x2="4" y2="27" stroke="${stroke}" stroke-width="${strokeW + 1}"/>
        <line x1="4" y1="2" x2="4" y2="27" stroke="#444" stroke-width="${strokeW - 0.5}"/>
        <path d="M4 3h15l-3.5 5 3.5 5H4z" fill="${color}" stroke="${stroke}" stroke-width="${strokeW}" stroke-linejoin="round"/>
      </svg>`;
      iconSize = [w, h];
      iconAnchor = [4, h];
    } else {
      // circle (default fallback)
      html = `<svg width="${w}" height="${w}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" fill="${color}" stroke="${stroke}" stroke-width="${strokeW}"/>
      </svg>`;
      iconSize = [w, w];
      iconAnchor = [w / 2, w / 2];
    }

    return L.divIcon({ className: cls, html, iconSize, iconAnchor });
  }

  function popupHtml(p: PlacePin): string {
    const dir = `https://www.google.com/maps/dir/?api=1&destination=${p.latitude},${p.longitude}`;
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div class="place-popup">
      <strong>${esc(p.name)}</strong>
      ${p.address ? `<div class="pp-addr">${esc(p.address)}</div>` : ""}
      <div class="pp-coord">${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}</div>
      <a href="${dir}" target="_blank" rel="noopener" class="pp-dir">Directions ↗</a>
    </div>`;
  }

  function renderMarkers() {
    if (!map || !markersLayer) return;
    markersLayer.clearLayers();
    markersById.clear();

    for (const p of places) {
      const isSelected = p.id === selectedId;
      const marker = L.marker([p.latitude, p.longitude], {
        icon: createIcon(p.color || "#3b82f6", p.shape || "pin", isSelected),
        zIndexOffset: isSelected ? 1000 : 0,
        draggable: canEdit,
      });
      marker.bindPopup(popupHtml(p));
      marker.on("click", () => onSelectPlace?.(p.id));
      if (canEdit) {
        marker.on("dragend", () => {
          const { lat, lng } = marker.getLatLng();
          onMovePlace?.(p.id, lat, lng);
        });
      }
      markersLayer.addLayer(marker);
      markersById.set(p.id, marker);
    }
  }

  /** Pan to and open the popup for the currently-selected marker. */
  function focusSelected() {
    if (!map || selectedId == null) return;
    const marker = markersById.get(selectedId);
    if (!marker) return;
    map.panTo(marker.getLatLng(), { animate: true });
    marker.openPopup();
  }

  function renderPreview() {
    if (!map) return;
    if (previewMarker) {
      map.removeLayer(previewMarker);
      previewMarker = undefined;
    }
    if (previewPin) {
      previewMarker = L.marker([previewPin.latitude, previewPin.longitude], {
        icon: L.divIcon({
          className: "place-marker-preview",
          html: `<div style="
            width:28px;height:28px;
            background:#f59e0b;
            border:2px dashed #fff;
            border-radius:50%;
            box-shadow:0 2px 6px rgba(0,0,0,0.4);
            opacity:0.85;
          "></div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        }),
        zIndexOffset: 2000,
      });
      previewMarker.bindPopup(`<em>${previewPin.name}</em>`).openPopup();
      previewMarker.addTo(map);
      map.panTo([previewPin.latitude, previewPin.longitude]);
    }
  }

  export function fitBounds() {
    if (!map || places.length === 0) return;
    const bounds = L.latLngBounds(places.map((p) => [p.latitude, p.longitude]));
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
  }

  function toggleAddMode() {
    addMode = !addMode;
    mapEl?.classList.toggle("add-mode", addMode);
  }

  $effect(() => {
    // Re-render markers whenever places, selection, or edit-rights change,
    // then re-focus the selected marker.
    void places;
    void selectedId;
    void canEdit;
    renderMarkers();
    focusSelected();
  });

  $effect(() => {
    void previewPin;
    renderPreview();
  });

  onMount(() => {
    map = L.map(mapEl, { zoomControl: true }).setView([30, 10], 4);

    // Base layers — street by default.
    const street = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    });
    const satellite = L.layerGroup([
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
          attribution: "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics",
          maxZoom: 19,
        }
      ),
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 19 }
      ),
    ]);
    const terrain = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      attribution: "Map data: &copy; OpenStreetMap, SRTM | &copy; OpenTopoMap",
      maxZoom: 17,
    });

    street.addTo(map);
    L.control
      .layers(
        { Street: street, Satellite: satellite, Terrain: terrain },
        {},
        { position: "topright" }
      )
      .addTo(map);

    markersLayer = L.layerGroup().addTo(map);

    map.on("click", (e: L.LeafletMouseEvent) => {
      if (addMode) onMapClick?.(e.latlng.lat, e.latlng.lng);
    });

    renderMarkers();
    if (places.length > 0) fitBounds();

    return () => {
      map?.remove();
    };
  });
</script>

<div class="map-wrap">
  <div class="map-container" bind:this={mapEl}></div>
  <div class="map-toolbar">
    {#if canEdit}
      <button
        type="button"
        class="tool-btn"
        class:active={addMode}
        title={addMode ? "Click the map to drop a pin (click to exit)" : "Add a place by clicking the map"}
        onclick={toggleAddMode}
      >
        <span class="tool-icon">＋</span> Add place
      </button>
    {/if}
    <button
      type="button"
      class="tool-btn"
      title="Fit all places in view"
      onclick={() => fitBounds()}
      disabled={places.length === 0}
    >
      <span class="tool-icon">⤢</span> Fit
    </button>
  </div>
</div>

<style>
  .map-wrap {
    position: relative;
    width: 100%;
    height: 100%;
  }
  .map-container {
    width: 100%;
    height: 100%;
    min-height: 400px;
  }
  :global(.map-container.add-mode) {
    cursor: crosshair;
  }
  :global(.place-marker),
  :global(.place-marker-preview) {
    background: transparent !important;
    border: none !important;
  }
  :global(.place-marker.selected svg) {
    filter: drop-shadow(0 0 4px rgba(0, 0, 0, 0.55));
  }
  :global(.place-popup) {
    font-size: 0.9em;
    line-height: 1.45;
  }
  :global(.place-popup .pp-addr) {
    color: #555;
  }
  :global(.place-popup .pp-coord) {
    color: #888;
    font-variant-numeric: tabular-nums;
    margin-top: 2px;
  }
  :global(.place-popup .pp-dir) {
    display: inline-block;
    margin-top: 4px;
    color: #0b5cad;
    text-decoration: none;
  }
  :global(.place-popup .pp-dir:hover) {
    text-decoration: underline;
  }

  .map-toolbar {
    position: absolute;
    top: 10px;
    left: 50px;
    z-index: 500;
    display: flex;
    gap: 6px;
  }
  .tool-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 10px;
    background: #fff;
    border: 1px solid #bbb;
    border-radius: 4px;
    font: inherit;
    font-size: 0.82em;
    cursor: pointer;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
    color: #333;
  }
  .tool-btn:hover:not(:disabled) {
    background: #f3f6fb;
  }
  .tool-btn.active {
    background: #0b5cad;
    color: #fff;
    border-color: #0b5cad;
  }
  .tool-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .tool-icon {
    font-size: 1.1em;
    line-height: 1;
  }
</style>
