interface ImportMetaEnv {
  /**
   * Base URL of the API (for example http://localhost:8001/api for E2E);
   * when unset, the api client falls back to the relative same-origin /api.
   */
  readonly VITE_API_BASE_URL?: string;
}
