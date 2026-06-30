import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import path from "path";

export default defineConfig({
  plugins: [svelte()],
  base: "/-/static-plugins/datasette_places/",
  build: {
    target: "esnext",
    outDir: path.resolve(__dirname, "../datasette_places"),
    assetsDir: "static/gen",
    emptyOutDir: false,
    manifest: "manifest.json",
    rollupOptions: {
      input: {
        index: path.resolve(__dirname, "src/pages/index/main.ts"),
        list: path.resolve(__dirname, "src/pages/list/main.ts"),
        // Web component + renderer for embedding a map in datasette-paper.
        "paper-embed": path.resolve(__dirname, "src/pages/paper-embed/main.ts"),
      },
      // Keep entry-module exports in the build output. A multi-entry app build
      // otherwise tree-shakes the unconsumed `export default` off each entry —
      // which would strip the paper provider object that datasette-paper reads
      // as `mod.default` to register the embed (it'd silently render
      // "Resource not found").
      preserveEntrySignatures: "exports-only",
    },
  },
  server: {
    port: 5176,
    strictPort: true,
    cors: true,
    origin: "http://localhost:5176",
    hmr: {
      host: "localhost",
      protocol: "ws",
    },
  },
});
