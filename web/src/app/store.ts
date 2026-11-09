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
 *
 * @param {RootState} [preloadedState] - State to seed the store with; production leaves it unset.
 */
export const makeStore = (preloadedState?: RootState) =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer, auth: authReducer },
    // Collapsed to RootState before configureStore sees it: an optional
    // parameter would leak `| undefined` into its state inference.
    preloadedState: preloadedState ?? initialRootState(),
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
  });

/** The singleton store production mounts; tests build their own through {@link makeStore}. */
export const store = makeStore();

/** The store type {@link makeStore} returns. */
export type AppStore = ReturnType<typeof makeStore>;

/** Dispatch type pre-bound to the store's action and state types. */
export type AppDispatch = AppStore["dispatch"];
