/**
 * The only module that touches localStorage (spec 6.1): swapping the storage
 * backend later means changing this file alone.
 *
 * XSS trade-off, recorded deliberately: a script injected via XSS can read the
 * token from localStorage. S2 renders no user-supplied HTML, so the attack
 * surface is the app's own code, and the contained upgrade path is an
 * httpOnly-cookie session plus a CSRF token (see docs/backlog.md).
 */
const TOKEN_KEY = "rag.accessToken";

/** Returns the persisted access token, or null when no session is stored. */
export function loadToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

/** Persists the access token for the next page load. */
export function saveToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

/** Drops the persisted token; the server-side revocation is a separate call. */
export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}
