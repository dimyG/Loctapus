import { defineConfig } from "@playwright/test";
import { PYTHON } from "./e2e/venv";

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    {
      // Bootstrap the dedicated E2E database, then serve the API on 8001.
      command:
        `"${PYTHON}" scripts\\e2e_db.py bootstrap && ` +
        `"${PYTHON}" -m uvicorn app.main:app --port 8001`,
      cwd: "../backend",
      url: "http://localhost:8001/health",
      env: { RAG_DATABASE_URL: "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      env: { VITE_API_BASE_URL: "http://localhost:8001" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
