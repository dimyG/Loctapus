import { configureStore } from "@reduxjs/toolkit";
import authReducer from "../features/auth/authSlice";
import { api } from "./api";

/** The full state tree shape, kept structural so no type infers from itself. */
export type RootState = {
  api: ReturnType<typeof api.reducer>;
  auth: ReturnType<typeof authReducer>;
};

/**
 * The pristine state a fresh store starts from: each slice reducer seeded with
 * nothing, so persisted session data is read at call time, never at module load.
 */
export const initialRootState = (): RootState => ({
  api: api.reducer(undefined, { type: "@@s2/initial" }),
  auth: authReducer(undefined, { type: "@@s2/initial" }),
});

/**
 * Builds a configured store. Tests seed auth or api state through
 * preloadedState; production uses the singleton {@link store} below.
 */
export const makeStore = (preloadedState?: RootState) =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer, auth: authReducer },
    // Collapsed to RootState before configureStore sees it: an optional
    // parameter would leak `| undefined` into its state inference.
    preloadedState: preloadedState ?? initialRootState(),
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
  });

export const store = makeStore();

export type AppStore = ReturnType<typeof makeStore>;
export type AppDispatch = AppStore["dispatch"];
