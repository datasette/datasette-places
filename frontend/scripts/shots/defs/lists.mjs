// The Places index: create-a-list form, Active/Trash tabs, and the table of
// lists with place counts and relative "Updated" times.

import { defineShot } from "../defineShot.mjs";
import { PLACES } from "../config.mjs";

export default defineShot({
  name: "lists",
  url: () => `${PLACES}/`,
  async prepare(page) {
    // Wait for the list table to render with the seeded rows.
    await page.locator(".places-index table tbody tr").first().waitFor({ timeout: 15000 });
  },
});
