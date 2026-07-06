// A marker popup opened inside a datasette-paper block embed — showing that the
// embedded mini-map loads the list's custom fields too (rating, vibe, …), not
// just name/address. Clipped to the embed block + the open popup.

import { defineShot } from "../defineShot.mjs";
import { PAPER, VIEWPORT_TALL, sleep } from "../config.mjs";
import { waitMap, shotUnion } from "../helpers.mjs";

export default defineShot({
  name: "paper-popup",
  viewport: VIEWPORT_TALL,
  url: (_ctx, ids) => `${PAPER}/doc/${ids.paperDoc}`,
  async prepare(page) {
    await page.locator(".ProseMirror").first().waitFor({ timeout: 15000 });
    const block = page.locator(".pm-block-embed").first();
    await block.waitFor({ state: "visible", timeout: 15000 });
    await block.locator(".pm-block-embed-skeleton").waitFor({ state: "detached", timeout: 15000 });
    await waitMap(page);
    // Open a marker's popup. autoPan is disabled, so the map stays put and the
    // popup lands deterministically over its marker.
    await block.locator(".leaflet-marker-icon").first().click();
    await page.locator(".leaflet-popup").first().waitFor({ state: "visible", timeout: 15000 });
    await sleep(300);
  },
  async capture(page, path) {
    await shotUnion(page, [".pm-block-embed", ".leaflet-popup"], path);
  },
});
