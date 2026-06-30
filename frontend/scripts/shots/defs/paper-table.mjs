// The Table view inside a datasette-paper block embed — the embed now offers a
// Map / Table toggle, so a reader can see the list's custom fields as a
// spreadsheet without leaving the document.

import { defineShot } from "../defineShot.mjs";
import { PAPER, VIEWPORT_TALL, sleep } from "../config.mjs";

export default defineShot({
  name: "paper-table",
  viewport: VIEWPORT_TALL,
  url: (_ctx, ids) => `${PAPER}/doc/${ids.paperDoc}`,
  async prepare(page) {
    await page.locator(".ProseMirror").first().waitFor({ timeout: 15000 });
    const block = page.locator(".pm-block-embed").first();
    await block.waitFor({ state: "visible", timeout: 15000 });
    await block.locator(".pm-block-embed-skeleton").waitFor({ state: "detached", timeout: 15000 });
    // Switch the embed to its Table view.
    await block.locator(".embed-toolbar button", { hasText: "Table" }).first().click();
    await block.locator(".table-wrap table tbody tr").first().waitFor({ timeout: 15000 });
    await sleep(200);
  },
  async capture(page, path) {
    const block = page.locator(".pm-block-embed").first();
    const box = await block.boundingBox();
    const pad = 10;
    await page.screenshot({
      path,
      clip: {
        x: Math.max(0, Math.round(box.x - pad)),
        y: Math.max(0, Math.round(box.y - pad)),
        width: Math.round(box.width + pad * 2),
        height: Math.round(box.height + pad * 2),
      },
    });
  },
});
