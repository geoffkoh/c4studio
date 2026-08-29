import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build directly into the Python package's static directory so the FastAPI
// backend can serve the compiled SPA.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/c4studio/webapp/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8090",
        changeOrigin: true,
      },
    },
  },
});
