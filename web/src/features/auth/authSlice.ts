import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import { createAsyncThunk, createSlice, isAnyOf } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";
import { api, baseQuery, thunkBaseQueryApi } from "../../app/api";
import { clearToken, loadToken, saveToken } from "../../lib/tokenStorage";

/** Rejections carry the base query error shape so pages can map them to copy. */
type RejectsApiError = { rejectValue: FetchBaseQueryError };

export type AuthUser = { id: string; email: string };
export type AuthStatus = "idle" | "booting" | "busy";
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
      // A stored token that no longer authenticates is indistinguishable from
      // no session: drop it and let the guard send the visitor to /login.
      clearToken();
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
  // Revocation is best-effort (spec 6.2): the token expires server-side
  // within 24h anyway, so a failed POST must not block the local sign-out.
  try {
    await baseQuery(
      { url: "/auth/logout", method: "POST" },
      thunkBaseQueryApi(context.dispatch, context.getState),
      {},
    );
  } catch {
    // Ignored on purpose: the local session is cleared below regardless.
  }
  clearToken();
  context.dispatch(api.util.resetApiState());
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
      .addCase(bootstrapAuth.fulfilled, (state, action) => {
        state.user = action.payload;
        state.status = "idle";
      })
      .addMatcher(isAnyOf(loginUser.pending, registerUser.pending, logoutUser.pending), (state) => {
        state.status = "busy";
      })
      .addMatcher(isAnyOf(loginUser.fulfilled, registerUser.fulfilled), (state, action) => {
        state.user = action.payload;
        state.status = "idle";
      })
      .addMatcher(
        isAnyOf(loginUser.rejected, registerUser.rejected, bootstrapAuth.rejected),
        (state) => {
          state.token = null;
          state.user = null;
          state.status = "idle";
        },
      )
      .addMatcher(isAnyOf(logoutUser.fulfilled, logoutUser.rejected), (state) => {
        state.token = null;
        state.user = null;
        state.status = "idle";
      });
  },
});

export const { tokenReceived } = authSlice.actions;

// Selectors take a structural slice key so they work against any state shape
// that contains auth (the full RootState, or a test-local store).
type WithAuth = { auth: AuthState };

/** The whole auth slice. */
export const selectAuth = (state: WithAuth): AuthState => state.auth;

/** The session lifecycle: idle, booting (token present, user pending), busy. */
export const selectAuthStatus = (state: WithAuth): AuthStatus => state.auth.status;

/** The hydrated session user, or null when signed out / still booting. */
export const selectUser = (state: WithAuth): AuthUser | null => state.auth.user;

/** The session token from the store (never read localStorage directly). */
export const selectToken = (state: WithAuth): string | null => state.auth.token;

export default authSlice.reducer;
