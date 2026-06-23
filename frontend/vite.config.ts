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
