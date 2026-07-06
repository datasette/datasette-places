// The spreadsheet (Table) view of a list: one row per place, one column per
// declared custom field (Rating ★, Vibe chip, Instagram link, Wi-Fi ✓/—),
// reached via the Map/Table toggle in the floating panel.

import { defineShot } from "../defineShot.mjs";
import { PLACES, sleep } from "../config.mjs";

export default defineShot({
  name: "table",
  url: (_ctx, ids) => `${PLACES}/list/${ids.primaryList}`,
  async prepare(page) {
    // Wait for the list detail (toggle + fields) to render, then reveal the
    // table pane (it stacks on top of the map).
    await page.locator(".view-toggle-btn").first().waitFor({ timeout: 15000 });
    await page.locator(".view-toggle-btn").first().click();
    await page.locator(".table-wrap table tbody tr").first().waitFor({ timeout: 15000 });
    await sleep(200);
  },
});
