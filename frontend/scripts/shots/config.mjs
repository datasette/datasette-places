// Shared constants for the documentation-screenshot harness.
//
// One throwaway `uv run datasette` server, booted on a fixed port with a fresh
// internal DB, a dev-only seed plugin (--plugins-dir), and a hard-coded signing
// secret so we can mint signed `ds_actor` cookies. See server.mjs / cookie.mjs.

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

// Port is fixed but overridable; 8491 is free in the datasette-* family
// (paper=8486, sheets=8487, town=8489, skill-default=8490).
export const PORT = Number(process.env.SHOTS_PORT) || 8491;
export const BASE = `http://localhost:${PORT}`;
export const PLACES = `${BASE}/-/places`;
export const PAPER = `${BASE}/-/paper`;

// Throwaway signing secret — NOT for production. Must match the `--secret`
// passed to datasette so the cookies we mint validate. Fixed (not random) so
// re-runs are deterministic.
export const SECRET = "screenshots-secret-not-for-prod";

// Throwaway databases. The internal DB holds places' lists/places + acl grants
// (places stores everything in the internal database); a fresh data.db keeps
// datasette happy with at least one attached, mutable DB.
export const INTERNAL_DB = "/tmp/datasette-places-shots-internal.db";
export const DATA_DIR = "/tmp/datasette-places-shots-data";
export const DATA_DB = `${DATA_DIR}/data.db`;

// Demo actors. alice owns the seeded lists (gets the Manager grant on create);
// bob is granted Editor so the share dialog shows a real collaborator. Display
// names come from the seed plugin's actors_from_ids hook.
export const OWNER = "alice";
export const COLLABORATOR = "bob";

// Where the dev-only seed plugin lives (loaded via --plugins-dir).
export const PLUGINS_DIR = resolve(HERE, "shot-plugins");

// Output: PNGs committed under docs/screenshots, named after the shot.
export const OUT = resolve(HERE, "../../../docs/screenshots");
export const out = (name) => resolve(OUT, `${name}.png`);

// Default capture geometry. deviceScaleFactor:2 → crisp retina PNGs.
export const VIEWPORT = { width: 1100, height: 820 };
export const VIEWPORT_TALL = { width: 1100, height: 1000 };
export const DEVICE_SCALE_FACTOR = 2;

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
