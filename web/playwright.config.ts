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
      // Bootstrap the dedicated E2E database and broker vhost, then serve the API on 8001.
      command:
        `"${PYTHON}" scripts\\e2e_db.py bootstrap && ` +
        `"${PYTHON}" -m uvicorn app.main:app --port 8001`,
      cwd: "../backend",
      url: "http://localhost:8001/api/health",
      env: {
        RAG_DATABASE_URL: "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e",
        // E2E stays on the offline stub stack whatever the local backend/.env opts into.
        RAG_LLM_PROVIDER: "stub",
        RAG_ENVIRONMENT: "dev",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // No ready URL exists, so the entries wait on stderr lines; Celery logs to
      // stderr and worker_redirect_stdouts sends print() output there too.
      command: `"${PYTHON}" -m celery -A app.workers.celery_app worker --pool=solo -Q ingestion,embed`,
      cwd: "../backend",
      env: {
        RAG_DATABASE_URL: "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e",
        RAG_BROKER_URL: "amqp://guest:guest@localhost:5672/rag_e2e",
        RAG_LLM_PROVIDER: "stub",
        RAG_ENVIRONMENT: "dev",
      },
      wait: { stderr: /celery worker ready/ },
      timeout: 120_000,
    },
    {
      command: `"${PYTHON}" -m app.workers.dispatcher`,
      cwd: "../backend",
      env: {
        RAG_DATABASE_URL: "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e",
        RAG_BROKER_URL: "amqp://guest:guest@localhost:5672/rag_e2e",
        RAG_LLM_PROVIDER: "stub",
        RAG_ENVIRONMENT: "dev",
      },
      wait: { stderr: /dispatcher ready/ },
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      env: { VITE_API_BASE_URL: "http://localhost:8001/api" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
