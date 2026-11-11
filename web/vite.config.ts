import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

// e2e/ belongs to Playwright, so vitest must never pick it up as unit tests;
// the default excludes still apply (node_modules, dist, config files, ...).
// The dev server serves the SPA and forwards /api to the backend itself, so the
// browser stays same-origin exactly as it is behind Caddy in production. Without it a
// host-run dev server would need VITE_API_BASE_URL to point at the API's own origin,
// which brings CORS into play.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: [...configDefaults.exclude, "e2e/**"],
    // Generous per-test budget: under parallel load, 1s findBy polls flake.
    testTimeout: 10_000,
    // The default forks pool spawns one worker per CPU core, and each worker
    // builds its own jsdom environments; that saturates the machine and flakes
    // the timeouts above. Four workers keep the suite fast without starving
    // everything else running alongside it.
    maxWorkers: 4,
    // Node's Request rejects relative URLs, so tests need an absolute base.
    env: { VITE_API_BASE_URL: "http://localhost:3000/api" },
  },
});
