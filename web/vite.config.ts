import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

// The dev server forwards /api/ to the backend itself, so the browser stays same-origin
// exactly as it is behind Caddy in production; a host-run dev server needs no
// VITE_API_BASE_URL either. Plain environment only: Vite does not load .env files into
// process.env here, and the name deliberately lacks the VITE_ prefix that would expose
// the value to client code.
const apiProxyTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // "/api/" matches Caddy's `handle /api/*` (a bare /api falls through to the SPA
      // in both), and xfwd forwards the browser's Host like Caddy's reverse_proxy, so
      // backend-generated absolute URLs stay reachable.
      "/api/": {
        target: apiProxyTarget,
        xfwd: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // e2e/ belongs to Playwright, so vitest must never pick it up as unit tests;
    // the default excludes still apply (node_modules, dist, config files, ...).
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
