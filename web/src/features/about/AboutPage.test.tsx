import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import AboutPage from "./AboutPage";

describe("AboutPage", () => {
  it("renders the heading, the copy, and the repository link", () => {
    renderWithProviders(<AboutPage />);
    expect(screen.getByRole("heading", { name: "About Loctapus" })).toBeInTheDocument();
    expect(screen.getByText(/unified, searchable knowledge base/)).toBeInTheDocument();
    expect(screen.getByText(/still under development\. It is open source/)).toBeInTheDocument();
    const repository = screen.getByRole("link", { name: "View on GitHub" });
    expect(repository).toHaveAttribute("href", "https://github.com/dimyG/Loctapus");
    expect(repository).toHaveAttribute("target", "_blank");
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
    expect(screen.getByRole("heading", { name: "About Loctapus" })).toBeInTheDocument();
  });
});
