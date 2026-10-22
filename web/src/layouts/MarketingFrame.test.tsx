import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import MarketingFrame from "./MarketingFrame";

describe("MarketingFrame", () => {
  it("renders the navbar links, the mode switcher, children, and the footer copyright", async () => {
    renderWithProviders(
      <MarketingFrame>
        <div>marketing-content</div>
      </MarketingFrame>,
    );
    const brandLink = screen.getByRole("link", { name: "Loctapus" });
    expect(brandLink).toHaveAttribute("href", "/");
    // The decorative logo rides inside the wordmark link; the empty alt keeps
    // the link's accessible name as "Loctapus".
    expect(brandLink.querySelector('img[src="/logo.png"]')).toHaveAttribute("alt", "");
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    // The switcher's trigger answers once useColorScheme settles its mount effect.
    expect(await screen.findByRole("button", { name: "color mode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/register");
    expect(screen.getByText("marketing-content")).toBeInTheDocument();
    // The footer wordmark is plain text, so the navbar link stays the only
    // "Loctapus" link; the footer is asserted through its own scope.
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByText("Loctapus")).toBeInTheDocument();
    expect(
      within(footer).getByText(/retrieval-augmented generation workspace/),
    ).toBeInTheDocument();
    expect(
      within(footer).getByText(/© \d{4} Loctapus\. All rights reserved\./),
    ).toBeInTheDocument();
  });
});
