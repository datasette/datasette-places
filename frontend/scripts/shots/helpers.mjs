// Page-stabilization + capture helpers shared by the shot definitions.

import { actorCookie } from "./cookie.mjs";
import { installTileCache } from "./tiles.mjs";
import { VIEWPORT, DEVICE_SCALE_FACTOR, OWNER } from "./config.mjs";

// Injected on every navigation: kill the caret, transitions and animations,
// and hide datasette's debug bar, so re-runs produce no binary diff.
export const STABILITY_CSS = `
  *, *::before, *::after {
    caret-color: transparent !important;
    transition: none !important;
    animation: none !important;
  }
  #datasette-debug-bar { display: none !important; }
`;

// Rewrite volatile on-screen text (relative timestamps) to fixed strings so the
// pixels don't change between runs. Runs just before each capture.
export async function freezeVolatile(page) {
  await page.evaluate(() => {
    document.getElementById("datasette-debug-bar")?.remove();
    // PlacesIndex renders "just now" / "5m ago" / "2h ago" / "3d ago" in the
    // Updated column — pin them all to a single stable value.
    document.querySelectorAll("td[title]").forEach((td) => {
      if (/\b(just now|\d+[mhd] ago)\b/.test(td.textContent || "")) {
        td.textContent = "just now";
      }
    });
  });
}

// New context for a given actor: viewport + retina, signed cookie, cached
// tiles, and the stability stylesheet injected on initial doc + every nav.
export async function makeContext(browser, { actor = OWNER, viewport = VIEWPORT } = {}) {
  const ctx = await browser.newContext({
    viewport,
    deviceScaleFactor: DEVICE_SCALE_FACTOR,
  });
  await ctx.addInitScript((css) => {
    const inject = () => {
      const style = document.createElement("style");
      style.textContent = css;
      document.head?.appendChild(style);
    };
    if (document.head) inject();
    document.addEventListener("DOMContentLoaded", inject);
  }, STABILITY_CSS);
  await ctx.addCookies([actorCookie(actor)]);
  await installTileCache(ctx);
  return ctx;
}

// Screenshot the padded bounding-box union of one or more selectors — for
// floating UI (a trigger button plus its detached dialog/popup).
export async function shotUnion(page, selectors, path, pad = 16) {
  const boxes = [];
  for (const sel of selectors) {
    const el = page.locator(sel).first();
    const box = await el.boundingBox();
    if (box) boxes.push(box);
  }
  if (!boxes.length) throw new Error(`shotUnion: no selectors matched: ${selectors}`);
  const x = Math.min(...boxes.map((b) => b.x));
  const y = Math.min(...boxes.map((b) => b.y));
  const right = Math.max(...boxes.map((b) => b.x + b.width));
  const bottom = Math.max(...boxes.map((b) => b.y + b.height));
  const vp = page.viewportSize();
  const clip = {
    x: Math.max(0, x - pad),
    y: Math.max(0, y - pad),
    width: Math.min(vp.width, right + pad) - Math.max(0, x - pad),
    height: Math.min(vp.height, bottom + pad) - Math.max(0, y - pad),
  };
  await page.screenshot({ path, clip });
}

// Wait until leaflet's map pane stops moving. Leaflet's pan (fitBounds /
// popup autoPan) is a requestAnimationFrame tween — our STABILITY_CSS disables
// CSS transitions but NOT that JS tween, so capturing mid-pan is the main
// source of non-determinism. Poll the pane transform until it holds steady.
export async function waitPanSettled(page) {
  // Reset the counter so a prior waitPanSettled() on this page can't leave a
  // stale "already stable" state that short-circuits before a fresh pan (e.g.
  // popup autoPan) has even started.
  await page.evaluate(() => {
    window.__panT = undefined;
    window.__panStable = 0;
  });
  await page.waitForFunction(
    () => {
      const pane = document.querySelector(".leaflet-map-pane");
      if (!pane) return false;
      const t = pane.style.transform;
      const w = window;
      if (w.__panT === t) return (w.__panStable = (w.__panStable || 0) + 1) >= 3;
      w.__panT = t;
      w.__panStable = 0;
      return false;
    },
    null,
    { polling: 80, timeout: 15000 },
  );
}

// Wait for the leaflet map + its tiles + markers to render and settle.
export async function waitMap(page, { markers = true } = {}) {
  await page.locator(".leaflet-container").first().waitFor({ timeout: 15000 });
  await page.locator(".leaflet-tile-loaded").first().waitFor({ timeout: 15000 });
  if (markers) {
    await page.locator(".place-marker").first().waitFor({ timeout: 15000 });
  }
  await waitPanSettled(page);
}
