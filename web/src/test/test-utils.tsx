import { render } from "@testing-library/react";
import type { RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router";
import type { AppStore, RootState } from "../app/store";
import { makeStore } from "../app/store";
import AppTheme from "../theme/AppTheme";

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
        <AppTheme>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </AppTheme>
      </Provider>
    );
  }

  return { ...render(ui, { wrapper: Wrapper, ...renderOptions }), store: testStore };
}
