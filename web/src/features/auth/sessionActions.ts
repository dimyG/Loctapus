import { createAction } from "@reduxjs/toolkit";

/**
 * Clears the local session token and user, dispatched synchronously by
 * logout before its best-effort revocation POST. The status field is
 * intentionally left alone ("busy" from the pending action): the guard then
 * shows the splash instead of bouncing to /login while the navigation lands.
 */
export const sessionCleared = createAction("auth/sessionCleared");

/**
 * Clears the whole local session, dispatched by the base query wrapper when
 * an authenticated request comes back 401 (the token is expired or revoked).
 * Status drops to "idle" so the guard sends the visitor to /login.
 */
export const sessionExpired = createAction("auth/sessionExpired");
