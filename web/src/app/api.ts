import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import type { BaseQueryApi } from "@reduxjs/toolkit/query";
import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

/** Where the FastAPI backend lives; E2E points it at the port-8001 instance. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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

/** The one RTK Query instance every feature api extends. */
export const api = createApi({
  reducerPath: "api",
  baseQuery,
  tagTypes: ["Project", "Workspace", "Team"],
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
