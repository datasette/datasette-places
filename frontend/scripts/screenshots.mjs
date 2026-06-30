#!/usr/bin/env node
// Documentation-screenshot harness for datasette-places.
//
//   node frontend/scripts/screenshots.mjs            # all shots
//   node frontend/scripts/screenshots.mjs map share  # a subset, by name
//
// Boots a throwaway `uv run datasette` (fresh internal DB + dev seed plugin),
// seeds demo data over the real API, drives headless Chromium with locally
// cached map tiles + a stability stylesheet, and writes deterministic PNGs to
// docs/screenshots/. Run via `just shots` (which builds the frontend first).

import { chromium } from "@playwright/test";
import { readdirSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { startServer, stopServer } from "./shots/server.mjs";
import { seed } from "./shots/seed.mjs";
import { OUT } from "./shots/config.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFS_DIR = resolve(HERE, "shots/defs");

// Auto-discover shots: every shots/defs/<name>.mjs default-exports a descriptor
// whose `name` must equal its filename.
async function loadShots() {
  const shots = new Map();
  for (const file of readdirSync(DEFS_DIR).sort()) {
    if (!file.endsWith(".mjs")) continue;
    const expected = file.slice(0, -4);
    const mod = await import(pathToFileURL(resolve(DEFS_DIR, file)).href);
    const shot = mod.default;
    if (!shot?.name) throw new Error(`${file}: missing default-exported shot`);
    if (shot.name !== expected) {
      throw new Error(`${file}: shot name "${shot.name}" must match filename`);
    }
    shots.set(shot.name, shot);
  }
  return shots;
}

async function main() {
  const requested = process.argv.slice(2);
  const shots = await loadShots();

  const unknown = requested.filter((n) => !shots.has(n));
  if (unknown.length) {
    console.error(`Unknown shot(s): ${unknown.join(", ")}`);
    console.error(`Available: ${[...shots.keys()].join(", ")}`);
    process.exit(1);
  }
  const toRun = requested.length ? requested : [...shots.keys()];

  await mkdir(OUT, { recursive: true });

  let server;
  let browser;
  const cleanup = () => {
    stopServer(server);
  };
  process.on("SIGINT", () => (cleanup(), process.exit(130)));
  process.on("SIGTERM", () => (cleanup(), process.exit(143)));

  try {
    server = await startServer();
    const ids = await seed();
    browser = await chromium.launch();

    for (const name of toRun) {
      const path = await shots.get(name).run(browser, ids);
      console.log(`✓ ${name} → ${path}`);
    }
  } finally {
    if (browser) await browser.close();
    cleanup();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
