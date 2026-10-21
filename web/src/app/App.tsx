import CssBaseline from "@mui/material/CssBaseline";
import { useEffect, useMemo } from "react";
import { Provider } from "react-redux";
import { BrowserRouter } from "react-router";
import { bootstrapAuth } from "../features/auth/authSlice";
import AppTheme from "../theme/AppTheme";
import AppRoutes from "./AppRoutes";
import { makeStore } from "./store";

/** Root component: composes store, theme, and router, and bootstraps the session. */
export default function App() {
  // A store per mount (the app mounts exactly once in production): the lazy
  // auth initial state then reads the persisted token at mount time.
  const store = useMemo(() => makeStore(), []);
  useEffect(() => {
    const { auth } = store.getState();
    if (auth.token !== null && auth.user === null) {
      store.dispatch(bootstrapAuth());
    }
  }, [store]);
  return (
    <Provider store={store}>
      <AppTheme>
        <CssBaseline />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AppTheme>
    </Provider>
  );
}
