import { screen } from "@testing-library/react";
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
    expect(screen.getByRole("link", { name: "RAG" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    // The switcher's trigger answers once useColorScheme settles its mount effect.
    expect(await screen.findByRole("button", { name: "color mode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/register");
    expect(screen.getByText("marketing-content")).toBeInTheDocument();
    expect(screen.getByText(/© \d{4} RAG\. All rights reserved\./)).toBeInTheDocument();
  });
});
