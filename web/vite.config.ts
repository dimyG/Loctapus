import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { configDefaults, defineConfig } from "vitest/config";

// e2e/ belongs to Playwright, so vitest must never pick it up as unit tests;
// the default excludes still apply (node_modules, dist, config files, ...).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: [...configDefaults.exclude, "e2e/**"],
    // Generous per-test budget: under parallel load, 1s findBy polls flake.
    testTimeout: 10_000,
  },
});
