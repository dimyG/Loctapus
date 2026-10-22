// The storage key shares the "rag." prefix the token storage already uses.
export const LAST_PROJECT_ID_KEY = "rag.lastProjectId";

/** Returns the id of the project the user last opened, or null when none is stored. */
export function loadLastProjectId(): string | null {
  return window.localStorage.getItem(LAST_PROJECT_ID_KEY);
}

/**
 * Remembers the opened project so section links outside a project URL (the
 * /projects list page) can lead back to it instead of the newest project.
 */
export function saveLastProjectId(projectId: string): void {
  window.localStorage.setItem(LAST_PROJECT_ID_KEY, projectId);
}
