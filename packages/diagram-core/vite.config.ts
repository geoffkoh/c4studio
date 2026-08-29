import { defineConfig } from "vite";

// Bundle the headless renderer into a single dependency-free ES module that
// ships inside the Python package, so `c4 render` works from an
// installed wheel with nothing but a `node` binary — no npm install, no
// node_modules. dagre is bundled in; nothing is left external.
export default defineConfig({
  build: {
    target: "node18",
    outDir: "../../src/c4studio/renderer",
    emptyOutDir: false,
    minify: false,
    lib: {
      entry: "src/cli.ts",
      formats: ["es"],
      fileName: () => "diagram-render.mjs",
    },
    rollupOptions: {
      external: [],
      output: { codeSplitting: false },
    },
  },
});
