import { screen, waitForElementToBeRemoved, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("opens a mobile menu with About, Sign in, and the mode switcher", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <MarketingFrame>
        <div>marketing-content</div>
      </MarketingFrame>,
    );
    await user.click(screen.getByRole("button", { name: "menu" }));
    const menu = await screen.findByRole("navigation", { name: "Mobile menu" });
    expect(within(menu).getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    expect(within(menu).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(await within(menu).findByRole("button", { name: "color mode" })).toBeInTheDocument();
  });

  it("closes the mobile menu after a destination is chosen", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <MarketingFrame>
        <div>marketing-content</div>
      </MarketingFrame>,
    );
    await user.click(screen.getByRole("button", { name: "menu" }));
    const menu = await screen.findByRole("navigation", { name: "Mobile menu" });
    await user.click(within(menu).getByRole("link", { name: "About" }));
    await waitForElementToBeRemoved(() =>
      screen.queryByRole("navigation", { name: "Mobile menu" }),
    );
  });
});
