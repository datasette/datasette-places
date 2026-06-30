// A marker's popup — the per-place card (name / address / coords / directions).
//
// We select the place from the list panel (a single focusSelected() path)
// rather than clicking the marker (which also fires Leaflet's native popup
// autoPan, racing to a different end state). Even so, the app pans the map with
// animation, so the popup's *screen position* isn't deterministic — but its
// rendered content is. So we clip to the popup card itself: identical pixels
// every run, regardless of where the map settled.

import { defineShot } from "../defineShot.mjs";
import { PLACES } from "../config.mjs";
import { waitMap, waitPanSettled } from "../helpers.mjs";

export default defineShot({
  name: "popup",
  url: (_ctx, ids) => `${PLACES}/list/${ids.primaryList}`,
  async prepare(page) {
    await waitMap(page);
    await page.locator(".place-card", { hasText: "Never Coffee" }).first().click();
    await page.locator(".leaflet-popup").first().waitFor({ timeout: 15000 });
    await waitPanSettled(page);
  },
  async capture(page, path) {
    const pad = 12;
    const popup = page.locator(".leaflet-popup").first();
    const box = await popup.boundingBox();
    // Integer-rounded clip so sub-pixel popup placement can't perturb the PNG.
    await page.screenshot({
      path,
      clip: {
        x: Math.round(box.x - pad),
        y: Math.round(box.y - pad),
        width: Math.round(box.width + pad * 2),
        height: Math.round(box.height + pad * 2),
      },
    });
  },
});
