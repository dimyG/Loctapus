import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import AboutPage from "./AboutPage";

describe("AboutPage", () => {
  it("renders the heading and the release copy", () => {
    renderWithProviders(<AboutPage />);
    expect(screen.getByRole("heading", { name: "About RAG" })).toBeInTheDocument();
    // The frame's footer repeats the opening one-liner, so the body paragraph
    // is matched on the continuation only it carries.
    expect(screen.getByText(/workspace\. Group your documents/)).toBeInTheDocument();
    expect(screen.getByText(/accounts, sessions, teams, and projects/)).toBeInTheDocument();
  });

  it("renders for signed-in visitors without redirecting", () => {
    renderWithProviders(<AboutPage />, {
      preloadedState: {
        ...initialRootState(),
        auth: {
          token: "t-1",
          user: { id: "u-1", email: "user@example.test" },
          status: "idle",
        },
      },
    });
    expect(screen.getByRole("heading", { name: "About RAG" })).toBeInTheDocument();
  });
});
