// The share dialog (datasette-acl-share-dialog) open over a list, showing the
// owner (Alice, Manager) and the shared collaborator (Bob, Editor). Clipped to
// the dialog itself.

import { defineShot } from "../defineShot.mjs";
import { PLACES, sleep } from "../config.mjs";
import { waitMap, shotUnion } from "../helpers.mjs";

const DIALOG = "dialog.datasette-acl-share-dialog[open]";

export default defineShot({
  name: "share",
  url: (_ctx, ids) => `${PLACES}/list/${ids.primaryList}`,
  async prepare(page) {
    await waitMap(page);
    await page.locator(".datasette-acl-share__trigger").first().click();
    await page.locator(DIALOG).waitFor({ state: "visible", timeout: 15000 });
    // Let the dialog's async "People with access" list settle.
    await page.locator(`${DIALOG} .datasette-acl-share-dialog__list`).first().waitFor({ timeout: 15000 });
    await sleep(400);
  },
  async capture(page, path) {
    await shotUnion(page, [DIALOG], path);
  },
});
