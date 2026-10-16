import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import type {
  BaseQueryApi,
  BaseQueryFn,
  FetchBaseQueryError,
  FetchArgs,
} from "@reduxjs/toolkit/query";
import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import { sessionExpired } from "../features/auth/sessionActions";

/**
 * Where the API lives. Defaults to the relative same-origin `/api` that the
 * reverse proxy forwards to the backend; E2E overrides it with the absolute
 * port-8001 URL and vitest pins an absolute one because Node's Request
 * rejects relative URLs.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

/**
 * Structural slice of the store the base query needs. Importing the real
 * RootState here would create a store <-> api import cycle.
 */
type WithAuthSlice = { auth: { token: string | null } };

export const baseQuery = fetchBaseQuery({
  baseUrl: API_BASE_URL,
  prepareHeaders: (headers, { getState }) => {
    const token = (getState() as WithAuthSlice).auth?.token;
    if (token) {
      headers.set("authorization", `Bearer ${token}`);
    }
    return headers;
  },
});

const VALIDATION_COPY = "Check the highlighted fields and try again.";
const NETWORK_COPY = "Could not reach the server. Check your connection and try again.";
const GENERIC_COPY = "Something went wrong. Please try again.";

type ErrorLike = { status?: number | string; data?: unknown };

/**
 * Maps an RTK Query error to user-facing copy. FastAPI errors carry
 * `{detail}` bodies; validation failures carry an array; network failures
 * carry FETCH_ERROR. Nothing raw from the payload is ever shown.
 */
export function getErrorMessage(error: unknown): string {
  if (typeof error !== "object" || error === null) {
    return GENERIC_COPY;
  }
  const apiError = error as ErrorLike;
  if (apiError.status === "FETCH_ERROR") {
    return NETWORK_COPY;
  }
  const data = apiError.data;
  if (typeof data === "object" && data !== null && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return VALIDATION_COPY;
    }
  }
  return GENERIC_COPY;
}

/**
 * Wraps the raw base query so a 401 on a request that carried a session token
 * clears the session (expired or revoked mid-use): the guard then sends the
 * visitor to login instead of leaving them with forever-failing pages.
 */
const baseQueryWithSessionExpiry: BaseQueryFn<
  string | FetchArgs,
  unknown,
  FetchBaseQueryError
> = async (args, api, extraOptions) => {
  const result = await baseQuery(args, api, extraOptions);
  if (
    "error" in result &&
    (result.error as { status?: number | string }).status === 401 &&
    (api.getState() as WithAuthSlice).auth?.token != null
  ) {
    api.dispatch(sessionExpired());
  }
  return result;
};

/** The one RTK Query instance every feature api extends. */
export const api = createApi({
  reducerPath: "api",
  baseQuery: baseQueryWithSessionExpiry,
  tagTypes: ["Project", "Upload", "Workspace", "Team"],
  endpoints: () => ({}),
});

/**
 * Builds the full BaseQueryApi shape RTK requires, for manual baseQuery
 * calls from createAsyncThunk payloads (which only have dispatch and
 * getState). Each call gets its own AbortController.
 */
export function thunkBaseQueryApi(
  dispatch: ThunkDispatch<unknown, unknown, UnknownAction>,
  getState: () => unknown,
): BaseQueryApi {
  const controller = new AbortController();
  return {
    signal: controller.signal,
    abort: (reason?: string) => controller.abort(reason),
    dispatch,
    getState,
    extra: undefined,
    endpoint: "auth",
    type: "query",
  };
}
