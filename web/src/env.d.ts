interface ImportMetaEnv {
  /**
   * Base URL of the FastAPI backend (for example http://localhost:8001 for
   * E2E); when unset, the api client falls back to http://localhost:8000.
   */
  readonly VITE_API_BASE_URL?: string;
}
