import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import SiteFooter from "./SiteFooter";

describe("SiteFooter", () => {
  it("renders the copyright and the About link", () => {
    renderWithProviders(<SiteFooter />);
    expect(screen.getByText(/© \d{4} RAG\. All rights reserved\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
  });

  it("navigates to /about through the router", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<SiteFooter />} />
        <Route path="/about" element={<div>about-content</div>} />
      </Routes>,
    );
    await userEvent.setup().click(screen.getByRole("link", { name: "About" }));
    expect(await screen.findByText("about-content")).toBeInTheDocument();
  });
});
