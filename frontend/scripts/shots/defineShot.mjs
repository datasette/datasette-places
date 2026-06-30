// Turn a declarative shot descriptor into a runner function.
//
// Each defs/<name>.mjs default-exports defineShot({...}); the filename must
// equal `name` (asserted by screenshots.mjs — no central registry).
//
// Descriptor fields:
//   name      required, must match the filename
//   actor     actor id for the cookie (default OWNER)
//   viewport  context viewport (default VIEWPORT)
//   url       (ctx, ids) => string — where to navigate
//   prepare   async (page, { ids, ctx }) => void — wait for readiness, interact
//   capture   async (page, path) => void — defaults to a full-page screenshot

import { makeContext, freezeVolatile } from "./helpers.mjs";
import { out } from "./config.mjs";

export function defineShot(descriptor) {
  const { name } = descriptor;
  if (!name) throw new Error("defineShot: `name` is required");
  return {
    name,
    async run(browser, ids) {
      const ctx = await makeContext(browser, {
        actor: descriptor.actor,
        viewport: descriptor.viewport,
      });
      try {
        const page = await ctx.newPage();
        const url = descriptor.url(ctx, ids);
        // domcontentloaded (not networkidle): the paper editor holds a live
        // connection that never goes idle. Readiness is asserted explicitly in
        // each shot's prepare() instead.
        await page.goto(url, { waitUntil: "domcontentloaded" });
        if (descriptor.prepare) await descriptor.prepare(page, { ids, ctx });
        await freezeVolatile(page);
        const path = out(name);
        if (descriptor.capture) {
          await descriptor.capture(page, path);
        } else {
          await page.screenshot({ path, fullPage: false });
        }
        return path;
      } finally {
        await ctx.close();
      }
    },
  };
}
