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
  };

  let {
    places = [],
    selectedId = null,
    previewPin = null,
    onSelectPlace,
    onMapClick,
  }: {
    places: PlacePin[];
    selectedId: number | null;
    previewPin: { latitude: number; longitude: number; name: string } | null;
    onSelectPlace?: (id: number) => void;
    onMapClick?: (lat: number, lon: number) => void;
  } = $props();

  let mapEl: HTMLDivElement;
  let map: L.Map | undefined;
  let markersLayer: L.LayerGroup | undefined;
  let previewMarker: L.Marker | undefined;

  function createIcon(color: string, isSelected: boolean): L.DivIcon {
    const size = isSelected ? 32 : 24;
    const borderColor = isSelected ? "#000" : "#fff";
    return L.divIcon({
      className: "place-marker",
      html: `<div style="
        width:${size}px;height:${size}px;
        background:${color};
        border:2px solid ${borderColor};
        border-radius:50%;
        box-shadow:0 2px 4px rgba(0,0,0,0.3);
        transition: all 0.15s;
      "></div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function renderMarkers() {
    if (!map || !markersLayer) return;
    markersLayer.clearLayers();

    for (const p of places) {
      const isSelected = p.id === selectedId;
      const marker = L.marker([p.latitude, p.longitude], {
        icon: createIcon(p.color || "#3b82f6", isSelected),
        zIndexOffset: isSelected ? 1000 : 0,
      });
      marker.bindPopup(`<strong>${p.name}</strong>${p.address ? `<br>${p.address}` : ""}`);
      marker.on("click", () => {
        onSelectPlace?.(p.id);
      });
      markersLayer.addLayer(marker);
    }
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
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }

  $effect(() => {
    // Re-render markers whenever places or selectedId changes
    void places;
    void selectedId;
    renderMarkers();
  });

  $effect(() => {
    void previewPin;
    renderPreview();
  });

  onMount(() => {
    // Fix Leaflet default icon paths (broken by bundlers)
    delete (L.Icon.Default.prototype as any)._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
      iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
      shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
    });

    map = L.map(mapEl).setView([40, -95], 4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);

    map.on("click", (e: L.LeafletMouseEvent) => {
      onMapClick?.(e.latlng.lat, e.latlng.lng);
    });

    renderMarkers();
    // Auto-fit on initial load
    if (places.length > 0) {
      fitBounds();
    }

    return () => {
      map?.remove();
    };
  });
</script>

<div class="map-container" bind:this={mapEl}></div>

<style>
  .map-container {
    width: 100%;
    height: 100%;
    min-height: 400px;
  }
  :global(.place-marker),
  :global(.place-marker-preview) {
    background: transparent !important;
    border: none !important;
  }
</style>
