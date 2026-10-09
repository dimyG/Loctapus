import { ThemeProvider, createTheme } from "@mui/material/styles";
import { render } from "@testing-library/react";
import type { RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import type { AppStore, RootState } from "../app/store";
import { makeStore } from "../app/store";
import { createAppTheme } from "../theme/theme";

const theme = createTheme(createAppTheme());

type Options = {
  /** Initial router entry; defaults to "/". */
  route?: string;
  /** Redux state to preload before rendering. */
  preloadedState?: RootState;
} & Omit<RenderOptions, "wrapper">;

/** Renders ui inside the router, store, and theme the real app composes. */
export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const { route = "/", preloadedState, ...renderOptions } = options;
  const testStore: AppStore = makeStore(preloadedState);

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={testStore}>
        <ThemeProvider theme={theme}>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </ThemeProvider>
      </Provider>
    );
  }

  return { ...render(ui, { wrapper: Wrapper, ...renderOptions }), store: testStore };
}
