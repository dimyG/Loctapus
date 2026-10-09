import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import LandingPage from "./LandingPage";

describe("LandingPage", () => {
  it("renders the hero copy and both CTAs with correct hrefs", () => {
    render(<LandingPage />, { wrapper: MemoryRouter });
    expect(screen.getByRole("heading", { name: /searchable by meaning/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("renders the three how-it-works steps", () => {
    render(<LandingPage />, { wrapper: MemoryRouter });
    for (const step of ["Create a project", "Upload documents", "Ask questions"]) {
      expect(screen.getByText(step)).toBeVisible();
    }
  });
});
