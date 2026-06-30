// Serve map tiles from a local, gitignored cache so map shots look like real
// maps while staying deterministic and (after the first run) offline.
//
// MapView.svelte pulls tiles from *.tile.openstreetmap.org,
// server.arcgisonline.com, and *.tile.opentopomap.org. On the first run we
// fetch each tile for real and cache it under .tile-cache/; every run after
// that is served from disk — same bytes, no network.
//
// The cache is NOT committed (see .gitignore) — screenshot generation is a
// manual local task, so a developer's first run (which needs network)
// populates it.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CACHE_DIR = resolve(HERE, ".tile-cache");

// Matches the raster tile endpoints used in MapView.svelte.
const TILE_RE = /tile\.openstreetmap\.org|tile\.opentopomap\.org|server\.arcgisonline\.com/;

// Stable cache filename for a tile URL. Collapses the a/b/c subdomain rotation
// (those hosts serve identical tiles) so we don't cache the same tile thrice.
function cacheKey(url) {
  const u = new URL(url);
  const host = u.host.replace(/^[abc]\./, "");
  return `${host}${u.pathname}`.replace(/[^a-z0-9._/-]/gi, "_");
}

// Install on a browser context: serve cached tiles, fetching+caching on miss.
export async function installTileCache(ctx) {
  await ctx.route(TILE_RE, async (route) => {
    const file = resolve(CACHE_DIR, cacheKey(route.request().url()));
    if (existsSync(file)) {
      return route.fulfill({ contentType: "image/png", body: readFileSync(file) });
    }
    // Cache miss → fetch for real (needs network), cache, and serve.
    const resp = await route.fetch(); // bypasses this route handler
    const body = await resp.body();
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, body);
    return route.fulfill({ response: resp });
  });
}
