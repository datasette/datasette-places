// A Places map embedded as a block inside a datasette-paper document — the
// paper-embed integration (paper.py + src/pages/paper-embed/main.ts). Paper
// lazy-loads our bundle for the doc's `/-/places/...` ref and mounts a
// read-only <datasette-places-map>.

import { defineShot } from "../defineShot.mjs";
import { PAPER, VIEWPORT_TALL } from "../config.mjs";
import { waitMap } from "../helpers.mjs";

export default defineShot({
  name: "paper-embed",
  viewport: VIEWPORT_TALL,
  url: (_ctx, ids) => `${PAPER}/doc/${ids.paperDoc}`,
  async prepare(page) {
    // Wait for the paper editor, then the embed block to resolve (skeleton
    // gone) and its leaflet map to render + settle.
    await page.locator(".ProseMirror").first().waitFor({ timeout: 15000 });
    const block = page.locator(".pm-block-embed").first();
    await block.waitFor({ state: "visible", timeout: 15000 });
    await block.locator(".pm-block-embed-skeleton").waitFor({ state: "detached", timeout: 15000 });
    await waitMap(page);
  },
});
