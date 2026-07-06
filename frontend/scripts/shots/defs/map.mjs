// A single place list: the full-screen leaflet map with the seeded markers and
// the floating list panel.

import { defineShot } from "../defineShot.mjs";
import { PLACES } from "../config.mjs";
import { waitMap } from "../helpers.mjs";

export default defineShot({
  name: "map",
  url: (_ctx, ids) => `${PLACES}/list/${ids.primaryList}`,
  async prepare(page) {
    await waitMap(page);
  },
});
