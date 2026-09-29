import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// publicDir: false keeps the build's only output paths to index.html and hashed files under
// assets/ — the backend's Host/Origin guard exemption (research.md R4/R5) enumerates exactly
// that set, so an unhashed top-level file (e.g. a favicon) must never silently appear.
export default defineConfig({
  plugins: [react()],
  publicDir: false,
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    globals: false,
    css: false,
  },
});
