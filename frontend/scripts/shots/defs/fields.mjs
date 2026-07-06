// The Fields settings modal (manage-gated): the per-list metadata schema —
// each custom field with its key, type, and required/unique badges, plus the
// add-field form. Opened from the floating panel's "Fields" trigger.

import { defineShot } from "../defineShot.mjs";
import { PLACES, sleep } from "../config.mjs";
import { shotUnion } from "../helpers.mjs";

export default defineShot({
  name: "fields",
  url: (_ctx, ids) => `${PLACES}/list/${ids.primaryList}`,
  async prepare(page) {
    await page.locator(".fields-trigger").first().waitFor({ timeout: 15000 });
    await page.locator(".fields-trigger").first().click();
    await page.locator(".fields-modal").first().waitFor({ state: "visible", timeout: 15000 });
    await page.locator(".fm-list li").first().waitFor({ timeout: 15000 });
    await sleep(200);
  },
  async capture(page, path) {
    await shotUnion(page, [".fields-modal"], path);
  },
});
