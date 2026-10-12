import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import { createAsyncThunk, createSlice, isAnyOf } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";
import { api, baseQuery, thunkBaseQueryApi } from "../../app/api";
import { clearToken, loadToken, saveToken } from "../../lib/tokenStorage";
import { sessionCleared, sessionExpired } from "./sessionActions";

/** Rejections carry the base query error shape so pages can map them to copy. */
type RejectsApiError = { rejectValue: FetchBaseQueryError };

export type AuthUser = { id: string; email: string };
/**
 * The session lifecycle. "signedout" is distinct from "idle": the auth
 * guard routes a signed-out session home (the sign-out flow owns routing)
 * while idle-without-token means the session expired and must
 * re-authenticate. Collapsing them reopens the sign-out race.
 */
export type AuthStatus = "idle" | "booting" | "busy" | "signedout";
export type AuthState = { token: string | null; user: AuthUser | null; status: AuthStatus };
export type Credentials = { email: string; password: string };

type TokenResponse = { access_token: string; token_type: string };
type UsersMeResponse = { user_id: string; email: string };

type ThunkContext = {
  dispatch: ThunkDispatch<unknown, unknown, UnknownAction>;
  getState: () => unknown;
};

/**
 * Initial session state derived from whatever token is persisted at call time.
 * Lazy by design: evaluated per store creation, never at module load.
 */
export const getInitialAuthState = (): AuthState => {
  const token = loadToken();
  return { token, user: null, status: token === null ? "idle" : "booting" };
};

/** GET /users/me mapped onto the client's AuthUser shape. */
async function fetchCurrentUser({ dispatch, getState }: ThunkContext): Promise<AuthUser> {
  const result = await baseQuery(
    { url: "/users/me", method: "GET" },
    thunkBaseQueryApi(dispatch, getState),
    {},
  );
  if (result.error !== undefined) {
    throw result.error;
  }
  const me = result.data as UsersMeResponse;
  return { id: me.user_id, email: me.email };
}

/** GETs the session from a stored token; rejects when the token no longer works. */
export const bootstrapAuth = createAsyncThunk<AuthUser | null, void, RejectsApiError>(
  "auth/bootstrap",
  async (_arg, context) => {
    if (loadToken() === null) {
      return null;
    }
    try {
      return await fetchCurrentUser(context);
    } catch (error) {
      // Only a 401 proves the stored token bad; a network or server error
      // keeps it so a transient failure does not sign the user out (spec 6.2).
      if ((error as { status?: number | string }).status === 401) {
        clearToken();
      }
      return context.rejectWithValue(error as FetchBaseQueryError);
    }
  },
);

/** Logs in, persists the token, and hydrates the user. */
export const loginUser = createAsyncThunk<AuthUser, Credentials, RejectsApiError>(
  "auth/login",
  async (credentials, context) => {
    const result = await baseQuery(
      { url: "/auth/login", method: "POST", body: credentials },
      thunkBaseQueryApi(context.dispatch, context.getState),
      {},
    );
    if (result.error !== undefined) {
      return context.rejectWithValue(result.error);
    }
    const token = (result.data as TokenResponse).access_token;
    saveToken(token);
    // The /users/me call reads the token from the store via prepareHeaders,
    // so publish it before hydrating.
    context.dispatch(tokenReceived(token));
    try {
      return await fetchCurrentUser(context);
    } catch (error) {
      clearToken();
      return context.rejectWithValue(error as FetchBaseQueryError);
    }
  },
);

/** Registers, persists the returned token, and hydrates the user. */
export const registerUser = createAsyncThunk<AuthUser, Credentials, RejectsApiError>(
  "auth/register",
  async (credentials, context) => {
    const result = await baseQuery(
      { url: "/auth/register", method: "POST", body: credentials },
      thunkBaseQueryApi(context.dispatch, context.getState),
      {},
    );
    if (result.error !== undefined) {
      return context.rejectWithValue(result.error);
    }
    const token = (result.data as TokenResponse).access_token;
    saveToken(token);
    context.dispatch(tokenReceived(token));
    try {
      return await fetchCurrentUser(context);
    } catch (error) {
      clearToken();
      return context.rejectWithValue(error as FetchBaseQueryError);
    }
  },
);

/** Revokes the token server-side (best-effort) and clears the local session. */
export const logoutUser = createAsyncThunk<void, void>("auth/logout", async (_arg, context) => {
  // The local session drops first, synchronously: revocation is best-effort
  // (spec 6.2) and must never block on the network.
  const token = (context.getState() as WithAuth).auth?.token;
  clearToken();
  context.dispatch(sessionCleared());
  context.dispatch(api.util.resetApiState());
  if (token == null) {
    return;
  }
  try {
    await baseQuery(
      {
        url: "/auth/logout",
        method: "POST",
        // The header is explicit: the store token is already cleared, so
        // prepareHeaders cannot supply it.
        headers: { authorization: `Bearer ${token}` },
      },
      thunkBaseQueryApi(context.dispatch, context.getState),
      {},
    );
  } catch {
    // Ignored on purpose: the token expires server-side within 24h anyway.
  }
});

const authSlice = createSlice({
  name: "auth",
  // Lazy: read per store creation so each test seeds its own storage.
  initialState: getInitialAuthState,
  reducers: {
    tokenReceived(state, action: PayloadAction<string>) {
      state.token = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(sessionCleared, (state) => {
        state.token = null;
        state.user = null;
        // Status stays as-is ("busy" from the pending action): the guard then
        // shows the splash rather than bouncing to /login while the
        // sign-out navigation lands.
      })
      .addCase(sessionExpired, (state) => {
        state.token = null;
        state.user = null;
        state.status = "idle";
      })
      .addCase(bootstrapAuth.fulfilled, (state, action) => {
        state.user = action.payload;
        state.status = "idle";
      })
      .addCase(bootstrapAuth.rejected, (state, action) => {
        state.status = "idle";
        // A 401 proves the token bad; anything else keeps it for the next
        // attempt (the guard still renders the app; pages retry).
        if ((action.payload as { status?: number | string } | undefined)?.status === 401) {
          state.token = null;
          state.user = null;
        }
      })
      .addMatcher(isAnyOf(loginUser.pending, registerUser.pending, logoutUser.pending), (state) => {
        state.status = "busy";
      })
      .addMatcher(isAnyOf(loginUser.fulfilled, registerUser.fulfilled), (state, action) => {
        state.user = action.payload;
        state.status = "idle";
      })
      .addMatcher(isAnyOf(loginUser.rejected, registerUser.rejected), (state) => {
        state.token = null;
        state.user = null;
        state.status = "idle";
      })
      .addMatcher(isAnyOf(logoutUser.fulfilled, logoutUser.rejected), (state) => {
        state.token = null;
        state.user = null;
        // Not "idle": the guard must distinguish just-signed-out (route to
        // the public landing) from expired (route to /login).
        state.status = "signedout";
      });
  },
});

export const { tokenReceived } = authSlice.actions;

// Selectors take a structural slice key so they work against any state shape
// that contains auth (the full RootState, or a test-local store).
type WithAuth = { auth: AuthState };

/** The whole auth slice. */
export const selectAuth = (state: WithAuth): AuthState => state.auth;

/** The session lifecycle: idle, booting (token present, user pending), busy, signedout. */
export const selectAuthStatus = (state: WithAuth): AuthStatus => state.auth.status;

/** The hydrated session user, or null when signed out / still booting. */
export const selectUser = (state: WithAuth): AuthUser | null => state.auth.user;

/** The session token from the store (never read localStorage directly). */
export const selectToken = (state: WithAuth): string | null => state.auth.token;

export default authSlice.reducer;
