import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import AddSourceMenu from "./AddSourceMenu";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Prints the live pathname, so every navigation lands as observable text. */
function LocationProbe() {
  return <div>at:{useLocation().pathname}</div>;
}

/** Renders the menu beside an echoing route for its destination. */
function renderMenu() {
  return renderWithProviders(
    <>
      <AddSourceMenu projectId="p-1" />
      <Routes>
        <Route path="/projects/:projectId/sources/upload" element={<LocationProbe />} />
      </Routes>
    </>,
    { route: "/projects/p-1/sources", preloadedState: authed() },
  );
}

describe("AddSourceMenu", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("lists the source types with the future ones disabled", async () => {
    renderMenu();
    await userEvent.setup().click(screen.getByRole("button", { name: "Add source" }));
    expect(screen.getByRole("menuitem", { name: "File upload" })).toBeInTheDocument();
    // The chip text joins the accessible name, so match the label by substring.
    const website = screen.getByRole("menuitem", { name: /website/i });
    const gdrive = screen.getByRole("menuitem", { name: /google drive/i });
    // MUI exposes disabled menu items via aria-disabled, not the native attribute.
    expect(website).toHaveAttribute("aria-disabled", "true");
    expect(gdrive).toHaveAttribute("aria-disabled", "true");
    expect(within(website).getByText("Coming soon")).toBeInTheDocument();
    expect(within(gdrive).getByText("Coming soon")).toBeInTheDocument();
  });

  it("navigates to the file-upload page when File upload is chosen", async () => {
    renderMenu();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add source" }));
    await user.click(screen.getByRole("menuitem", { name: "File upload" }));
    expect(await screen.findByText("at:/projects/p-1/sources/upload")).toBeInTheDocument();
  });
});
