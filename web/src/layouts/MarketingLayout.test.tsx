import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/test-utils";
import MarketingLayout from "./MarketingLayout";

describe("MarketingLayout", () => {
  it("renders the wordmark, children, and the site footer", () => {
    renderWithProviders(
      <MarketingLayout>
        <div>marketing-content</div>
      </MarketingLayout>,
    );
    expect(screen.getByRole("link", { name: "RAG" })).toHaveAttribute("href", "/");
    expect(screen.getByText("marketing-content")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
  });
});
